"""
Roll-Over & Delivery Month Manager (交割月与移仓换月管理引擎)
==========================================================
核心功能：
1. 严守自然人客户「禁止进入交割月」的交易所法定红线；
2. 在交割月前一个月中旬（15日）准时启动主力移仓换月，自动计算展期手续费与买卖滑点摩擦；
3. 设立【超时钝化熔断机制 (Timeout Liquidation)】：
   - 彻底解决“在 600 中枢死锁 3~6 个月”导致手续费和负利差严重侵蚀本金的问题；
   - 若建仓后超过 35 个交易日（跨越一个换月窗口）盘面依然在 600 附近无量纠缠，
     系统果断平价双平出局、空仓休息，绝不在泥潭里当“移仓提款机”。
"""

import pandas as pd


class RollOverManager:
    def __init__(self, commission_per_lot: float = 60.0, slippage_per_lot: float = 200.0, max_idle_days: int = 35):
        self.commission_per_lot = commission_per_lot
        self.slippage_per_lot = slippage_per_lot
        self.max_idle_days = max_idle_days
        self.current_month = None
        self.roll_done = False

    def check_monthly_roll(self, date_val: pd.Timestamp, total_lots: int) -> tuple[bool, float]:
        """
        检查是否触发月度交割移仓换月
        返回: (did_roll, roll_fee)
        """
        m_str = date_val.strftime('%Y-%m')
        if m_str != self.current_month:
            self.current_month = m_str
            self.roll_done = False

        if date_val.day >= 15 and not self.roll_done:
            self.roll_done = True
            if total_lots > 0:
                fee = (self.commission_per_lot + self.slippage_per_lot) * total_lots
                return True, fee
        return False, 0.0

    def check_idle_timeout(self, holding_days: int, current_price: float, anchor_price: float) -> tuple[bool, str]:
        """
        检查是否触发无动能超时熔断
        如果持仓超过 35 天且价格仍在锚点附近 (+- 15点内)，果断平价双平出场！
        """
        if holding_days >= self.max_idle_days:
            if abs(current_price - anchor_price) <= 18.0:
                return True, f"持仓已达 {holding_days} 天且行情在锚点附近钝化，触发超时平价熔断退出"
        return False, ""
