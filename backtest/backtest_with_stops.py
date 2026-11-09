"""
backtest_with_stops.py
改进版趋势跟踪策略：
BASE_DIR = Path(__file__).resolve().parent.parent
1. 均线金叉/死叉入场
2. 初始硬止损：亏损达到 2 * ATR 坚决平仓止损
3. 吊灯移动止盈 (Chandelier Exit)：从持仓最高点（或最低点）回撤超过 2.5 * ATR 立即止盈平仓，锁定利润！
4. 真实打印每一笔交易清单
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

RAW_DIR = Path(r"../data/raw")

INSTRUMENTS = {
    "SC": {"name": "原油", "multiplier": 1000, "commission": 20, "slippage": 1.0},
    "AG": {"name": "白银", "multiplier": 15,   "commission": 5,  "slippage": 2.0},
    "CU": {"name": "铜",   "multiplier": 5,    "commission": 15, "slippage": 10.0},
}

FAST_MA, SLOW_MA, ATR_PERIOD = 20, 60, 20
INIT_CASH = 500_000
RISK_PCT = 0.01

STOP_LOSS_ATR = 2.0      # 2倍ATR硬止损
TRAILING_STOP_ATR = 2.5  # 2.5倍ATR从极值回撤止盈

def backtest_with_stops(code: str, cfg: dict):
    file_path = RAW_DIR / f"{code}_daily.csv"
    df = pd.read_csv(file_path, parse_dates=["date"]).set_index("date").sort_index()
    
    df["ma_fast"] = df["close"].rolling(FAST_MA).mean()
    df["ma_slow"] = df["close"].rolling(SLOW_MA).mean()
    
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
    position = 0      # 1=多, -1=空, 0=空仓
    pos_size = 0
    entry_date = None
    entry_price = 0.0
    highest_price = 0.0
    lowest_price = float("inf")
    stop_loss_price = 0.0
    trailing_stop_price = 0.0
    
    equity = INIT_CASH
    equity_curve = []
    
    dates = df.index
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    ma_fasts = df["ma_fast"].values
    ma_slows = df["ma_slow"].values
    atrs = df["atr"].values
    
    for i in range(1, len(df)):
        dt = dates[i]
        close = closes[i]
        high = highs[i]
        low = lows[i]
        atr = atrs[i]
        
        # 前一天的均线交叉
        prev_fast = ma_fasts[i-1]
        prev_slow = ma_slows[i-1]
        curr_fast = ma_fasts[i]
        curr_slow = ma_slows[i]
        
        gold_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
        death_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)
        
        exit_trade = False
        exit_reason = ""
        exit_price = close
        
        # 1. 检查当前持仓是否触发 止损 或 移动止盈
        if position == 1: # 持多仓
            if high > highest_price:
                highest_price = high
                # 抬高移动止盈线
                trailing_stop_price = highest_price - TRAILING_STOP_ATR * atr
                
            # 检查是否跌破止盈线或初始止损线
            if low <= max(stop_loss_price, trailing_stop_price):
                exit_trade = True
                exit_price = max(stop_loss_price, trailing_stop_price)
                exit_reason = "止盈" if exit_price > entry_price else "止损"
            elif death_cross:
                exit_trade = True
                exit_price = close
                exit_reason = "死叉反转"
                
        elif position == -1: # 持空仓
            if low < lowest_price:
                lowest_price = low
                # 下移移动止盈线
                trailing_stop_price = lowest_price + TRAILING_STOP_ATR * atr
                
            if high >= min(stop_loss_price, trailing_stop_price):
                exit_trade = True
                exit_price = min(stop_loss_price, trailing_stop_price)
                exit_reason = "止盈" if exit_price < entry_price else "止损"
            elif gold_cross:
                exit_trade = True
                exit_price = close
                exit_reason = "金叉反转"
                
        # 2. 执行平仓
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
                "entry_price": round(entry_price, 2),
                "exit_date": dt.strftime("%Y-%m-%d"),
                "exit_price": round(exit_price, 2),
                "size": pos_size,
                "holding_days": days_held,
                "reason": exit_reason,
                "net_pnl": round(net_pnl, 2),
                "return_pct": round(pct_return, 2),
                "equity_after": round(equity, 2),
            })
            
            position = 0
            pos_size = 0
            
        # 3. 检查开新仓
        if position == 0:
            if gold_cross and atr > 0:
                risk_cash = equity * RISK_PCT
                pos_size = max(1, int(risk_cash / (atr * mul)))
                position = 1
                entry_date = dt
                entry_price = close
                highest_price = high
                stop_loss_price = entry_price - STOP_LOSS_ATR * atr
                trailing_stop_price = highest_price - TRAILING_STOP_ATR * atr
                
            elif death_cross and atr > 0:
                risk_cash = equity * RISK_PCT
                pos_size = max(1, int(risk_cash / (atr * mul)))
                position = -1
                entry_date = dt
                entry_price = close
                lowest_price = low
                stop_loss_price = entry_price + STOP_LOSS_ATR * atr
                trailing_stop_price = lowest_price + TRAILING_STOP_ATR * atr
                
        equity_curve.append(equity)
        
    trades_df = pd.DataFrame(trades)
    df["strategy_equity"] = [INIT_CASH] + equity_curve
    return df, trades_df

def main():
    print("\n" + "="*85)
    print("  【升级版】带吊灯移动止盈 + 2*ATR硬止损的策略回测及每一单明细")
    print("="*85)
    
    for code, cfg in INSTRUMENTS.items():
        df, tdf = backtest_with_stops(code, cfg)
        final_eq = df["strategy_equity"].iloc[-1]
        tot_ret = (final_eq - INIT_CASH) / INIT_CASH * 100
        n_years = (df.index[-1] - df.index[0]).days / 365.25
        ann_ret = ((final_eq / INIT_CASH) ** (1 / n_years) - 1) * 100
        
        eq_series = df["strategy_equity"]
        roll_max = eq_series.cummax()
        dd = (eq_series - roll_max) / roll_max * 100
        max_dd = dd.min()
        
        win_trades = len(tdf[tdf["net_pnl"] > 0]) if not tdf.empty else 0
        total_trades = len(tdf)
        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        
        print(f"\n【{cfg['name']} ({code}) 升级版表现】")
        print(f"  最终净值: {final_eq:,.2f} 元  |  总收益率: {tot_ret:+.2f}%  |  年化: {ann_ret:+.2f}%")
        print(f"  最大回撤: {max_dd:.2f}%  |  总交易: {total_trades} 笔  |  胜率: {win_rate:.1f}%")
        print("-" * 85)
        
        if not tdf.empty:
            print(f"  {'#':<3} {'方向':<3} {'开仓日期':<10} {'开仓价':>7} {'平仓日期':<10} {'平仓价':>7} {'手数':>3} {'天数':>4} {'出场原因':<6} {'净盈亏(元)':>11} {'单笔%':>6}")
            print("  " + "-" * 81)
            for _, r in tdf.iterrows():
                pnl_str = f"{r['net_pnl']:+,.0f}"
                print(f"  {r['trade_id']:<3} {r['direction']:<3} {r['entry_date']:<10} {r['entry_price']:>7.1f} {r['exit_date']:<10} {r['exit_price']:>7.1f} {r['size']:>3} {r['holding_days']:>4} {r['reason']:<8} {pnl_str:>11} {r['return_pct']:>+5.1f}%")
        print("="*85)

if __name__ == "__main__":
    main()
