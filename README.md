# SK hynix: alt-data thesis notes

Alternative-data checks on the SK hynix memory cycle: Korean customs exports (HS 854232), DRAM contract prices, an export-based revenue nowcast, and Sentinel-2 imagery of the M15X fab.

- **Site:** `docs/` (GitHub Pages). Regenerate the site data with `python -I src/site/export_site_data.py`.
- **Code:** `src/data/` (ingestion and cleaning), `src/analysis/` (decomposition, nowcast, quarter-to-date forecast), `src/satellite/` (Sentinel-2).
- **Data:** `data/raw/` holds the original files with provenance notes; `data/processed/` holds the derived tables.
