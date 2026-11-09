"""
导出回测数据为 JSON，供前端图表使用
"""
BASE_DIR = Path(__file__).resolve().parent.parent
import pandas as pd
import numpy as np
import json
from pathlib import Path
import backtrader as bt
import warnings
warnings.filterwarnings("ignore")

DATA_FILE  = Path(r"../data/raw\RB_daily.csv")
OUT_FILE   = Path(r"../data/processed\chart_data.json")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

FAST_MA, SLOW_MA, ATR_PERIOD = 20, 60, 20
INIT_CASH = 500_000
RISK_PCT  = 0.01
CONTRACT_MUL = 10
COMMISSION = 0.0001

class MACrossStrategy(bt.Strategy):
    params = dict(fast=FAST_MA, slow=SLOW_MA, atr_period=ATR_PERIOD, risk_pct=RISK_PCT)
    def __init__(self):
        self.ma_fast = bt.ind.SMA(period=self.p.fast)
        self.ma_slow = bt.ind.SMA(period=self.p.slow)
        self.atr     = bt.ind.ATR(period=self.p.atr_period)
        self.cross   = bt.ind.CrossOver(self.ma_fast, self.ma_slow)
        self.records = []
        self.trades_log = []

    def next(self):
        self.records.append({
            "date":     self.data.datetime.date(0).isoformat(),
            "close":    round(float(self.data.close[0]), 2),
            "ma_fast":  round(float(self.ma_fast[0]), 2),
            "ma_slow":  round(float(self.ma_slow[0]), 2),
            "equity":   round(self.broker.getvalue(), 2),
        })
        if self.atr[0] == 0: return
        risk_per_contract = self.atr[0] * CONTRACT_MUL
        max_risk_cash     = self.broker.getvalue() * self.p.risk_pct
        size = max(1, int(max_risk_cash / risk_per_contract))
        if self.cross[0] > 0:
            if self.position.size < 0: self.close()
            if not self.position:
                self.buy(size=size)
                self.trades_log.append({"date": self.data.datetime.date(0).isoformat(), "type": "buy", "price": float(self.data.close[0])})
        elif self.cross[0] < 0:
            if self.position.size > 0: self.close()
            if not self.position:
                self.sell(size=size)
                self.trades_log.append({"date": self.data.datetime.date(0).isoformat(), "type": "sell", "price": float(self.data.close[0])})

df = pd.read_csv(DATA_FILE, parse_dates=["date"], index_col="date")
df = df[["open","high","low","close","volume"]].dropna()
df.index.name = "datetime"
feed = bt.feeds.PandasData(dataname=df)
cerebro = bt.Cerebro()
cerebro.adddata(feed)
cerebro.addstrategy(MACrossStrategy)
cerebro.broker.setcash(INIT_CASH)
cerebro.broker.setcommission(commission=COMMISSION)
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02, annualize=True)
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
cerebro.addanalyzer(bt.analyzers.Returns, _name="ret", tann=252)
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
results = cerebro.run()
strat = results[0]

final_value  = cerebro.broker.getvalue()
trade_info   = strat.analyzers.trades.get_analysis()
total_trades = trade_info.get("total", {}).get("closed", 0)
won_trades   = trade_info.get("won", {}).get("total", 0)

out = {
    "summary": {
        "init_cash":    INIT_CASH,
        "final_value":  round(final_value, 2),
        "total_return": round((final_value - INIT_CASH) / INIT_CASH * 100, 2),
        "ann_return":   round(strat.analyzers.ret.get_analysis().get("rnorm100", 0) or 0, 2),
        "sharpe":       round(strat.analyzers.sharpe.get_analysis().get("sharperatio", 0) or 0, 3),
        "max_dd":       round(strat.analyzers.dd.get_analysis()["max"]["drawdown"], 2),
        "total_trades": total_trades,
        "win_rate":     round(won_trades / total_trades * 100, 2) if total_trades else 0,
        "strategy":     f"双均线 MA{FAST_MA}/MA{SLOW_MA} + ATR定仓",
        "symbol":       "螺纹钢(RB) 主力连续",
        "period":       "2020-01-02 ~ 2024-12-31",
    },
    "series": strat.records,
    "trades": strat.trades_log,
}

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)

print(f"导出完成：{OUT_FILE}，共 {len(strat.records)} 条数据")
