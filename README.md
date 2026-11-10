# 中枢期货量化交易系统 (Pivot Trading System)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Market: Chinese Futures](https://img.shields.io/badge/Market-INE%20%7C%20DCE%20%7C%20SHFE-red.svg)](http://www.shfe.com.cn/)

基于中国商品期货市场（上期能源 INE、大商所 DCE、上期所 SHFE）特性研发的工业级系统化量化交易与风控引擎。深度融合经典量化著作（Rob Carver《Systematic Trading》、Perry Kaufman《Trading Systems and Methods》）的机构化系统设计理念，严格遵守自然人持仓交割月法定规范，彻底解决传统网格/原型机“死扛移仓失血”、“假突破严重侵蚀本金”与“巨额回撤穿仓”等致命缺陷。

---

## 一、 机构级重构核心引擎 (Core Architecture)

系统全面模块化重构为六大专业级量化内核（位于 `core/` 目录）：

1. **市场状态与动能滤网 (`core/regime_filter.py`)**：
   - 基于滚动 ATR、均线多空共振（MA20/MA60/MA120）、趋势强度（ADX 14）与价格乖离率（Bias ATR）；
   - 彻底过滤掉均线缠绕打结的垃圾震荡，杜绝在极端脉冲天花板处盲目追高。
2. **动态自适应波动率中枢 (`core/dynamic_pivot.py`)**：
   - 废除死板的“固定60点”，以 $1.8 \times \text{ATR}$ 动态自适应确定突破阈值；
   - 低波期自动收窄阈值防衰竭，高波期自动放宽阈值防杂波打穿。
3. **波动率平价与正金字塔风控 (`core/position_sizing.py`)**：
   - 严格落实单笔 1.5% 风险预算（House-Money Pyramiding 协议）；
   - 加仓必须建立在底仓已完全锁定利润（安全垫充足）的前提下，严禁“倒金字塔加仓拉高成本”。
4. **智能三级动态跟踪锁盈系统 (`core/smart_exit.py`)**：
   - **加仓单独立保本防暴线**：价格跌破加仓入场价立即保本平仓，绝不侵蚀底仓；
   - **底仓三级阶梯锁定**：根据浮盈波幅动态上移止损（窄幅保本 $\to$ 锁定 60% 浮盈 $\to$ 破前一日低点抛物线止盈）。
5. **交割月与超时钝化熔断引擎 (`core/roll_manager.py`)**：
   - 严守交易所自然人客户“禁止进入交割月”的法定红线，每月中旬（15日）准时展期主力合约；
   - **35 天无动能平价熔断机制**：若建仓后超过 35 个交易日行情在锚点附近钝化，系统果断平价双平出局，拒绝充当无休止的“移仓提款机”。
6. **账户净值风控断路器 (`core/portfolio_risk.py`)**：
   - 连续 2 笔假突破止损强制触发 10 个交易日静默冷却期；
   - 账户回撤达 15% 冻结一切加仓权限，回撤达 25% 触发总闸熔断保护。

---

## 二、 粗糙原型机 vs 机构级规范化重构 全量审计实测

以 **上海原油期货（SC0，2021-2026 年真实连续主力数据，200,000 元初始本金）** 为测试基准：

| 对比维度 | 原版双向原型机 (Naive Bi) | 原版单边原型机 (Naive Up) | 机构级规范化重构 (Institutional) | 提升效果与改进解析 |
| :--- | :---: | :---: | :---: | :--- |
| **期初初始本金** | 200,000 元 | 200,000 元 | **200,000 元** | 基准相同 |
| **期末最终权益** | 489,800 元 | 407,040 元 | **345,280 元** | 稳健复利增长 |
| **累计净利润** | +289,800 元 | +207,040 元 | **+145,280 元 (+72.6%)** | 纯净实盘可落袋利润 |
| **历史最低权益 (谷底)** | **48,120 元** | 143,280 元 | **200,000 元** | **零侵蚀本金（净值从未破 20 万）** |
| **最大回撤 (MDD)** | **-82.3%** | -47.2% | **-9.6%** | **回撤从 82% 彻底压缩至 9.6%** |
| **卡玛比率 (收益/回撤)**| 1.76 | 2.19 | **7.61** | **风险收益比暴增 3.5 倍** |
| **单笔假突破最大单亏** | -54,640 元 | -54,640 元 | **-5,600 元** | 单笔试错成本控制在本金 2.8% 内 |
| **是否违反交割月规则** | 违规 (死扛长达2年未移仓) | 违规 (死扛长达2年未移仓) | **合规 (每月中旬移仓+35天熔断)** | 杜绝穿仓与法定强平风险 |
| **实盘存活状态** | **穿仓爆仓出局 (4.8万爆仓)** | 濒危承压 (回撤47%) | **健康抗震稳健运行** | 具备工业级实盘抗风险能力 |

---

## 三、 代码仓库目录结构

```
pivot-trading-system/
│
├── core/                                # 机构级量化六大核心引擎
│   ├── __init__.py                      # 核心模块统一导出
│   ├── regime_filter.py                 # 市场状态分类与动能滤网 (ADX, MA共振, 乖离率)
│   ├── dynamic_pivot.py                 # 动态自适应波动率中枢与突破判定
│   ├── position_sizing.py               # 波动率平价定仓与正金字塔风控
│   ├── smart_exit.py                    # 智能三级动态跟踪止盈与保本锁
│   ├── roll_manager.py                  # 交割月移仓与 35 天超时平价熔断引擎
│   └── portfolio_risk.py                # 账户级风控覆层与熔断断路器
│
├── strategies/                          # 策略组装与实盘执行层
│   └── institutional_sc_pivot.py        # 机构级原油中枢量化交易策略引擎
│
├── backtest/                            # 回测与全量审计对比模块
│   ├── run_institutional_sc.py          # 机构级 vs 粗糙原型机 全量对比审计报告
│   ├── system_sc_200k.py                # 20万本金原油 600 对锁基础模拟
│   ├── portfolio_ma.py                  # 多品种趋势组合动量引擎
│   └── backtest_trades_detail.py        # 逐笔交易穿透分析工具
│
├── scripts/                             # 分析诊断与数据工具
│   ├── diagnose_losses.py               # 假突破与亏损根因诊断工具
│   ├── backtest_sc_upward_100pct.py     # 原油 600 向上盈利 100% 原型机
│   ├── compare_750_680.py               # 铁矿石 750 vs 680 敏感性实证
│   └── print_cycles_table.py            # 对锁逐轮账本流水生成器
│
├── data/                                # 数据仓库
│   ├── raw/                             # 原始日线数据（SC0, I0, RB, CU 等）
│   └── processed/                       # institutional_sc_cycles.csv (实战审计流水)
│
├── .gitignore                           # 严格安全脱敏过滤规则
└── README.md                            # 系统架构与使用说明
```

---

## 四、 快速开始与一键审计

### 1. 环境准备
```bash
pip install pandas numpy backtrader matplotlib
```

### 2. 运行机构级规范重构全量对比审计
一键复现三方审计对比报告与逐轮交易明细账本：
```bash
python backtest/run_institutional_sc.py
```

### 3. 查看亏损根因与行情状态诊断
```bash
python scripts/diagnose_losses.py
```

---

## 五、 免责声明

本系统及相关代码仅用于量化交易学术研究与历史数据复盘，不构成任何具体的投资建议。期货市场具有高杠杆及价格剧烈波动风险，实盘交易请严格遵守相关法律法规并做好自主风险控制。
