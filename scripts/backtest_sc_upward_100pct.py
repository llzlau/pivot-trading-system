from pathlib import Path
import os
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent

# Load SC data
df = pd.read_csv(str(BASE_DIR / 'data' / 'raw' / 'SC0_latest.csv'))
df.columns = [c.strip() for c in df.columns]
df['日期'] = pd.to_datetime(df['日期'])
df = df.sort_values('日期').reset_index(drop=True)

sim_df = df[df['日期'] >= '2021-01-01'].copy().reset_index(drop=True)

def simulate_strategy(pts_trigger=60.0, add_position=False, bidirectional=False):
    INITIAL_CAPITAL = 200000.0
    MULTIPLIER = 1000.0
    COMMISSION = 60.0
    SLIPPAGE = 200.0
    
    cash = INITIAL_CAPITAL
    long_pos, short_pos = 0, 0
    long_entry, short_entry = 0.0, 0.0
    long_peak, short_trough = 0.0, 999999.0
    current_month = None
    roll_done = False
    
    cycles = []
    current_cycle = None
    last_exit_idx = -10
    
    for i in range(1, len(sim_df)):
        row = sim_df.iloc[i]
        prev = sim_df.iloc[i-1]
        d, c, o, h, l = row['日期'], row['收盘价'], row['开盘价'], row['最高价'], row['最低价']
        
        # Monthly roll
        m_str = d.strftime('%Y-%m')
        if m_str != current_month:
            current_month = m_str
            roll_done = False
        if d.day >= 15 and not roll_done:
            roll_done = True
            pos_count = long_pos + short_pos
            if pos_count > 0:
                fee_roll = (COMMISSION + SLIPPAGE) * pos_count
                cash -= fee_roll
                if current_cycle:
                    current_cycle['rolls'] += 1
                    current_cycle['roll_fees'] += fee_roll

        # Entry at 600
        if long_pos == 0 and short_pos == 0:
            crossed = (prev['收盘价'] < 600 <= c) or (prev['收盘价'] > 600 >= c)
            near = abs(c - 600.0) <= 10.0
            if (i > last_exit_idx + 1) and (crossed or near):
                long_pos, short_pos = 1, 1
                long_entry, short_entry = 600.0, 600.0
                long_peak, short_trough = 600.0, 600.0
                open_fee = (COMMISSION + SLIPPAGE) * 2
                cash -= open_fee
                current_cycle = {
                    'cycle_id': len(cycles) + 1,
                    'direction': None,
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_price': 600.0,
                    'trigger_date': None,
                    'trigger_price': None,
                    'cut_leg': None,
                    'cut_price': None,
                    'cut_pnl': 0.0,
                    'win_leg': None,
                    'win_date': None,
                    'win_price': None,
                    'win_pnl': 0.0,
                    'rolls': 0,
                    'roll_fees': 0.0,
                    'total_fees': open_fee,
                    'net_pnl': 0.0,
                    'equity_after': 0.0
                }
                
        elif long_pos > 0 and short_pos > 0:
            if (c - long_entry) >= pts_trigger:
                # Upward trigger!
                cut_price = c
                cut_pnl = (short_entry - cut_price) * MULTIPLIER
                fee = COMMISSION + SLIPPAGE
                cash += cut_pnl - fee
                short_pos = 0
                if add_position:
                    long_pos = 2
                    fee_add = COMMISSION + SLIPPAGE
                    cash -= fee_add
                    current_cycle['total_fees'] += fee_add
                long_peak = c
                current_cycle['direction'] = '多头'
                current_cycle['trigger_date'] = d.strftime('%Y-%m-%d')
                current_cycle['trigger_price'] = round(c, 1)
                current_cycle['cut_leg'] = '空头'
                current_cycle['cut_price'] = round(cut_price, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
                
            elif bidirectional and (short_entry - c) >= pts_trigger:
                # Downward trigger!
                cut_price = c
                cut_pnl = (cut_price - long_entry) * MULTIPLIER
                fee = COMMISSION + SLIPPAGE
                cash += cut_pnl - fee
                long_pos = 0
                if add_position:
                    short_pos = 2
                    fee_add = COMMISSION + SLIPPAGE
                    cash -= fee_add
                    current_cycle['total_fees'] += fee_add
                short_trough = c
                current_cycle['direction'] = '空头'
                current_cycle['trigger_date'] = d.strftime('%Y-%m-%d')
                current_cycle['trigger_price'] = round(c, 1)
                current_cycle['cut_leg'] = '多头'
                current_cycle['cut_price'] = round(cut_price, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
                
        else:
            # Smart Exit
            if long_pos > 0:
                long_peak = max(long_peak, c)
                floating = long_peak - 600.0
                if floating >= 150:
                    stop_line = max(600.0 + 0.75 * floating, prev['最低价'])
                elif floating >= 100:
                    stop_line = max(600.0 + 0.65 * floating, prev['最低价'])
                elif floating >= pts_trigger + 20:
                    stop_line = 600.0 + pts_trigger
                else:
                    stop_line = 600.0 + pts_trigger - 15.0
                    
                if c <= stop_line:
                    exit_price = c
                    if add_position:
                        win_pnl = ((exit_price - 600.0) + (exit_price - current_cycle['trigger_price'])) * MULTIPLIER
                    else:
                        win_pnl = (exit_price - 600.0) * MULTIPLIER
                    fee = (COMMISSION + SLIPPAGE) * long_pos
                    cash += win_pnl - fee
                    long_pos = 0
                    current_cycle['win_leg'] = '多头'
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(exit_price, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    cycles.append(current_cycle)
                    current_cycle = None
                    last_exit_idx = i
                    
            elif short_pos > 0:
                short_trough = min(short_trough, c)
                floating = 600.0 - short_trough
                if floating >= 150:
                    stop_line = min(600.0 - 0.75 * floating, prev['最高价'])
                elif floating >= 100:
                    stop_line = min(600.0 - 0.65 * floating, prev['最高价'])
                elif floating >= pts_trigger + 20:
                    stop_line = 600.0 - pts_trigger
                else:
                    stop_line = 600.0 - pts_trigger + 15.0
                    
                if c >= stop_line:
                    exit_price = c
                    if add_position:
                        win_pnl = ((600.0 - exit_price) + (current_cycle['trigger_price'] - exit_price)) * MULTIPLIER
                    else:
                        win_pnl = (600.0 - exit_price) * MULTIPLIER
                    fee = (COMMISSION + SLIPPAGE) * short_pos
                    cash += win_pnl - fee
                    short_pos = 0
                    current_cycle['win_leg'] = '空头'
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(exit_price, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    cycles.append(current_cycle)
                    current_cycle = None
                    last_exit_idx = i

    res = pd.DataFrame(cycles)
    return res, cash

if __name__ == '__main__':
    print('========================================================================================')
    print('                 原油600分界线：向上盈利100%入场平空策略 复盘总汇')
    print('========================================================================================')
    for b in [False, True]:
        b_name = '双向对称' if b else '仅做向上'
        for add in [False, True]:
            add_name = '顺势加仓(+1手)' if add else '单多顺势'
            for trig in [60.0, 72.0]:
                res, cash = simulate_strategy(pts_trigger=trig, add_position=add, bidirectional=b)
                tot_pnl = res['net_pnl'].sum() if len(res) > 0 else 0
                win_rate = (res['net_pnl'] > 0).mean() * 100 if len(res) > 0 else 0
                
                eq_curve = [200000.0] + res['equity_after'].tolist()
                peak = 200000.0
                mdd = 0.0
                for val in eq_curve:
                    if val > peak:
                        peak = val
                    dd = (peak - val) / peak
                    if dd > mdd:
                        mdd = dd
                
                print(f"模式: {b_name} | 操作: {add_name} | 触发门槛: +{trig:.0f}点 | 轮次: {len(res):2d} | 胜率: {win_rate:4.1f}% | 净盈亏: {tot_pnl:+9.0f} 元 | 最大回撤: {mdd*100:4.1f}% | 最终权益: {cash:8.0f} 元")
