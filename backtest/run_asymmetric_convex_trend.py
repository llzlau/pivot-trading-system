"""
Run Asymmetric Convex Trend System (ACTS - 纯价格非对称反脆弱趋势系统全量回测与审计)
===================================================================================
覆盖国内六大代表性大宗商品主力连续数据 (2021-2026)：
1. 原油 SC (宏观能化旗舰，20万本金)
2. 沪铜 CU (有色大宗之王，10万本金)
3. 玻璃 FG (地产工业链条，10万本金)
4. 纯碱 SA (高弹性化工制造，10万本金)
5. 螺纹钢 RB (黑色建材基石，10万本金)
6. 玉米 C (农产大宗基准，10万本金)
"""

from pathlib import Path
import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from strategies.asymmetric_convex_trend import COMMODITY_PORTFOLIO, run_asymmetric_convex_engine

if __name__ == '__main__':
    print('=' * 132)
    print('            非对称反脆弱趋势量化交易系统 (ACTS)：六大多品种实战审计大表 (2021-2026)')
    print('=' * 132 + '\n')

    all_res = []
    for cfg in COMMODITY_PORTFOLIO:
        res = run_asymmetric_convex_engine(cfg, start_date='2021-01-01', entry_window=20, exit_window=10, ma_span=60)
        all_res.append(res)

    print('【全量核心绩效与风控指标对比总表】')
    print('-' * 132)
    fmt_h = f"{'交易品种':<10} | {'板块属性':<8} | {'期初本金':>12} | {'期末最终权益':>12} | {'累计净利润':>12} | {'总收益率':>8} | {'最大回撤':>8} | {'交易笔数':>8} | {'胜率':>6} | {'单笔盈亏比':>10} | {'卡玛比率':>8}"
    print(fmt_h)
    print('-' * 132)

    total_cap = sum(r['capital'] for r in all_res)
    total_profit = sum(r['profit'] for r in all_res)

    for r in all_res:
        print(f"{r['symbol']:<10} | {r['category']:<8} | {r['capital']:>12,.0f} 元 | {r['cash']:>12,.0f} 元 | {r['profit']:>12,.0f} 元 | {r['ret_pct']:>7.1f}% | {r['mdd']:>7.1f}% | {r['trades']:>8d} 笔 | {r['win_rate']:>5.1f}% | {r['pl_ratio']:>8.2f}:1 | {r['calmar']:>8.2f}")
    print('-' * 132)
    print(f"【多品种资产组合合计】总投入本金: {total_cap:,.0f} 元 | 累计总净利润: {total_profit:,.0f} 元 | 资产组合累计收益率: {total_profit/total_cap*100:.1f}%\n")

    # 导出实战流水记录
    out_dir = BASE_DIR / 'data' / 'processed'
    for r in all_res:
        sym_code = r['symbol'].split()[1]
        f_name = f"acts_cycles_{sym_code}.csv"
        r['res_df'].to_csv(out_dir / f_name, index=False)
    print(f"全品种逐笔实战交易流水账本已安全存盘至: {out_dir}\n")
