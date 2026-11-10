from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
df = pd.read_csv(str(BASE_DIR / 'data' / 'raw' / 'SC0_latest.csv'))
df.columns = [c.strip() for c in df.columns]
df['日期'] = pd.to_datetime(df['日期'])
df = df.sort_values('日期').reset_index(drop=True)

prev_close = df['收盘价'].shift(1)
tr = pd.concat([df['最高价'] - df['最低价'], (df['最高价'] - prev_close).abs(), (df['最低价'] - prev_close).abs()], axis=1).max(axis=1)
df['atr'] = tr.rolling(20).mean()

df['ma20'] = df['收盘价'].rolling(20).mean()
df['ma60'] = df['收盘价'].rolling(60).mean()

plus_dm = df['最高价'].diff()
minus_dm = -df['最低价'].diff()
plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
tr14 = tr.rolling(14).mean()
plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / tr14)
minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / tr14)
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
df['adx'] = dx.rolling(14).mean()

check_dates = [
    ('2022-03-02', '真大牛市 (大赚)'),
    ('2023-08-15', '假突破陷阱 (亏5万)'),
    ('2023-12-07', '假摔底抽 (亏4.3万)'),
    ('2024-04-03', '假上冲 (亏4万)'),
    ('2024-08-22', '假摔底抽 (亏5.3万)'),
    ('2026-09-02', '真大牛市 (大赚)'),
]

print(f"{'日期':<12} | {'性质':<18} | {'收盘':>6} | {'MA20':>6} | {'MA60':>6} | {'ADX':>5} | {'ATR':>5} | {'趋势排列'}")
print('-' * 80)
for cd, desc in check_dates:
    row = df[df['日期'] == cd]
    if len(row) > 0:
        r = row.iloc[0]
        trend = "多头排列(MA20>MA60)" if r['ma20'] > r['ma60'] else "空头排列(MA20<MA60)"
        print(f"{cd:<12} | {desc:<18} | {r['收盘价']:>6.1f} | {r['ma20']:>6.1f} | {r['ma60']:>6.1f} | {r['adx']:>5.1f} | {r['atr']:>5.1f} | {trend}")
