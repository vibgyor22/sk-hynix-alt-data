"""HBM proxy: Korean memory exports to Taiwan.

Why: HBM has no public price series; it is priced in private annual contracts with
Nvidia, AMD and others. Physically, though, HBM stacks made in Korea are shipped to Taiwan,
where TSMC packages them next to the GPU (CoWoS). Commodity DRAM and NAND mostly go to China,
Hong Kong and Vietnam, for phone and PC assembly. So the Taiwan flow, and its $/g, is the
closest public read on HBM volume and pricing.

Data: UN Comtrade, Korea exports HS 854232 by partner (monthly, 2019-2025; Taiwan = "Other Asia, nes", 490),
      then the Korea Customs by-country x HS10 file for later months. They match exactly on Oct-Dec 2025.
Caveat: Taiwan also buys some commodity memory, and the flow includes Samsung's HBM as well as SK hynix's.
Run:  python -I src/analysis/hbm_proxy.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/korean_exports/comtrade_by_partner"
OUT = ROOT / "data/processed/korean_exports"
GROUPS = {490: "Taiwan", 156: "China", 344: "Hong Kong", 704: "Vietnam"}
KCS = next((ROOT / "data/raw/korean_exports/kcs").glob("kcs_854232_by_country_hs10_*.xlsx"))
KCS_NAMES = {"대만": "Taiwan", "중국": "China", "홍콩": "Hong Kong", "베트남": "Vietnam"}
LINES = {"8542321010": "DRAM", "8542323000": "Composite-chip ICs"}


def load_kcs() -> pd.DataFrame:
    raw = pd.read_excel(KCS, header=None, dtype=str)
    df = raw.iloc[6:, :6].dropna(subset=[0]).copy()
    df.columns = ["month", "country", "hs10", "name", "weight_kg", "value_k"]
    df = df[df.month.str.match(r"\d{4}\.\d{2}$")]
    df["month"] = pd.PeriodIndex(df.month.str.replace(".", "-"), freq="M")
    df["weight_kg"] = pd.to_numeric(df.weight_kg.str.replace(",", ""))
    df["value_usd"] = pd.to_numeric(df.value_k.str.replace(",", "")) * 1000  # file is thousand USD
    df["partner"] = df.country.map(KCS_NAMES).fillna("Rest")
    df["line"] = df.hs10.map(LINES).fillna("Other")
    return df


def load() -> pd.DataFrame:
    rows = []
    for f in sorted(RAW.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        for d in rec["response"].get("data") or []:
            if d["partnerCode"] == 0:
                continue
            rows.append({"month": pd.Period(rec["period"], "M"), "partner": GROUPS.get(d["partnerCode"], "Rest"),
                         "value_usd": d["primaryValue"], "weight_kg": d["netWgt"] or np.nan})
    return pd.DataFrame(rows).groupby(["month", "partner"], as_index=False).sum(min_count=1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    com, kcs = load(), load_kcs()
    m = pd.concat([com[com.month < kcs.month.min()],
                   kcs.groupby(["month", "partner"], as_index=False)[["value_usd", "weight_kg"]].sum()], ignore_index=True)
    m.to_csv(OUT / "monthly_by_destination.csv", index=False)
    q = m.assign(quarter=m.month.dt.asfreq("Q")).groupby(["quarter", "partner"])[["value_usd", "weight_kg"]].sum(min_count=1)
    q["usd_per_g"] = q.value_usd / q.weight_kg / 1000
    tot = q.groupby(level=0).value_usd.sum()
    q["value_share_%"] = q.value_usd / tot.reindex(q.index.get_level_values(0)).values * 100
    q.to_csv(OUT / "quarterly_by_destination.csv")
    pd.set_option("display.width", 200)
    piv = q.reset_index().pivot(index="quarter", columns="partner", values=["usd_per_g", "value_share_%"]).round(1)
    print("QUARTERLY: $/g and share of Korean memory export value, by destination")
    print(piv.loc["2021Q1":].to_string())
    tw = q.xs("Taiwan", level=1)
    tw["yoy_value_%"] = (tw.value_usd / tw.value_usd.shift(4) - 1) * 100
    tw["yoy_uv_%"] = (tw.usd_per_g / tw.usd_per_g.shift(4) - 1) * 100
    print("\nTAIWAN (HBM proxy)")
    print(tw.assign(value_bn=tw.value_usd / 1e9)[["value_bn", "usd_per_g", "value_share_%", "yoy_value_%", "yoy_uv_%"]].loc["2022Q1":].round(1).to_string())

    # What goes to Taiwan, by HS10 line (KCS months only)
    k = kcs.assign(quarter=kcs.month.dt.asfreq("Q"))
    t = k[k.partner == "Taiwan"].groupby(["quarter", "line"])[["value_usd", "weight_kg"]].sum()
    t["usd_per_g"] = t.value_usd / t.weight_kg / 1000
    t["share_of_taiwan_value_%"] = t.value_usd / t.groupby(level=0).value_usd.transform("sum") * 100
    t.to_csv(OUT / "taiwan_by_line_quarterly.csv")
    print("\nTAIWAN BY HS10 LINE (Korea Customs)")
    print(t.assign(value_bn=t.value_usd / 1e9)[["value_bn", "usd_per_g", "share_of_taiwan_value_%"]].round(2).to_string())


if __name__ == "__main__":
    main()
