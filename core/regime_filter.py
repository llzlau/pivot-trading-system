"""
Market Regime Filter (市场状态分类器)
=======================================
核心功能：
1. 识别当前大宗商品是处于「强单边趋势」、「高波震荡」还是「死水纠缠」；
2. 过滤掉 ADX 低于 20、均线打结粘合的“垃圾时间”；
3. 避免在无趋势阶段盲目对锁与频繁被假突破绞杀。
"""

import numpy as np
import pandas as pd


class MarketRegimeFilter:
    def __init__(self, df: pd.DataFrame, adx_threshold: float = 20.0):
        self.df = df.copy()
        self.adx_threshold = adx_threshold
        self._calculate_indicators()

    def _calculate_indicators(self):
        c = self.df['收盘价']
        h = self.df['最高价']
        l = self.df['最低价']
        prev_c = c.shift(1)

        # 1. 真实波幅 ATR (20日)
        tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        self.df['atr'] = tr.rolling(20).mean().bfill()

        # 2. 均线系统 (MA20, MA60, MA120)
        self.df['ma20'] = c.rolling(20).mean()
        self.df['ma60'] = c.rolling(60).mean()
        self.df['ma120'] = c.rolling(120).mean()

        # 3. 趋势强度指标 ADX (14)
        plus_dm = h.diff()
        minus_dm = -l.diff()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
        tr14 = tr.rolling(14).mean().replace(0, np.nan)
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / tr14)
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / tr14)
        denom = (plus_di + minus_di).replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / denom
        self.df['adx'] = dx.rolling(14).mean().bfill()

        # 4. 乖离率 (Bias = |Close - MA20| / ATR)
        self.df['bias_atr'] = ((c - self.df['ma20']).abs() / self.df['atr']).fillna(0)

        # 5. 布林带宽度 (Bandwidth)
        std20 = c.rolling(20).std()
        self.df['bb_upper'] = self.df['ma20'] + 2.0 * std20
        self.df['bb_lower'] = self.df['ma20'] - 2.0 * std20
        self.df['bb_width'] = ((self.df['bb_upper'] - self.df['bb_lower']) / self.df['ma20']).fillna(0)

    def get_row_by_index(self, idx: int) -> pd.Series:
        return self.df.iloc[idx]

    def check_regime(self, idx: int, direction: str = 'LONG') -> tuple[bool, str]:
        """
        检查当前状态是否具备健康趋势条件:
        返回 (is_allowed, reason)
        """
        row = self.df.iloc[idx]
        c = row['收盘价']
        ma20 = row['ma20']
        ma60 = row['ma60']
        adx = row['adx']
        bias = row['bias_atr']

        # 1. 过滤垃圾震荡市 (ADX 过低)
        if adx < self.adx_threshold:
            return False, f"ADX趋势动能过弱 ({adx:.1f} < {self.adx_threshold})"

        # 2. 检查多空排列共振
        if direction == 'LONG':
            if pd.notna(ma60) and c < ma60:
                return False, f"价格处于中期均线MA60下方 ({c:.1f} < {ma60:.1f})，逆势风险高"
        elif direction == 'SHORT':
            if pd.notna(ma60) and c > ma60:
                return False, f"价格处于中期均线MA60上方 ({c:.1f} > {ma60:.1f})，逆势做空风险高"

        # 3. 检查乖离率透支 (防脉冲追高)
        if bias > 2.5:
            return False, f"乖离率过大透支均线 (Bias={bias:.2f} ATR > 2.5)，谨防衰竭回踩"

        return True, "市场状态健康，支持顺势入场"
