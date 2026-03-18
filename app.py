import streamlit as st
import pandas as pd
import time
import io
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval

st.set_page_config(page_title="Advanced GPS Tracker", layout="wide")

# =========================
# SESSION STATE
# =========================
if "tracking" not in st.session_state:
    st.session_state.tracking = False

if "data" not in st.session_state:
    st.session_state.data = []

if "kf_speed" not in st.session_state:
    st.session_state.kf_speed = 0

# =========================
# TITLE
# =========================
st.title("🚗 Advanced GPS Tracker (Pro)")

# =========================
# HAVERSINE
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))

# =========================
# SIMPLE KALMAN FILTER
# =========================
def kalman_filter(measured, prev_estimate, Q=0.01, R=0.5):
    # Predict
    pred = prev_estimate
    P = 1.0

    # Update
    K = P / (P + R)
    estimate = pred + K * (measured - pred)

    return estimate

# =========================
# BUTTONS
# =========================
col1, col2 = st.columns(2)

if col1.button("▶ Start"):
    st.session_state.tracking = True

if col2.button("⏹ Stop"):
    st.session_state.tracking = False

# =========================
# REAL-TIME GPS (watchPosition)
# =========================
coords = streamlit_js_eval(
    js_expressions="""
    new Promise((resolve, reject) => {
        if (!window.coords) window.coords = null;

        if (!window.watchId) {
            window.watchId = navigator.geolocation.watchPosition(
                (pos) => {
                    window.coords = {
                        lat: pos.coords.latitude,
                        lon: pos.coords.longitude,
                        t: Date.now()
                    };
                },
                (err) => console.log(err),
                { enableHighAccuracy: true, maximumAge: 0, timeout: 5000 }
            );
        }
        resolve(window.coords);
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
    t = time.time()

    if st.session_state.data:
        prev = st.session_state.data[-1]

        dist = haversine(prev["lat"], prev["lon"], lat, lon)
        dt = t - prev["time"]

        raw_speed = (dist / dt) * 3600 if dt > 0 else 0

        # Kalman smoothing
        smooth_speed = kalman_filter(raw_speed, st.session_state.kf_speed)
        st.session_state.kf_speed = smooth_speed

        # Acceleration
        acc = (smooth_speed - prev["speed"]) / dt if dt > 0 else 0

        # Drive cycle classification
        if smooth_speed < 2:
            mode = "Idle"
        elif smooth_speed < 40:
            mode = "Urban"
        else:
            mode = "Highway"

        st.session_state.data.append({
            "time": t,
            "lat": lat,
            "lon": lon,
            "speed": smooth_speed,
            "raw_speed": raw_speed,
            "acc": acc,
            "mode": mode,
            "distance_step": dist
        })

    else:
        st.session_state.data.append({
            "time": t,
            "lat": lat,
            "lon": lon,
            "speed": 0,
            "raw_speed": 0,
            "acc": 0,
            "mode": "Idle",
            "distance_step": 0
        })

# =========================
# DISPLAY
# =========================
if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    latest = df.iloc[-1]

    total_dist = df["distance_step"].sum()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Speed (km/h)", f"{latest['speed']:.2f}")
    c2.metric("Acceleration (m/s²)", f"{latest['acc']:.2f}")
    c3.metric("Mode", latest["mode"])
    c4.metric("Distance (km)", f"{total_dist:.3f}")

    st.subheader("Speed Profile")
    st.line_chart(df["speed"])

    st.subheader("Acceleration Profile")
    st.line_chart(df["acc"])

    st.subheader("Route Map")
    st.map(df[["lat", "lon"]])

    # Download
    if not st.session_state.tracking:
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)

        st.download_button("📥 Download Data", output, "GPS_Pro_Data.xlsx")

else:
    st.info("Start tracking to see data")

# =========================
# AUTO REFRESH (FAST)
# =========================
if st.session_state.tracking:
    time.sleep(0.8)
    st.rerun()
