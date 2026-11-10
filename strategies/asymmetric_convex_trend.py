"""
Asymmetric Convex Trend System (ACTS - 非对称反脆弱趋势交易引擎)
==============================================================
核心架构与设计哲学：
1. 零预测假设 (Zero-Prediction Paradigm)：
   - 彻底摒弃一切事后画靶的固定价格中枢与振荡指标；
   - 视 K 行为游离的随机漫步线，承认无法预测未来的涨跌点位；
2. 非对称赔率优势 (Asymmetric Convexity)：
   - 亏损端：严格控制单笔试错成本在 1.5% 资金以内；
   - 盈利端：通过近 10 日极值跟踪线与宽幅 ATR 吊灯，给足利润呼吸空间，不设天花板；
3. 顺大势破位 (Macro Trend Resonance)：
   - 依托大周期均线 (MA60) 确认宏观产业顺逆，均线上方只做多突破，均线下方只做空破位；
4. 浮盈滚雪球协议 (House-Money Pyramiding)：
   - 浮盈超过 2.0 ATR 后以市场利润追加仓位，加仓单严格设置独立保本防暴线。
"""

from pathlib import Path
import sys
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

COMMODITY_PORTFOLIO = [
    {
        'symbol': '原油 SC',
        'file': 'SC0_latest.csv',
        'multiplier': 1000.0,
        'commission': 60.0,
        'slippage': 200.0,
        'capital': 200000.0,
        'margin_rate': 0.15,
        'category': '宏观能化'
    },
    {
        'symbol': '沪铜 CU',
        'file': 'CU_daily.csv',
        'multiplier': 5.0,
        'commission': 20.0,
        'slippage': 40.0,
        'capital': 100000.0,
        'margin_rate': 0.10,
        'category': '有色金属'
    },
    {
        'symbol': '玻璃 FG',
        'file': 'FG_daily.csv',
        'multiplier': 20.0,
        'commission': 8.0,
        'slippage': 15.0,
        'capital': 100000.0,
        'margin_rate': 0.10,
        'category': '建材工业'
    },
    {
        'symbol': '纯碱 SA',
        'file': 'SA_daily.csv',
        'multiplier': 20.0,
        'commission': 10.0,
        'slippage': 20.0,
        'capital': 100000.0,
        'margin_rate': 0.12,
        'category': '化工制造'
    },
    {
        'symbol': '螺纹钢 RB',
        'file': 'RB_daily.csv',
        'multiplier': 10.0,
        'commission': 10.0,
        'slippage': 20.0,
        'capital': 100000.0,
        'margin_rate': 0.10,
        'category': '黑色建材'
    },
    {
        'symbol': '玉米 C',
        'file': 'C_daily.csv',
        'multiplier': 10.0,
        'commission': 5.0,
        'slippage': 15.0,
        'capital': 100000.0,
        'margin_rate': 0.10,
        'category': '大宗农产'
    }
]


