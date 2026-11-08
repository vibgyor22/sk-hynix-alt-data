"""Quarter-to-date forecast: how early in a quarter can Korean exports call SK hynix revenue?

Rule (no fitted parameters, so nothing to overfit):
    after k months of quarter q (k = 1, 2, 3):
    revenue_hat(q) = revenue(q-1) * exports_krw(first k months of q) / exports_krw(first k months of q-1)
Comparing the same months in both quarters cancels seasonality within the quarter.

Baseline: revenue_hat(q) = revenue(q-1) * revenue(q-1)/revenue(q-2)   (last quarter's growth repeats)

Each forecast uses only data that existed at that point: last quarter's reported revenue plus the
exports so far. The one exception is that export values are today's (possibly revised) figures.
Run:  python -I src/analysis/quarter_to_date_forecast.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/financials"


def load():
    fin = pd.read_csv(ROOT / "data/financials/skhynix_quarterly.csv")
    fin.index = pd.PeriodIndex(fin.quarter, freq="Q")
    rev = fin.revenue_krw_m / 1e6  # KRW trillion

    fx = json.loads((ROOT / "data/raw/fx/usdkrw_monthly_yahoo_retrieved20261108.json").read_text())["chart"]["result"][0]
    fx = pd.Series(fx["indicators"]["quote"][0]["close"],
                   # +12h: Yahoo stamps month-starts at London midnight (23:00 UTC in summer), which would shift labels a month back
                   index=pd.PeriodIndex([datetime.fromtimestamp(t + 43200, timezone.utc).strftime("%Y-%m") for t in fx["timestamp"]], freq="M"))
    fx = fx.groupby(level=0).last()

    ex = pd.read_csv(ROOT / "data/processed/korean_exports/monthly_total.csv")
    ex.index = pd.PeriodIndex(ex.month, freq="M")
    exk = (ex.value_usd * fx.reindex(ex.index)).dropna() / 1e12  # KRW trillion
    return rev, exk


def qtd(exk, q, k):
    """Sum of the first k months of quarter q (NaN if any month is missing)."""
    months = pd.period_range(q.asfreq("M", "s"), periods=k, freq="M")
    v = exk.reindex(months)
    return v.sum() if v.notna().all() else np.nan


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rev, exk = load()
    rows = []
    for q in rev.index[2:]:
        r = {"quarter": str(q), "actual": rev[q], "baseline": rev[q - 1] ** 2 / rev[q - 2]}
        for k in (1, 2, 3):
            r[f"m{k}"] = rev[q - 1] * qtd(exk, q, k) / qtd(exk, q - 1, k)
        rows.append(r)
    bt = pd.DataFrame(rows).set_index("quarter")

    score = {}
    for c in ["m1", "m2", "m3", "baseline"]:
        e = (bt[c] / bt.actual - 1) * 100
        bt[f"{c}_err%"] = e.round(1)
        prev = rev.shift(1).reindex(pd.PeriodIndex(bt.index, freq="Q")).values
        ok = bt[c].notna()
        hit = (np.sign(bt[c] - prev) == np.sign(bt.actual - prev))[ok].mean() * 100  # did it call up vs down right?
        score[c] = {"MAPE_%": e.abs().mean(), "median_APE_%": e.abs().median(), "worst_%": e.abs().max(),
                    "up/down_hit_%": hit, "n": int(ok.sum())}
    score = pd.DataFrame(score).T.round(1)
    score.index = ["after month 1", "after month 2", "after month 3 (full quarter)", "baseline: last growth repeats"]

    OUT.mkdir(parents=True, exist_ok=True)
    bt.to_csv(OUT / "quarter_to_date_backtest.csv")
    score.to_csv(OUT / "quarter_to_date_scorecard.csv")
    pd.set_option("display.width", 200)
    print("BACKTEST (KRW trillion)")
    print(bt[["actual", "m1", "m2", "m3", "baseline", "m1_err%", "m2_err%", "m3_err%", "baseline_err%"]].round(1).to_string())
    print("\nSCORECARD")
    print(score.to_string())

    # Live forecast for the current quarter, if any months of it are in the data
    cur = exk.index.max().asfreq("Q")
    if cur not in rev.index:
        k = int((exk.index.max() - cur.asfreq("M", "s")).n) + 1
        f = rev[cur - 1] * qtd(exk, cur, k) / qtd(exk, cur - 1, k)
        print(f"\nLIVE: {cur} after {k} month(s): revenue forecast ₩{f:.1f}tn")
    else:
        print(f"\nLIVE: no {cur + 1} export months yet. Add October 2026 customs data to forecast Q4 2026.")


if __name__ == "__main__":
    main()
