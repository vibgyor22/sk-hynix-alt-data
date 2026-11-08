"""Build docs/data/nand.json (NAND 128Gb MLC contract price series) and docs/data/provenance.json
(how many price rows each press outlet supplied, for the method graphic on the site).

Inputs : data/raw/nand_prices/nand_contract_monthly.csv, data/raw/dram_prices/dram_contract_monthly.csv
Output : docs/data/nand.json, docs/data/provenance.json
Missing months stay blank; nothing is filled in.
Run:  python -I src/site/export_nand.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/data"
OUTLETS = [("asia economy", "Asia Economy"), ("newsis", "Newsis"), ("semimedia", "SemiMedia"), ("statementdog", "StatementDog"),
           ("financial news", "Financial News"), ("yonhap", "Yonhap"), ("herald", "Herald"), ("hankyung", "Hankyung"),
           ("the elec", "The Elec"), ("sbs", "SBS Biz"), ("zdnet", "ZDNet Korea")]


def outlet(src):
    s = str(src).lower()
    for key, name in OUTLETS:
        if key in s:
            return name
    return str(src)


def clean(v):
    return None if pd.isna(v) else v


def main():
    nand = pd.read_csv(ROOT / "data/raw/nand_prices/nand_contract_monthly.csv")
    nand["month"] = pd.PeriodIndex(nand.month, freq="M")
    nand = nand.set_index("month")
    full = pd.period_range(nand.index.min(), nand.index.max(), freq="M")
    s = nand.avg_usd.reindex(full)
    mom = (s / s.shift(1) - 1) * 100
    mom3 = (s / s.shift(3) - 1) * 100
    rows = []
    for m in full:
        r = nand.loc[m] if m in nand.index else None
        rows.append({
            "month": str(m), "avg_usd": clean(s[m]),
            # month-on-month as stated in the article where given, otherwise from the rounded prices
            "mom_pct": (None if r is None else clean(r.mom_change_pct_stated)) if (r is not None and pd.notna(r.mom_change_pct_stated))
                       else (None if pd.isna(mom[m]) else round(float(mom[m]), 3)),
            "mom3_pct": None if pd.isna(mom3[m]) else round(float(mom3[m]), 3),
            "publication_date": None if r is None else clean(r.publication_date),
            "source": None if r is None else clean(r.source),
            "source_url": None if r is None else clean(r.source_url),
            "quote": None if r is None else clean(r.source_quote),
            "flag": None if r is None else clean(r.flag),
        })
    (OUT / "nand.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    ddr4 = pd.read_csv(ROOT / "data/raw/dram_prices/dram_contract_monthly.csv")
    ddr4 = ddr4[(ddr4.item == "DDR4 8Gb 1Gx8") & ddr4.avg_usd.notna()]
    counts = {}
    for key, df in (("ddr4", ddr4), ("nand", nand.dropna(subset=["avg_usd"]))):
        for o in df.source.map(outlet):
            counts.setdefault(o, {"ddr4": 0, "nand": 0})[key] += 1
    outlets = sorted(({"name": k, **v} for k, v in counts.items()), key=lambda d: -(d["ddr4"] + d["nand"]))
    prov = {"outlets": outlets, "rows": {"ddr4": int(len(ddr4)), "nand": int(nand.avg_usd.notna().sum())}}
    (OUT / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"nand.json: {int(s.notna().sum())} months with a price of {len(full)}; last {full[-1]} ${s.iloc[-1]:.2f}, 3m change {mom3.iloc[-1]:+.1f}%")
    print("provenance:", prov["rows"], [(o['name'], o['ddr4'], o['nand']) for o in outlets])


if __name__ == "__main__":
    main()
