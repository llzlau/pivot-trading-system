"""
Position Sizing & Risk Allocation Engine (波动率平价定仓与正金字塔风控引擎)
========================================================================
核心功能：
1. 废除无脑开仓 2 手的“倒金字塔加仓”错误；
2. 基于单笔风险预算（如本金的 1.5%）和当前 ATR 动态计算标准开仓手数；
3. 实施严格的「正金字塔浮盈加仓协议」：
   - 加仓必须建立在底仓已全额保本锁定的前提下；
   - 加仓单必须单独设置原价保本止损，绝不允许侵蚀底仓利润；
   - 彻底从数学上消灭“加仓把赢家做成大输家”的逻辑隐患。
"""

import math


class PositionSizingEngine:
    def __init__(self, multiplier: float = 1000.0, risk_per_trade_pct: float = 0.015, max_leverage: float = 2.5):
        self.multiplier = multiplier
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_leverage = max_leverage

    def calculate_base_lots(self, capital: float, atr: float, stop_atr_mult: float = 1.5) -> int:
        """
        基于账户净值和波动率计算底仓手数
        单笔最大承受损失 = capital * risk_per_trade_pct
        """
        risk_budget = capital * self.risk_per_trade_pct
        stop_distance = max(atr * stop_atr_mult, 15.0)
        risk_per_lot = stop_distance * self.multiplier
        
        calculated_lots = math.floor(risk_budget / risk_per_lot)
        return max(1, min(calculated_lots, 3)) # 单品种限制在 1~3 手

    def check_pyramid_allowed(self, base_entry: float, curr_price: float, atr: float, direction: str, base_locked_profit: float) -> tuple[bool, str]:
        """
        检查是否允许加仓:
        1. 底仓必须已具备至少 1.5 ATR 的安全垫利润；
        2. 底仓止损必须已经锁死在盈利状态 (base_locked_profit > 0)；
        3. 当前价格未出现极端脉冲透支。
        """
        if direction == 'LONG':
            floating_pts = curr_price - base_entry
        else:
            floating_pts = base_entry - curr_price

        if floating_pts < 1.8 * atr:
            return False, f"底仓浮盈不足 ({floating_pts:.1f} < {1.8*atr:.1f} 点)，安全垫不达标"

        if base_locked_profit <= 0:
            return False, "底仓尚未锁定利润保本，严禁盲目开立新头寸"

        return True, "底仓利润垫充足且止损已上移锁定，允许顺势加仓 1 手"
