"""Stage 3: can Korean memory exports nowcast SK hynix quarterly revenue?

Timing: Korea Customs publishes a month's exports on the 1st of the next month,
so a full quarter of exports is public about 4 weeks before SK hynix reports.

Nowcast (one idea, no fitted parameters):
    revenue_hat(q) = revenue(q-1) * exports_krw(q) / exports_krw(q-1)
i.e. assume Hynix's revenue moves one-for-one with Korean memory exports in KRW.

Baselines: naive  = revenue(q-1)            (no change)
           trend  = revenue(q-1) * revenue(q-1)/revenue(q-2)  (last growth repeats)

Caveats: exports use today's (possibly revised) customs values; Hynix's China fabs
(Wuxi DRAM, Dalian NAND) ship from China and are not in Korean customs data; HS 854232
includes Samsung. FX is the average of Yahoo month-end USD/KRW closes in the quarter.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "financials"


def load():
    fin = pd.read_csv(ROOT / "data/raw/financials/hynix_quarterly_stockanalysis_retrieved20261108.csv")
    fin["q"] = pd.PeriodIndex(fin.quarter, freq="Q")
    fin = fin.set_index("q")[["revenue_krw_m", "operating_income_krw_m"]]

    fx = json.load(open(ROOT / "data/raw/fx/usdkrw_monthly_yahoo_retrieved20261108.json"))["chart"]["result"][0]
    fx = pd.Series(fx["indicators"]["quote"][0]["close"],
                   # +12h: Yahoo stamps month-starts at London midnight (23:00 UTC in summer), which would shift labels a month back
                   index=[datetime.fromtimestamp(t + 43200, timezone.utc).strftime("%Y-%m") for t in fx["timestamp"]])
    fx.index = pd.PeriodIndex(fx.index, freq="M")
    fx = fx.groupby(level=0).last()

    ex = pd.read_csv(ROOT / "data/processed/korean_exports/monthly_total.csv")
    ex["month"] = pd.PeriodIndex(ex.month, freq="M")
    ex = ex.set_index("month")
    ex["value_krw_m"] = ex.value_usd * fx.reindex(ex.index) / 1e6
    q = ex.groupby(ex.index.asfreq("Q")).agg(months=("value_usd", "size"), value_krw_m=("value_krw_m", "sum"),
                                             value_usd=("value_usd", "sum"))
    q = q[q.months == 3]
    return fin.join(q[["value_krw_m", "value_usd"]], how="inner")


def main():
    d = load()
    d["exports_qoq"] = d.value_krw_m / d.value_krw_m.shift(1)
    d["nowcast"] = d.revenue_krw_m.shift(1) * d.exports_qoq
    d["naive"] = d.revenue_krw_m.shift(1)
    d["trend"] = d.revenue_krw_m.shift(1) ** 2 / d.revenue_krw_m.shift(2)
    d["hynix_share_of_exports"] = d.revenue_krw_m / d.value_krw_m
    # Year-on-year version: compares each quarter with the same quarter last year,
    # which cancels the Q4/Q1 seasonality in Hynix's share of Korean exports.
    d["nowcast_yoy"] = d.revenue_krw_m.shift(4) * d.value_krw_m / d.value_krw_m.shift(4)
    d["trend_yoy"] = d.revenue_krw_m.shift(4) * d.revenue_krw_m.shift(1) / d.revenue_krw_m.shift(5)

    s = d.dropna(subset=["nowcast_yoy", "trend_yoy"]).copy()
    actual_dir = np.sign(s.revenue_krw_m - s.naive)
    rows = []
    for m in ["nowcast_yoy", "trend_yoy", "nowcast", "trend", "naive"]:
        err = (s[m] / s.revenue_krw_m - 1) * 100
        s[f"{m}_err_pct"] = err
        hit = (np.sign(s[m] - s.naive) == actual_dir).mean() * 100 if m != "naive" else np.nan
        rows.append({"model": m, "MAPE_%": err.abs().mean(), "median_APE_%": err.abs().median(),
                     "direction_hit_%": hit, "n": len(err)})
    score = pd.DataFrame(rows).set_index("model").round(1)

    OUT.mkdir(parents=True, exist_ok=True)
    s.to_csv(OUT / "nowcast_backtest.csv")
    show = s[["revenue_krw_m", "nowcast_yoy", "nowcast_yoy_err_pct", "trend_yoy_err_pct", "nowcast_err_pct",
              "hynix_share_of_exports"]].copy()
    show[["revenue_krw_m", "nowcast_yoy"]] = (show[["revenue_krw_m", "nowcast_yoy"]] / 1e6).round(2)  # trillion KRW
    print("QUARTER BY QUARTER (revenue and nowcast in KRW trillion)")
    print(show.round(2).to_string())
    print("\nSCORECARD")
    print(score.to_string())
    print("\nexports vs revenue QoQ growth correlation:",
          round(np.log(s.exports_qoq).corr(np.log(s.revenue_krw_m / s.naive)), 2))


if __name__ == "__main__":
    main()
