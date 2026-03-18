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
if "tick" not in st.session_state:
    st.session_state.tick = 0  # ✅ FIX 1: tick counter for dynamic key

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
# KALMAN FILTER
# =========================
def kalman_filter(measured, prev_estimate, Q=0.01, R=0.5):
    pred = prev_estimate
    P = 1.0
    K = P / (P + R)
    estimate = pred + K * (measured - pred)
    return estimate

# =========================
# BUTTONS
# =========================
col1, col2, col3 = st.columns(3)

if col1.button("▶ Start"):
    st.session_state.tracking = True
    st.session_state.tick = 0

if col2.button("⏹ Stop"):
    st.session_state.tracking = False

if col3.button("🗑 Clear Data"):
    st.session_state.data = []
    st.session_state.kf_speed = 0
    st.session_state.tick = 0

# =========================
# ✅ FIX 2: DYNAMIC KEY — forces fresh GPS call every rerun
# =========================
gps_key = f"GPS_{st.session_state.tick}"

coords = streamlit_js_eval(
    js_expressions="""
    new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                resolve({
                    lat: pos.coords.latitude,
                    lon: pos.coords.longitude,
                    acc: pos.coords.accuracy,
                    gps_speed: pos.coords.speed,
                    altitude: pos.coords.altitude,
                    timestamp: pos.timestamp
                });
            },
            (err) => {
                resolve({ error: err.message });
            },
            {
                enableHighAccuracy: true,
                timeout: 6000,
                maximumAge: 0      // ✅ FIX 3: maximumAge: 0 forces fresh GPS reading
            }
        );
    })
    """,
    key=gps_key   # ✅ Dynamic key — never reuses cached value
)

# =========================
# STATUS DISPLAY
# =========================
status_placeholder = st.empty()
if coords:
    if "error" in coords:
        status_placeholder.error(f"GPS Error: {coords['error']}")
    else:
        status_placeholder.success(
            f"📍 GPS Lock | Lat: {coords.get('lat', 'N/A'):.5f} "
            f"| Lon: {coords.get('lon', 'N/A'):.5f} "
            f"| Accuracy: {coords.get('acc', 'N/A'):.1f}m"
            f"| Tick: {st.session_state.tick}"  # shows it's refreshing
        )
else:
    status_placeholder.warning("⏳ Waiting for GPS...")

# =========================
# PROCESS DATA
# =========================
if coords and "error" not in coords and st.session_state.tracking:

    lat = coords["lat"]
    lon = coords["lon"]
    acc = coords["acc"]
    gps_speed_raw = coords.get("gps_speed")  # Native GPS speed (may be null)
    t = time.time()

    if st.session_state.data:
        prev = st.session_state.data[-1]

        dist = haversine(prev["lat"], prev["lon"], lat, lon)
        dt = t - prev["time"]

        # ✅ FIX 4: Use native GPS speed if available, else calculate from position
        if gps_speed_raw is not None and gps_speed_raw >= 0:
            raw_speed = gps_speed_raw * 3.6  # m/s → km/h
        else:
            raw_speed = (dist / dt) * 3600 if dt > 0 else 0

        # Kalman smoothing
        smooth_speed = kalman_filter(raw_speed, st.session_state.kf_speed)
        st.session_state.kf_speed = smooth_speed

        # Acceleration (km/h/s → m/s²)
        acc_val = ((smooth_speed - prev["speed"]) / 3.6) / dt if dt > 0 else 0

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
            "accuracy_m": acc,
            "speed": round(smooth_speed, 3),
            "raw_speed": round(raw_speed, 3),
            "acc": round(acc_val, 4),
            "mode": mode,
            "distance_step": dist
        })

    else:
        # First point
        st.session_state.data.append({
            "time": t,
            "lat": lat,
            "lon": lon,
            "accuracy_m": acc,
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

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Speed (km/h)", f"{latest['speed']:.2f}")
    c2.metric("Accel (m/s²)", f"{latest['acc']:.3f}")
    c3.metric("Mode", latest["mode"])
    c4.metric("Distance (km)", f"{total_dist:.3f}")
    c5.metric("GPS Accuracy (m)", f"{latest['accuracy_m']:.1f}")

    st.subheader("Speed Profile")
    st.line_chart(df["speed"])

    st.subheader("Acceleration Profile")
    st.line_chart(df["acc"])

    st.subheader("Route Map")
    st.map(df[["lat", "lon"]])

    # Download only when stopped
    if not st.session_state.tracking:
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        st.download_button("📥 Download GPS Data", output, "GPS_Pro_Data.xlsx")

else:
    st.info("Press ▶ Start to begin tracking")

# =========================
# ✅ FIX 5: AUTO REFRESH — increment tick THEN rerun (no sleep block)
# =========================
if st.session_state.tracking:
    st.session_state.tick += 1   # changes the key → forces fresh JS call
    time.sleep(1)
    st.rerun()
