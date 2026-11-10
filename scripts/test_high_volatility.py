"""
High-Volatility Commodity Futures Audit (高波动商品期货量化审计引擎)
===================================================================
测试品种：
1. 纯碱 (SA): 妖碱，2021-2026 巨震 919 ~ 3583 元/吨 (20吨/手)
2. 玻璃 (FG): 地产强链条，828 ~ 3072 元/吨 (20吨/手)
3. 棕榈油 (P): 能化农产双属性，6330 ~ 12718 元/吨 (10吨/手)
4. 苹果 (AP): 季节性巨震，4939 ~ 10753 元/吨 (10吨/手)
"""

from pathlib import Path
import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent

HIGH_VOL_COMMODITIES = [
    {
        'symbol': '纯碱 SA',
        'file': 'SA_daily.csv',
        'multiplier': 20.0,
        'commission': 10.0,
        'slippage': 20.0,
        'capital': 100000.0,
        'margin_rate': 0.12
    },
    {
        'symbol': '玻璃 FG',
        'file': 'FG_daily.csv',
        'multiplier': 20.0,
        'commission': 8.0,
        'slippage': 15.0,
        'capital': 100000.0,
        'margin_rate': 0.10
    },
    {
        'symbol': '棕榈油 P',
        'file': 'P_daily.csv',
        'multiplier': 10.0,
        'commission': 8.0,
        'slippage': 20.0,
        'capital': 100000.0,
        'margin_rate': 0.10
    },
    {
        'symbol': '苹果 AP',
        'file': 'AP_daily.csv',
        'multiplier': 10.0,
        'commission': 15.0,
        'slippage': 30.0,
        'capital': 100000.0,
        'margin_rate': 0.12
    }
]


