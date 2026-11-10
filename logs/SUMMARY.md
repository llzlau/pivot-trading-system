# 量化期货交易系统资产与公用数据全景备忘录 (Common Data & System Inventory)

> 本备忘录记录当前会话构建的所有公用数据、策略引擎源码、多品种审计流水账本及架构决策资产。

---

## 一、 原始主力连续行情数据仓库 (`data/raw/`)
全量清洗、时间戳对齐至 2026 年底的标准化主力连续日线数据（OHLCV + 成交持仓量）：

1. **宏观能化与有色**：
   - `SC0_latest.csv`：上海原油主力连续 (2018-2026，2092 根 K 线，乘数 1000 桶/手)
   - `CU_daily.csv`：沪铜主力连续 (2020-2026，1213 根 K 线，乘数 5 吨/手)
2. **高波动工业建材与化工**：
   - `SA_daily.csv`：纯碱主力连续 (2021-2026，1679 根 K 线，乘数 20 吨/手)
   - `FG_daily.csv`：玻璃主力连续 (2021-2026，3375 根 K 线，乘数 20 吨/手)
   - `RB_daily.csv`：螺纹钢主力连续 (2010-2026，5492 根 K 线，乘数 10 吨/手)
   - `I0_full.csv` / `I_daily.csv`：铁矿石主力连续 (3175 根 K 线，乘数 100 吨/手)
3. **农产品与软商品**：
   - `C_daily.csv`：玉米主力连续 (2010-2026，5311 根 K 线，乘数 10 吨/手)
   - `CS_daily.csv`：淀粉主力连续 (2886 根 K 线，乘数 10 吨/手)
   - `AP_daily.csv`：苹果主力连续 (2148 根 K 线，乘数 10 吨/手)
   - `P_daily.csv`：棕榈油主力连续 (4629 根 K 线，乘数 10 吨/手)
   - `M_daily.csv`：豆粕主力连续 (6530 根 K 线，乘数 10 吨/手)
   - `JD_daily.csv`：鸡蛋主力连续
   - `SR_daily.csv`：白糖主力连续
4. **金融与贵金属**：
   - `AG_daily.csv` (白银), `AU_daily.csv` (黄金), `T_daily.csv` (10年期国债), `TA_daily.csv` (PTA)

---

## 二、 核心策略架构与模块源码 (`strategies/`, `core/`)

1. **ACTS 纯价格非对称反脆弱趋势引擎 (`strategies/asymmetric_convex_trend.py`)**：
   - 零预测入场：20 日唐奇安通道破位 + 60 日宏观均线 (MA60) 顺势滤波；
   - 动态风险定仓：以单笔 1.5% 资金风险与 1.5 ATR 动态核算开仓手数；
   - 时空非对称移动追踪：以近 10 日反向极值（或 2.5 ATR 吊灯）全天候保护，假突破平均 19 天小亏离场，真单边持仓 80~250 天放飞利润；
   - House-Money 风险隔离加仓：浮盈达 2.0 ATR 后仅追加 1 手，加仓单设独立原价保本线。
2. **机构级对锁防守与交割月熔断引擎 (`strategies/institutional_sc_pivot.py`, `core/*`)**：
   - 6 大核心模块：`regime_filter.py` (动能状态)、`dynamic_pivot.py` (1.8 ATR 动态中枢)、`position_sizing.py` (金字塔定仓)、`smart_exit.py` (阶梯三级锁盈)、`roll_manager.py` (每月15日移仓+35天钝化熔断)、`portfolio_risk.py` (账户断路器)。
   - 战绩：把原油 82.3% 的穿仓灾难回撤死死压缩至 9.6%，卡玛比率达 7.61。

---

## 三、 实战穿透账本与图表资产 (`data/processed/`)

1. **ACTS 多品种逐笔流水大账本**：
   - `acts_cycles_SC.csv`：原油 38 笔穿透流水 (净利 +190,320 元, 盈亏比 1.82:1)
   - `acts_cycles_SA.csv`：纯碱 38 笔穿透流水 (净利 +27,450 元, 盈亏比 3.14:1)
   - `acts_cycles_FG.csv`：玻璃 33 笔穿透流水 (净利 +35,094 元, 回撤仅 9.8%, 盈亏比 2.29:1)
   - `acts_cycles_CU.csv`：沪铜 25 笔穿透流水 (净利 +56,070 元, 盈亏比 1.52:1)
   - `acts_cycles_RB.csv`：螺纹钢 39 笔流水
   - `acts_cycles_C.csv`：玉米 44 笔流水
2. **中枢对锁流水与可视化**：
   - `institutional_sc_cycles.csv`：机构级 10 轮规范移仓对锁完整流水
   - `ma_crossover_result.html`：3,630 行独立交互式资金曲线走势看板
   - `chart_data.json` / `embed_data.json`：前端图表全量脱敏渲染数据

---

## 四、 远程同步与代码托管
- **GitHub 官方公共仓库**：`https://github.com/llzlau/pivot-trading-system.git`
- **本地主干分支**：`main` (工作区保持干净，所有敏感绝对路径均已做相对化脱敏)
