"""
fetch_multi.py
批量下载多品种期货主力连续日线数据
BASE_DIR = Path(__file__).resolve().parent.parent
品种：螺纹钢(RB)、铜(CU)、黄金(AU)、豆粕(M)、PTA(TA)、铁矿石(I)
"""

import akshare as ak
import pandas as pd
from pathlib import Path
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(r"..\logs\fetch_multi.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── 品种配置 ──────────────────────────────────────────────
INSTRUMENTS = {
    "RB": {"name": "螺纹钢", "symbol": "RB0", "multiplier": 10},
    "CU": {"name": "铜",    "symbol": "CU0", "multiplier": 5},
    "AU": {"name": "黄金",  "symbol": "AU0", "multiplier": 1000},
    "M":  {"name": "豆粕",  "symbol": "M0",  "multiplier": 10},
    "TA": {"name": "PTA",   "symbol": "TA0", "multiplier": 5},
    "I":  {"name": "铁矿石","symbol": "I0",  "multiplier": 100},
}

START_DATE = "20200101"
END_DATE   = "20241231"
RAW_DIR    = Path(r"../data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)


def fetch_one(code: str, cfg: dict) -> pd.DataFrame | None:
    try:
        log.info(f"下载 {cfg['name']}({cfg['symbol']})...")
        df = ak.futures_main_sina(symbol=cfg["symbol"], start_date=START_DATE, end_date=END_DATE)

        # 统一列名
        col_map = {
            "日期": "date", "开盘价": "open", "最高价": "high",
            "最低价": "low", "收盘价": "close", "成交量": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df = df.dropna(subset=["close"])
        df["instrument"] = code
        df["multiplier"] = cfg["multiplier"]

        keep = [c for c in ["date","open","high","low","close","volume","instrument","multiplier"] if c in df.columns]
        df = df[keep]

        out = RAW_DIR / f"{code}_daily.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        log.info(f"  ✓ {cfg['name']}: {len(df)} 条 | {df['date'].min().date()} ~ {df['date'].max().date()} → {out.name}")
        return df

    except Exception as e:
        log.error(f"  ✗ {cfg['name']}({code}) 下载失败: {e}")
        return None


def main():
    log.info(f"开始批量下载 {len(INSTRUMENTS)} 个品种数据...")
    success, failed = [], []

    for code, cfg in INSTRUMENTS.items():
        df = fetch_one(code, cfg)
        if df is not None:
            success.append(code)
        else:
            failed.append(code)
        time.sleep(1)  # 礼貌性延迟，避免触发频率限制

    log.info(f"\n{'='*45}")
    log.info(f"下载完成: 成功 {len(success)} 个 → {success}")
    if failed:
        log.warning(f"失败 {len(failed)} 个 → {failed}")
    log.info(f"数据目录: {RAW_DIR}")


if __name__ == "__main__":
    main()
