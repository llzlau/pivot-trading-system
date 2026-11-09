"""
calc_points.py
计算各品种每笔交易的点数盈亏 (Points PnL)、单手实际盈亏、以及品种总盈亏
BASE_DIR = Path(__file__).resolve().parent.parent
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.append(r'..\backtest')
sys.path.append(r'..\scripts')
import pandas as pd
import numpy as np
from pathlib import Path

from backtest_with_stops import backtest_with_stops, INSTRUMENTS
from hedge_and_atr_analysis import backtest_hedge, ALL_INSTRUMENTS

instruments_to_show = {
    'SC': ('原油', 1000, '元/桶'),
    'AG': ('白银', 15,   '元/千克'),
    'CU': ('铜',   5,    '元/吨'),
    'T':  ('10年国债', 10000, '元'),
    'SR': ('白糖', 10,   '元/吨'),
}

for code, (name, mul, unit) in instruments_to_show.items():
    if code in ['T', 'SR']:
        cfg = ALL_INSTRUMENTS[code]
        df, tdf = backtest_hedge(code, cfg)
    else:
        cfg = INSTRUMENTS[code]
        df, tdf = backtest_with_stops(code, cfg)
    
    pts = []
    one_hand_pnl = []
    fee_per_hand = (cfg['commission'] + cfg['slippage']) * 2
    
    for _, r in tdf.iterrows():
        sign = 1 if r['direction'] == '多' else -1
        pt = (r['exit_price'] - r['entry_price']) * sign
        pts.append(round(pt, 2))
        one_hand_pnl.append(round(pt * mul - fee_per_hand, 1))
        
    tdf['points_pnl'] = pts
    tdf['one_hand_pnl'] = one_hand_pnl
    
    total_pts = sum(pts)
    total_cash = tdf['net_pnl'].sum()
    total_one_hand_cash = sum(one_hand_pnl)
    win_trades = len(tdf[tdf['points_pnl'] > 0])
    
    print(f"=== {name} ({code}) ===")
    print(f"报价单位: {unit} | 合约乘数: {mul} | 总交易: {len(tdf)} 笔 | 胜率: {win_trades}/{len(tdf)} ({win_trades/len(tdf)*100:.1f}%)")
    print(f"★ 该品种【累计总盈利点数】: {total_pts:+.2f} {unit}")
    print(f"★ 该品种【单手累计净盈亏】: {total_one_hand_cash:+,.1f} 元")
    print(f"★ 该品种【实际总净利润】: {total_cash:+,.1f} 元 (按ATR仓位管理)")
    print("-" * 95)
    print(f"{'#':<3} {'方向':<3} {'开仓日期':<10} {'开仓价':>8} {'平仓日期':<10} {'平仓价':>8} {'手数':>3} {'出场':<5} {'盈利点数':>10} {'1手净利(元)':>13} {'该笔总净利(元)':>14}")
    print("-" * 95)
    for _, r in tdf.iterrows():
        pt_str = f"{r['points_pnl']:+.2f}"
        oh_str = f"{r['one_hand_pnl']:+,.0f}"
        act_str = f"{r['net_pnl']:+,.0f}"
        print(f"{r['trade_id']:<3} {r['direction']:<3} {r['entry_date']:<10} {r['entry_price']:>8.2f} {r['exit_date']:<10} {r['exit_price']:>8.2f} {r['size']:>3} {r['reason']:<5} {pt_str:>10} {oh_str:>13} {act_str:>14}")
    print("\n" + "="*95 + "\n")
