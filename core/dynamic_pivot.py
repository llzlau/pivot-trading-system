"""
Dynamic Pivot Engine (动态中枢与自适应突破引擎)
==============================================
核心功能：
1. 废除死板的“固定60点”，以当前波动的真实度量 1.8~2.0 * ATR 动态确定突破阈值；
2. 在低波动时期自适应收窄阈值，防止等到行情衰竭才追入；
3. 在高波动时期自适应放宽阈值，避免被日常地缘杂波频繁打穿对锁。
"""

import pandas as pd


class DynamicPivotEngine:
    def __init__(self, anchor: float, atr_multiplier: float = 1.8, min_buffer: float = 25.0, max_buffer: float = 60.0):
        self.anchor = anchor
        self.atr_multiplier = atr_multiplier
        self.min_buffer = min_buffer
        self.max_buffer = max_buffer

    def get_dynamic_threshold(self, atr: float) -> float:
        """根据当前 ATR 动态计算突破阈值"""
        raw_buf = self.atr_multiplier * atr
        return max(self.min_buffer, min(raw_buf, self.max_buffer))

    def check_anchor_entry(self, prev_close: float, curr_close: float, curr_low: float, curr_high: float) -> bool:
        """判断价格是否处于锚点附近或穿越锚点，适合建立中枢对锁"""
        crossed = (prev_close < self.anchor <= curr_close) or (prev_close > self.anchor >= curr_close)
        touched = curr_low <= self.anchor <= curr_high
        near = abs(curr_close - self.anchor) <= 10.0
        return crossed or (touched and near)

    def check_breakout(self, entry_price: float, curr_close: float, atr: float, direction: str) -> tuple[bool, float]:
        """
        判断是否触发单边有效突破
        返回: (is_breakout, trigger_threshold)
        """
        buf = self.get_dynamic_threshold(atr)
        if direction == 'LONG':
            if (curr_close - entry_price) >= buf:
                return True, buf
        elif direction == 'SHORT':
            if (entry_price - curr_close) >= buf:
                return True, buf
        return False, buf
