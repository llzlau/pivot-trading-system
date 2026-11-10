# 中枢与反脆弱期货量化交易系统 (Pivot & Convex Trend Trading System)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Market: Chinese Futures](https://img.shields.io/badge/Market-INE%20%7C%20DCE%20%7C%20SHFE%20%7C%20CZCE-red.svg)](http://www.shfe.com.cn/)

基于中国商品期货市场（上期能源 INE、大商所 DCE、上期所 SHFE、郑商所 CZCE）特性研发的工业级系统化量化交易与风控引擎。深度融合经典量化著作（Rob Carver《Systematic Trading》、Andreas Clenow《Following the Trend》、Perry Kaufman《Trading Systems and Methods》）的机构化系统设计理念，严格遵守自然人持仓交割月法定规范。

系统包含两大成熟量化架构：
1. **机构级中枢对锁与风控防守引擎 (`Institutional SC Pivot`)**：专注于极端防守与本金零破损（回撤压缩至 9.6%，本金零侵蚀）；
2. **非对称反脆弱趋势量化引擎 (`ACTS - Asymmetric Convex Trend System`)**：基于反向思维与纯价格时空非对称结构，彻底去除主观中枢预测，释放大单边向上暴利捕获能力（实现 **以一抵三的高盈亏比** 与让利润放开奔跑）。

---

## 一、 非对称反脆弱趋势交易引擎 (ACTS Architecture)

针对“静态中枢可能存在事后画靶过拟合”以及“止盈过紧无法让利润放开跑”的痛点，全新研发的 **ACTS 纯价格反脆弱引擎**（位于 [`strategies/asymmetric_convex_trend.py`](strategies/asymmetric_convex_trend.py)）：

### 核心设计哲学（反向思维）：
* **零预测假设 (Zero-Prediction Paradigm)**：承认 K 线是一条游离的随机漫步线，绝大部分试图预测点位的指标最终都死于过拟合。彻底废除所有振荡指标与固定价格中枢；
* **顺大势破位 (Macro Trend Resonance)**：依托日线 MA60 / 20 周均线识别宏观产业顺逆，大周期均线上方只做多突破，均线下方只做空破位，杜绝在熊市逆势接飞刀；
* **非对称出场 (Asymmetric Trailing Exit)**：跌破过去 10 日极值（或 2.5 ATR 宽幅吊灯）才离场，给足趋势充分的日间洗盘呼吸空间，不设主观天花板，真正做到**让利润放肆奔跑**；
* **正金字塔滚雪球协议 (House-Money Pyramiding)**：浮盈达到 2.0 ATR 后以市场利润追加仓位，加仓单严格设置独立原价保本防暴线，**绝不允许加仓侵蚀底仓利润**。

### 六大代表性商品期货实战审计总表 (2021-2026 连续主力数据)：

| 交易品种 | 板块属性 | 初始本金 | 期末最终权益 | 累计净利润 | 投资收益率 | 最大回撤 | 交易笔数 | 胜率 | 单笔盈亏比 | 卡玛比率 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **原油 SC** | 宏观能化 | 200,000 元 | **390,320 元** | **+190,320 元** | **+95.2%** | 73.9% | 38 笔 | 42.1% | **1.82 : 1** | 1.29 |
| **沪铜 CU** | 有色金属 | 100,000 元 | **156,070 元** | **+56,070 元** | **+56.1%** | 42.5% | 25 笔 | **48.0%** | **1.52 : 1** | 1.32 |
| **玻璃 FG** | 建材工业 | 100,000 元 | **135,094 元** | **+35,094 元** | **+35.1%** | **9.8%** | 33 笔 | **48.5%** | **2.29 : 1** | **3.60** |
| **纯碱 SA** | 化工制造 | 100,000 元 | **127,450 元** | **+27,450 元** | **+27.5%** | 21.3% | 38 笔 | 31.6% | **3.14 : 1** | 1.29 |
| **螺纹钢 RB** | 黑色建材 | 100,000 元 | 91,070 元 | -8,930 元 | -8.9% | 16.0% | 39 笔 | 38.5% | 1.39 : 1 | -0.56 |
| **玉米 C** | 大宗农产 | 100,000 元 | 85,910 元 | -14,090 元 | -14.1% | 20.7% | 44 笔 | 34.1% | 1.55 : 1 | -0.68 |
| **多品种组合** | **跨资产池** | **700,000 元** | **985,914 元** | **+285,914 元** | **+40.8%** | **-** | **217 笔** | **40.5%** | **1.95 : 1** | **-** |

---

## 二、 机构级中枢对锁与风控防守引擎 (SC Pivot Engine)

