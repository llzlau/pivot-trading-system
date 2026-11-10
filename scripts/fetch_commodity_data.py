"""
===================================================================================
模块名称: scripts/fetch_commodity_data.py
业务定位: 外部商品期货主力连续历史数据抓取、清洗与本地增量入库管线
输入依赖: AKShare futures_main_sina API (新浪财经主力连续合约数据源)
核心输出: data/raw/{SYMBOL}_daily.csv 标准化 OHLCV 行情仓库
===================================================================================
"""

from pathlib import Path
import sys
import time
import pandas as pd
import akshare as ak

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / 'data' / 'raw'
RAW_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SYMBOLS = {
    'Y0': 'Y_daily.csv',     # 豆油主连
    'AU0': 'AU_daily.csv',   # 沪金主连 (刷新至2026)
    'AG0': 'AG_daily.csv',   # 沪银主连 (刷新至2026)
    'SH0': 'SH_daily.csv',   # 烧碱主连
    'JD0': 'JD_daily.csv',   # 鸡蛋主连
    'EC0': 'EC_daily.csv',   # 欧线集运主连
    'FU0': 'FU_daily.csv',   # 燃料油主连
    'LU0': 'LU_daily.csv',   # 低硫燃油主连
}


def fetch_all():
    print("开始抓取最新商品期货主力连续行情数据...")
    for sym, filename in TARGET_SYMBOLS.items():
        out_path = RAW_DIR / filename
        try:
            print(f"正在拉取 {sym} -> {filename} ...", end=" ", flush=True)
            df = ak.futures_main_sina(symbol=sym)
            if df is not None and len(df) > 0:
                df.to_csv(out_path, index=False, encoding='utf-8')
                d0 = df.iloc[0]['日期']
                d1 = df.iloc[-1]['日期']
                print(f"成功: {len(df)} 根K线 ({d0} ~ {d1})")
            else:
                print("失败: 返回空数据")
        except Exception as e:
            print(f"发生异常: {e}")
        time.sleep(0.5)
    print("所有目标品种数据抓取完成！\n")


if __name__ == '__main__':
    fetch_all()
