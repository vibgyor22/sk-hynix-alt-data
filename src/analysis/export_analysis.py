"""Stage 1 analysis: year-on-year price/volume split of Korean memory exports (HS 854232).

Identity (exact for any sums):  ln(V1/V0) = ln(W1/W0) + ln(UV1/UV0),  UV = V / W
  V = export value (USD), W = export weight (kg), UV = "implied unit value" (USD per kg; shown per gram).
UV is NOT a chip price: product mix (e.g. HBM vs commodity DRAM) moves it too.
We sum V and W over the period FIRST and then divide, never average monthly unit values.
Run:  python -I src/analysis/export_analysis.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data/processed/korean_exports"


def decompose_yoy(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """df has month, value_usd, weight_kg. Returns period sums, unit value and YoY log split."""
    s = df.set_index("month")[["value_usd", "weight_kg"]]
    g = s.groupby(s.index.asfreq(freq))
    # A period with any missing month is left blank rather than summed over a gap.
    out = g.sum(min_count=1)
    out.loc[g.size() != (3 if freq == "Q" else 1)] = np.nan
    out["weight_t"] = out.weight_kg / 1000
    out["usd_per_g"] = out.value_usd / out.weight_kg / 1000
    lag = 4 if freq == "Q" else 12
    out["yoy_value_pct"] = (out.value_usd / out.value_usd.shift(lag) - 1) * 100
    out["dln_value"] = np.log(out.value_usd / out.value_usd.shift(lag))
    out["dln_weight"] = np.log(out.weight_kg / out.weight_kg.shift(lag))
    out["dln_unitvalue"] = np.log(out.usd_per_g / out.usd_per_g.shift(lag))
    out["weight_share"] = out.dln_weight / out.dln_value  # share of growth from volume (unstable if growth ~0)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    total = pd.read_csv(PROC / "monthly_total.csv")
    total["month"] = pd.PeriodIndex(total["month"], freq="M")

    # unit test of the identity (true by construction; it only guards against code bugs)
    q = decompose_yoy(total, "Q")
    chk = (q.dln_value - q.dln_weight - q.dln_unitvalue).abs().max()
    assert chk < 1e-9, chk
    q.to_csv(PROC / "quarterly_decomposition.csv")

    pd.set_option("display.width", 200)
    cols = ["value_usd", "weight_t", "usd_per_g", "yoy_value_pct", "dln_weight", "dln_unitvalue"]
    show = q[cols].copy()
    show["value_usd"] = (show.value_usd / 1e9).round(2)
    print("QUARTERLY (value in $bn, weight in tonnes, YoY log changes)")
    print(show.loc["2024Q1":].round(3).to_string())

    # Monthly: 3-month rolling sums, YoY
    m = total.set_index("month")[["value_usd", "weight_kg"]].copy()
    r3 = m.rolling(3, min_periods=3).sum()
    r3["usd_per_g"] = r3.value_usd / r3.weight_kg / 1000
    r3["yoy_uv_pct"] = (r3.usd_per_g / r3.usd_per_g.shift(12) - 1) * 100
    r3["yoy_wt_pct"] = (r3.weight_kg / r3.weight_kg.shift(12) - 1) * 100
    r3["uv_mom3_pct"] = (r3.usd_per_g / r3.usd_per_g.shift(3) - 1) * 100
    print("\nROLLING 3-MONTH (ending month shown)")
    print(r3.loc["2026-01":, ["usd_per_g", "yoy_uv_pct", "yoy_wt_pct", "uv_mom3_pct"]].round(1).to_string())

    # Line-level: which HS10 lines carry the value?
    L = pd.read_csv(PROC / "monthly_lines.csv")
    L["month"] = pd.PeriodIndex(L["month"], freq="M")
    L["grp"] = L.hs10.astype(str).map(lambda h: {"8542321010": "DRAM", "8542321030": "Flash", "8542323000": "Composite-chip ICs (MCP etc.)"}.get(h, "Other"))
    g = L.groupby(["month", "grp"])[["value_usd", "weight_kg"]].sum().reset_index()
    for a, b in [("2025-09", "2026-09"), ("2025-03", "2026-03")]:
        print(f"\nLINE CONTRIBUTION  {a} -> {b}")
        x = g[g.month == pd.Period(a, "M")].set_index("grp"); y = g[g.month == pd.Period(b, "M")].set_index("grp")
        t = pd.DataFrame({"value_a_bn": x.value_usd / 1e9, "value_b_bn": y.value_usd / 1e9,
                          "wt_a_t": x.weight_kg / 1e3, "wt_b_t": y.weight_kg / 1e3}).fillna(0)
        t["usd_g_a"] = t.value_a_bn * 1e9 / (t.wt_a_t * 1e6)
        t["usd_g_b"] = t.value_b_bn * 1e9 / (t.wt_b_t * 1e6)
        t["share_of_growth_%"] = (t.value_b_bn - t.value_a_bn) / (t.value_b_bn.sum() - t.value_a_bn.sum()) * 100
        print(t.round(2).to_string())


if __name__ == "__main__":
    main()
