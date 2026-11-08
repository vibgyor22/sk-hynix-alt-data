"""Stage 1: pull Korea HS 854232 monthly exports (world) from the UN Comtrade public preview API.

The keyless preview endpoint allows ONE period per request, so we loop month by month.
Each raw response is saved untouched (plus a retrieval timestamp) so nothing is overwritten
or invented; months already on disk are skipped, which makes re-runs incremental.

Usage:  python src/data/export_ingestion.py 2015-01 2026-06
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "korean_exports" / "comtrade"
PARAMS = {"reporterCode": 410, "cmdCode": "854232", "flowCode": "X", "partnerCode": 0, "includeDesc": "true"}
PAUSE_S = 2.5
MAX_RETRIES = 4


def months(start: str, end: str):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield f"{y}{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_month(period: str) -> dict:
    """Fetch one period with backoff on rate limits / transient errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(URL, params={**PARAMS, "period": period}, timeout=30)
            if r.status_code == 200:
                return r.json()
            wait = 10 * attempt
            print(f"  {period}: HTTP {r.status_code}, retry in {wait}s")
        except requests.RequestException as e:
            wait = 10 * attempt
            print(f"  {period}: {type(e).__name__}, retry in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"giving up on {period}")


def main(start: str, end: str) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched = skipped = failed = 0
    for period in months(start, end):
        path = RAW_DIR / f"{period}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            payload = fetch_month(period)
        except RuntimeError as e:
            print(e)
            failed += 1
            continue
        record = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "period": period, "response": payload}
        path.write_text(json.dumps(record, indent=1), encoding="utf-8")
        fetched += 1
        print(f"{period}: count={payload.get('count')} error={payload.get('error')!r}")
        time.sleep(PAUSE_S)
    print(f"done: fetched={fetched} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
