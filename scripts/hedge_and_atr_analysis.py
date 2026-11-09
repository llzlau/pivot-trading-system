"""
hedge_and_atr_analysis.py
1. 计算各大品种的 20 日 ATR 统计（均值、最新值、单手每日波动风险金）
BASE_DIR = Path(__file__).resolve().parent.parent
2. 下载并回测对冲品种：10年期国债期货(T) 和 白糖(SR)
3. 输出对冲品种每一笔交易的入场、出场、持仓天数与盈亏明细
"""

import akshare as ak
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

RAW_DIR = Path(r"../data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 所有的监测品种
ALL_INSTRUMENTS = {
    "AU": {"name": "黄金",   "symbol": "AU0", "multiplier": 1000,  "commission": 10, "slippage": 0.1,  "type": "贵金属"},
    "AG": {"name": "白银",   "symbol": "AG0", "multiplier": 15,    "commission": 5,  "slippage": 2.0,  "type": "贵金属"},
    "CU": {"name": "铜",     "symbol": "CU0", "multiplier": 5,     "commission": 15, "slippage": 10.0, "type": "有色金属"},
    "SC": {"name": "原油",   "symbol": "SC0", "multiplier": 1000,  "commission": 20, "slippage": 1.0,  "type": "能源"},
    "RB": {"name": "螺纹钢", "symbol": "RB0", "multiplier": 10,    "commission": 5,  "slippage": 2.0,  "type": "黑色金属"},
    "T":  {"name": "10年国债","symbol": "T0",  "multiplier": 10000, "commission": 3,  "slippage": 0.01, "type": "利率债(对冲)"},
    "SR": {"name": "白糖",   "symbol": "SR0", "multiplier": 10,    "commission": 3,  "slippage": 1.0,  "type": "软商品(对冲)"},
}

ATR_PERIOD = 20 # 20个交易日 (约1个月)

def ensure_data(code: str, cfg: dict) -> pd.DataFrame:
    file_path = RAW_DIR / f"{code}_daily.csv"
    if not file_path.exists():
        df = ak.futures_main_sina(symbol=cfg["symbol"], start_date="20200101", end_date="20241231")
        col_map = {"日期": "date", "开盘价": "open", "最高价": "high", "最低价": "low", "收盘价": "close", "成交量": "volume"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True).dropna(subset=["close"])
        df[["date", "open", "high", "low", "close", "volume"]].to_csv(file_path, index=False, encoding="utf-8-sig")
    else:
        df = pd.read_csv(file_path, parse_dates=["date"])
    
    df = df.set_index("date").sort_index()
    return df

def analyze_atr():
    atr_summary = []
    for code, cfg in ALL_INSTRUMENTS.items():
        df = ensure_data(code, cfg)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(ATR_PERIOD).mean()
        
        last_price = df["close"].iloc[-1]
        mean_atr = df["atr"].mean()
        last_atr = df["atr"].iloc[-1]
        mul = cfg["multiplier"]
        
        # 1手承担的单日波动金额
        risk_per_hand = last_atr * mul
        atr_pct = (last_atr / last_price) * 100
        
        atr_summary.append({
            "code": code,
            "name": cfg["name"],
            "type": cfg["type"],
            "multiplier": mul,
            "last_price": round(last_price, 2),
            "mean_atr": round(mean_atr, 2),
            "last_atr": round(last_atr, 2),
            "atr_pct": round(atr_pct, 2),
            "risk_per_hand": round(risk_per_hand, 0),
        })
    return pd.DataFrame(atr_summary)

def backtest_hedge(code: str, cfg: dict):
    df = ensure_data(code, cfg)
    df["ma_fast"] = df["close"].rolling(20).mean()
    df["ma_slow"] = df["close"].rolling(60).mean()
    
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()
    df = df.dropna(subset=["ma_slow", "atr"])
    
    mul = cfg["multiplier"]
    fee_per_hand = cfg["commission"] + cfg["slippage"]
    
    trades = []
    position = 0
    pos_size = 0
    entry_date = None
    entry_price = 0.0
    highest_price = 0.0
    lowest_price = float("inf")
    stop_loss_price = 0.0
    trailing_stop_price = 0.0
    
    equity = 500_000
    equity_curve = []
    
    dates = df.index
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    ma_fasts = df["ma_fast"].values
    ma_slows = df["ma_slow"].values
    atrs = df["atr"].values
    
    # 对冲品种：国债波动极低，使用 2*ATR 止盈；白糖使用 2.5*ATR
    trailing_mul = 2.0 if code == "T" else 2.5
    stop_mul = 2.0
    
    for i in range(1, len(df)):
        dt = dates[i]
        close = closes[i]
        high = highs[i]
        low = lows[i]
        atr = atrs[i]
        
        gold_cross = (ma_fasts[i-1] <= ma_slows[i-1]) and (ma_fasts[i] > ma_slows[i])
        death_cross = (ma_fasts[i-1] >= ma_slows[i-1]) and (ma_fasts[i] < ma_slows[i])
        
        exit_trade = False
        exit_reason = ""
        exit_price = close
        
        if position == 1:
            if high > highest_price:
                highest_price = high
                trailing_stop_price = highest_price - trailing_mul * atr
            if low <= max(stop_loss_price, trailing_stop_price):
                exit_trade = True
                exit_price = max(stop_loss_price, trailing_stop_price)
                exit_reason = "止盈" if exit_price > entry_price else "止损"
            elif death_cross:
                exit_trade = True
                exit_price = close
                exit_reason = "死叉反转"
                
        elif position == -1:
            if low < lowest_price:
                lowest_price = low
                trailing_stop_price = lowest_price + trailing_mul * atr
            if high >= min(stop_loss_price, trailing_stop_price):
                exit_trade = True
                exit_price = min(stop_loss_price, trailing_stop_price)
                exit_reason = "止盈" if exit_price < entry_price else "止损"
            elif gold_cross:
                exit_trade = True
                exit_price = close
                exit_reason = "金叉反转"
                
        if exit_trade and position != 0:
            gross_pnl = position * (exit_price - entry_price) * mul * pos_size
            total_fee = pos_size * fee_per_hand * 2
            net_pnl = gross_pnl - total_fee
            equity += net_pnl
            pct_return = (exit_price - entry_price) / entry_price * 100 * position
            days_held = (dt - entry_date).days
            
            trades.append({
                "trade_id": len(trades) + 1,
                "direction": "多" if position == 1 else "空",
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 3),
                "exit_date": dt.strftime("%Y-%m-%d"),
                "exit_price": round(exit_price, 3),
                "size": pos_size,
                "holding_days": days_held,
                "reason": exit_reason,
                "net_pnl": round(net_pnl, 2),
                "return_pct": round(pct_return, 2),
                "equity_after": round(equity, 2),
            })
            position = 0
            pos_size = 0
            
        if position == 0:
            if gold_cross and atr > 0:
                risk_cash = equity * 0.01
                pos_size = max(1, int(risk_cash / (atr * mul)))
                position = 1
                entry_date = dt
                entry_price = close
                highest_price = high
                stop_loss_price = entry_price - stop_mul * atr
                trailing_stop_price = highest_price - trailing_mul * atr
            elif death_cross and atr > 0:
                risk_cash = equity * 0.01
                pos_size = max(1, int(risk_cash / (atr * mul)))
                position = -1
                entry_date = dt
                entry_price = close
                lowest_price = low
                stop_loss_price = entry_price + stop_mul * atr
                trailing_stop_price = lowest_price + trailing_mul * atr
                
        equity_curve.append(equity)
        
    return df, pd.DataFrame(trades)

