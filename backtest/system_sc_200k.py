from pathlib import Path
import os
import sys
import numpy as np
import pandas as pd

# Set stdout encoding
sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent

def run_sc_system():
    csv_path = str(BASE_DIR / 'data' / 'raw' / 'SC0_latest.csv')
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    df['日期'] = pd.to_datetime(df['日期'])
    df = df.sort_values('日期').reset_index(drop=True)
    
    # Calculate ATR(20)
    high = df['最高价']
    low = df['最低价']
    close = df['收盘价']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(20).mean()
    df['atr'] = atr
    
    # EWMAC trend speeds
    ema8 = close.ewm(span=8, adjust=False).mean()
    ema32 = close.ewm(span=32, adjust=False).mean()
    ema16 = close.ewm(span=16, adjust=False).mean()
    ema64 = close.ewm(span=64, adjust=False).mean()
    ema128 = close.ewm(span=128, adjust=False).mean()
    
    # Carver raw forecasts normalized by ATR
    f_fast = (ema8 - ema32) / atr
    f_med = (ema16 - ema64) / atr
    f_slow = (ema32 - ema128) / atr
    raw_forecast = (f_fast + f_med + f_slow) / 3.0
    # Scale forecast to [-20, +20]
    scaled_forecast = np.clip(raw_forecast * 4.0, -20.0, 20.0)
    df['forecast'] = scaled_forecast
    
    # Backtest parameters
    INITIAL_CAPITAL = 200000.0  # 200,000 RMB
    MULTIPLIER = 1000.0         # 1000 barrels / lot
    COMMISSION = 60.0           # 60 RMB round trip per lot
    SLIPPAGE_POINTS = 0.2       # 0.2 points (200 RMB) execution friction
    
    # We will simulate trading from 2021 to 2026 (recent years)
    start_date = pd.to_datetime('2021-01-01')
    sim_df = df[df['日期'] >= start_date].copy().reset_index(drop=True)
    
    # Trading State
    cash = INITIAL_CAPITAL
    equity = INITIAL_CAPITAL
    
    # Positions: 1 = Long, -1 = Short, 0 = Flat
    # We allow dual positions (long_pos, short_pos)
    long_pos = 0     # 0 or 1
    short_pos = 0    # 0 or 1
    long_entry_price = 0.0
    short_entry_price = 0.0
    long_peak_price = 0.0
    short_trough_price = 999999.0
    
    trade_logs = []
    daily_records = []
    
    # Monthly roll tracking
    # Rollover occurs around day 18-20 of each month
    current_month = None
    roll_done_this_month = False
    
    for i in range(1, len(sim_df)):
        row = sim_df.iloc[i]
        prev_row = sim_df.iloc[i-1]
        
        d = row['日期']
        o = row['开盘价']
        h = row['最高价']
        l = row['最低价']
        c = row['收盘价']
        cur_atr = row['atr']
        fc = row['forecast']
        
        if pd.isna(cur_atr) or cur_atr <= 0:
            cur_atr = 15.0
            
        m_str = d.strftime('%Y-%m')
        if m_str != current_month:
            current_month = m_str
            roll_done_this_month = False
            
        # 1. Check Rollover (移仓处理)
        # SC contracts roll monthly. Between the 15th and 20th of the month, roll open positions.
        if d.day >= 15 and not roll_done_this_month:
            roll_done_this_month = True
            # Roll long position if open
            if long_pos > 0:
                # Fee + slippage for roll (close old + open new)
                roll_cost = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                cash -= roll_cost
                trade_logs.append({
                    'date': d, 'type': 'ROLL_LONG', 'price': c,
                    'pnl': 0, 'fee': roll_cost, 'note': f'Monthly Roll {m_str}'
                })
            # Roll short position if open
            if short_pos > 0:
                roll_cost = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                cash -= roll_cost
                trade_logs.append({
                    'date': d, 'type': 'ROLL_SHORT', 'price': c,
                    'pnl': 0, 'fee': roll_cost, 'note': f'Monthly Roll {m_str}'
                })

        # 2. Dual-Position Breakout / Unlocking Logic around 600 or entry triggers
        # If flat, and price is around 600 (within 590-610) OR strong signal:
        if long_pos == 0 and short_pos == 0:
            # Check 600 crossing or strong forecast trigger
            near_600 = abs(c - 600.0) <= 15.0
            crossed_600 = (prev_row['收盘价'] < 600 and c >= 600) or (prev_row['收盘价'] > 600 and c <= 600)
            
            if crossed_600 or near_600:
                # Open BOTH Long and Short at 600 level!
                long_pos = 1
                short_pos = 1
                long_entry_price = c
                short_entry_price = c
                long_peak_price = c
                short_trough_price = c
                fee = (COMMISSION + SLIPPAGE_POINTS * MULTIPLIER) * 2
                cash -= fee
                trade_logs.append({
                    'date': d, 'type': 'OPEN_DUAL_600', 'price': c,
                    'pnl': 0, 'fee': fee, 'note': f'Dual Entry at {c:.1f}'
                })
            elif abs(fc) >= 12.0:
                # Pure Carver trend entry
                if fc > 0:
                    long_pos = 1
                    long_entry_price = c
                    long_peak_price = c
                    fee = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                    cash -= fee
                    trade_logs.append({'date': d, 'type': 'OPEN_LONG', 'price': c, 'pnl': 0, 'fee': fee, 'note': f'Trend Buy (fc={fc:.1f})'})
                else:
                    short_pos = 1
                    short_entry_price = c
                    short_trough_price = c
                    fee = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                    cash -= fee
                    trade_logs.append({'date': d, 'type': 'OPEN_SHORT', 'price': c, 'pnl': 0, 'fee': fee, 'note': f'Trend Sell (fc={fc:.1f})'})
                    
        # 3. If holding DUAL positions (both Long and Short open):
        elif long_pos > 0 and short_pos > 0:
            # We are in locked state. Check for BREAKOUT UNLOCKING:
            delta = 1.5 * cur_atr
            up_breakout = (c - long_entry_price) >= delta
            down_breakout = (short_entry_price - c) >= delta
            
            if up_breakout or fc >= 10.0:
                # Bullish breakout! Cut the SHORT leg (stop loss on short), let LONG run!
                short_loss = (c - short_entry_price) * MULTIPLIER  # loss is negative pnl
                pnl = -short_loss
                fee = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                cash += (pnl - fee)
                short_pos = 0
                long_peak_price = max(long_peak_price, c)
                trade_logs.append({
                    'date': d, 'type': 'CUT_SHORT_UNLOCK_LONG', 'price': c,
                    'pnl': pnl, 'fee': fee, 'note': f'Cut Short at {c:.1f}, Loss={pnl:.0f}'
                })
            elif down_breakout or fc <= -10.0:
                # Bearish breakout! Cut the LONG leg (stop loss on long), let SHORT run!
                long_loss = (c - long_entry_price) * MULTIPLIER
                pnl = long_loss
                fee = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                cash += (pnl - fee)
                long_pos = 0
                short_trough_price = min(short_trough_price, c)
                trade_logs.append({
                    'date': d, 'type': 'CUT_LONG_UNLOCK_SHORT', 'price': c,
                    'pnl': pnl, 'fee': fee, 'note': f'Cut Long at {c:.1f}, Loss={pnl:.0f}'
                })
                
        # 4. If holding SINGLE position (Long only or Short only):
        else:
            if long_pos > 0:
                long_peak_price = max(long_peak_price, c)
                # Hard Stop: 2.0 * ATR
                hard_stop_price = long_entry_price - 2.0 * cur_atr
                # Chandelier Trailing Stop: 2.5 * ATR from peak
                chandelier_stop_price = long_peak_price - 2.5 * cur_atr
                exit_price = max(hard_stop_price, chandelier_stop_price)
                
                # Check exit
                if c <= exit_price or fc <= -8.0:
                    pnl = (c - long_entry_price) * MULTIPLIER
                    fee = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                    cash += (pnl - fee)
                    long_pos = 0
                    trade_logs.append({
                        'date': d, 'type': 'EXIT_LONG', 'price': c,
                        'pnl': pnl, 'fee': fee, 'note': f'Exit Long, PnL={pnl:.0f}, Peak={long_peak_price:.1f}'
                    })
                    
            elif short_pos > 0:
                short_trough_price = min(short_trough_price, c)
                # Hard Stop: 2.0 * ATR
                hard_stop_price = short_entry_price + 2.0 * cur_atr
                # Chandelier Trailing Stop: 2.5 * ATR from trough
                chandelier_stop_price = short_trough_price + 2.5 * cur_atr
                exit_price = min(hard_stop_price, chandelier_stop_price)
                
                # Check exit
                if c >= exit_price or fc >= 8.0:
                    pnl = (short_entry_price - c) * MULTIPLIER
                    fee = COMMISSION + SLIPPAGE_POINTS * MULTIPLIER
                    cash += (pnl - fee)
                    short_pos = 0
                    trade_logs.append({
                        'date': d, 'type': 'EXIT_SHORT', 'price': c,
                        'pnl': pnl, 'fee': fee, 'note': f'Exit Short, PnL={pnl:.0f}, Trough={short_trough_price:.1f}'
                    })
                    
        # 5. Calculate Mark-to-Market Equity
        mtm_long = (c - long_entry_price) * MULTIPLIER if long_pos > 0 else 0.0
        mtm_short = (short_entry_price - c) * MULTIPLIER if short_pos > 0 else 0.0
        equity = cash + mtm_long + mtm_short
        
        daily_records.append({
            'date': d,
            'close': c,
            'cash': cash,
            'equity': equity,
            'long_pos': long_pos,
            'short_pos': short_pos
        })
        
    res_df = pd.DataFrame(daily_records)
    res_df['cum_max'] = res_df['equity'].cummax()
    res_df['drawdown'] = (res_df['equity'] - res_df['cum_max']) / res_df['cum_max']
    
    total_ret = (res_df['equity'].iloc[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL
    max_dd = res_df['drawdown'].min()
    
    print('='*50)
    print('【20万本金 原油(SC) 突破对锁与移仓实盘复盘结果】')
    print('='*50)
    print(f'起始资金: {INITIAL_CAPITAL:,.2f} 元')
    print(f'最终权益: {res_df["equity"].iloc[-1]:,.2f} 元')
    print(f'累计净收益: {res_df["equity"].iloc[-1] - INITIAL_CAPITAL:+,.2f} 元 (收益率: {total_ret*100:+.2f}%)')
    print(f'最大回撤 (MDD): {max_dd*100:.2f}%')
    print(f'总交易次数: {len(trade_logs)} 次 (含移仓与调仓)')
    
    trades_df = pd.DataFrame(trade_logs)
    print('\n最近 10 次交易与移仓记录:')
    print(trades_df.tail(10)[['date', 'type', 'price', 'pnl', 'fee', 'note']])
    
    # Save results
    res_df.to_csv(r'../data/processed\sc_200k_backtest.csv', index=False)
    trades_df.to_csv(r'../data/processed\sc_200k_trades.csv', index=False)
    print('\n[+] Saved backtest results to data/processed/')

if __name__ == '__main__':
    run_sc_system()
