"""
Multi-Commodity Pivot Trading Audit (多品种中枢量化回测与审计引擎)
===================================================================
覆盖四大代表性大宗商品：
1. 上海原油 (SC): 600 元/桶价值中枢 (OPEC成本与地缘风险溢价)
2. 郑州苹果 (AP): 8000 元/吨产业中枢 (果农种植与冷库仓储折旧成本)
3. 大连豆粕 (M):  3400 元/吨压榨中枢 (进口大豆压榨与下游养殖需求)
4. 大连玉米 (C):  2500 元/吨种植中枢 (东北农户地租化肥与中储粮政策中枢)
"""

from pathlib import Path
import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent

COMMODITY_CONFIGS = [
    {
        'symbol': 'SC 原油',
        'file': 'SC0_latest.csv',
        'anchor': 600.0,
        'multiplier': 1000.0,
        'capital': 200000.0,
        'min_buffer': 25.0,
        'max_buffer': 60.0,
        'margin_rate': 0.20,
        'commission': 60.0,
        'slippage': 200.0,
        'idle_days': 35,
        'idle_pct': 0.03
    },
    {
        'symbol': 'AP 苹果',
        'file': 'AP_daily.csv',
        'anchor': 8000.0,
        'multiplier': 10.0,
        'capital': 100000.0,
        'min_buffer': 200.0,
        'max_buffer': 450.0,
        'margin_rate': 0.12,
        'commission': 15.0,
        'slippage': 30.0,
        'idle_days': 35,
        'idle_pct': 0.03
    },
    {
        'symbol': 'M 豆粕',
        'file': 'M_daily.csv',
        'anchor': 3400.0,
        'multiplier': 10.0,
        'capital': 100000.0,
        'min_buffer': 70.0,
        'max_buffer': 160.0,
        'margin_rate': 0.10,
        'commission': 5.0,
        'slippage': 15.0,
        'idle_days': 35,
        'idle_pct': 0.025
    },
    {
        'symbol': 'C 玉米',
        'file': 'C_daily.csv',
        'anchor': 2500.0,
        'multiplier': 10.0,
        'capital': 100000.0,
        'min_buffer': 35.0,
        'max_buffer': 90.0,
        'margin_rate': 0.10,
        'commission': 5.0,
        'slippage': 15.0,
        'idle_days': 35,
        'idle_pct': 0.025
    }
]