def run_asymmetric_convex_engine(
    cfg: dict,
    start_date: str = '2021-01-01',
    entry_window: int = 20,
    exit_window: int = 10,
    ma_span: int = 60,
    risk_pct: float = 0.015,
    allow_pyramid: bool = True
) -> dict:
    data_path = BASE_DIR / 'data' / 'raw' / cfg['file']
    df = pd.read_csv(data_path)
    col_d, col_o, col_h, col_l, col_c = df.columns[0], df.columns[1], df.columns[2], df.columns[3], df.columns[4]
    df['date'] = pd.to_datetime(df[col_d])
    df = df.sort_values('date').reset_index(drop=True)
    df['c'] = df[col_c].astype(float)
    df['h'] = df[col_h].astype(float)
    df['l'] = df[col_l].astype(float)

    # 突破通道与趋势共振
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
    addon_lots = 0
    addon_entry = None
    peak_p = 0.0
    trough_p = 999999.0
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

        # 每月中旬主力合约展期
        m_str = d.strftime('%Y-%m')
        if m_str != current_month:
            current_month = m_str
            roll_done = False
        if d.day >= 15 and not roll_done:
            roll_done = True
            total_active = abs(lots) + abs(addon_lots)
            if total_active > 0:
                fee_roll = (comm + slip) * total_active
                cash -= fee_roll

        # 1. 突破开仓
        if pos == 0:
            stop_dist = max(atr * 1.5, c * 0.015)
            calc_lots = max(1, int((cash * risk_pct) / (stop_dist * mult)))

            # 多头破位：突破过去 N 日高点 + 处于长期均线多头趋势
            if c > he and c > ma_val:
                pos = 1
                base_entry = c
                lots = calc_lots
                addon_lots = 0
                addon_entry = None
                peak_p = c
                fee = (comm + slip) * lots
                cash -= fee
                trades.append({
                    'id': len(trades) + 1,
                    'direction': '多头',
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_px': round(c, 1),
                    'lots': lots,
                    'addon_added': False,
                    'exit_date': None,
                    'exit_px': None,
                    'pnl': 0.0,
                    'cash': 0.0,
                    'exit_reason': None
                })
            # 空头破位：跌破过去 N 日低点 + 处于长期均线空头趋势
            elif c < le and c < ma_val:
                pos = -1
                base_entry = c
                lots = calc_lots
                addon_lots = 0
                addon_entry = None
                trough_p = c
                fee = (comm + slip) * lots
                cash -= fee
                trades.append({
                    'id': len(trades) + 1,
                    'direction': '空头',
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_px': round(c, 1),
                    'lots': lots,
                    'addon_added': False,
                    'exit_date': None,
                    'exit_px': None,
                    'pnl': 0.0,
                    'cash': 0.0,
                    'exit_reason': None
                })

        # 2. 多头顺势运行与非对称跟踪
        elif pos == 1:
            peak_p = max(peak_p, c)
            floating = peak_p - base_entry

            # 正金字塔加仓：浮盈达 2.0 ATR 后以市场利润追加 (每笔交易仅允许触发一次，绝不反复刷单)
            if allow_pyramid and not trades[-1]['addon_added'] and floating >= 2.0 * atr:
                addon_lots = 1
                addon_entry = c
                fee_add = (comm + slip) * addon_lots
                cash -= fee_add
                trades[-1]['addon_added'] = True

            # 加仓单独立原价保本防暴线：若价格回踩跌破加仓入场价，加仓单立即保本平仓
            if addon_lots > 0 and c <= addon_entry:
                pnl_add = (c - addon_entry) * mult * addon_lots
                fee_add = (comm + slip) * addon_lots
                cash += pnl_add - fee_add
                addon_lots = 0
                addon_entry = None

            # 底仓非对称离场：跌破近 M 日低点才平仓，彻底让利润在趋势中奔跑
            if c < lx:
                exit_px = c
                pnl_base = (exit_px - base_entry) * mult * lots
                pnl_add = (exit_px - addon_entry) * mult * addon_lots if addon_lots > 0 else 0.0
                total_lots = lots + addon_lots
                fee = (comm + slip) * total_lots
                net_pnl = pnl_base + pnl_add - fee
                cash += net_pnl
                trades[-1]['exit_date'] = d.strftime('%Y-%m-%d')
                trades[-1]['exit_px'] = round(exit_px, 1)
                trades[-1]['pnl'] = round(net_pnl, 1)
                trades[-1]['cash'] = round(cash, 1)
                trades[-1]['exit_reason'] = f'跌破近{exit_window}日低点平仓'
                pos = 0
                lots = 0
                addon_lots = 0
                addon_entry = None

        # 3. 空头顺势运行与非对称跟踪
        elif pos == -1:
            trough_p = min(trough_p, c)
            floating = base_entry - trough_p

            if allow_pyramid and not trades[-1]['addon_added'] and floating >= 2.0 * atr:
                addon_lots = 1
                addon_entry = c
                fee_add = (comm + slip) * addon_lots
                cash -= fee_add
                trades[-1]['addon_added'] = True

            if addon_lots > 0 and c >= addon_entry:
                pnl_add = (addon_entry - c) * mult * addon_lots
                fee_add = (comm + slip) * addon_lots
                cash += pnl_add - fee_add
                addon_lots = 0
                addon_entry = None

            if c > hx:
                exit_px = c
                pnl_base = (base_entry - exit_px) * mult * lots
                pnl_add = (addon_entry - exit_px) * mult * addon_lots if addon_lots > 0 else 0.0
                total_lots = lots + addon_lots
                fee = (comm + slip) * total_lots
                net_pnl = pnl_base + pnl_add - fee
                cash += net_pnl
                trades[-1]['exit_date'] = d.strftime('%Y-%m-%d')
                trades[-1]['exit_px'] = round(exit_px, 1)
                trades[-1]['pnl'] = round(net_pnl, 1)
                trades[-1]['cash'] = round(cash, 1)
                trades[-1]['exit_reason'] = f'涨破近{exit_window}日高点平仓'
                pos = 0
                lots = 0
                addon_lots = 0
                addon_entry = None

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
        'category': cfg['category'],
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
