"""Build compact JSON for the static research site (docs/).

Reads the processed/raw data files (read-only) and writes docs/data/*.json.
Derived metrics are recomputed the same way as src/analysis: sum value and weight
over the window FIRST, then divide. Checks against the analysis outputs are asserted.

Run:  python -I src/site/export_site_data.py
"""
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "data"

F_TOTAL = ROOT / "data/processed/korean_exports/monthly_total.csv"
F_LINES = ROOT / "data/processed/korean_exports/monthly_lines.csv"
F_QDEC = ROOT / "data/processed/korean_exports/quarterly_decomposition.csv"
F_DDR4 = ROOT / "data/processed/dram_prices/ddr4_8gb_contract_monthly.csv"
F_DDR4_RAW = ROOT / "data/raw/dram_prices/dram_contract_monthly.csv"
F_RETAIL = ROOT / "data/raw/memory_prices/stanford_dam_memory_prices_retrieved20261108.csv"
F_FIN_RAW = ROOT / "data/raw/financials/hynix_quarterly_stockanalysis_retrieved20261108.csv"
F_FIN = ROOT / "data/financials/skhynix_quarterly.csv"
F_QTD = ROOT / "data/processed/financials/quarter_to_date_backtest.csv"
F_QTD_SCORE = ROOT / "data/processed/financials/quarter_to_date_scorecard.csv"

GROUPS = {"8542321010": "DRAM", "8542321030": "Flash", "8542323000": "Composite-chip ICs"}
GROUP_ORDER = ["DRAM", "Flash", "Composite-chip ICs", "Other"]


