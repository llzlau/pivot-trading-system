"""
fetch_data.py
下载螺纹钢(RB)期货主力连续合约历史日线数据
BASE_DIR = Path(__file__).resolve().parent.parent
数据来源：AKShare (新浪财经)
输出：../data/raw\RB_daily.csv
"""

import akshare as ak
import pandas as pd
from pathlib import Path
import logging
from datetime import datetime

# ── 日志配置 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(r"..\logs\fetch_data.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────
SYMBOL     = "RB0"            # 螺纹钢主力连续合约 (新浪代码)
START_DATE = "20200101"
END_DATE   = "20241231"
RAW_DIR    = Path(r"../data/raw")
OUT_FILE   = RAW_DIR / "RB_daily.csv"

RAW_DIR.mkdir(parents=True, exist_ok=True)


def fetch_rebar() -> pd.DataFrame:
    log.info(f"开始下载 {SYMBOL} 数据 ({START_DATE} ~ {END_DATE})...")
    df = ak.futures_main_sina(symbol=SYMBOL, start_date=START_DATE, end_date=END_DATE)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    # 统一列名
    col_map = {
        "日期": "date",
        "开盘价": "open",
        "最高价": "high",
        "最低价": "low",
        "收盘价": "close",
        "成交量": "volume",
        "持仓量": "open_interest",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 兼容英文列名（部分版本 akshare 返回英文）
    if "date" not in df.columns and "Date" in df.columns:
        df = df.rename(columns={"Date": "date", "Open": "open", "High": "high",
                                 "Low": "low", "Close": "close", "Volume": "volume"})

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["close"])

    # 只保留核心列
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "open_interest"] if c in df.columns]
    df = df[keep]

    log.info(f"数据清洗完成：{len(df)} 条记录，时间范围 {df['date'].min().date()} ~ {df['date'].max().date()}")
    return df


def main():
    df = fetch_rebar()
    df = clean(df)
    df.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
    log.info(f"数据已保存至：{OUT_FILE}")
    print(df.tail(10).to_string())


if __name__ == "__main__":
    main()
