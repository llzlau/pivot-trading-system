from pathlib import Path
import os
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent

def generate_table():
    df = pd.read_csv(str(BASE_DIR / 'data' / 'raw' / 'SC0_latest.csv'))
    df.columns = [c.strip() for c in df.columns]
    df['日期'] = pd.to_datetime(df['日期'])
    df = df.sort_values('日期').reset_index(drop=True)

    high, low, close = df['最高价'], df['最低价'], df['收盘价']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(20).mean()

    INITIAL_CAPITAL = 200000.0
    MULTIPLIER = 1000.0
    COMMISSION = 60.0
    SLIPPAGE = 200.0

    sim_df = df[df['日期'] >= '2021-01-01'].copy().reset_index(drop=True)
    cash = INITIAL_CAPITAL
    long_pos, short_pos = 0, 0
    long_entry, short_entry = 0.0, 0.0
    long_peak, short_trough = 0.0, 999999.0
    current_month = None
    roll_done = False

    cycles = []
    current_cycle = None

    for i in range(1, len(sim_df)):
        row = sim_df.iloc[i]
        prev = sim_df.iloc[i-1]
        d, c, o, h, l = row['日期'], row['收盘价'], row['开盘价'], row['最高价'], row['最低价']
        atr = row['atr'] if not pd.isna(row['atr']) and row['atr'] > 0 else 15.0
        
        # Monthly roll
        m_str = d.strftime('%Y-%m')
        if m_str != current_month:
            current_month = m_str
            roll_done = False
        if d.day >= 15 and not roll_done:
            roll_done = True
            if long_pos > 0 or short_pos > 0:
                fee_roll = COMMISSION + SLIPPAGE
                cash -= fee_roll
                if current_cycle:
                    current_cycle['rolls'] += 1
                    current_cycle['roll_fees'] += fee_roll
                
        # STRICT 600 ENTRY
        if long_pos == 0 and short_pos == 0:
            near_600 = abs(c - 600.0) <= 15.0
            crossed_600 = (prev['收盘价'] < 600 and c >= 600) or (prev['收盘价'] > 600 and c <= 600)
            if crossed_600 or near_600:
                long_pos, short_pos = 1, 1
                long_entry, short_entry = c, c
                long_peak, short_trough = c, c
                open_fee = (COMMISSION + SLIPPAGE) * 2
                cash -= open_fee
                current_cycle = {
                    'cycle_id': len(cycles) + 1,
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_price': round(c, 1),
                    'cut_leg': None,
                    'cut_date': None,
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
            delta = 1.5 * atr
            if (c - long_entry) >= delta:
                # Bullish breakout: cut short
                cut_pnl = (short_entry - c) * MULTIPLIER
                fee = COMMISSION + SLIPPAGE
                cash += cut_pnl - fee
                short_pos = 0
                long_peak = c
                current_cycle['cut_leg'] = '空头'
                current_cycle['cut_date'] = d.strftime('%Y-%m-%d')
                current_cycle['cut_price'] = round(c, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
            elif (short_entry - c) >= delta:
                # Bearish breakout: cut long
                cut_pnl = (c - long_entry) * MULTIPLIER
                fee = COMMISSION + SLIPPAGE
                cash += cut_pnl - fee
                long_pos = 0
                short_trough = c
                current_cycle['cut_leg'] = '多头'
                current_cycle['cut_date'] = d.strftime('%Y-%m-%d')
                current_cycle['cut_price'] = round(c, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
                
        else:
            # Smart exit for running leg
            if long_pos > 0:
                long_peak = max(long_peak, c)
                floating = long_peak - long_entry
                if floating >= 100:
                    stop_line = max(long_entry + 0.75 * floating, prev['最低价'])
                elif floating >= 40:
                    stop_line = long_entry + 0.5 * floating
                elif floating >= 20:
                    stop_line = long_entry + 2.0
                else:
                    stop_line = long_entry - 1.5 * atr
                
                if c <= stop_line:
                    win_pnl = (c - long_entry) * MULTIPLIER
                    fee = COMMISSION + SLIPPAGE
                    cash += win_pnl - fee
                    long_pos = 0
                    current_cycle['win_leg'] = '多头'
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(c, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    cycles.append(current_cycle)
                    current_cycle = None
                    
            elif short_pos > 0:
                short_trough = min(short_trough, c)
                floating = short_entry - short_trough
                if floating >= 100:
                    stop_line = min(short_entry - 0.75 * floating, prev['最高价'])
                elif floating >= 40:
                    stop_line = short_entry - 0.5 * floating
                elif floating >= 20:
                    stop_line = short_entry - 2.0
                else:
                    stop_line = short_entry + 1.5 * atr
                
                if c >= stop_line:
                    win_pnl = (short_entry - c) * MULTIPLIER
                    fee = COMMISSION + SLIPPAGE
                    cash += win_pnl - fee
                    short_pos = 0
                    current_cycle['win_leg'] = '空头'
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(c, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    cycles.append(current_cycle)
                    current_cycle = None

    res = pd.DataFrame(cycles)
    res.to_csv(str(BASE_DIR / 'data' / 'processed' / 'cycles_smart_exit.csv'), index=False)
    print(res.to_string())

if __name__ == '__main__':
    generate_table()
