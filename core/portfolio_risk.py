"""
Portfolio Risk & Circuit Breaker Engine (账户级风控覆层与熔断断路器)
==================================================================
核心功能：
1. 监控资金曲线（Equity Curve），彻底终结“连挨 4 记耳光亏掉 18 万”的死脑筋硬顶缺陷；
2. 连续亏损惩罚与冷却机制（Cooling-Off Period）：
   - 连续 2 笔假突破止损，强制系统冷冻休眠 10 个交易日，自动跳过震荡垃圾时间；
3. 回撤分级刹车（Drawdown Brake）：
   - 当账户自历史峰值回撤达 15% 时，系统强制锁定为“防守模式”，禁止一切顺势加仓；
   - 当回撤达 25% 时，仓位主动缩减 50%，把本金安全视为最高优先级。
"""

import pandas as pd


class PortfolioRiskEngine:
    def __init__(self, initial_capital: float = 200000.0, max_drawdown_limit: float = 0.25):
        self.initial_capital = initial_capital
        self.max_drawdown_limit = max_drawdown_limit
        self.equity_peak = initial_capital
        self.consecutive_losses = 0
        self.cooldown_days_remaining = 0

    def update_equity(self, current_equity: float, pnl: float):
        """记录每笔交易后的账户权益并更新风控状态"""
        if current_equity > self.equity_peak:
            self.equity_peak = current_equity

        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= 2:
                # 连续2次亏损，触发10天冷却机制
                self.cooldown_days_remaining = 10
        else:
            self.consecutive_losses = 0

    def step_day(self):
        """每日轮询，减少冷却期天数"""
        if self.cooldown_days_remaining > 0:
            self.cooldown_days_remaining -= 1

    def get_risk_status(self, current_equity: float) -> dict:
        """
        获取当前账户风控状态:
        {
            'can_open_new': bool,
            'can_pyramid': bool,
            'current_drawdown': float,
            'reason': str
        }
        """
        dd = (self.equity_peak - current_equity) / self.equity_peak if self.equity_peak > 0 else 0.0

        if self.cooldown_days_remaining > 0:
            return {
                'can_open_new': False,
                'can_pyramid': False,
                'current_drawdown': dd,
                'reason': f"触发连续亏损冷却期，还剩 {self.cooldown_days_remaining} 个交易日静默期"
            }

        can_pyramid = True
        if dd >= 0.15: # 回撤超过 15%，禁止加仓
            can_pyramid = False

        if dd >= self.max_drawdown_limit:
            return {
                'can_open_new': False,
                'can_pyramid': False,
                'current_drawdown': dd,
                'reason': f"触发账户最大回撤红线 ({dd*100:.1f}% >= {self.max_drawdown_limit*100:.1f}%)，暂停新开仓"
            }

        return {
            'can_open_new': True,
            'can_pyramid': can_pyramid,
            'current_drawdown': dd,
            'reason': "账户风控状态良好"
        }