def run_commodity_backtest(cfg: dict, start_date: str = '2021-01-01', bidirectional: bool = False) -> dict:
    data_path = BASE_DIR / 'data' / 'raw' / cfg['file']
    df = pd.read_csv(data_path)
    col_d, col_o, col_h, col_l, col_c = df.columns[0], df.columns[1], df.columns[2], df.columns[3], df.columns[4]
    df['date'] = pd.to_datetime(df[col_d])
    df = df.sort_values('date').reset_index(drop=True)
    df['close'] = df[col_c].astype(float)
    df['high'] = df[col_h].astype(float)
    df['low'] = df[col_l].astype(float)
    df['open'] = df[col_o].astype(float)

    sim_df = df[df['date'] >= start_date].copy().reset_index(drop=True)

    # 1. 计算 20日 ATR
    prev_c = sim_df['close'].shift(1)
    tr = pd.concat([sim_df['high'] - sim_df['low'], (sim_df['high'] - prev_c).abs(), (sim_df['low'] - prev_c).abs()], axis=1).max(axis=1)
    sim_df['atr'] = tr.rolling(20).mean().bfill()

    capital = cfg['capital']
    cash = capital
    anchor = cfg['anchor']
    mult = cfg['multiplier']
    comm = cfg['commission']
    slip = cfg['slippage']
    min_buf = cfg['min_buffer']
    max_buf = cfg['max_buffer']
    max_idle = cfg['idle_days']
    idle_pct = cfg['idle_pct']

    long_pos, short_pos = 0, 0
    long_peak = 0.0
    short_trough = 999999.0
    trig_px = 0.0
    cycles = []
    current_cycle = None
    last_exit_idx = -10

    current_month = None
    roll_done = False

    for i in range(1, len(sim_df)):
        row = sim_df.iloc[i]
        prev = sim_df.iloc[i-1]
        d, c, h, l = row['date'], row['close'], row['high'], row['low']
        atr = row['atr']

        # 每月15日主力移仓换月
        m_str = d.strftime('%Y-%m')
        if m_str != current_month:
            current_month = m_str
            roll_done = False
        if d.day >= 15 and not roll_done:
            roll_done = True
            pos_cnt = long_pos + short_pos
            if pos_cnt > 0:
                fee_roll = (comm + slip) * pos_cnt
                cash -= fee_roll
                if current_cycle:
                    current_cycle['roll_fees'] += fee_roll
                    current_cycle['rolls'] += 1

        # 1. 空仓阶段：中枢对锁建仓
        if long_pos == 0 and short_pos == 0:
            crossed = (prev['close'] < anchor <= c) or (prev['close'] > anchor >= c)
            near = abs(c - anchor) <= (0.015 * anchor)
            if (i > last_exit_idx + 1) and (crossed or near):
                long_pos, short_pos = 1, 1
                open_fee = (comm + slip) * 2
                cash -= open_fee
                current_cycle = {
                    'cycle_id': len(cycles) + 1,
                    'direction': None,
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_idx': i,
                    'trigger_date': None,
                    'trigger_price': None,
                    'cut_leg': None,
                    'cut_pnl': 0.0,
                    'win_date': None,
                    'win_price': None,
                    'win_pnl': 0.0,
                    'rolls': 0,
                    'roll_fees': 0.0,
                    'total_fees': open_fee,
                    'net_pnl': 0.0,
                    'equity_after': 0.0,
                    'exit_reason': None
                }

        # 2. 对锁阶段：超时熔断或单边突破
        elif long_pos > 0 and short_pos > 0:
            holding_days = i - current_cycle['entry_idx']
            if holding_days >= max_idle and abs(c - anchor) <= (idle_pct * anchor):
                fee = (comm + slip) * 2
                cash -= fee
                long_pos, short_pos = 0, 0
                current_cycle['direction'] = '平价对冲'
                current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                current_cycle['win_price'] = round(c, 1)
                current_cycle['exit_reason'] = '超时平价熔断'
                current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                current_cycle['net_pnl'] = round(-current_cycle['total_fees'], 1)
                current_cycle['equity_after'] = round(cash, 1)
                cycles.append(current_cycle)
                current_cycle = None
                last_exit_idx = i
                continue

            threshold = max(min_buf, min(1.8 * atr, max_buf))
            # 向上突破
            if (c - anchor) >= threshold:
                cut_price = c
                cut_pnl = (anchor - cut_price) * mult
                fee = comm + slip
                cash += cut_pnl - fee
                short_pos = 0
                long_peak = c
                trig_px = c
                current_cycle['direction'] = '多头'
                current_cycle['trigger_date'] = d.strftime('%Y-%m-%d')
                current_cycle['trigger_price'] = round(c, 1)
                current_cycle['cut_leg'] = '空头'
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
                continue

            # 向下突破 (双向模式)
            if bidirectional and (anchor - c) >= threshold:
                cut_price = c
                cut_pnl = (cut_price - anchor) * mult
                fee = comm + slip
                cash += cut_pnl - fee
                long_pos = 0
                short_trough = c
                trig_px = c
                current_cycle['direction'] = '空头'
                current_cycle['trigger_date'] = d.strftime('%Y-%m-%d')
                current_cycle['trigger_price'] = round(c, 1)
                current_cycle['cut_leg'] = '多头'
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
                continue

        # 3. 单边顺势阶段：智能三级跟踪止盈
        else:
            if long_pos > 0:
                long_peak = max(long_peak, c)
                floating = long_peak - anchor

                if floating >= 5.0 * atr:
                    stop_line = max(anchor + 0.75 * floating, prev['low'])
                    reason = '破前低/锁定75%浮盈'
                elif floating >= 3.0 * atr:
                    stop_line = max(anchor + 0.60 * floating, prev['low'])
                    reason = '阶梯锁定60%浮盈'
                elif floating >= 1.5 * atr:
                    stop_line = anchor + 0.5 * atr
                    reason = '底仓保本锁'
                else:
                    stop_line = max(anchor, trig_px - 0.3 * atr)
                    reason = '假突破窄幅保本'

                if c <= stop_line:
                    exit_px = c
                    win_pnl = (exit_px - anchor) * mult
                    fee = comm + slip
                    cash += win_pnl - fee
                    long_pos = 0
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(exit_px, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['exit_reason'] = reason
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    cycles.append(current_cycle)
                    current_cycle = None
                    last_exit_idx = i

            elif short_pos > 0:
                short_trough = min(short_trough, c)
                floating = anchor - short_trough

                if floating >= 5.0 * atr:
                    stop_line = min(anchor - 0.75 * floating, prev['high'])
                    reason = '破前高/锁定75%浮盈'
                elif floating >= 3.0 * atr:
                    stop_line = min(anchor - 0.60 * floating, prev['high'])
                    reason = '阶梯锁定60%浮盈'
                elif floating >= 1.5 * atr:
                    stop_line = anchor - 0.5 * atr
                    reason = '底仓保本锁'
                else:
                    stop_line = min(anchor, trig_px + 0.3 * atr)
                    reason = '假摔窄幅保本'

                if c >= stop_line:
                    exit_px = c
                    win_pnl = (anchor - exit_px) * mult
                    fee = comm + slip
                    cash += win_pnl - fee
                    short_pos = 0
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(exit_px, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['exit_reason'] = reason
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    cycles.append(current_cycle)
                    current_cycle = None
                    last_exit_idx = i

    res_df = pd.DataFrame(cycles)
    eq_curve = [capital] + (res_df['equity_after'].tolist() if len(res_df) > 0 else [])
    peak = capital
    mdd = 0.0
    for val in eq_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > mdd: mdd = dd

    profit = cash - capital
    ret_pct = profit / capital * 100
    win_rate = (res_df['net_pnl'] > 0).mean() * 100 if len(res_df) > 0 else 0
    margin_occupied = anchor * mult * cfg['margin_rate']

    return {
        'symbol': cfg['symbol'],
        'anchor': anchor,
        'multiplier': mult,
        'margin_rate': cfg['margin_rate'],
        'margin_occupied': margin_occupied,
        'capital': capital,
        'cash': cash,
        'profit': profit,
        'ret_pct': ret_pct,
        'mdd': mdd * 100,
        'min_equity': min(eq_curve),
        'calmar': ret_pct / (mdd * 100) if mdd > 0 else 0,
        'cycles': len(res_df),
        'win_rate': win_rate,
        'res_df': res_df
    }


if __name__ == '__main__':
    print('=' * 126)
    print('               大宗商品中枢量化交易系统：多品种通用化实战回测与风控审计报告 (2021-2026)')
    print('=' * 126 + '\n')

    # 1. 运行单向顺势旗舰版 (Upward Only)
    up_results = [run_commodity_backtest(cfg, bidirectional=False) for cfg in COMMODITY_CONFIGS]

    # 2. 运行双向对称突破版 (Bidirectional)
    bi_results = [run_commodity_backtest(cfg, bidirectional=True) for cfg in COMMODITY_CONFIGS]

    print('【一、四大主力品种：单向顺势突破 (Upward Only) 审计大表】')
    print('-' * 126)
    fmt_header = f"{'交易品种':<10} | {'产业中枢':>8} | {'1手合约价值':>12} | {'保证金占用 (比例)':>18} | {'初始本金':>10} | {'最终权益':>12} | {'累计净利润':>10} | {'总收益率':>8} | {'最大回撤':>8} | {'卡玛比率':>8} | {'轮次':>4}"
    print(fmt_header)
    print('-' * 126)

    for r in up_results:
        contract_val = r['anchor'] * r['multiplier']
        m_str = f"{r['margin_occupied']:>9,.0f} 元 ({r['margin_rate']*100:.0f}%)"
        print(f"{r['symbol']:<10} | {r['anchor']:>8.0f} | {contract_val:>10,.0f} 元 | {m_str:>20} | {r['capital']:>10,.0f} 元 | {r['cash']:>12,.0f} 元 | {r['profit']:>10,.0f} 元 | {r['ret_pct']:>7.1f}% | {r['mdd']:>7.1f}% | {r['calmar']:>8.2f} | {r['cycles']:>4d}")
    print('-' * 126)

    print('\n【二、四大主力品种：双向对称突破 (Bidirectional 多空双做) 审计大表】')
    print('-' * 126)
    print(fmt_header)
    print('-' * 126)

    for r in bi_results:
        contract_val = r['anchor'] * r['multiplier']
        m_str = f"{r['margin_occupied']:>9,.0f} 元 ({r['margin_rate']*100:.0f}%)"
        print(f"{r['symbol']:<10} | {r['anchor']:>8.0f} | {contract_val:>10,.0f} 元 | {m_str:>20} | {r['capital']:>10,.0f} 元 | {r['cash']:>12,.0f} 元 | {r['profit']:>10,.0f} 元 | {r['ret_pct']:>7.1f}% | {r['mdd']:>7.1f}% | {r['calmar']:>8.2f} | {r['cycles']:>4d}")
    print('-' * 126)

    # 保存流水
    out_dir = BASE_DIR / 'data' / 'processed'
    for r in up_results:
        f_name = f"cycles_{r['symbol'].split()[0]}_up.csv"
        r['res_df'].to_csv(out_dir / f_name, index=False)
    print(f"\n四大品种审计流水已全部存盘至: {out_dir}")
