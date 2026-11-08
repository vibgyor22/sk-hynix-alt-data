"""Supply module: is SK hynix's M15X fab (Cheongju) physically built, and when?

Data: Sentinel-2 L2A (10 m, free) via the Element84 Earth Search STAC (AWS open data).
Site: OpenStreetMap way 1467790692 "M15X DRAM 공장" (construction),
      bbox lat 36.6546-36.6565, lon 127.4330-127.4349, next to the existing M15 fab.

For each calendar quarter we pick the clearest scene, judged on the site itself using the
Scene Classification Layer (SCL), not the whole tile. We then measure over the M15X footprint:
  NDVI = (B08-B04)/(B08+B04)   vegetation; falls when the site is cleared
  NDBI = (B11-B08)/(B11+B08)   built-up; rises as roofs and concrete appear
  brightness = mean visible reflectance
and save a greyscale image chip of the surrounding ~1.6 km for visual before/after.

Limits: 10 m pixels show the building shell, not tools, cleanroom fit-out or wafer output.
Run:  python -I src/satellite/m15x_sentinel.py
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                  CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/processed/satellite/m15x"
SITE = (127.4330, 36.6546, 127.4349, 36.6565)        # lon_min, lat_min, lon_max, lat_max (OSM)
CHIP = (127.4240, 36.6480, 127.4440, 36.6620)        # ~1.8 x 1.6 km context incl. M15 and older fabs
DATES = "2022-01-01/2026-11-07"
CLEAR_MIN = 0.98                                      # share of site pixels that must be clear
GOOD_SCL = {4, 5, 6, 7}                               # vegetation, bare, water, unclassified (no cloud/shadow)


def read(href, bounds_ll, out_shape=None):
    with rasterio.open(href) as src:
        b = transform_bounds("EPSG:4326", src.crs, *bounds_ll)
        w = from_bounds(*b, transform=src.transform)
        kw = {"out_shape": out_shape, "resampling": rasterio.enums.Resampling.nearest} if out_shape else {}
        return src.read(1, window=w, boundless=True, fill_value=0, **kw).astype("float32")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cat = Client.open("https://earth-search.aws.element84.com/v1")
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=SITE, datetime=DATES,
                            query={"eo:cloud_cover": {"lt": 30}}).items())
    print(f"candidate scenes: {len(items)}")
    df = pd.DataFrame({"item": items, "date": [pd.Timestamp(i.datetime).tz_localize(None) for i in items],
                       "tile_cloud": [i.properties["eo:cloud_cover"] for i in items]})
    df["quarter"] = df.date.dt.to_period("Q")
    rows = []
    for q, grp in df.sort_values("tile_cloud").groupby("quarter"):
        for _, r in grp.iterrows():
            it = r["item"]
            scl = read(it.assets["scl"].href, SITE)
            clear = np.isin(scl, list(GOOD_SCL)).mean() if scl.size else 0
            if clear < CLEAR_MIN:
                continue
            red, nir = read(it.assets["red"].href, SITE), read(it.assets["nir"].href, SITE)
            swir = read(it.assets["swir16"].href, SITE, out_shape=red.shape)  # 20 m band resampled to the 10 m grid
            grn, blu = read(it.assets["green"].href, SITE), read(it.assets["blue"].href, SITE)
            ndvi = np.nanmean((nir - red) / (nir + red + 1e-6))
            ndbi = np.nanmean((swir - nir) / (swir + nir + 1e-6))
            bright = np.nanmean((red + grn + blu) / 3) / 10000
            # greyscale context chip from the true-colour bands, same contrast stretch every quarter
            rgb = np.stack([read(it.assets[b].href, CHIP) for b in ("red", "green", "blue")])
            grey = np.clip(rgb.mean(0) / 2500 * 255, 0, 255).astype("uint8")
            fname = f"m15x_{q}_{r.date:%Y%m%d}.png"
            Image.fromarray(grey).resize((grey.shape[1] * 3, grey.shape[0] * 3), Image.NEAREST).save(OUT / fname)
            rows.append({"quarter": str(q), "date": r.date.date(), "scene": it.id, "site_clear": round(clear, 3),
                         "site_pixels": int(red.size), "ndvi": round(float(ndvi), 3), "ndbi": round(float(ndbi), 3),
                         "brightness": round(float(bright), 4), "chip": fname})
            print(rows[-1])
            break
        else:
            print(f"{q}: no scene with >= {CLEAR_MIN:.0%} clear site pixels")
    pd.DataFrame(rows).to_csv(OUT / "m15x_quarterly.csv", index=False)


if __name__ == "__main__":
    main()
