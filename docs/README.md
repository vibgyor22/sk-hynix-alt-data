# SK hynix alt-data site

Static research site (plain HTML/CSS/JS + D3 from a CDN). No build step.

```
docs/
  index.html
  assets/style.css, assets/app.js
  assets/sat/        Sentinel-2 chips of the M15X site (copied by the export script)
  data/*.json        generated; do not edit by hand
```

## Regenerate the data

From the project root:

```
python -I src/site/export_site_data.py
```

The script reads the processed/raw files under `data/` (read-only). It recomputes the derived metrics (period sums first, then divide), checks them against the analysis outputs, writes `docs/data/*.json`, copies the satellite chips to `docs/assets/sat/`, and prints the headline figures.

To refresh the forecast inputs first, run the analysis scripts:

```
python -I src/analysis/export_analysis.py
python -I src/analysis/quarter_to_date_forecast.py
```

## Preview locally

```
python -m http.server -d docs 8000
```

Then open http://localhost:8000. Opening `index.html` straight from disk will not work, because the browser blocks `fetch()` of the JSON files over `file://`.

## Publish on GitHub Pages

1. Push the repository to GitHub with `docs/` on the `main` branch.
2. Go to Settings → Pages → Build and deployment → Source: Deploy from a branch.
3. Choose branch `main`, folder `/docs`, then Save.

All paths in the site are relative, so it works under `https://<user>.github.io/<repo>/`.
