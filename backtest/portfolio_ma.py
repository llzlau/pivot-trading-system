"""
portfolio_ma.py
多品种趋势跟踪组合回测
BASE_DIR = Path(__file__).resolve().parent.parent
策略：双均线信号 + ATR波动率归一化定仓
品种：RB / CU / AU / M / TA / I
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════
RAW_DIR    = Path(r"../data/raw")
RESULT_DIR = Path(r"..\backtest\results")
RESULT_DIR.mkdir(parents=True, exist_ok=True)

INSTRUMENTS = {
    "RB": {"name": "螺纹钢", "multiplier": 10,   "commission": 10},     # 元/手(单边)
    "CU": {"name": "铜",    "multiplier": 5,    "commission": 5},
    "AU": {"name": "黄金",  "multiplier": 1000, "commission": 10},
    "M":  {"name": "豆粕",  "multiplier": 10,   "commission": 1.5},
    "TA": {"name": "PTA",   "multiplier": 5,    "commission": 3},
    "I":  {"name": "铁矿石","multiplier": 100,  "commission": 3},
}

FAST_MA    = 20          # 快线周期
SLOW_MA    = 60          # 慢线周期
ATR_PERIOD = 20          # ATR周期
INIT_CASH  = 500_000     # 初始资金（元）
RISK_PCT   = 0.01        # 每品种每笔风险：账户净值的1%
SLIPPAGE   = 2           # 滑点（元/手，单边估算）


# ══════════════════════════════════════════════════════════
# 核心函数
# ══════════════════════════════════════════════════════════

def load_instrument(code: str) -> pd.DataFrame | None:
    path = RAW_DIR / f"{code}_daily.csv"
    if not path.exists():
        print(f"  [跳过] {code} 数据文件不存在: {path}")
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.set_index("date").sort_index()
    return df


def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(FAST_MA).mean()
    df["ma_slow"] = df["close"].rolling(SLOW_MA).mean()

    # ATR
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    # 信号: 1=多, -1=空, 0=空仓
    df["signal"] = 0
    df.loc[df["ma_fast"] > df["ma_slow"], "signal"] =  1
    df.loc[df["ma_fast"] < df["ma_slow"], "signal"] = -1

    # 信号变化（开平仓点）
    df["signal_change"] = df["signal"].diff().fillna(0)

    return df.dropna(subset=["ma_slow", "atr"])


def calc_pnl(df: pd.DataFrame, cfg: dict, equity_series: pd.Series) -> pd.DataFrame:
    """
    逐日计算品种 PnL
    仓位大小 = risk_cash / (ATR × multiplier)，每日用前一日账户净值计算
    """
    mul  = cfg["multiplier"]
    comm = cfg["commission"] + SLIPPAGE

    results = []
    position = 0        # 当前持仓（手数，正=多，负=空）
    entry_price = 0.0

    for i, (dt, row) in enumerate(df.iterrows()):
        # 当前账户净值（用前日净值计算仓位）
        eq = equity_series.get(dt, INIT_CASH)

        new_signal = int(row["signal"])

        # 判断是否需要换仓
        if new_signal != np.sign(position) and row["atr"] > 0:
            # 平旧仓
            if position != 0:
                close_pnl = position * (row["close"] - entry_price) * mul
                close_pnl -= abs(position) * comm
            else:
                close_pnl = 0.0

            # 开新仓
            if new_signal != 0:
                risk_cash = eq * RISK_PCT
                size = max(1, int(risk_cash / (row["atr"] * mul)))
                position    = new_signal * size
                entry_price = row["close"]
                open_cost   = abs(position) * comm
            else:
                position   = 0
                entry_path = 0.0
                open_cost  = 0.0

            day_pnl = close_pnl - open_cost
        else:
            # 持仓未变：计算浮动盈亏
            if position != 0:
                day_pnl = position * (row["close"] - df["close"].iloc[max(0, i-1)]) * mul
            else:
                day_pnl = 0.0

        results.append({"date": dt, f"{cfg['name']}_pnl": day_pnl, f"{cfg['name']}_pos": position})

    return pd.DataFrame(results).set_index("date")


def run_portfolio():
    print(f"\n{'='*55}")
    print(f"  多品种趋势跟踪组合回测")
    print(f"  快线:{FAST_MA}日  慢线:{SLOW_MA}日  ATR:{ATR_PERIOD}日")
    print(f"  品种: {list(INSTRUMENTS.keys())}")
    print(f"  初始资金: {INIT_CASH:,.0f} 元")
    print(f"{'='*55}\n")

    # 加载所有品种数据并添加信号
    all_data = {}
    for code, cfg in INSTRUMENTS.items():
        df = load_instrument(code)
        if df is not None:
            df = add_signals(df)
            all_data[code] = (df, cfg)
            print(f"  OK {cfg['name']}({code}): {len(df)} rows")

    if not all_data:
        print("没有可用数据，退出。")
        return

    # 建立共同交易日历
    all_dates = sorted(set.union(*[set(df.index) for df, _ in all_data.values()]))
    all_dates = pd.DatetimeIndex(all_dates)

    # 组合净值逐日累计
    portfolio_equity = pd.Series(INIT_CASH, index=all_dates)
    pnl_df = pd.DataFrame(index=all_dates)

    for code, (df, cfg) in all_data.items():
        name = cfg["name"]
        df_aligned = df.reindex(all_dates).ffill()

        eq_series = portfolio_equity.copy()
        inst_pnl = calc_pnl(df_aligned, cfg, eq_series)

        col = f"{name}_pnl"
        if col in inst_pnl.columns:
            pnl_df[col] = inst_pnl[col].reindex(all_dates).fillna(0)

    # 组合每日总 PnL → 净值曲线
    pnl_df["total_pnl"] = pnl_df.sum(axis=1)
    pnl_df["equity"]    = INIT_CASH + pnl_df["total_pnl"].cumsum()

    equity = pnl_df["equity"]

    # ── 绩效指标 ──────────────────────────────────────────
    total_ret   = (equity.iloc[-1] - INIT_CASH) / INIT_CASH * 100
    n_years     = (all_dates[-1] - all_dates[0]).days / 365.25
    ann_ret     = ((equity.iloc[-1] / INIT_CASH) ** (1 / n_years) - 1) * 100

    daily_ret   = pnl_df["total_pnl"] / INIT_CASH
    sharpe      = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0

    roll_max    = equity.cummax()
    drawdown    = (equity - roll_max) / roll_max * 100
    max_dd      = drawdown.min()

    calmar      = ann_ret / abs(max_dd) if max_dd != 0 else 0

    print(f"\n{'='*55}")
    print(f"  {'指标':<15} {'数值':>15}")
    print(f"  {'-'*35}")
    print(f"  {'初始资金':<15} {INIT_CASH:>14,.0f} 元")
    print(f"  {'最终净值':<15} {equity.iloc[-1]:>14,.2f} 元")
    print(f"  {'总收益率':<15} {total_ret:>14.2f} %")
    print(f"  {'年化收益率':<13} {ann_ret:>14.2f} %")
    print(f"  {'夏普比率':<15} {sharpe:>14.3f}")
    print(f"  {'最大回撤':<15} {max_dd:>14.2f} %")
    print(f"  {'卡玛比率':<15} {calmar:>14.3f}")
    print(f"  {'回测年数':<15} {n_years:>14.1f} 年")
    print(f"{'='*55}\n")

    # ── 各品种贡献 ────────────────────────────────────────
    print(f"  各品种累计贡献:")
    for col in pnl_df.columns:
        if col.endswith("_pnl") and col != "total_pnl":
            name = col.replace("_pnl", "")
            contrib = pnl_df[col].sum()
            print(f"    {name:<8}: {contrib:>+10,.0f} 元")

    # ── 保存净值数据 ──────────────────────────────────────
    out_csv = RESULT_DIR / "portfolio_equity.csv"
    pnl_df.to_csv(out_csv, encoding="utf-8-sig")
    print(f"\n  净值数据已保存: {out_csv}")

    return pnl_df, equity


if __name__ == "__main__":
    run_portfolio()
