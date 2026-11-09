from pathlib import Path
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(r'D:\antigravity-trading\backtest')
from backtest_with_stops import backtest_with_stops, INSTRUMENTS

cfg = INSTRUMENTS['CU']
df, tdf = backtest_with_stops('CU', cfg)
pts = []
fee_per_hand = (cfg['commission'] + cfg['slippage']) * 2
for _, r in tdf.iterrows():
    sign = 1 if r['direction'] == '多' else -1
    pt = (r['exit_price'] - r['entry_price']) * sign
    pts.append(round(pt, 2))
tdf['points_pnl'] = pts
print('CU total points:', sum(pts))
for _, r in tdf.iterrows():
    pt = r['points_pnl']
    oh = pt * 5 - fee_per_hand
    print(f"{r['trade_id']:<3} {r['direction']} {r['entry_date']} {r['entry_price']:>7.0f} -> {r['exit_date']} {r['exit_price']:>7.0f} | 点数: {pt:>+7.1f} 点 | 1手净利: {oh:>+7.0f} 元 | 出场: {r['reason']}")
