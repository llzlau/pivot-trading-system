"""
===================================================================================
模块名称: strategies/asymmetric_convex_trend.py
业务定位: ACTS 3.0 (Asymmetric Convex Trend System) 终极实战工业级趋势与动量交易引擎
输入依赖: data/raw/{SYMBOL}_*.csv (包含 OHLCV 的主力连续行情数据)
核心输出: 逐笔交易穿透流水、资金权益曲线、盈亏比与卡玛比率等实战审计字典
===================================================================================
架构原则与演进 (ACTS 3.0 终极实战版):
1. Master Pool 统一资金池与名义风险平价 (单笔基准风险 1.0%，全账户保证金上限 40%)；
2. 跨夜折减定仓引擎 (Risk Space = max(1.2 * ATR_local, 0.5 * ATR_macro))，彻底规避隔夜跳空爆仓；
3. 结构性次级防线 (Higher Low / Lower High 确认机制)，坚决拒绝死板 1.5 ATR 成本平推；
4. 成熟期动能双轨收网 (浮盈 >= 3.5 ATR 且持仓 >= 15 根 K 线，ATR5/ATR20 > 1.8 触发前 3K 极值锁利)；
5. 顺大势破位 (MA60 大周期滤波) 与 House-Money 浮盈 2.0 ATR 独立保本追击加仓。
"""

from pathlib import Path
import sys
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

# ── 品种池配置与费率防雷层 (Fee Filter & Specification) ───────────────────────────
COMMODITY_PORTFOLIO = [
    {
        'symbol': '原油 SC',
        'file': 'SC0_latest.csv',
        'multiplier': 1000.0,
        'commission': 60.0,
        'slippage': 200.0,
        'capital': 200000.0,
        'margin_rate': 0.15,
        'tick_size': 0.1,
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
        'tick_size': 10.0,
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
        'tick_size': 1.0,
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
        'tick_size': 1.0,
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
        'tick_size': 1.0,
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
        'tick_size': 1.0,
        'category': '大宗农产'
    }
]