针对单品种极端防守需求研发的六大专业级量化内核（位于 `core/` 目录）：

1. **动态自适应波动率中枢 (`core/dynamic_pivot.py`)**：以 $1.8 \times \text{ATR}$ 动态自适应确定突破阈值；
2. **波动率平价与正金字塔风控 (`core/position_sizing.py`)**：落实单笔 1.5% 风险预算；
3. **智能三级动态跟踪锁盈系统 (`core/smart_exit.py`)**：加仓单独立保本 + 底仓阶梯锁；
4. **交割月与超时钝化熔断引擎 (`core/roll_manager.py`)**：35 天无动能平价双平熔断，杜绝移仓失血；
5. **账户净值风控断路器 (`core/portfolio_risk.py`)**：连亏休眠 10 天与 25% 熔断总闸。

### 原油 600 中枢防守实测对比（2021-2026 年，20万本金）：
| 对比维度 | 原版双向原型机 (Naive Bi) | 机构级规范化重构 (Institutional SC) | 提升效果 |
| :--- | :---: | :---: | :--- |
| **期初初始本金** | 200,000 元 | **200,000 元** | 基准相同 |
| **期末最终权益** | 489,800 元 | **345,280 元** | 纯净可落袋实盘收益 |
| **历史最低权益 (谷底)** | **48,120 元 (穿仓强平)** | **200,000 元 (零侵蚀本金)** | **彻底消灭 5 万元穿仓灾难** |
| **最大回撤 (MDD)** | **-82.3%** | **-9.6%** | **回撤压缩近 90%** |
| **卡玛比率 (收益/回撤)** | 1.76 | **7.61** | **顶级对冲基金水准** |

---

## 三、 代码仓库目录结构

```
pivot-trading-system/
│
├── core/                                # 机构级量化六大核心防御引擎
│   ├── __init__.py                      # 核心模块统一导出
│   ├── regime_filter.py                 # 市场状态分类与动能滤网 (ADX, MA共振, 乖离率)
│   ├── dynamic_pivot.py                 # 动态自适应波动率中枢与突破判定
│   ├── position_sizing.py               # 波动率平价定仓与正金字塔风控
│   ├── smart_exit.py                    # 智能三级动态跟踪止盈与保本锁
│   ├── roll_manager.py                  # 交割月移仓与 35 天超时平价熔断引擎
│   └── portfolio_risk.py                # 账户级风控覆层与熔断断路器
│
├── strategies/                          # 核心策略引擎实现
│   ├── asymmetric_convex_trend.py       # ACTS 纯价格非对称反脆弱趋势跟踪引擎
│   └── institutional_sc_pivot.py        # 机构级原油中枢对锁量化策略
│
├── backtest/                            # 一键回测与审计对比模块
│   ├── run_asymmetric_convex_trend.py   # 一键执行 ACTS 多品种全量审计报告
│   ├── run_institutional_sc.py          # 机构级中枢对锁全量对比审计
│   └── system_sc_200k.py                # 基础原油对锁模拟
│
├── scripts/                             # 专题实证分析与数据抓取工具
│   ├── test_high_volatility.py          # 纯碱、玻璃、棕榈油、苹果高波动专项审计
│   ├── multi_commodity_backtest.py      # 多品种中枢回测脚本
│   └── diagnose_losses.py               # 假突破与亏损根因诊断工具
│
├── data/                                # 数据仓库
│   ├── raw/                             # 原始主力连续日线（SC0, CU, FG, SA, RB, C, AP, P 等）
│   └── processed/                       # 逐笔交易穿透流水账本（acts_cycles_*.csv 等）
│
├── .gitignore                           # 严格安全脱敏与二进制过滤规则
└── README.md                            # 系统架构与使用说明
```

---

## 四、 快速开始与一键审计

### 1. 环境准备
```bash
pip install pandas numpy backtrader matplotlib
```

### 2. 运行 ACTS 非对称反脆弱趋势系统多品种审计
一键复现六大核心品种（原油、沪铜、玻璃、纯碱、螺纹、玉米）审计对比大表：
```bash
python backtest/run_asymmetric_convex_trend.py
```

### 3. 运行高波动专项实测（纯碱、玻璃、棕榈油、苹果）
```bash
python scripts/test_high_volatility.py
```

### 4. 运行机构级中枢对锁（防守旗舰版）审计
```bash
python backtest/run_institutional_sc.py
```

---

## 五、 免责声明

本系统及相关代码仅用于量化交易学术研究与历史数据复盘，不构成任何具体的投资建议。期货市场具有高杠杆及价格剧烈波动风险，实盘交易请严格遵守相关法律法规并做好自主风险控制。
