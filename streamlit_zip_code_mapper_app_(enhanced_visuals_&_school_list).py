import streamlit as st
import pandas as pd
import folium
import zipcodes as zc
from streamlit_folium import st_folium
import re
from pathlib import Path

st.set_page_config(layout="wide")
st.title("ZIP Code Map")

BASE_DIR = Path(__file__).resolve().parent
_ZIP_COORDS_PATH = BASE_DIR / "zip_coords.csv"

###############################################################################
# HELPER FUNCTIONS
###############################################################################

@st.cache_data
def _load_zip_coords_csv() -> dict:
    """Loads Census ZCTA representative-point CSV → zip: (lat, lon) dict."""
    if not _ZIP_COORDS_PATH.is_file():
        return {}
    df = pd.read_csv(_ZIP_COORDS_PATH, dtype={"zip": str})
    df["zip"] = df["zip"].str.zfill(5)
    return {row["zip"]: (row["lat"], row["lon"]) for _, row in df.iterrows()}


@st.cache_data
def get_zip_coords(zip_code: str) -> dict | None:
    """Returns {lat, lon, city, state, county} for a ZIP code, or None.

    Coordinate source priority:
      1. Census ZCTA 2020 representative_point() — guaranteed on land
      2. zipcodes package centroid — fallback for non-ZCTA ZIPs
    """
    coords = _load_zip_coords_csv()
    if zip_code in coords:
        lat, lon = coords[zip_code]
    else:
        results = zc.matching(zip_code)
        if not results or results[0].get('lat') is None:
            return None
        lat = float(results[0]['lat'])
        lon = float(results[0]['long'])

    # Enrich with city/state/county metadata from zipcodes package
    meta = zc.matching(zip_code)
    city   = meta[0].get('city', '')   if meta else ''
    state  = meta[0].get('state', '')  if meta else ''
    county = meta[0].get('county', '') if meta else ''
    return {'lat': lat, 'lon': lon, 'city': city, 'state': state, 'county': county}


def process_input_dataframe(df_input: pd.DataFrame) -> pd.DataFrame:
    if df_input is None or df_input.empty:
        return pd.DataFrame(columns=['zip', 'teachers', 'tas'])

    df = df_input.copy()
    df.columns = df.columns.str.strip().str.lower()

    if 'zip code' in df.columns and 'zip' not in df.columns:
        df.rename(columns={'zip code': 'zip'}, inplace=True)

    if 'zip' not in df.columns:
        return pd.DataFrame(columns=['zip', 'teachers', 'tas'])

    df['zip'] = df['zip'].astype(str).str.strip().fillna('').str.zfill(5)
    df = df[df['zip'].str.match(r'^\d{5}$')].copy()

    for col_name in ['teachers', 'tas']:
        if col_name in df.columns:
            df[col_name] = pd.to_numeric(df[col_name], errors='coerce').fillna(0).astype(int)
        else:
            df[col_name] = 0

    return df[['zip', 'teachers', 'tas']].drop_duplicates(subset=['zip'], keep='first')


def load_and_process_csv_data(uploaded_file_object) -> pd.DataFrame:
    if uploaded_file_object is None:
        return pd.DataFrame(columns=['zip', 'teachers', 'tas'])
    try:
        uploaded_file_object.seek(0)
        try:
            first_lines_bytes = uploaded_file_object.read(2048)
            first_lines_str = first_lines_bytes.decode('utf-8-sig').splitlines()[0]
        except UnicodeDecodeError:
            uploaded_file_object.seek(0)
            first_lines_bytes = uploaded_file_object.read(2048)
            first_lines_str = first_lines_bytes.decode('latin1', errors='ignore').splitlines()[0]
        except IndexError:
            st.warning("Uploaded CSV file appears to be empty.")
            return pd.DataFrame(columns=['zip', 'teachers', 'tas'])

        delimiter = ';' if ';' in first_lines_str and first_lines_str.count(';') >= first_lines_str.count(',') else ','
        uploaded_file_object.seek(0)
        df_csv = pd.read_csv(uploaded_file_object, delimiter=delimiter, encoding='utf-8-sig', encoding_errors='ignore')

        temp_cols = [col.strip().lower() for col in df_csv.columns]
        if 'zip' not in temp_cols and 'zip code' not in temp_cols:
            st.error("Uploaded CSV must contain a 'zip' or 'zip code' column.")
            return pd.DataFrame(columns=['zip', 'teachers', 'tas'])

        return process_input_dataframe(df_csv)
    except Exception as e:
        st.error(f"Error loading or processing uploaded CSV: {e}")
        return pd.DataFrame(columns=['zip', 'teachers', 'tas'])


def parse_zips_from_text(text: str) -> pd.DataFrame:
    tokens = re.split(r'[\s,;]+', text.strip())
    zips = [t.zfill(5) for t in tokens if re.fullmatch(r'\d{3,5}', t.strip())]
    zips = list(dict.fromkeys(zips))
    return pd.DataFrame({'zip': zips, 'teachers': 0, 'tas': 0})


###############################################################################
# FOLIUM MAP FUNCTION
###############################################################################

