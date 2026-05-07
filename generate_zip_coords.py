"""
One-time script: downloads Census ZCTA 2020 shapefile, computes a
representative_point() for each polygon (guaranteed on land), and saves
a lightweight zip_coords.csv for use by the Streamlit app.

Run: python3 generate_zip_coords.py
"""
import geopandas as gpd
import pandas as pd
import requests
import zipfile
import io
import warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www2.census.gov/geo/tiger/TIGER2020/ZCTA520/tl_2020_us_zcta520.zip"
OUT = "zip_coords.csv"

import tempfile, os

CACHE_ZIP = "/tmp/zcta2020.zip"
if not os.path.exists(CACHE_ZIP):
    print("Downloading Census ZCTA 2020 shapefile (~500 MB)…")
    r = requests.get(URL, verify=False, timeout=600)
    r.raise_for_status()
    with open(CACHE_ZIP, "wb") as f:
        f.write(r.content)
    print(f"Saved {os.path.getsize(CACHE_ZIP) / 1_048_576:.1f} MB to {CACHE_ZIP}")
else:
    print(f"Using cached download at {CACHE_ZIP}")

print("Extracting and reading shapefile…")
with tempfile.TemporaryDirectory() as tmpdir:
    zf = zipfile.ZipFile(CACHE_ZIP)
    zf.extractall(tmpdir)
    shp = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".shp")][0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf = gpd.read_file(shp)

print(f"Loaded {len(gdf)} ZCTAs. Computing representative points…")
gdf["rep"] = gdf.geometry.representative_point()
gdf["lat"] = gdf["rep"].y
gdf["lon"] = gdf["rep"].x

out = gdf[["ZCTA5CE20", "lat", "lon"]].rename(columns={"ZCTA5CE20": "zip"}).copy()
out["zip"] = out["zip"].str.zfill(5)
out = out.sort_values("zip").reset_index(drop=True)
out.to_csv(OUT, index=False)
print(f"Saved {len(out)} ZIP codes to {OUT}")

# Quick sanity check for 10004
row = out[out["zip"] == "10004"]
if not row.empty:
    print(f"\nSanity check 10004: lat={row.iloc[0]['lat']:.5f}, lon={row.iloc[0]['lon']:.5f}")
