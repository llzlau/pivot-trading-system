"""
Institutional SC Pivot Trading Strategy (机构级原油中枢量化交易策略)
=====================================================================
整合六大专业量化核心引擎：
1. 市场状态与趋势动能滤网 (Market Regime Filter: ADX >= 20 & 均线多头共振)
2. 动态自适应波动率中枢 (Dynamic Pivot: 1.8 * ATR 动态阈值)
3. 乖离率防透支过滤器 (Anti-Chasing Bias Filter: Bias < 2.5 ATR 防止追顶/追底)
4. 正金字塔安全垫加仓引擎 (Position Sizing & House Money Pyramiding)
5. 智能三级动态跟踪锁盈系统 (Smart Exit: 加仓单保本 + 底仓阶梯锁 + 破前高/前低离场)
6. 机构级移仓与账户风控断路器 (Roll Manager & Drawdown Circuit Breaker)
"""

from pathlib import Path
import pandas as pd
import numpy as np

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from core.regime_filter import MarketRegimeFilter
from core.dynamic_pivot import DynamicPivotEngine
from core.position_sizing import PositionSizingEngine
from core.smart_exit import SmartExitEngine
from core.roll_manager import RollOverManager
from core.portfolio_risk import PortfolioRiskEngine


def run_institutional_strategy(
    start_date: str = '2021-01-01',
    initial_capital: float = 200000.0,
    allow_pyramid: bool = True,
    bidirectional: bool = False
) -> tuple[pd.DataFrame, float, dict]:
    # 1. 加载行情数据
    data_path = BASE_DIR / 'data' / 'raw' / 'SC0_latest.csv'
    df = pd.read_csv(data_path)
    df.columns = [c.strip() for c in df.columns]
    df['日期'] = pd.to_datetime(df['日期'])
    df = df.sort_values('日期').reset_index(drop=True)

    sim_df = df[df['日期'] >= start_date].copy().reset_index(drop=True)

    # 2. 初始化核心引擎
    regime = MarketRegimeFilter(sim_df, adx_threshold=20.0)
    pivot = DynamicPivotEngine(anchor=600.0, atr_multiplier=1.8, min_buffer=25.0, max_buffer=60.0)
    sizing = PositionSizingEngine(multiplier=1000.0, risk_per_trade_pct=0.015)
    smart_exit = SmartExitEngine(multiplier=1000.0)
    roll = RollOverManager(commission_per_lot=60.0, slippage_per_lot=200.0, max_idle_days=35)
    risk = PortfolioRiskEngine(initial_capital=initial_capital, max_drawdown_limit=0.25)

    cash = initial_capital
    long_pos = 0 # 0, 1, 2
    short_pos = 0
    addon_entry = None
    long_peak = 0.0
    short_trough = 999999.0
    
    cycles = []
    current_cycle = None
    last_exit_idx = -10

    for i in range(1, len(sim_df)):
        risk.step_day()
        row = sim_df.iloc[i]
        prev = sim_df.iloc[i-1]
        d, c, o, h, l = row['日期'], row['收盘价'], row['开盘价'], row['最高价'], row['最低价']
        atr = regime.df.loc[i, 'atr']

        # 检查移仓换月
        total_lots = long_pos + short_pos
        did_roll, roll_fee = roll.check_monthly_roll(d, total_lots)
        if did_roll:
            cash -= roll_fee
            if current_cycle:
                current_cycle['rolls'] += 1
                current_cycle['roll_fees'] += roll_fee

        # 1. 空仓阶段：检查中枢对锁建仓
        if long_pos == 0 and short_pos == 0:
            risk_status = risk.get_risk_status(cash)
            if not risk_status['can_open_new']:
                continue

            if (i > last_exit_idx + 1) and pivot.check_anchor_entry(prev['收盘价'], c, l, h):
                long_pos = 1
                short_pos = 1
                addon_entry = None
                long_peak = 600.0
                short_trough = 600.0
                open_fee = (roll.commission_per_lot + roll.slippage_per_lot) * 2
                cash -= open_fee

                current_cycle = {
                    'cycle_id': len(cycles) + 1,
                    'entry_date': d.strftime('%Y-%m-%d'),
                    'entry_idx': i,
                    'entry_price': 600.0,
                    'direction': None,
                    'trigger_date': None,
                    'trigger_price': None,
                    'cut_leg': None,
                    'cut_price': None,
                    'cut_pnl': 0.0,
                    'addon_added': False,
                    'addon_price': None,
                    'win_leg': None,
                    'win_date': None,
                    'win_price': None,
                    'win_pnl': 0.0,
                    'exit_reason': None,
                    'rolls': 0,
                    'roll_fees': 0.0,
                    'total_fees': open_fee,
                    'net_pnl': 0.0,
                    'equity_after': 0.0
                }

        # 2. 对锁阶段：监控超时熔断与突破解锁
        elif long_pos > 0 and short_pos > 0:
            holding_days = i - current_cycle['entry_idx']
            is_timeout, timeout_reason = roll.check_idle_timeout(holding_days, c, 600.0)
            
            # 超时钝化平价熔断退出 (避免无休止移仓失血)
            if is_timeout:
                pnl_l = (c - 600.0) * 1000.0
                pnl_s = (600.0 - c) * 1000.0
                fee = (roll.commission_per_lot + roll.slippage_per_lot) * 2
                cash += pnl_l + pnl_s - fee
                long_pos, short_pos = 0, 0
                current_cycle['direction'] = '平价对冲'
                current_cycle['win_leg'] = '超时平价熔断'
                current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                current_cycle['win_price'] = round(c, 1)
                current_cycle['exit_reason'] = timeout_reason
                current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                current_cycle['net_pnl'] = round(-current_cycle['total_fees'], 1)
                current_cycle['equity_after'] = round(cash, 1)
                risk.update_equity(cash, current_cycle['net_pnl'])
                cycles.append(current_cycle)
                current_cycle = None
                last_exit_idx = i
                continue

            # 检查向上突破 (斩断空头亏损腿，必须无条件执行)
            is_breakout_l, trig_buf_l = pivot.check_breakout(600.0, c, atr, 'LONG')
            if is_breakout_l:
                cut_price = c
                cut_pnl = (600.0 - cut_price) * 1000.0
                fee = roll.commission_per_lot + roll.slippage_per_lot
                cash += cut_pnl - fee
                short_pos = 0
                long_peak = c

                current_cycle['direction'] = '多头'
                current_cycle['trigger_date'] = d.strftime('%Y-%m-%d')
                current_cycle['trigger_price'] = round(cut_price, 1)
                current_cycle['cut_leg'] = '空头'
                current_cycle['cut_price'] = round(cut_price, 1)
                current_cycle['cut_pnl'] = round(cut_pnl, 1)
                current_cycle['total_fees'] += fee
                continue

            # 检查向下突破 (双向模式开启时，斩断多头亏损腿)
            if bidirectional:
                is_breakout_s, trig_buf_s = pivot.check_breakout(600.0, c, atr, 'SHORT')
                if is_breakout_s:
                    cut_price = c
                    cut_pnl = (cut_price - 600.0) * 1000.0
                    fee = roll.commission_per_lot + roll.slippage_per_lot
                    cash += cut_pnl - fee
                    long_pos = 0
                    short_trough = c

                    current_cycle['direction'] = '空头'
                    current_cycle['trigger_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['trigger_price'] = round(cut_price, 1)
                    current_cycle['cut_leg'] = '多头'
                    current_cycle['cut_price'] = round(cut_price, 1)
                    current_cycle['cut_pnl'] = round(cut_pnl, 1)
                    current_cycle['total_fees'] += fee
                    continue

        # 3. 单边顺势阶段：智能动态出场与正金字塔加仓
        else:
            trig_px = current_cycle['trigger_price']

            # 3.1 多头运行状态
            if long_pos > 0:
                long_peak = max(long_peak, c)

                # 正金字塔加仓评估 (底仓浮盈充足 + 市场趋势健康未透支 + 账户风控良好)
                risk_status = risk.get_risk_status(cash)
                if allow_pyramid and long_pos == 1 and risk_status['can_pyramid']:
                    can_pyramid, pyramid_reason = sizing.check_pyramid_allowed(
                        base_entry=600.0,
                        curr_price=c,
                        atr=atr,
                        direction='LONG',
                        base_locked_profit=long_peak - 600.0 - 1.5 * atr
                    )
                    is_regime_ok, regime_reason = regime.check_regime(i, 'LONG')
                    if can_pyramid and is_regime_ok and (c > prev['收盘价']):
                        long_pos = 2
                        addon_entry = c
                        fee_add = roll.commission_per_lot + roll.slippage_per_lot
                        cash -= fee_add
                        current_cycle['addon_added'] = True
                        current_cycle['addon_price'] = round(c, 1)
                        current_cycle['total_fees'] += fee_add

                # 智能跟踪止盈评估
                exit_eval = smart_exit.evaluate_long_exit(
                    curr_row=row,
                    prev_row=prev,
                    base_entry=600.0,
                    trigger_price=trig_px,
                    addon_entry=addon_entry,
                    long_peak=long_peak,
                    atr=atr
                )

                # 加仓单保本平仓
                if exit_eval['exit_addon'] and long_pos == 2:
                    pnl_addon = (c - addon_entry) * 1000.0
                    fee_addon = roll.commission_per_lot + roll.slippage_per_lot
                    cash += pnl_addon - fee_addon
                    long_pos = 1
                    addon_entry = None
                    current_cycle['total_fees'] += fee_addon
                    current_cycle['cut_pnl'] += pnl_addon

                # 底仓平仓离场
                if exit_eval['exit_base']:
                    exit_px = exit_eval['exit_price']
                    win_pnl = (exit_px - 600.0) * 1000.0
                    if long_pos == 2:
                        win_pnl += (exit_px - addon_entry) * 1000.0
                    
                    fee = (roll.commission_per_lot + roll.slippage_per_lot) * long_pos
                    cash += win_pnl - fee
                    long_pos = 0
                    addon_entry = None

                    current_cycle['win_leg'] = '多头'
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(exit_px, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['exit_reason'] = exit_eval['reason']
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    
                    risk.update_equity(cash, current_cycle['net_pnl'])
                    cycles.append(current_cycle)
                    current_cycle = None
                    last_exit_idx = i

            # 3.2 空头运行状态 (双向突破支持)
            elif short_pos > 0:
                short_trough = min(short_trough, c)

                # 正金字塔加仓评估
                risk_status = risk.get_risk_status(cash)
                if allow_pyramid and short_pos == 1 and risk_status['can_pyramid']:
                    can_pyramid, pyramid_reason = sizing.check_pyramid_allowed(
                        base_entry=600.0,
                        curr_price=c,
                        atr=atr,
                        direction='SHORT',
                        base_locked_profit=600.0 - short_trough - 1.5 * atr
                    )
                    is_regime_ok, regime_reason = regime.check_regime(i, 'SHORT')
                    if can_pyramid and is_regime_ok and (c < prev['收盘价']):
                        short_pos = 2
                        addon_entry = c
                        fee_add = roll.commission_per_lot + roll.slippage_per_lot
                        cash -= fee_add
                        current_cycle['addon_added'] = True
                        current_cycle['addon_price'] = round(c, 1)
                        current_cycle['total_fees'] += fee_add

                # 智能跟踪止盈评估
                exit_eval = smart_exit.evaluate_short_exit(
                    curr_row=row,
                    prev_row=prev,
                    base_entry=600.0,
                    trigger_price=trig_px,
                    addon_entry=addon_entry,
                    short_trough=short_trough,
                    atr=atr
                )

                # 加仓单保本平仓
                if exit_eval['exit_addon'] and short_pos == 2:
                    pnl_addon = (addon_entry - c) * 1000.0
                    fee_addon = roll.commission_per_lot + roll.slippage_per_lot
                    cash += pnl_addon - fee_addon
                    short_pos = 1
                    addon_entry = None
                    current_cycle['total_fees'] += fee_addon
                    current_cycle['cut_pnl'] += pnl_addon

                # 底仓平仓离场
                if exit_eval['exit_base']:
                    exit_px = exit_eval['exit_price']
                    win_pnl = (600.0 - exit_px) * 1000.0
                    if short_pos == 2:
                        win_pnl += (addon_entry - exit_px) * 1000.0
                    
                    fee = (roll.commission_per_lot + roll.slippage_per_lot) * short_pos
                    cash += win_pnl - fee
                    short_pos = 0
                    addon_entry = None

                    current_cycle['win_leg'] = '空头'
                    current_cycle['win_date'] = d.strftime('%Y-%m-%d')
                    current_cycle['win_price'] = round(exit_px, 1)
                    current_cycle['win_pnl'] = round(win_pnl, 1)
                    current_cycle['exit_reason'] = exit_eval['reason']
                    current_cycle['total_fees'] += fee + current_cycle['roll_fees']
                    current_cycle['net_pnl'] = round(current_cycle['cut_pnl'] + win_pnl - current_cycle['total_fees'], 1)
                    current_cycle['equity_after'] = round(cash, 1)
                    
                    risk.update_equity(cash, current_cycle['net_pnl'])
                    cycles.append(current_cycle)
                    current_cycle = None
                    last_exit_idx = i

    res_df = pd.DataFrame(cycles)
    
    # 计算统计指标
    eq_curve = [initial_capital] + (res_df['equity_after'].tolist() if len(res_df) > 0 else [])
    peak = initial_capital
    mdd = 0.0
    for val in eq_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > mdd:
            mdd = dd
            
    stats = {
        'initial_capital': initial_capital,
        'final_equity': cash,
        'net_profit': cash - initial_capital,
        'total_return_pct': (cash - initial_capital) / initial_capital * 100,
        'total_cycles': len(res_df),
        'win_rate_pct': (res_df['net_pnl'] > 0).mean() * 100 if len(res_df) > 0 else 0,
        'max_drawdown_pct': mdd * 100,
        'min_equity': min(eq_curve),
        'calmar_ratio': ((cash - initial_capital) / initial_capital * 100) / (mdd * 100) if mdd > 0 else 0
    }
    return res_df, cash, stats