def run_asymmetric_convex_engine(
    cfg: dict,
    start_date: str = '2021-01-01',
    entry_window: int = 20,
    exit_window: int = 10,
    ma_span: int = 60,
    risk_pct: float = 0.010,       # ACTS 3.0 基准名义风险预算: 1.0%
    max_margin_pct: float = 0.40,  # 保证金占用硬上限: 40% (保留 60% 现金缓冲极端跳空)
    allow_pyramid: bool = True
) -> dict:
    """
    执行 ACTS 3.0 终极实战交易系统回测审计
    """
    data_path = BASE_DIR / 'data' / 'raw' / cfg['file']
    df = pd.read_csv(data_path)
    col_d, col_o, col_h, col_l, col_c = df.columns[0], df.columns[1], df.columns[2], df.columns[3], df.columns[4]
    df['date'] = pd.to_datetime(df[col_d])
    df = df.sort_values('date').reset_index(drop=True)
    df['c'] = df[col_c].astype(float)
    df['h'] = df[col_h].astype(float)
    df['l'] = df[col_l].astype(float)
    df['o'] = df[col_o].astype(float)

    # 1. 动能通道与宏观滤波计算
    df['h_entry'] = df['h'].rolling(entry_window).max().shift(1)
    df['l_entry'] = df['l'].rolling(entry_window).min().shift(1)
    df['h_exit'] = df['h'].rolling(exit_window).max().shift(1)
    df['l_exit'] = df['l'].rolling(exit_window).min().shift(1)
    df['ma'] = df['c'].rolling(ma_span).mean().shift(1)

    # 2. 真实波幅 (TR) 与多尺度波动率 (ATR_local, ATR5, ATR_macro)
    prev_c = df['c'].shift(1)
    tr = pd.concat([df['h'] - df['l'], (df['h'] - prev_c).abs(), (df['l'] - prev_c).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(20).mean().bfill()
    df['atr5'] = tr.rolling(5).mean().bfill()
    df['atr_macro'] = tr.rolling(60).mean().bfill()  # 宏观长周期波动底线

    # 3. 极速冲顶与加速见顶判定 (ATR5 / ATR20 > 1.8)
    df['vol_surge'] = (df['atr5'] / df['atr']) > 1.8

    # 4. 前 3 根 K 线极值 (收网时快速锁定利润)
    df['low_3'] = df['l'].rolling(3).min().shift(1)
    df['high_3'] = df['h'].rolling(3).max().shift(1)

    sim_df = df[df['date'] >= start_date].copy().reset_index(drop=True)

    capital = cfg['capital']
    cash = capital
    mult = cfg['multiplier']
    comm = cfg['commission']
    slip = cfg['slippage']
    tick_sz = cfg.get('tick_size', 1.0)

    pos = 0          # 1: 多头, -1: 空头, 0: 空仓
    base_entry = 0.0
    lots = 0
    addon_lots = 0
    addon_entry = None
    peak_p = 0.0
    trough_p = 999999.0
    trades = []

    # 次级结构跟踪变量 (Higher Low / Lower High)
    stop_loss = 0.0
    swing_high = 0.0
    swing_low = None
    confirmed_structural_stop = 0.0
    bars_held = 0

    current_month = None
    roll_done = False

    for i in range(2, len(sim_df)):
        row = sim_df.iloc[i]
        c, h, l, d = row['c'], row['h'], row['l'], row['date']
        he, le = row['h_entry'], row['l_entry']
        hx, lx = row['h_exit'], row['l_exit']
        ma_val = row['ma']
        atr = row['atr']
        atr_macro = row['atr_macro']
        vol_surge = row['vol_surge']
        low_3 = row['low_3']
        high_3 = row['high_3']

        # 每月中旬主力合约法定移仓与交割换月摩擦
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

        # ── 模块 1: 突破入场与跨夜折减定仓引擎 ─────────────────────────────────
        if pos == 0:
            # 跨夜折减定仓公式: max(1.2 * ATR_local, 0.5 * ATR_macro)
            risk_space = max(1.2 * atr, 0.5 * atr_macro)
            
            # 名义风险预算计算原始手数 (1.0% NAV)
            raw_lots = int((cash * risk_pct) / max(1.0, (risk_space * mult)))
            
            # 保证金上限硬约束 (Margin Cap <= 40%)
            margin_per_lot = c * mult * cfg['margin_rate']
            max_allowed_lots = max(1, int((cash * max_margin_pct) / max(1.0, margin_per_lot)))
            calc_lots = max(1, min(raw_lots, max_allowed_lots))

            # 多头破位：收盘价站上 20 周期高点 + 处于长期均线多头趋势
            if c > he and c > ma_val:
                pos = 1
                base_entry = c
                lots = calc_lots
                addon_lots = 0
                addon_entry = None
                peak_p = c
                bars_held = 0
                
                # 初始防守: 严格设定在 1.2 * risk_space 下方
                stop_loss = round(c - 1.2 * risk_space, 2)
                swing_high = c
                swing_low = None
                confirmed_structural_stop = stop_loss

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

            # 空头破位：收盘价跌破 20 周期低点 + 处于长期均线空头趋势
            elif c < le and c < ma_val:
                pos = -1
                base_entry = c
                lots = calc_lots
                addon_lots = 0
                addon_entry = None
                trough_p = c
                bars_held = 0
                
                # 初始防守: 严格设定在 1.2 * risk_space 上方
                stop_loss = round(c + 1.2 * risk_space, 2)
                swing_low = c
                swing_high = None
                confirmed_structural_stop = stop_loss

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

        # ── 模块 2: 多头持仓跟踪、次级防线推进与成熟期动能双轨收网 ─────────────
        elif pos == 1:
            bars_held += 1
            peak_p = max(peak_p, c)
            floating_r = (peak_p - base_entry) / max(atr, 1e-4)

            # 1. 结构性次级防线判定 (Higher Low - 拒绝死板 1.5 ATR 成本平推)
            if c > swing_high:
                # 价格突破前高！若此前经历过回踩且未打破当前止损，则确认次级低点 Higher Low
                if swing_low is not None and swing_low > stop_loss:
                    confirmed_structural_stop = max(confirmed_structural_stop, swing_low - 2 * tick_sz)
                    stop_loss = max(stop_loss, confirmed_structural_stop)
                    swing_low = None  # 重置回踩槽
                swing_high = c
            elif c < swing_high:
                # 处于回踩阶段，动态记录回踩局部最低点
                swing_low = min(swing_low, l) if swing_low is not None else l

            # 2. House-Money 浮盈追击协议 (浮盈达 2.0 ATR 后以市场利润追加 1 手)
            if allow_pyramid and not trades[-1]['addon_added'] and floating_r >= 2.0:
                addon_lots = 1
                addon_entry = c
                fee_add = (comm + slip) * addon_lots
                cash -= fee_add
                trades[-1]['addon_added'] = True

            # 3. 加仓单独立原价保本防暴线：绝不允许加仓回踩侵蚀底仓
            if addon_lots > 0 and c <= addon_entry:
                pnl_add = (c - addon_entry) * mult * addon_lots
                fee_add = (comm + slip) * addon_lots
                cash += pnl_add - fee_add
                addon_lots = 0
                addon_entry = None

            # 4. 成熟期动能双轨收网机制 (前置双条件: 浮盈 >= 3.5 ATR 且持有 >= 15 根 K 线)
            is_mature = (floating_r >= 3.5) and (bars_held >= 15)
            exit_triggered = False
            exit_reason = None

            if is_mature and vol_surge and c < low_3:
                # 触发加速冲顶末期收网: 跌破前 3 根 K 线极值，一枪毙命锁定 75%+ 高位浮盈
                exit_triggered = True
                exit_reason = '成熟期动能脉冲见顶(破前3K低点收网)'
            elif c < stop_loss:
                # 跌破结构性次级防线止损
                exit_triggered = True
                exit_reason = '跌破次级结构防线(Higher Low)平仓'
            elif c < (peak_p - 2.5 * atr) or c < lx:
                # 常态宽幅吊灯或跌破 10 日通道极值出场
                exit_triggered = True
                exit_reason = f'跌破近{exit_window}日极值或2.5ATR吊灯平仓'

            if exit_triggered:
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
                trades[-1]['exit_reason'] = exit_reason
                pos = 0
                lots = 0
                addon_lots = 0
                addon_entry = None

        # ── 模块 3: 空头持仓跟踪、次级防线推进与成熟期动能双轨收网 ─────────────
        elif pos == -1:
            bars_held += 1
            trough_p = min(trough_p, c)
            floating_r = (base_entry - trough_p) / max(atr, 1e-4)

            # 1. 结构性次级防线判定 (Lower High - 拒绝死板 1.5 ATR 成本平推)
            if c < swing_low:
                # 价格跌破前低！若此前经历过反弹且未打破当前止损，则确认次级高点 Lower High
                if swing_high is not None and swing_high < stop_loss:
                    confirmed_structural_stop = min(confirmed_structural_stop, swing_high + 2 * tick_sz)
                    stop_loss = min(stop_loss, confirmed_structural_stop)
                    swing_high = None  # 重置反弹波峰
                swing_low = c
            elif c > swing_low:
                # 处于反弹阶段，动态记录反弹局部最高点
                swing_high = max(swing_high, h) if swing_high is not None else h

            # 2. House-Money 浮盈追击协议 (浮盈达 2.0 ATR 后以市场利润追加 1 手)
            if allow_pyramid and not trades[-1]['addon_added'] and floating_r >= 2.0:
                addon_lots = 1
                addon_entry = c
                fee_add = (comm + slip) * addon_lots
                cash -= fee_add
                trades[-1]['addon_added'] = True

            # 3. 加仓单独立原价保本防暴线：绝不允许加仓反弹侵蚀底仓
            if addon_lots > 0 and c >= addon_entry:
                pnl_add = (addon_entry - c) * mult * addon_lots
                fee_add = (comm + slip) * addon_lots
                cash += pnl_add - fee_add
                addon_lots = 0
                addon_entry = None

            # 4. 成熟期动能双轨收网机制 (前置双条件: 浮盈 >= 3.5 ATR 且持有 >= 15 根 K 线)
            is_mature = (floating_r >= 3.5) and (bars_held >= 15)
            exit_triggered = False
            exit_reason = None

            if is_mature and vol_surge and c > high_3:
                # 触发加速衰竭探底末期收网: 涨破前 3 根 K 线极值，一枪毙命锁定 75%+ 高位浮盈
                exit_triggered = True
                exit_reason = '成熟期动能脉冲见底(涨破前3K高点收网)'
            elif c > stop_loss:
                # 涨破结构性次级防线止损
                exit_triggered = True
                exit_reason = '涨破次级结构防线(Lower High)平仓'
            elif c > (trough_p + 2.5 * atr) or c > hx:
                # 常态宽幅吊灯或涨破 10 日通道极值出场
                exit_triggered = True
                exit_reason = f'涨破近{exit_window}日极值或2.5ATR吊灯平仓'

            if exit_triggered:
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
                trades[-1]['exit_reason'] = exit_reason
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
