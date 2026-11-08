"""Stage 1: build clean monthly tables from the raw Comtrade JSONs and the KCS Excel file.

Outputs (data/processed/korean_exports/):
  monthly_total.csv  one row per month, Jan 2015 - latest. Comtrade before 2021-10, KCS from 2021-10.
  monthly_lines.csv  KCS HS10 lines (DRAM, flash, composite chips ...) from 2021-10.
Missing values stay blank (NaN); nothing is filled in.
Run:  python -I src/data/build_exports.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COMTRADE = ROOT / "data/raw/korean_exports/comtrade"
KCS_XLSX = next((ROOT / "data/raw/korean_exports/kcs").glob("*.xlsx"))
OUT = ROOT / "data/processed/korean_exports"
KCS_START = "2021-10"


def load_comtrade() -> pd.DataFrame:
    rows = []
    for f in sorted(COMTRADE.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        data = rec["response"].get("data") or []
        if not data:
            continue  # month not published yet: leave out, don't invent
        d = data[0]
        rows.append({"month": pd.Period(rec["period"], "M"), "value_usd": d["primaryValue"],
                     "weight_kg": d["netWgt"] or float("nan"), "source": "comtrade",
                     "retrieved_utc": rec["retrieved_utc"]})
    return pd.DataFrame(rows)


def load_kcs_lines() -> pd.DataFrame:
    raw = pd.read_excel(KCS_XLSX, header=None, dtype=str)
    df = raw.iloc[6:, :5].dropna(subset=[0]).copy()
    df.columns = ["month", "hs10", "name", "weight_kg", "value_usd_k"]
    df = df[df["month"].str.match(r"\d{4}\.\d{2}$")]  # drops the 'Total' row
    df["month"] = pd.PeriodIndex(df["month"].str.replace(".", "-"), freq="M")
    df["weight_kg"] = pd.to_numeric(df["weight_kg"].str.replace(",", ""))
    df["value_usd"] = pd.to_numeric(df["value_usd_k"].str.replace(",", "")) * 1000  # file is in thousand USD
    return df.drop(columns="value_usd_k")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console default can't print Korean names
    OUT.mkdir(parents=True, exist_ok=True)
    com, lines = load_comtrade(), load_kcs_lines()
    kcs_tot = lines.groupby("month")[["value_usd", "weight_kg"]].sum().reset_index().assign(source="kcs")

    # Validation: the two sources must agree where they overlap
    ov = com.merge(kcs_tot, on="month", suffixes=("_c", "_k"))
    print(f"overlap months: {len(ov)}  max |value diff| {(ov.value_usd_k/ov.value_usd_c-1).abs().max():.2e}"
          f"  max |weight diff| {(ov.weight_kg_k/ov.weight_kg_c-1).abs().max():.2e}")

    total = pd.concat([com[com["month"] < pd.Period(KCS_START, "M")], kcs_tot], ignore_index=True)
    total = total.sort_values("month").reset_index(drop=True)
    full = pd.period_range(total.month.min(), total.month.max(), freq="M")
    total = total.set_index("month").reindex(full).rename_axis("month").reset_index()  # exposes any gap as NaN
    total.to_csv(OUT / "monthly_total.csv", index=False)
    lines.to_csv(OUT / "monthly_lines.csv", index=False)

    # Data-quality report
    print(f"\nmonthly_total: {len(total)} months {total.month.min()} -> {total.month.max()}")
    print("missing value months :", total.loc[total.value_usd.isna(), "month"].astype(str).tolist())
    print("missing weight months:", total.loc[total.weight_kg.isna(), "month"].astype(str).tolist())
    print("duplicates           :", int(total.month.duplicated().sum()))
    print("source counts        :", total.source.value_counts().to_dict())
    mom = total.set_index("month").value_usd.pct_change()
    print("largest MoM value moves:\n", mom.reindex(mom.abs().nlargest(5).index).round(3).to_string())
    print(f"\nmonthly_lines: {len(lines)} rows, {lines.hs10.nunique()} HS10 lines: "
          f"{lines.groupby('hs10').name.first().to_dict()}")


if __name__ == "__main__":
    main()
