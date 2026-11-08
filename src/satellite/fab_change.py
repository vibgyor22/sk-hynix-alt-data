"""Land converted from vegetation to cleared/built, 2022 vs 2026, at memory fab sites.

Same recipe for every site: Sentinel-2 L2A (10 m), May-Oct median composite of cloud-free
pixels in 2022 and in 2026. A pixel counts as "converted" if it was vegetated in 2022
(NDVI > 0.35) and is not vegetated in 2026 (NDVI < 0.20). Output is hectares plus
side-by-side true-colour chips. Run: python -I src/satellite/fab_change.py
"""
import json, os
from pathlib import Path
import numpy as np
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                  CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/assets/sat"
SITES = {  # name: (lat, lon, half-width km)
    "m15x":      ("SK hynix M15X, Cheongju", 36.6555, 127.4340, 1.4),
    "yongin":    ("SK hynix Yongin cluster", 37.1523, 127.3190, 2.5),
    "pyeongtaek":("Samsung Pyeongtaek", 37.0356, 127.0602, 2.5),
    "boise":     ("Micron Boise, Idaho", 43.5275, -116.1444, 1.8),
}
PERIODS = {"2022": ("2022-05-01", "2022-10-31"), "2026": ("2026-05-01", "2026-10-31")}
BANDS = ["red", "green", "blue", "nir"]


def bbox(lat, lon, km):
    dlat = km / 111.0; dlon = km / (111.0 * np.cos(np.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def read(href, bb, shape=None):
    with rasterio.open(href) as s:
        b = transform_bounds("EPSG:4326", s.crs, *bb)
        w = from_bounds(*b, transform=s.transform)
        kw = {"out_shape": shape, "resampling": rasterio.enums.Resampling.nearest} if shape else {}
        return s.read(1, window=w, boundless=True, fill_value=0, **kw).astype("float32")


def composite(cat, bb, d0, d1, maxn=14):
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bb, datetime=f"{d0}/{d1}",
                            query={"eo:cloud_cover": {"lt": 50}}).items())
    items.sort(key=lambda i: i.properties["eo:cloud_cover"])
    stack, used = [], []
    ref = None
    for it in items[:maxn]:
        try:
            if ref is None:
                ref = read(it.assets["red"].href, bb).shape
            scl = read(it.assets["scl"].href, bb, ref)
            ok = np.isin(scl, [4, 5, 6, 7])
            arr = np.stack([read(it.assets[b].href, bb, ref) for b in BANDS]) / 10000.0
            arr[:, ~ok] = np.nan
            stack.append(arr); used.append(it.id)
        except Exception as e:
            print("skip", it.id, str(e)[:80])
    comp = np.nanmedian(np.stack(stack), axis=0)
    return comp, used


def rgb8(comp):
    img = np.clip(comp[:3][::-1].transpose(1, 2, 0) / 0.28, 0, 1) ** 0.8
    return (np.nan_to_num(img) * 255).astype("uint8")


def main():
    cat = Client.open("https://earth-search.aws.element84.com/v1")
    res = {}
    for key, (name, lat, lon, km) in SITES.items():
        bb = bbox(lat, lon, km)
        comps = {}
        for y, (a, b) in PERIODS.items():
            comps[y], used = composite(cat, bb, a, b)
            print(key, y, len(used), "scenes")
        ndvi = {y: (c[3] - c[0]) / (c[3] + c[0] + 1e-6) for y, c in comps.items()}
        conv = (ndvi["2022"] > 0.35) & (ndvi["2026"] < 0.20)
        valid = np.isfinite(ndvi["2022"]) & np.isfinite(ndvi["2026"])
        from scipy import ndimage
        lab, n = ndimage.label(ndimage.binary_closing(conv, iterations=2))
        big = lab == (1 + int(np.argmax(ndimage.sum(conv, lab, range(1, n + 1))))) if n else conv
        conv = conv & ndimage.binary_dilation(big, iterations=1)   # keep the single largest converted block
        ha = float(conv.sum()) * 100 / 10000.0       # 10 m x 10 m = 100 m2 per pixel
        res[key] = {"name": name, "hectares": round(ha, 1), "area_km2": round((2 * km) ** 2, 1),
                    "valid_share": round(float(valid.mean()), 3), "block": "largest single converted block"}
        im = [rgb8(comps["2022"]), rgb8(comps["2026"])]
        ov = rgb8(comps["2026"]).copy(); ov[conv] = (0.55 * ov[conv] + 0.45 * np.array([255, 60, 30])).astype("uint8")
        im.append(ov)
        strip = np.concatenate(im, axis=1)
        Image.fromarray(strip).resize((strip.shape[1] * 2, strip.shape[0] * 2), Image.LANCZOS).save(OUT / f"fab_{key}.jpg", quality=88)
        print(key, res[key])
    (ROOT / "docs/data/fab_change.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
