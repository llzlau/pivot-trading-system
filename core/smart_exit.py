"""
Smart Exit Engine (智能三级动态跟踪锁盈与离场引擎)
=================================================
核心功能：
1. 彻底解决假突破回撤深达 25 点导致单笔亏损 5 万元的灾难；
2. 一旦解锁单边，强制将整体试错风险压缩在极狭窄的保本带内；
3. 加仓单与底仓独立管理：加仓单回踩入场价直接平手出局，绝不拖累账户；
4. 顺势奔跑时采用「阶梯锁盈 + 抛物线破前低」双保险收割大单边。
"""

import pandas as pd


class SmartExitEngine:
    def __init__(self, multiplier: float = 1000.0):
        self.multiplier = multiplier

    def evaluate_long_exit(
        self,
        curr_row: pd.Series,
        prev_row: pd.Series,
        base_entry: float,
        trigger_price: float,
        addon_entry: float | None,
        long_peak: float,
        atr: float
    ) -> dict:
        """
        多头出场与止盈综合评估
        返回字典:
        {
            'exit_addon': bool,
            'exit_base': bool,
            'exit_price': float,
            'reason': str,
            'locked_stop': float
        }
        """
        c = curr_row['收盘价']
        prev_l = prev_row['最低价']
        peak_floating = long_peak - base_entry

        # 1. 加仓单独立保本防暴线：一旦价格跌破加仓入场价，加仓单立即保本出场！
        exit_addon = False
        if addon_entry is not None:
            if c <= addon_entry - 1.0:
                exit_addon = True

        # 2. 底仓止损线动态推移
        if peak_floating >= 5.0 * atr:
            # 超级单边大牛市：锁定75%峰值利润，并以跌破前一日最低价为最终止盈线
            locked_stop = max(base_entry + 0.75 * peak_floating, prev_l)
            reason = "抛物线破前低/锁定75%峰值利润止盈"
        elif peak_floating >= 3.0 * atr:
            # 中级别单边趋势：锁定60%峰值利润
            locked_stop = max(base_entry + 0.60 * peak_floating, prev_l)
            reason = "阶梯分级锁定60%浮盈止盈"
        elif peak_floating >= 1.5 * atr:
            # 已启动波段：底仓死死锁住保本线 (base_entry + 10点)，绝不让赢家变输家
            locked_stop = base_entry + 10.0
            reason = "底仓全额保本锁触发"
        else:
            # 刚突破后的试错阶段：允许回踩的底线钉在 (trigger_price - 5.0 点)
            # 绝不允许像过去那样一路跌穿 645 导致大亏！
            locked_stop = max(base_entry, trigger_price - 5.0)
            reason = "假突破窄幅保本止损"

        exit_base = c <= locked_stop
        exit_price = min(c, locked_stop) if exit_base else c

        return {
            'exit_addon': exit_addon,
            'exit_base': exit_base,
            'exit_price': exit_price,
            'reason': reason,
            'locked_stop': locked_stop
        }

    def evaluate_short_exit(
        self,
        curr_row: pd.Series,
        prev_row: pd.Series,
        base_entry: float,
        trigger_price: float,
        addon_entry: float | None,
        short_trough: float,
        atr: float
    ) -> dict:
        """空头出场与止盈综合评估"""
        c = curr_row['收盘价']
        prev_h = prev_row['最高价']
        trough_floating = base_entry - short_trough

        exit_addon = False
        if addon_entry is not None:
            if c >= addon_entry + 1.0:
                exit_addon = True

        if trough_floating >= 5.0 * atr:
            locked_stop = min(base_entry - 0.75 * trough_floating, prev_h)
            reason = "抛物线破前高/锁定75%峰值利润止盈"
        elif trough_floating >= 3.0 * atr:
            locked_stop = min(base_entry - 0.60 * trough_floating, prev_h)
            reason = "阶梯分级锁定60%浮盈止盈"
        elif trough_floating >= 1.5 * atr:
            locked_stop = base_entry - 10.0
            reason = "底仓全额保本锁触发"
        else:
            locked_stop = min(base_entry, trigger_price + 5.0)
            reason = "假摔窄幅保本止损"

        exit_base = c >= locked_stop
        exit_price = max(c, locked_stop) if exit_base else c

        return {
            'exit_addon': exit_addon,
            'exit_base': exit_base,
            'exit_price': exit_price,
            'reason': reason,
            'locked_stop': locked_stop
        }