def run_trend_engine(
    cfg: dict,
    start_date: str = '2021-01-01',
    entry_window: int = 20,
    exit_window: int = 10,
    use_ma_filter: bool = True,
    ma_span: int = 60
) -> dict:
    data_path = BASE_DIR / 'data' / 'raw' / cfg['file']
    df = pd.read_csv(data_path)
    col_d, col_o, col_h, col_l, col_c = df.columns[0], df.columns[1], df.columns[2], df.columns[3], df.columns[4]
    df['date'] = pd.to_datetime(df[col_d])
    df = df.sort_values('date').reset_index(drop=True)
    df['c'] = df[col_c].astype(float)
    df['h'] = df[col_h].astype(float)
    df['l'] = df[col_l].astype(float)

    # 突破通道与均线共振
    df['h_entry'] = df['h'].rolling(entry_window).max().shift(1)
    df['l_entry'] = df['l'].rolling(entry_window).min().shift(1)
    df['h_exit'] = df['h'].rolling(exit_window).max().shift(1)
    df['l_exit'] = df['l'].rolling(exit_window).min().shift(1)
    df['ma'] = df['c'].rolling(ma_span).mean().shift(1)

    prev_c = df['c'].shift(1)
    tr = pd.concat([df['h'] - df['l'], (df['h'] - prev_c).abs(), (df['l'] - prev_c).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(20).mean().bfill()

    sim_df = df[df['date'] >= start_date].copy().reset_index(drop=True)

    capital = cfg['capital']
    cash = capital
    mult = cfg['multiplier']
    comm = cfg['commission']
    slip = cfg['slippage']

    pos = 0 # 1 or -1 or 0
    base_entry = 0.0
    lots = 0
    trades = []
    
    current_month = None
    roll_done = False

    for i in range(2, len(sim_df)):
        row = sim_df.iloc[i]
        c, h, l, d = row['c'], row['h'], row['l'], row['date']
        he, le = row['h_entry'], row['l_entry']
        hx, lx = row['h_exit'], row['l_exit']
        ma_val = row['ma']
        atr = row['atr']

        # 每月主力合约展期
        m_str = d.strftime('%Y-%m')
        if m_str != current_month:
            current_month = m_str
            roll_done = False
        if d.day >= 15 and not roll_done:
            roll_done = True
            if pos != 0:
                fee_roll = (comm + slip) * lots
                cash -= fee_roll

        # 1. 突破开仓
        if pos == 0:
            long_ok = (c > he) and ((c > ma_val) if use_ma_filter else True)
            short_ok = (c < le) and ((c < ma_val) if use_ma_filter else True)

            # 等风险头寸定仓：基于 1.5% 风险和 ATR 测算标准手数
            stop_dist = max(atr * 1.5, c * 0.015)
            calc_lots = max(1, int((cash * 0.015) / (stop_dist * mult)))

            if long_ok:
                pos = 1
                base_entry = c
                lots = calc_lots
                fee = (comm + slip) * lots
                cash -= fee
                trades.append({
                    'id': len(trades) + 1,
                    'direction': '多头',
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_px': round(c, 1),
                    'lots': lots,
                    'exit_date': None,
                    'exit_px': None,
                    'pnl': 0.0,
                    'cash': 0.0,
                    'exit_reason': None
                })
            elif short_ok:
                pos = -1
                base_entry = c
                lots = calc_lots
                fee = (comm + slip) * lots
                cash -= fee
                trades.append({
                    'id': len(trades) + 1,
                    'direction': '空头',
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_px': round(c, 1),
                    'lots': lots,
                    'exit_date': None,
                    'exit_px': None,
                    'pnl': 0.0,
                    'cash': 0.0,
                    'exit_reason': None
                })

        # 2. 纯价格非对称通道跟踪离场（跌破近 M 日低点才走，让利润放开奔跑）
        elif pos == 1:
            if c < lx:
                exit_px = c
                pnl = (exit_px - base_entry) * mult * lots
                fee = (comm + slip) * lots
                net_pnl = pnl - fee
                cash += net_pnl
                trades[-1]['exit_date'] = d.strftime('%Y-%m-%d')
                trades[-1]['exit_px'] = round(exit_px, 1)
                trades[-1]['pnl'] = round(net_pnl, 1)
                trades[-1]['cash'] = round(cash, 1)
                trades[-1]['exit_reason'] = f'跌破近{exit_window}日低点止盈/离场'
                pos = 0
                lots = 0

        elif pos == -1:
            if c > hx:
                exit_px = c
                pnl = (base_entry - exit_px) * mult * lots
                fee = (comm + slip) * lots
                net_pnl = pnl - fee
                cash += net_pnl
                trades[-1]['exit_date'] = d.strftime('%Y-%m-%d')
                trades[-1]['exit_px'] = round(exit_px, 1)
                trades[-1]['pnl'] = round(net_pnl, 1)
                trades[-1]['cash'] = round(cash, 1)
                trades[-1]['exit_reason'] = f'涨破近{exit_window}日高点止盈/离场'
                pos = 0
                lots = 0

    valid_trades = [t for t in trades if t['exit_date'] is not None]
    res_df = pd.DataFrame(valid_trades)
    eq_curve = [capital] + (res_df['cash'].tolist() if len(res_df) > 0 else [])
    peak, mdd = capital, 0.0
    for v in eq_curve:
        if v > peak: peak = v
        dd = (peak - v) / peak
        if dd > mdd: mdd = dd

    profit = cash - capital
    ret_pct = profit / capital * 100
    wins = res_df[res_df['pnl'] > 0]['pnl'] if len(res_df) > 0 else []
    losses = res_df[res_df['pnl'] < 0]['pnl'] if len(res_df) > 0 else []
    win_rate = len(wins) / len(res_df) * 100 if len(res_df) > 0 else 0
    pl_ratio = (wins.mean() / abs(losses.mean())) if len(wins) > 0 and len(losses) > 0 else 0

    return {
        'symbol': cfg['symbol'],
        'capital': capital,
        'cash': cash,
        'profit': profit,
        'ret_pct': ret_pct,
        'mdd': mdd * 100,
        'trades': len(res_df),
        'win_rate': win_rate,
        'pl_ratio': pl_ratio,
        'calmar': ret_pct / (mdd * 100) if mdd > 0 else 0,
        'min_equity': min(eq_curve),
        'res_df': res_df
    }


if __name__ == '__main__':
    print('=' * 128)
    print('      高波动商品期货量化实战审计报告：纯碱、玻璃、棕榈油、苹果 (2021-2026)')
    print('=' * 128 + '\n')

    results = [run_trend_engine(cfg, entry_window=20, exit_window=10, use_ma_filter=True, ma_span=60) for cfg in HIGH_VOL_COMMODITIES]

    print('【一、四大高波动核心品种全量绩效审计对比】')
    print('-' * 128)
    fmt_h = f"{'交易品种':<10} | {'初始本金':>12} | {'最终权益':>12} | {'累计净利润':>12} | {'总收益率':>8} | {'最大回撤':>8} | {'交易笔数':>8} | {'胜率':>6} | {'单笔盈亏比':>10} | {'卡玛比率':>8}"
    print(fmt_h)
    print('-' * 128)

    for r in results:
        print(f"{r['symbol']:<10} | {r['capital']:>12,.0f} 元 | {r['cash']:>12,.0f} 元 | {r['profit']:>12,.0f} 元 | {r['ret_pct']:>7.1f}% | {r['mdd']:>7.1f}% | {r['trades']:>8d} 笔 | {r['win_rate']:>5.1f}% | {r['pl_ratio']:>8.2f}:1 | {r['calmar']:>8.2f}")
    print('-' * 128)

    for r in results:
        print(f"\n【{r['symbol']}：近期交易实战流水样例 (最近 6 笔)】")
        print('=' * 128)
        df_sub = r['res_df'].tail(6)
        if len(df_sub) > 0:
            cols = ['id', 'direction', 'entry_date', 'entry_px', 'lots', 'exit_date', 'exit_px', 'pnl', 'cash', 'exit_reason']
            t = df_sub[cols].copy()
            t.columns = ['序号', '方向', '开仓日', '开仓价', '手数', '出场日', '出场价', '净损益', '账户权益', '离场原因']
            print(t.to_string(index=False))
        print('=' * 128)
