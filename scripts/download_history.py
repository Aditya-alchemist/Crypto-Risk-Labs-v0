from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"


HEADERS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]


def download_klines(symbol: str, interval: str, limit: int) -> list[list[str]]:
    query = urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    url = f"{BINANCE_KLINES}?{query}"
    with urlopen(url, timeout=20) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return raw


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(HEADERS)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download starter BTC historical data from Binance")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--daily-limit", type=int, default=1000)
    parser.add_argument("--m5-limit", type=int, default=1000)
    args = parser.parse_args()

    out_dir = Path("data/historical")
    out_dir.mkdir(parents=True, exist_ok=True)

    daily = download_klines(symbol=args.symbol, interval="1d", limit=args.daily_limit)
    m5 = download_klines(symbol=args.symbol, interval="5m", limit=args.m5_limit)

    write_csv(out_dir / "btc_daily.csv", daily)
    write_csv(out_dir / "btc_5min.csv", m5)

    print(f"Saved: {out_dir / 'btc_daily.csv'}")
    print(f"Saved: {out_dir / 'btc_5min.csv'}")


if __name__ == "__main__":
    main()
