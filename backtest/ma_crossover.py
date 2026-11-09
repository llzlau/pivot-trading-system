"""
ma_crossover.py
双均线趋势跟踪回测策略 —— 螺纹钢(RB)日线
BASE_DIR = Path(__file__).resolve().parent.parent
策略逻辑：
  - 快线(20日均线) 上穿 慢线(60日均线) → 买入做多
  - 快线(20日均线) 下穿 慢线(60日均线) → 平多做空
  - 波动率归一化定仓（ATR仓位管理）
"""

import backtrader as bt
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings("ignore")

# ── 路径配置 ──────────────────────────────────────────────
DATA_FILE   = Path(r"../data/raw\RB_daily.csv")
RESULT_DIR  = Path(r"..\backtest\results")
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# ── 策略参数 ──────────────────────────────────────────────
FAST_MA     = 20          # 快线周期
SLOW_MA     = 60          # 慢线周期
ATR_PERIOD  = 20          # ATR周期（波动率定仓用）
INIT_CASH   = 500_000     # 初始资金（元）
RISK_PCT    = 0.01        # 每笔最大风险：账户净值的1%
CONTRACT_MUL = 10         # 螺纹钢合约乘数（10吨/手）
COMMISSION  = 0.0001      # 手续费率（单边万分之一）


# ══════════════════════════════════════════════════════════
class MACrossStrategy(bt.Strategy):
    params = dict(
        fast=FAST_MA,
        slow=SLOW_MA,
        atr_period=ATR_PERIOD,
        risk_pct=RISK_PCT,
    )

    def __init__(self):
        self.ma_fast = bt.ind.SMA(period=self.p.fast)
        self.ma_slow = bt.ind.SMA(period=self.p.slow)
        self.atr     = bt.ind.ATR(period=self.p.atr_period)
        self.cross   = bt.ind.CrossOver(self.ma_fast, self.ma_slow)

        # 记录每日净值
        self.portfolio_values = []

    def next(self):
        self.portfolio_values.append(self.broker.getvalue())

        # ATR为0时跳过
        if self.atr[0] == 0:
            return

        # 波动率归一化定仓：每手承担的点值风险 = ATR * 合约乘数
        risk_per_contract = self.atr[0] * CONTRACT_MUL
        max_risk_cash     = self.broker.getvalue() * self.p.risk_pct
        size              = max(1, int(max_risk_cash / risk_per_contract))

        if self.cross[0] > 0:          # 金叉 → 做多
            if self.position.size < 0:
                self.close()
            if not self.position:
                self.buy(size=size)

        elif self.cross[0] < 0:        # 死叉 → 做空
            if self.position.size > 0:
                self.close()
            if not self.position:
                self.sell(size=size)

    def stop(self):
        self.portfolio_values.append(self.broker.getvalue())


# ══════════════════════════════════════════════════════════
def run_backtest():
    # 读取数据
    df = pd.read_csv(DATA_FILE, parse_dates=["date"], index_col="date")
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index.name = "datetime"

    feed = bt.feeds.PandasData(dataname=df)

    cerebro = bt.Cerebro()
    cerebro.adddata(feed)
    cerebro.addstrategy(MACrossStrategy)
    cerebro.broker.setcash(INIT_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.broker.set_slippage_perc(0.0001)   # 万分之一滑点
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns,     _name="returns", tann=252)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    print(f"\n{'='*55}")
    print(f"  螺纹钢(RB) 双均线策略回测")
    print(f"  快线:{FAST_MA}日  慢线:{SLOW_MA}日  ATR:{ATR_PERIOD}日")
    print(f"  初始资金: {INIT_CASH:,.0f} 元")
    print(f"{'='*55}\n")

    results = cerebro.run()
    strat   = results[0]

    final_value  = cerebro.broker.getvalue()
    total_return = (final_value - INIT_CASH) / INIT_CASH * 100
    sharpe       = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0) or 0
    max_dd       = strat.analyzers.drawdown.get_analysis()["max"]["drawdown"]
    ann_return   = strat.analyzers.returns.get_analysis().get("rnorm100", 0) or 0
    trade_info   = strat.analyzers.trades.get_analysis()
    total_trades = trade_info.get("total", {}).get("closed", 0)
    won_trades   = trade_info.get("won",   {}).get("total", 0)
    win_rate     = won_trades / total_trades * 100 if total_trades else 0

    print(f"  最终净值:    {final_value:>12,.2f} 元")
    print(f"  总收益率:    {total_return:>11.2f} %")
    print(f"  年化收益率:  {ann_return:>11.2f} %")
    print(f"  夏普比率:    {sharpe:>11.3f}")
    print(f"  最大回撤:    {max_dd:>11.2f} %")
    print(f"  总交易次数:  {total_trades:>11} 次")
    print(f"  胜率:        {win_rate:>11.2f} %")
    print(f"{'='*55}\n")

    # ── 画净值曲线图 ──────────────────────────────────────
    pv = strat.portfolio_values
    dates = df.index[-len(pv):]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        subplot_titles=["策略净值曲线", "螺纹钢收盘价"],
        vertical_spacing=0.05,
    )

    fig.add_trace(go.Scatter(
        x=dates, y=pv,
        name="净值", line=dict(color="#00d4ff", width=1.5)
    ), row=1, col=1)

    fig.add_hline(y=INIT_CASH, line_dash="dash", line_color="gray", row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["close"],
        name="收盘价", line=dict(color="#f0a500", width=1)
    ), row=2, col=1)

    fig.update_layout(
        title=f"螺纹钢(RB) 双均线策略 ({FAST_MA}/{SLOW_MA}日)  |  年化:{ann_return:.1f}%  夏普:{sharpe:.2f}  最大回撤:{max_dd:.1f}%",
        template="plotly_dark",
        height=700,
        showlegend=True,
    )

    out_html = RESULT_DIR / "ma_crossover_result.html"
    fig.write_html(str(out_html))
    print(f"  图表已保存：{out_html}")
    print("  用浏览器打开即可查看交互式净值曲线\n")


if __name__ == "__main__":
    run_backtest()