# ---------------------------------------------------------------- helpers
def clean(x):
    """Recursively turn NaN/inf/numpy scalars into JSON-safe values."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, (pd.Period,)):
        return str(x)
    if x is pd.NaT:
        return None
    return x


def rnd(x, n=4):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    p.write_text(json.dumps(clean(obj), ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                 encoding="utf-8")
    print(f"wrote {p.relative_to(ROOT)}  ({p.stat().st_size/1024:.1f} KB)")


def records(df, cols, digits=None):
    digits = digits or {}
    out = []
    for _, r in df.iterrows():
        out.append({c: (rnd(r[c], digits.get(c, 4)) if isinstance(r[c], (float, np.floating)) else r[c])
                    for c in cols})
    return out


# ---------------------------------------------------------------- exports
def build_exports():
    t = pd.read_csv(F_TOTAL)
    t["month"] = pd.PeriodIndex(t["month"], freq="M")
    t = t.set_index("month")
    full = pd.period_range(t.index.min(), t.index.max(), freq="M")
    assert len(full) == len(t), "gap in monthly_total"
    m = t[["value_usd", "weight_kg"]].copy()

    # 3-month rolling sums, then divide (as export_analysis.py)
    r3 = m.rolling(3, min_periods=3).sum()
    r3["usd_per_g"] = r3.value_usd / r3.weight_kg / 1000
    r3["yoy_uv_pct"] = (r3.usd_per_g / r3.usd_per_g.shift(12) - 1) * 100
    r3["yoy_wt_pct"] = (r3.weight_kg / r3.weight_kg.shift(12) - 1) * 100
    r3["yoy_val_pct"] = (r3.value_usd / r3.value_usd.shift(12) - 1) * 100
    r3["uv_mom3_pct"] = (r3.usd_per_g / r3.usd_per_g.shift(3) - 1) * 100

    monthly = pd.DataFrame({
        "month": [str(p) for p in m.index],
        "value_usd": m.value_usd.values,
        "weight_kg": m.weight_kg.values,
        "usd_per_g": (m.value_usd / m.weight_kg / 1000).values,
        "source": t.source.values,
        "r3_value_usd": r3.value_usd.values,
        "r3_weight_kg": r3.weight_kg.values,
        "r3_usd_per_g": r3.usd_per_g.values,
        "r3_yoy_uv_pct": r3.yoy_uv_pct.values,
        "r3_yoy_wt_pct": r3.yoy_wt_pct.values,
        "r3_yoy_val_pct": r3.yoy_val_pct.values,
        "r3_uv_mom3_pct": r3.uv_mom3_pct.values,
    })

    # Quarterly: sum the 3 months, then divide; YoY log split
    g = m.groupby(m.index.asfreq("Q"))
    q = g.sum(min_count=1)
    q.loc[g.size() != 3] = np.nan
    q["usd_per_g"] = q.value_usd / q.weight_kg / 1000
    q["yoy_value_pct"] = (q.value_usd / q.value_usd.shift(4) - 1) * 100
    q["yoy_weight_pct"] = (q.weight_kg / q.weight_kg.shift(4) - 1) * 100
    q["yoy_uv_pct"] = (q.usd_per_g / q.usd_per_g.shift(4) - 1) * 100
    q["dln_value"] = np.log(q.value_usd / q.value_usd.shift(4))
    q["dln_weight"] = np.log(q.weight_kg / q.weight_kg.shift(4))
    q["dln_unitvalue"] = np.log(q.usd_per_g / q.usd_per_g.shift(4))
    q["uv_qoq_pct"] = (q.usd_per_g / q.usd_per_g.shift(1) - 1) * 100

    # check against the analysis output
    ref = pd.read_csv(F_QDEC)
    ref["q"] = pd.PeriodIndex(ref.month, freq="Q")
    ref = ref.set_index("q")
    for c in ["value_usd", "weight_kg", "usd_per_g", "dln_weight", "dln_unitvalue"]:
        a, b = q[c].reindex(ref.index), ref[c]
        ok = ((a - b).abs() <= 1e-6 * b.abs().clip(lower=1)) | (a.isna() & b.isna())
        assert ok.all(), f"quarterly mismatch in {c}"
    print("check: quarterly sums/unit values match quarterly_decomposition.csv")

    quarterly = q.reset_index().rename(columns={"index": "quarter", "month": "quarter"})
    quarterly["quarter"] = quarterly["quarter"].astype(str)
    quarterly = quarterly.dropna(subset=["value_usd"])
    return monthly, quarterly, r3, q


def build_lines():
    L = pd.read_csv(F_LINES, dtype={"hs10": str})
    L["month"] = pd.PeriodIndex(L["month"], freq="M")
    L["group"] = L.hs10.map(GROUPS).fillna("Other")
    gm = L.groupby(["month", "group"])[["value_usd", "weight_kg"]].sum().reset_index()
    months = sorted(gm.month.unique())

    def series(df, key):
        out = {}
        for grp in GROUP_ORDER:
            d = df[df.group == grp].set_index(key).reindex(sorted(df[key].unique()))
            out[grp] = [{"p": str(k), "v": rnd(r.value_usd, 0), "w": rnd(r.weight_kg, 0),
                         "uv": rnd(r.value_usd / r.weight_kg / 1000, 4) if r.weight_kg else None}
                        for k, r in d.iterrows()]
        return out

    # monthly as 3-month rolling sums per group (sum first, then divide), plus raw monthly
    roll = []
    for grp in GROUP_ORDER:
        d = gm[gm.group == grp].set_index("month").reindex(months)[["value_usd", "weight_kg"]]
        rr = d.rolling(3, min_periods=3).sum()
        rr["group"] = grp
        rr["month"] = rr.index
        roll.append(rr.reset_index(drop=True))
    roll = pd.concat(roll)

    gm["quarter"] = gm.month.dt.asfreq("Q") if hasattr(gm.month, "dt") else gm.month.map(lambda p: p.asfreq("Q"))
    nmon = gm.groupby("quarter").month.nunique()
    gq = gm.groupby(["quarter", "group"])[["value_usd", "weight_kg"]].sum().reset_index()
    gq = gq[gq.quarter.map(nmon) == 3]

    # Names of each HS10 line (Korean, as in the KCS file) for the method table
    names = L.groupby("hs10").agg(name=("name", "first"), group=("group", "first")).reset_index()
    return {
        "groups": GROUP_ORDER,
        "monthly": series(gm, "month"),
        "monthly_r3": series(roll.dropna(subset=["value_usd"]), "month"),
        "quarterly": series(gq, "quarter"),
        "hs10": names.to_dict("records"),
    }, gq


# ---------------------------------------------------------------- prices
def build_contract():
    p = pd.read_csv(F_DDR4)
    p["month"] = pd.PeriodIndex(p.month, freq="M")
    p = p.set_index("month")
    full = pd.period_range(p.index.min(), p.index.max(), freq="M")
    s = p.avg_usd.reindex(full)
    mom = (s / s.shift(1) - 1) * 100
    mom3 = (s / s.shift(3) - 1) * 100
    accel = mom3 - mom3.shift(1)
    for name, a, b in [("mom_pct", mom, p.mom_pct), ("mom3_pct", mom3, p.mom3_pct), ("accel_pp", accel, p.accel_pp)]:
        b = b.reindex(full)
        ok = ((a - b).abs() < 1e-9) | (a.isna() & b.isna())
        assert ok.all(), f"contract {name} mismatch"
    print("check: DDR4 mom/mom3/accel match ddr4_8gb_contract_monthly.csv")

    raw = pd.read_csv(F_DDR4_RAW)
    raw = raw[raw.item == "DDR4 8Gb 1Gx8"].copy()
    raw["month"] = pd.PeriodIndex(raw.month, freq="M")
    raw = raw.set_index("month").reindex(full)
    assert ((raw.avg_usd - s).abs().fillna(0) < 1e-9).all(), "raw vs processed contract price mismatch"

    rows = []
    for per in full:
        r = raw.loc[per]
        rows.append({"month": str(per), "avg_usd": rnd(s[per], 4), "mom_pct": rnd(mom[per], 3),
                     "mom3_pct": rnd(mom3[per], 3), "accel_pp": rnd(accel[per], 3),
                     "source": r.source if isinstance(r.source, str) else None,
                     "source_url": r.source_url if isinstance(r.source_url, str) else None,
                     "publication_date": r.publication_date if isinstance(r.publication_date, str) else None,
                     "quote": r.source_quote if isinstance(r.source_quote, str) else None,
                     "flag": r.flag if isinstance(r.flag, str) else None})
    return rows, s, mom3


def build_retail():
    d = pd.read_csv(F_RETAIL)
    out = {}
    for name in ["DDR4 (Keepa)", "DDR5 (Keepa)"]:
        x = d[d.series == name].sort_values("date")
        out[name] = [{"month": r.date[:7], "usd_per_gb": rnd(r.value, 5), "n": int(r.n_samples) if pd.notna(r.n_samples) else None}
                     for r in x.itertuples()]
        print(f"retail {name}: {len(x)} points, {x.date.min()[:7]} .. {x.date.max()[:7]}")
    return out


# ---------------------------------------------------------------- financials / quarter-to-date forecast
def build_financials():
    raw = pd.read_csv(F_FIN_RAW)
    raw["q"] = pd.PeriodIndex(raw.quarter, freq="Q")
    raw = raw.set_index("q")
    fin = pd.read_csv(F_FIN)
    fin["q"] = pd.PeriodIndex(fin.quarter, freq="Q")
    fin = fin.set_index("q")

    diffs = (raw.revenue_krw_m - fin.revenue_krw_m).abs()
    rev_diff = [{"quarter": str(k), "stockanalysis": int(raw.revenue_krw_m[k]), "company_file": int(fin.revenue_krw_m[k])}
                for k in diffs[diffs > 0].index]
    note = str(fin.note.iloc[-1])
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(fin.source.iloc[-1]))
    release_date = m.group(1) if m else None
    last_q = fin.index[-1]

    # Quarter-to-date backtest (written by src/analysis/quarter_to_date_forecast.py, KRW trillion)
    bt = pd.read_csv(F_QTD)
    bt["q"] = pd.PeriodIndex(bt.quarter, freq="Q")
    bt = bt.set_index("q")
    rev_tn = fin.revenue_krw_m / 1e6  # same revenue file the forecast uses
    assert (bt.actual - rev_tn.reindex(bt.index)).abs().max() < 1e-9, "QTD actuals differ from skhynix_quarterly.csv"
    prev = rev_tn.shift(1).reindex(bt.index)

    # Scorecard recomputed from the backtest rows, then checked against the analysis scorecard
    ref = pd.read_csv(F_QTD_SCORE, index_col=0)
    score = []
    for c, label in [("m1", "after month 1"), ("m2", "after month 2"), ("m3", "after month 3 (full quarter)"),
                     ("baseline", "baseline: last growth repeats")]:
        e = (bt[c] / bt.actual - 1) * 100
        hits = int((np.sign(bt[c] - prev) == np.sign(bt.actual - prev)).sum())
        row = {"model": c, "label": label, "mape": e.abs().mean(), "median_ape": e.abs().median(),
               "worst_ape": e.abs().max(), "hits": hits, "n": int(e.notna().sum())}
        r = ref.loc[label]
        assert abs(round(row["mape"], 1) - r["MAPE_%"]) < 0.051, (c, row["mape"], r["MAPE_%"])
        assert abs(round(row["worst_ape"], 1) - r["worst_%"]) < 0.051, (c, "worst")
        assert abs(hits / row["n"] * 100 - r["up/down_hit_%"]) < 0.051, (c, "hit")
        score.append({k: (rnd(v, 2) if isinstance(v, float) else v) for k, v in row.items()})
    print("check: quarter-to-date scorecard matches quarter_to_date_scorecard.csv")

    quarters = []
    for k in fin.index:
        r = {"quarter": str(k), "revenue_krw_m": int(fin.revenue_krw_m[k]),
             "op_krw_m": int(fin.operating_profit_krw_m[k]),
             "preliminary": bool(k == last_q and "prelim" in note.lower())}
        if k in bt.index:
            b = bt.loc[k]
            r.update({"prev_tn": rnd(prev[k], 4), "actual_tn": rnd(b.actual, 4),
                      **{c: rnd(b[c], 4) for c in ["m1", "m2", "m3", "baseline"]},
                      **{c + "_err": rnd((b[c] / b.actual - 1) * 100, 2) for c in ["m1", "m2", "m3", "baseline"]}})
        quarters.append(r)

    # Lead time before results, assuming customs publishes a month on the 1st of the next month
    # (the assumption stated in src/analysis/nowcast.py). Only the latest release date is in the data.
    lead = {}
    if release_date:
        q0 = last_q.asfreq("M", "s")
        for kk in (1, 2, 3):
            pub = (q0 + kk).start_time.date()
            lead[f"m{kk}"] = {"customs_public": str(pub), "days": (date.fromisoformat(release_date) - pub).days}
    lb = bt.loc[last_q]
    return {
        "quarters": quarters,
        "scorecard": score,
        "last": {"quarter": str(last_q), "actual_tn": rnd(lb.actual, 4),
                 **{c: rnd(lb[c], 4) for c in ["m1", "m2", "m3", "baseline"]},
                 **{c + "_err": rnd((lb[c] / lb.actual - 1) * 100, 2) for c in ["m1", "m2", "m3", "baseline"]},
                 "earnings_release_date": release_date, "lead": lead},
        "backtest_first": str(bt.index[0]), "backtest_last": str(bt.index[-1]),
        "revenue_file_differences": rev_diff,
    }


# ---------------------------------------------------------------- satellite (M15X)
SAT_DIR = ROOT / "data/processed/satellite/m15x"
SAT_OUT = ROOT / "docs/assets/sat"
SAT_BOUNDS = {"lon_min": 127.4240, "lon_max": 127.4440, "lat_min": 36.6480, "lat_max": 36.6620}
M15X_FOOTPRINT = {"lon_min": 127.4330, "lon_max": 127.4349, "lat_min": 36.6546, "lat_max": 36.6565}
# Milestones as stated in data/processed/satellite/m15x/README.md (text, not a data file).
# "date" only positions the marker on the strip; "when" is the precision the source gives.
MILESTONES = [
    {"date": "2022-10", "when": "Oct 2022", "label": "Groundbreaking", "detail": "Groundbreaking, Oct 2022",
     "source": "ETNews / Asia Economy, Sep 2022", "kind": "reported"},
    {"date": "2025-05", "when": "~2025Q2", "label": "Roof complete", "detail": "Roof visibly complete, around 2025Q2",
     "source": "Sentinel-2 imagery (this analysis)", "kind": "observed"},
    {"date": "2025-10", "when": "Oct 2025", "label": "Cleanroom opened", "detail": "Cleanroom opened Oct 2025; equipment installed in sequence",
     "source": "TrendForce", "kind": "reported"},
    {"date": "2026-02", "when": "early 2026", "label": "1b DRAM (HBM) start", "detail": "1b DRAM for HBM planned to start, early 2026",
     "source": "Planned, as reported", "kind": "planned"},
]


def png_size(p):
    b = p.read_bytes()[:24]
    assert b[:8] == b"\x89PNG\r\n\x1a\n", p
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def build_satellite():
    import shutil
    q = pd.read_csv(SAT_DIR / "m15x_quarterly.csv")
    SAT_OUT.mkdir(parents=True, exist_ok=True)
    frames, size = [], None
    for r in q.itertuples():
        src = SAT_DIR / r.chip
        assert src.exists(), src
        s = png_size(src)
        assert size is None or s == size, f"chip size differs: {r.chip}"
        size = s
        shutil.copyfile(src, SAT_OUT / r.chip)
        # NDVI / NDBI / brightness deliberately NOT exported (too noisy; not claimed)
        frames.append({"quarter": r.quarter, "date": r.date, "scene": r.scene,
                       "site_clear": rnd(r.site_clear, 2), "img": f"assets/sat/{r.chip}"})
    shutil.copyfile(SAT_DIR / "contact_sheet.png", SAT_OUT / "contact_sheet.png")
    print(f"copied {len(frames)} chips + contact sheet -> {SAT_OUT.relative_to(ROOT)}  ({size[0]}x{size[1]})")
    return {"frames": frames, "width": size[0], "height": size[1], "bounds": SAT_BOUNDS,
            "footprint": M15X_FOOTPRINT, "milestones": MILESTONES,
            "source": "Sentinel-2 L2A, 10 m, Element84 Earth Search STAC; footprint OpenStreetMap way 1467790692",
            "min_site_clear": min(f["site_clear"] for f in frames),
            "site_pixels": int(q.site_pixels.median()),
            "extent_km": {"ew": (SAT_BOUNDS["lon_max"] - SAT_BOUNDS["lon_min"]) * 111.32 * math.cos(math.radians((SAT_BOUNDS["lat_min"] + SAT_BOUNDS["lat_max"]) / 2)),
                          "ns": (SAT_BOUNDS["lat_max"] - SAT_BOUNDS["lat_min"]) * 110.95}}


# ---------------------------------------------------------------- main
def build_hbm():
    """HBM proxy: Korean memory exports by destination (Taiwan = TSMC CoWoS packaging), from src/analysis/hbm_proxy.py."""
    d = pd.read_csv(ROOT / "data/processed/korean_exports/quarterly_by_destination.csv")
    t = pd.read_csv(ROOT / "data/processed/korean_exports/taiwan_by_line_quarterly.csv")
    out = {"partners": ["Taiwan", "China", "Hong Kong", "Vietnam", "Rest"], "quarterly": {}}
    for prt in out["partners"]:
        x = d[d.partner == prt].sort_values("quarter")
        out["quarterly"][prt] = [{"q": r["quarter"], "v": rnd(r["value_usd"], 0), "w": rnd(r["weight_kg"], 0),
                                  "uv": rnd(r["usd_per_g"], 3), "share": rnd(r["value_share_%"], 2)} for r in x.to_dict("records")]
    out["taiwan_lines"] = [{"q": r["quarter"], "line": r["line"], "v": rnd(r["value_usd"], 0), "uv": rnd(r["usd_per_g"], 3),
                            "share": rnd(r["share_of_taiwan_value_%"], 2)} for r in t.to_dict("records")]
    tw = d[d.partner == "Taiwan"].set_index("quarter").sort_index()
    ch = d[d.partner == "China"].set_index("quarter").sort_index()
    lq = tw.index[-1]
    pq = tw.index[list(tw.index).index(lq) - 4]
    comp = t[t.line == "Composite-chip ICs"].set_index("quarter")
    pre = tw.loc[:"2024Q1"]
    out["headline"] = {
        "last_q": lq, "prior_q": pq, "value_usd": tw.value_usd[lq], "yoy_value_pct": (tw.value_usd[lq] / tw.value_usd[pq] - 1) * 100,
        "usd_per_g": tw.usd_per_g[lq], "usd_per_g_prior": tw.usd_per_g[pq],
        "china_usd_per_g": ch.usd_per_g[lq], "share_last": tw["value_share_%"][lq],
        "share_pre2024_avg": pre.loc["2021Q1":]["value_share_%"].mean(), "share_peak": tw["value_share_%"].max(),
        "share_peak_q": tw["value_share_%"].idxmax(),
        "comp_first_q": comp.index[0], "comp_uv_first": comp.usd_per_g.iloc[0], "comp_uv_last": comp.usd_per_g.iloc[-1],
        "comp_share_of_taiwan_last": comp["share_of_taiwan_value_%"].iloc[-1],
    }
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    monthly, quarterly, r3, q = build_exports()
    lines, gq = build_lines()
    contract, cs, cmom3 = build_contract()
    retail = build_retail()
    fin = build_financials()
    sat = build_satellite()

    write("exports_monthly.json", records(monthly, list(monthly.columns)))
    write("exports_quarterly.json", records(quarterly, ["quarter", "value_usd", "weight_kg", "usd_per_g",
                                                        "yoy_value_pct", "yoy_weight_pct", "yoy_uv_pct",
                                                        "dln_value", "dln_weight", "dln_unitvalue", "uv_qoq_pct"]))
    write("lines.json", lines)
    write("contract.json", contract)
    write("retail.json", retail)
    write("financials.json", fin)
    write("satellite.json", sat)
    hbm = build_hbm()
    write("hbm.json", hbm)
    print(f"  HBM proxy {hbm['headline']['last_q']}: Taiwan ${hbm['headline']['value_usd']/1e9:.1f}bn, "
          f"${hbm['headline']['usd_per_g']:.0f}/g vs China ${hbm['headline']['china_usd_per_g']:.0f}/g; "
          f"composite line to Taiwan ${hbm['headline']['comp_uv_first']:.0f} -> ${hbm['headline']['comp_uv_last']:.0f}/g")

    # ------------------------------------------------ headline numbers (all computed here)
    lq = q.dropna(subset=["value_usd"]).index[-1]
    pq = lq - 4
    gqi = gq.set_index(["quarter", "group"])
    dram_uv = lambda k: gqi.loc[(k, "DRAM")].value_usd / gqi.loc[(k, "DRAM")].weight_kg / 1000
    comp_uv = lambda k: gqi.loc[(k, "Composite-chip ICs")].value_usd / gqi.loc[(k, "Composite-chip ICs")].weight_kg / 1000
    lq_share = gq[gq.quarter == lq].set_index("group").value_usd
    pq_share = gq[gq.quarter == pq].set_index("group").value_usd
    contrib = ((lq_share - pq_share) / (lq_share.sum() - pq_share.sum()) * 100).to_dict()

    cvalid = cs.dropna()
    m3 = cmom3.dropna()
    uvm = r3.uv_mom3_pct.dropna()
    first_c = cvalid.index[0]
    headline = {
        "exports": {
            "quarter": str(lq), "prior_quarter": str(pq),
            "value_usd": q.value_usd[lq], "value_usd_prior": q.value_usd[pq],
            "value_multiple": q.value_usd[lq] / q.value_usd[pq],
            "yoy_value_pct": q.yoy_value_pct[lq], "yoy_weight_pct": q.yoy_weight_pct[lq],
            "usd_per_g": q.usd_per_g[lq], "usd_per_g_prior": q.usd_per_g[pq],
            "dln_value": q.dln_value[lq], "dln_weight": q.dln_weight[lq], "dln_unitvalue": q.dln_unitvalue[lq],
            "share_from_unitvalue_pct": q.dln_unitvalue[lq] / q.dln_value[lq] * 100,
            "dram_usd_per_g": dram_uv(lq), "dram_usd_per_g_prior": dram_uv(pq),
            "composite_usd_per_g": comp_uv(lq), "composite_usd_per_g_prior": comp_uv(pq),
            "line_contribution_pct": contrib,
            "yoy_uv_pct": q.yoy_uv_pct[lq],
            "dram_uv_qoq_pct": (dram_uv(lq) / dram_uv(lq - 1) - 1) * 100,
        },
        "contract": {
            "first_month": str(first_c), "first_usd": cvalid.iloc[0],
            "last_month": str(cvalid.index[-1]), "last_usd": cvalid.iloc[-1],
            "multiple": cvalid.iloc[-1] / cvalid.iloc[0],
            "mom3_peak_pct": m3.max(), "mom3_peak_month": str(m3.idxmax()),
            "mom3_last_pct": m3.iloc[-1], "mom3_last_month": str(m3.index[-1]),
            "mom_last_pct": ((cvalid.iloc[-1] / cvalid.iloc[-2]) - 1) * 100,
            # price path through the M15X ramp (1b DRAM start planned early 2026)
            "ramp_from_month": "2026-03", "ramp_from_usd": cs[pd.Period("2026-03", "M")],
        },
        "export_uv_momentum": {
            "peak_pct": uvm.max(), "peak_month": str(uvm.idxmax()),
            "last_pct": uvm.iloc[-1], "last_month": str(uvm.index[-1]),
        },
    }
    meta = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": "2026-11-08",
        "series": {
            "korean_exports_hs854232": {"first": monthly.month.iloc[0], "last": monthly.month.iloc[-1],
                                        "source": "UN Comtrade (2015-01..2021-09), Korea Customs Service (2021-10..)",
                                        "splice": "2021-10"},
            "hs10_lines": {"first": str(min(gq.quarter)), "last_month": str(pd.read_csv(F_LINES).month.max()),
                           "source": "Korea Customs Service"},
            "ddr4_8gb_contract": {"first": str(first_c), "last": str(cvalid.index[-1]),
                                  "missing_months": [str(k) for k in cs.index[cs.isna()]],
                                  "source": "Korean press reports of DRAMeXchange/TrendForce monthly fixed prices"},
            "retail_keepa": {k: {"first": v[0]["month"], "last": v[-1]["month"], "n": len(v)} for k, v in retail.items()},
            "hynix_financials": {"first": fin["quarters"][0]["quarter"], "last": fin["quarters"][-1]["quarter"],
                                 "last_preliminary": fin["quarters"][-1]["preliminary"],
                                 "source": "stockanalysis.com (K-IFRS consolidated); last quarter company preliminary release"},
            "qtd_backtest": {"first": fin["backtest_first"], "last": fin["backtest_last"], "n": fin["scorecard"][0]["n"]},
            "m15x_sentinel2": {"first": sat["frames"][0]["quarter"], "last": sat["frames"][-1]["quarter"],
                               "last_scene_date": sat["frames"][-1]["date"], "n": len(sat["frames"]),
                               "source": sat["source"]},
        },
        "headline": headline,
    }
    write("meta.json", meta)

    # ------------------------------------------------ print headline figures
    e, c, u, L = headline["exports"], headline["contract"], headline["export_uv_momentum"], fin["last"]
    print("\nHEADLINE FIGURES")
    print(f"  exports {e['quarter']} vs {e['prior_quarter']}: value x{e['value_multiple']:.2f} ({e['yoy_value_pct']:+.1f}%), "
          f"weight {e['yoy_weight_pct']:+.1f}%, $/g {e['usd_per_g_prior']:.2f} -> {e['usd_per_g']:.2f}, "
          f"unit-value share of log growth {e['share_from_unitvalue_pct']:.0f}%")
    print(f"  DRAM line $/g {e['dram_usd_per_g_prior']:.2f} -> {e['dram_usd_per_g']:.2f}; composite {e['composite_usd_per_g_prior']:.2f} -> {e['composite_usd_per_g']:.2f}")
    print(f"  line contribution to value growth: " + ", ".join(f"{k} {v:.0f}%" for k, v in e["line_contribution_pct"].items()))
    print(f"  DDR4 8Gb {c['first_month']} ${c['first_usd']:.2f} -> {c['last_month']} ${c['last_usd']:.2f} (x{c['multiple']:.1f})")
    print(f"  contract mom3 peak {c['mom3_peak_pct']:.1f}% ({c['mom3_peak_month']}) -> {c['mom3_last_pct']:.1f}% ({c['mom3_last_month']})")
    print(f"  M15X ramp window: DDR4 ${c['ramp_from_usd']:.2f} ({c['ramp_from_month']}) -> ${c['last_usd']:.2f} ({c['last_month']})")
    print(f"  DRAM line $/g QoQ {e['dram_uv_qoq_pct']:+.1f}%, export UV YoY {e['yoy_uv_pct']:+.1f}%")
    print(f"  export UV mom3 peak {u['peak_pct']:.1f}% ({u['peak_month']}) -> {u['last_pct']:.1f}% ({u['last_month']})")
    print(f"  QTD forecast {L['quarter']}: m1 {L['m1']:.1f}tn ({L['m1_err']:+.1f}%), m2 {L['m2']:.1f}tn ({L['m2_err']:+.1f}%), "
          f"m3 {L['m3']:.1f}tn ({L['m3_err']:+.1f}%), actual {L['actual_tn']:.2f}tn; lead days " +
          ", ".join(f"{k} {v['days']}" for k, v in L["lead"].items()))
    print("  QTD scorecard: " + "; ".join(f"{s['model']} MAPE {s['mape']:.1f}% worst {s['worst_ape']:.1f}% hits {s['hits']}/{s['n']}"
                                         for s in fin["scorecard"]))
    if fin["revenue_file_differences"]:
        print(f"  NOTE revenue differs between files: {fin['revenue_file_differences']}")


if __name__ == "__main__":
    main()
