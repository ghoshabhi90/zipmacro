# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
streamlit run "streamlit_zip_code_mapper_app_(enhanced_visuals_&_school_list).py"
```

Deployed at: https://zipmacro-57gxxdhwt7nrkhwcwtdbhy.streamlit.app/

## Dependencies

```bash
pip install streamlit pandas folium streamlit-folium zipcodes
```

`requirements.txt` must stay in sync with these five packages — nothing else is needed at runtime. `geopandas`, `requests`, `shapely` are only used by the one-time `generate_zip_coords.py` script and must not appear in `requirements.txt`.

## Architecture

Single-file Streamlit app (`streamlit_zip_code_mapper_app_(enhanced_visuals_&_school_list).py`), organised into four sections:

### 1. Coordinate resolution
- `_load_zip_coords_csv()` — loads `zip_coords.csv` into a `{zip: (lat, lon)}` dict, cached with `@st.cache_data`
- `get_zip_coords(zip_code)` — returns `{lat, lon, city, state, county}`. Primary source: `zip_coords.csv` (Census ZCTA 2020 `representative_point()`, guaranteed on land). Fallback: `zipcodes` package centroids for any ZIP not in the CSV. City/state/county metadata always comes from the `zipcodes` package.

### 2. Spread analysis
- `haversine_miles(lat1, lon1, lat2, lon2)` — pure-Python geodesic distance, no extra dependencies
- `analyse_spread(rows)` — computes every pairwise distance and classifies it into four tiers:

| Miles | Status | Meaning |
|---|---|---|
| < 10 | `too_close` | 5-mile rings overlap — clustered |
| 10–20 | `overlap_ok` | 10-mile rings overlap, 5-mile don't — acceptable |
| 20–25 | `ideal` | < 5-mile gap between 10-mile rings — good spread |
| > 25 | `too_sparse` | > 5-mile gap — coverage hole |

- `worst_status_per_zip(rows, pairs)` — maps the worst pairwise status to each ZIP index for marker colour-coding
- Marker colours: red = `too_close`, amber = `overlap_ok`, green = `ideal`, blue = `too_sparse`

### 3. Map building (`build_folium_map`)
- Returns `(folium.Map, pairs_list)`
- Resolves coords → runs spread analysis → adds numbered `DivIcon` markers (colour = worst status) → adds 5-mile solid blue `folium.Circle` + 10-mile dashed green `folium.Circle` per ZIP → optionally overlays `folium.plugins.HeatMap` (coverage density) → calls `m.fit_bounds()`
- Heatmap data via `build_heatmap_data(rows)`: samples 60 points on 5-mile ring (weight 1.0) + 60 on 10-mile ring (weight 0.4) + center (weight 1.5) per ZIP

### 4. Streamlit UI
- Session state key `map_zip_text` persists the ZIP input across reruns. This is necessary because `st_folium` triggers its own Streamlit reruns, which would reset a plain `st.button` result and clear the map.
- The `📊 Spread Analysis` expander renders in the sidebar after map generation, listing pair counts by tier and each pair sorted by distance.
- The "Show coverage heatmap" checkbox is read on every render and passed into `build_folium_map` — toggling it re-renders the map without requiring the button to be clicked again.

## zip_coords.csv

Must be committed to the repository (1.2 MB). Generated once by `generate_zip_coords.py`: downloads Census ZCTA 2020 shapefile (~500 MB) from `census.gov`, computes `representative_point()` per polygon via `geopandas`/`shapely`, saves only `zip, lat, lon`. Re-run only when the CSV needs refreshing. On macOS, SSL errors during download can be fixed with `/Applications/Python\ 3.12/Install\ Certificates.command`.

## Snapshots

Before significant changes, a snapshot is saved to `snapshots/snapshot_YYYYMMDD_HHMMSS/`. These are local only and not committed.

## Role data (teachers / TAs)

`teachers` and `tas` columns are optional. When any ZIP has non-zero values, marker popups show the breakdown. Coverage circles always appear regardless.