def main():
    print("=== 各大品种 20日 ATR 参数与波动分析 ===")
    atr_df = analyze_atr()
    print(atr_df.to_string(index=False))
    
    print("\n" + "="*85)
    print("  对冲品种【10年期国债期货 (T)】和【白糖 (SR)】策略表现与逐笔清单")
    print("="*85)
    
    for code in ["T", "SR"]:
        cfg = ALL_INSTRUMENTS[code]
        df, tdf = backtest_hedge(code, cfg)
        final_eq = tdf["equity_after"].iloc[-1] if not tdf.empty else 500_000
        tot_ret = (final_eq - 500_000) / 500_000 * 100
        n_years = (df.index[-1] - df.index[0]).days / 365.25
        ann_ret = ((final_eq / 500_000) ** (1 / n_years) - 1) * 100
        win_trades = len(tdf[tdf["net_pnl"] > 0]) if not tdf.empty else 0
        total_trades = len(tdf)
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        
        print(f"\n【{cfg['name']} ({code}) - 对冲品种回测概要】")
        print(f"  最终净值: {final_eq:,.2f} 元  |  总收益率: {tot_ret:+.2f}%  |  年化: {ann_ret:+.2f}%  |  交易: {total_trades} 笔  |  胜率: {win_rate:.1f}%")
        print("-" * 85)
        if not tdf.empty:
            print(f"  {'#':<3} {'方向':<3} {'开仓日期':<10} {'开仓价':>8} {'平仓日期':<10} {'平仓价':>8} {'手数':>3} {'天数':>4} {'出场原因':<6} {'净盈亏(元)':>11} {'单笔%':>6}")
            print("  " + "-" * 81)
            for _, r in tdf.iterrows():
                pnl_str = f"{r['net_pnl']:+,.0f}"
                print(f"  {r['trade_id']:<3} {r['direction']:<3} {r['entry_date']:<10} {r['entry_price']:>8.2f} {r['exit_date']:<10} {r['exit_price']:>8.2f} {r['size']:>3} {r['holding_days']:>4} {r['reason']:<8} {pnl_str:>11} {r['return_pct']:>+5.1f}%")
        print("="*85)

if __name__ == "__main__":
    main()