def build_folium_map(df_map_data: pd.DataFrame) -> folium.Map:
    if df_map_data.empty or 'zip' not in df_map_data.columns:
        return folium.Map(location=[39.5, -98.35], zoom_start=4, tiles='OpenStreetMap')

    df_map_data = df_map_data.copy()
    df_map_data['zip'] = df_map_data['zip'].astype(str).str.zfill(5)

    # Resolve coordinates for each ZIP
    rows = []
    not_found = []
    for _, row in df_map_data.iterrows():
        coords = get_zip_coords(row['zip'])
        if coords:
            rows.append({**row.to_dict(), **coords})
        else:
            not_found.append(row['zip'])

    if not_found:
        st.warning(f"ZIP codes not found in database: {', '.join(not_found)}")

    if not rows:
        return folium.Map(location=[39.5, -98.35], zoom_start=4, tiles='OpenStreetMap')

    lats = [r['lat'] for r in rows]
    lons = [r['lon'] for r in rows]
    center_lat = (min(lats) + max(lats)) / 2
    center_lon = (min(lons) + max(lons)) / 2

    m = folium.Map(location=[center_lat, center_lon], tiles='OpenStreetMap')

    has_role_data = any(
        (r.get('teachers', 0) or 0) + (r.get('tas', 0) or 0) > 0
        for r in rows
    )

    for serial, r in enumerate(rows, start=1):
        lat, lon = r['lat'], r['lon']
        zip_code = r['zip']
        teachers = int(r.get('teachers', 0) or 0)
        tas = int(r.get('tas', 0) or 0)
        city = r.get('city', '')
        state = r.get('state', '')
        county = r.get('county', '')

        location_label = f"{city}, {state}" if city and state else zip_code

        popup_lines = [
            f"<b>ZIP: {zip_code}</b>",
            f"{location_label}",
        ]
        if county:
            popup_lines.append(f"{county} County")
        if has_role_data:
            popup_lines.append("─────────")
            popup_lines.append(f"Teachers: {teachers}")
            popup_lines.append(f"TAs: {tas}")
            popup_lines.append(f"Total: {teachers + tas}")
        popup_html = "<br>".join(popup_lines)

        icon_html = f"""
            <div style="
                background-color: #2e7d32;
                color: white;
                border: 2px solid #1b5e20;
                border-radius: 50%;
                width: 28px;
                height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                font-weight: bold;
                box-shadow: 1px 1px 3px rgba(0,0,0,0.4);
            ">{serial}</div>
        """
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=f"#{serial} · ZIP {zip_code} · {location_label}",
            icon=folium.DivIcon(html=icon_html, icon_size=(28, 28), icon_anchor=(14, 14)),
        ).add_to(m)

        folium.Circle(
            location=[lat, lon],
            radius=8047,
            color='#1565C0',
            fill=False,
            weight=2.5,
            opacity=0.85,
            tooltip=f"5-mile radius — ZIP {zip_code}",
        ).add_to(m)
        folium.Circle(
            location=[lat, lon],
            radius=16093,
            color='#2E7D32',
            fill=False,
            weight=2.5,
            opacity=0.85,
            dash_array='8',
            tooltip=f"10-mile radius — ZIP {zip_code}",
        ).add_to(m)

    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    return m


###############################################################################
# STREAMLIT UI
###############################################################################

st.sidebar.header("ZIP Codes")

zip_text = st.sidebar.text_area(
    "Enter ZIP codes",
    placeholder="10001\n10002\n10003\n\nOne per line, or comma-separated.",
    height=200,
    key="zip_text_input",
)
if zip_text and zip_text.strip():
    preview_df = parse_zips_from_text(zip_text)
    count = len(preview_df)
    if count:
        st.sidebar.caption(f"{count} valid ZIP code{'s' if count != 1 else ''} recognised.")
    else:
        st.sidebar.caption("No valid ZIP codes found yet.")

generate_map_button = st.sidebar.button("Generate Map", key="generate_map_button_main")

if generate_map_button:
    raw_text = st.session_state.get("zip_text_input", "")
    if raw_text and raw_text.strip():
        df_parsed = parse_zips_from_text(raw_text)
        if df_parsed.empty:
            st.sidebar.warning("No valid 5-digit ZIP codes found. Please check your input.")
            st.session_state.pop('map_zip_text', None)
        else:
            st.session_state['map_zip_text'] = raw_text
    else:
        st.sidebar.warning("Please enter at least one ZIP code.")
        st.session_state.pop('map_zip_text', None)

if 'map_zip_text' in st.session_state:
    df_map_data_for_plot = parse_zips_from_text(st.session_state['map_zip_text'])
    try:
        folium_map = build_folium_map(df_map_data_for_plot)
        st_folium(folium_map, use_container_width=True, height=600)
        st.success("Map generated successfully! Pan and zoom freely.")

        map_html = folium_map._repr_html_()
        st.download_button(
            label="Download Map as HTML",
            data=map_html,
            file_name="zip_code_map.html",
            mime="text/html",
        )
    except Exception as e:
        st.error(f"Error during map generation: {e}")
        st.exception(e)
else:
    st.info("Enter ZIP codes in the sidebar and click **Generate Map**.")
