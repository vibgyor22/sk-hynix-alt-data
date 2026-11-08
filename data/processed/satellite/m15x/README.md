# M15X (Cheongju) satellite check

**Question for the pitch:** is SK hynix's new M15X DRAM fab physically built, and is that new supply arriving now or later?

**Data**
- Sentinel-2 L2A at 10 m, from the Element84 Earth Search STAC.
- One scene per quarter, 2022Q1 to 2026Q4, chosen as the clearest scene over the site itself using SCL. Every quarter has a scene with at least 98% of the site clear.
- Site footprint from OpenStreetMap way 1467790692, "M15X DRAM 공장", next to M15.
- Code: `src/satellite/m15x_sentinel.py`.

**What the images show** (see `contact_sheet.png`; the white box marks the M15X footprint)
- **2022 to 2024:** mixed texture inside the footprint, consistent with site works and a structure going up.
- **From 2025Q2:** a uniform bright roof fills the footprint and visually matches the finished M15 roof beside it.
- This fits the reported timeline:
  - groundbreaking in Oct 2022 (ETNews / Asia Economy, Sep 2022);
  - cleanroom opened in Oct 2025, with equipment installed in sequence (TrendForce);
  - 1b DRAM for HBM planned to start there in early 2026.

**Interpretation:** the building shell was finished by roughly mid-2025, so M15X supply is ramping in 2026, not still to come. Prices have kept rising through that ramp (DDR4 8Gb contract $13 → $27.50, Mar to Oct 2026). That says demand has so far absorbed M15X's new output.

**What did not work:** NDVI, NDBI, and brightness relative to the M15 roof are all noisy, because the site is only about 350 pixels and snow, sun angle and roads mix in. No quantitative capacity measure is claimed from them. The saved files `m15x_quarterly.csv` and `m15x_roof_metric.csv` are kept for transparency only.

**Limits:** 10 m imagery shows the building, not tools, cleanroom fit-out, yields or wafer starts.

**An observation, not verified:** a large area north-west of M15 was cleared in 2023–24 and shows new structures in 2025–26. It may be the packaging fab SK hynix confirmed for Cheongju in Jan 2026 (Korea Times), but that has not been checked.
