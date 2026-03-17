import streamlit as st
import pandas as pd
import numpy as np
import time
import io
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval


st.set_page_config(page_title="Live GPS Speed Tracker", layout="wide")

# =========================
# SESSION STATE INIT (VERY IMPORTANT)
# =========================
if "tracking" not in st.session_state:
    st.session_state.tracking = False

if "data" not in st.session_state:
    st.session_state.data = []

# =========================
# TITLE
# =========================
st.title("🚗 Live GPS Speed Tracker")

# =========================
# HAVERSINE FUNCTION
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    return R * c

# =========================
# BUTTONS
# =========================
col1, col2 = st.columns(2)

if col1.button("▶ Start Tracking"):
    st.session_state.tracking = True

if col2.button("⏹ Stop Tracking"):
    st.session_state.tracking = False

# =========================
# GPS DATA (STABLE METHOD)
# =========================
coords = streamlit_js_eval(
    js_expressions="""
    new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                resolve({
                    lat: pos.coords.latitude,
                    lon: pos.coords.longitude
                });
            },
            (err) => {
                resolve(null);
            }
        );
    })
    """,
    key="GPS"
)

# =========================
# PROCESS DATA
# =========================
if coords and st.session_state.tracking:
    lat = coords["lat"]
    lon = coords["lon"]
    current_time = time.time()

    if st.session_state.data:
        prev = st.session_state.data[-1]

        dist = haversine(prev["lat"], prev["lon"], lat, lon)
        dt = current_time - prev["time"]

        speed = (dist / dt) * 3600 if dt > 0 else 0

        # Remove noise at very low speeds
        if speed < 2:
            speed = 0
    else:
        speed = 0
        dist = 0

    st.session_state.data.append({
        "time": current_time,
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "distance_step": dist
    })

# =========================
# DISPLAY
# =========================
if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)

    latest = df.iloc[-1]
    total_distance = df["distance_step"].sum()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Speed (km/h)", f"{latest['speed']:.2f}")
    col2.metric("Latitude", f"{latest['lat']:.5f}")
    col3.metric("Longitude", f"{latest['lon']:.5f}")
    col4.metric("Distance (km)", f"{total_distance:.3f}")

    st.subheader("Speed Profile")
    st.line_chart(df["speed"])

    st.subheader("Route Map")
    st.map(df[["lat", "lon"]])

    # =========================
    # SAVE EXCEL WHEN STOPPED
    # =========================
    if not st.session_state.tracking and len(df) > 0:
        output_file = "GPS_Trip_Data.xlsx"
        if len(df) > 0 and not st.session_state.tracking:

          output = io.BytesIO()
          df.to_excel(output, index=False, engine='openpyxl')
          output.seek(0)

          st.download_button(
          label="📥 Download Trip Data",
          data=output,
          file_name="GPS_Trip_Data.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
         )
        st.success(f"Trip saved as {output_file}")

else:
    st.info("Click 'Start Tracking' to begin")

# =========================
# AUTO REFRESH (IMPORTANT)
# =========================
if st.session_state.tracking:
    time.sleep(1)
    st.rerun()
