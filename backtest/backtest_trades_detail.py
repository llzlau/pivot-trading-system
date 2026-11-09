"""
backtest_trades_detail.py
针对原油(SC)、白银(AG)、铜(CU)进行回测，
BASE_DIR = Path(__file__).resolve().parent.parent
并详细打印出每一笔交易的盈亏明细（买入/卖出价格、手数、持仓天数、净利润、收益率）。
同时计算品种间的收益相关性。
"""

import akshare as ak
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

RAW_DIR = Path(r"../data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

INSTRUMENTS = {
    "SC": {"name": "原油", "symbol": "SC0", "multiplier": 1000, "commission": 20, "slippage": 1.0}, # 1000桶/手，元/桶
    "AG": {"name": "白银", "symbol": "AG0", "multiplier": 15,   "commission": 5,  "slippage": 2.0}, # 15千克/手，元/千克
    "CU": {"name": "铜",   "symbol": "CU0", "multiplier": 5,    "commission": 15, "slippage": 10.0}, # 5吨/手，元/吨
}

FAST_MA, SLOW_MA, ATR_PERIOD = 20, 60, 20
INIT_CASH = 500_000
RISK_PCT = 0.01

def ensure_data(code: str, cfg: dict) -> pd.DataFrame:
    file_path = RAW_DIR / f"{code}_daily.csv"
    if not file_path.exists():
        print(f"正在下载 {cfg['name']}({code})...")
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

def backtest_single(code: str, cfg: dict):
    df = ensure_data(code, cfg)
    df["ma_fast"] = df["close"].rolling(FAST_MA).mean()
    df["ma_slow"] = df["close"].rolling(SLOW_MA).mean()
    
    # ATR
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()
    
    df["signal"] = 0
    df.loc[df["ma_fast"] > df["ma_slow"], "signal"] = 1
    df.loc[df["ma_fast"] < df["ma_slow"], "signal"] = -1
    df = df.dropna(subset=["ma_slow", "atr"])
    
    mul = cfg["multiplier"]
    fee_per_hand = cfg["commission"] + cfg["slippage"]
    
    trades = []
    position = 0
    entry_date = None
    entry_price = 0.0
    equity = INIT_CASH
    equity_curve = []
    
    for dt, row in df.iterrows():
        sig = int(row["signal"])
        
        # 信号发生翻转
        if sig != np.sign(position) and row["atr"] > 0:
            # 先平旧仓
            if position != 0:
                direction = "多" if position > 0 else "空"
                exit_price = row["close"]
                gross_pnl = position * (exit_price - entry_price) * mul
                total_fee = abs(position) * fee_per_hand * 2 # 开+平
                net_pnl = gross_pnl - total_fee
                equity += net_pnl
                
                pct_return = (exit_price - entry_price) / entry_price * 100 * (1 if position > 0 else -1)
                days_held = (dt - entry_date).days
                
                trades.append({
                    "trade_id": len(trades) + 1,
                    "direction": direction,
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "entry_price": round(entry_price, 2),
                    "exit_date": dt.strftime("%Y-%m-%d"),
                    "exit_price": round(exit_price, 2),
                    "size": abs(position),
                    "holding_days": days_held,
                    "gross_pnl": round(gross_pnl, 2),
                    "fees": round(total_fee, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round(pct_return, 2),
                    "equity_after": round(equity, 2),
                })
            
            # 开新仓
            if sig != 0:
                risk_cash = equity * RISK_PCT
                contract_risk = row["atr"] * mul
                size = max(1, int(risk_cash / contract_risk))
                position = sig * size
                entry_date = dt
                entry_price = row["close"]
            else:
                position = 0
                
        equity_curve.append(equity)
        
    trades_df = pd.DataFrame(trades)
    df["strategy_equity"] = equity_curve
    
    return df, trades_df

def main():
    results = {}
    trade_logs = {}
    
    print("\n" + "="*80)
    print("  原油(SC) / 白银(AG) / 铜(CU) 单品种独立回测及每一单明细")
    print("="*80)
    
    for code, cfg in INSTRUMENTS.items():
        df, tdf = backtest_single(code, cfg)
        results[code] = df
        trade_logs[code] = tdf
        
        final_eq = df["strategy_equity"].iloc[-1]
        tot_ret = (final_eq - INIT_CASH) / INIT_CASH * 100
        n_years = (df.index[-1] - df.index[0]).days / 365.25
        ann_ret = ((final_eq / INIT_CASH) ** (1 / n_years) - 1) * 100
        
        # 最大回撤
        eq_series = df["strategy_equity"]
        roll_max = eq_series.cummax()
        dd = (eq_series - roll_max) / roll_max * 100
        max_dd = dd.min()
        
        win_trades = len(tdf[tdf["net_pnl"] > 0]) if not tdf.empty else 0
        total_trades = len(tdf)
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        
        print(f"\n【{cfg['name']} ({code}) 策略表现概要】")
        print(f"  最终净值: {final_eq:,.2f} 元  |  总收益率: {tot_ret:+.2f}%  |  年化: {ann_ret:+.2f}%")
        print(f"  最大回撤: {max_dd:.2f}%  |  总交易: {total_trades} 笔  |  胜率: {win_rate:.1f}%")
        print("-" * 80)
        
        if not tdf.empty:
            print(f"  {'#':<3} {'方向':<4} {'开仓日期':<10} {'开仓价':>8} {'平仓日期':<10} {'平仓价':>8} {'手数':>4} {'天数':>4} {'净盈亏(元)':>12} {'单笔%':>7}")
            print("  " + "-" * 76)
            for _, r in tdf.iterrows():
                pnl_str = f"{r['net_pnl']:+,.1f}"
                print(f"  {r['trade_id']:<3} {r['direction']:<4} {r['entry_date']:<10} {r['entry_price']:>8.1f} {r['exit_date']:<10} {r['exit_price']:>8.1f} {r['size']:>4} {r['holding_days']:>4} {pnl_str:>12} {r['return_pct']:>+6.2f}%")
        print("="*80)
        
    # 相关性计算
    returns_df = pd.DataFrame()
    for code, df in results.items():
        returns_df[INSTRUMENTS[code]["name"]] = df["close"].pct_change()
    print("\n【三品种日收益率相关性矩阵 (2020-2024)】")
    print(returns_df.corr().round(3).to_string())
    print("\n")

if __name__ == "__main__":
    main()
