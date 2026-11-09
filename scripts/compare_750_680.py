from pathlib import Path
import os
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent

def run_simulation(anchor, delta_mult=1.2, start_date='2021-01-01'):
    df = pd.read_csv(str(BASE_DIR / 'data' / 'raw' / 'I0_full.csv'), encoding='utf-8')
    df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'open_interest', 'settlement']
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    prev_close = df['close'].shift(1)
    tr = pd.concat([df['high'] - df['low'], (df['high'] - prev_close).abs(), (df['low'] - prev_close).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(20).mean()

    sim_df = df[df['date'] >= start_date].copy().reset_index(drop=True)
    INITIAL_CAPITAL = 200000.0
    MULTIPLIER = 100.0 # 100 tons per lot
    COMMISSION = 20.0
    SLIPPAGE = 50.0

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
        d, c, o, h, l = row['date'], row['close'], row['open'], row['high'], row['low']
        atr = row['atr'] if not pd.isna(row['atr']) and row['atr'] > 0 else 20.0

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

        delta = delta_mult * atr

        # Entry logic
        if long_pos == 0 and short_pos == 0:
            crossed = (prev['close'] < anchor and c >= anchor) or (prev['close'] > anchor and c <= anchor)
            if (i > last_exit_idx + 1) and (crossed or (prev['low'] <= anchor <= prev['high'] and abs(c - anchor) <= 8.0)):
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
            if (c - long_entry) >= delta:
                # Bullish breakout: cut short
                cut_price = c
                cut_pnl = (short_entry - cut_price) * MULTIPLIER
                fee = COMMISSION + SLIPPAGE
                cash += cut_pnl - fee
                short_pos = 0
                long_peak = c
                current_cycle['cut_leg'] = '空头'
                current_cycle['cut_date'] = d.strftime('%Y-%m-%d')
                current_cycle['cut_price'] = round(cut_price, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
            elif (short_entry - c) >= delta:
                # Bearish breakout: cut long
                cut_price = c
                cut_pnl = (cut_price - long_entry) * MULTIPLIER
                fee = COMMISSION + SLIPPAGE
                cash += cut_pnl - fee
                long_pos = 0
                short_trough = c
                current_cycle['cut_leg'] = '多头'
                current_cycle['cut_date'] = d.strftime('%Y-%m-%d')
                current_cycle['cut_price'] = round(cut_price, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee

        else:
            # Smart Exit
            if long_pos > 0:
                long_peak = max(long_peak, c)
                floating = long_peak - long_entry
                if floating >= 80:
                    stop_line = max(long_entry + 0.70 * floating, prev['low'])
                elif floating >= 40:
                    stop_line = long_entry + 0.50 * floating
                elif floating >= 20:
                    stop_line = long_entry + 2.0
                else:
                    stop_line = long_entry - delta

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
                    last_exit_idx = i

            elif short_pos > 0:
                short_trough = min(short_trough, c)
                floating = short_entry - short_trough
                if floating >= 80:
                    stop_line = min(short_entry - 0.70 * floating, prev['high'])
                elif floating >= 40:
                    stop_line = short_entry - 0.50 * floating
                elif floating >= 20:
                    stop_line = short_entry - 2.0
                else:
                    stop_line = short_entry + delta

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
                    last_exit_idx = i

    res = pd.DataFrame(cycles)
    return res, cash

if __name__ == '__main__':
    print('========================================================================================')
    print('                       铁矿石对锁系统：750中枢 vs 680底轴 参数敏感性复测')
    print('========================================================================================')
    for a in [750, 680]:
        for dm in [1.0, 1.2, 1.5]:
            res, cash = run_simulation(a, delta_mult=dm, start_date='2021-01-01')
            tot_pnl = res['net_pnl'].sum() if len(res) > 0 else 0
            win_rate = (res['net_pnl'] > 0).mean() * 100 if len(res) > 0 else 0
            tot_pts = tot_pnl / 100.0

            eq_curve = [200000.0] + res['equity_after'].tolist()
            peak = 200000.0
            mdd = 0.0
            for val in eq_curve:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak
                if dd > mdd:
                    mdd = dd

            print(f"锚点 {a} | 阈值 {dm:3.1f} ATR : 轮次={len(res):2d} | 胜率={win_rate:4.1f}% | 总点数={tot_pts:+6.1f} 点 | 净盈亏={tot_pnl:+8.0f} 元 | 最大回撤={mdd*100:4.2f}% | 最终权益={cash:7.0f} 元")

