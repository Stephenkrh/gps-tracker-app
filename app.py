import streamlit as st
import pandas as pd
import time
import io
import os
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval
from openpyxl.styles import PatternFill, Font, Alignment
from datetime import datetime

st.set_page_config(page_title="Advanced GPS Tracker", layout="wide")

EXCEL_FILE = "GPS_Live_Data.xlsx"

# =========================
# SESSION STATE — ✅ ONLY initialize if key does NOT exist
# Never reset data accidentally
# =========================
if "tracking" not in st.session_state:
    st.session_state.tracking = False
if "data" not in st.session_state:
    st.session_state.data = []          # persists across reruns
if "kf_speed" not in st.session_state:
    st.session_state.kf_speed = 0.0
if "tick" not in st.session_state:
    st.session_state.tick = 0
if "excel_ready" not in st.session_state:
    st.session_state.excel_ready = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "just_stopped" not in st.session_state:
    st.session_state.just_stopped = False

st.title("🚗 GPS Tracker — Every Second Logged")

# =========================
# DEBUG COUNTER — confirm data is growing
# =========================
st.sidebar.markdown("### 🔍 Debug Info")
st.sidebar.write(f"Rows in memory: **{len(st.session_state.data)}**")
st.sidebar.write(f"Tick: **{st.session_state.tick}**")
st.sidebar.write(f"Tracking: **{st.session_state.tracking}**")

# =========================
# HAVERSINE
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2 +
         cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * R * asin(sqrt(a))

# =========================
# KALMAN FILTER
# =========================
def kalman_filter(measured, prev_estimate, R=0.5):
    K = 1.0 / (1.0 + R)
    return prev_estimate + K * (measured - prev_estimate)

# =========================
# WRITE EXCEL ON STOP
# =========================
def write_excel_on_stop(data: list):
    if not data or len(data) < 1:
        return False

    df = pd.DataFrame(data)

    # Elapsed seconds
    df["elapsed_sec"] = (df["time"] - df["time"].iloc[0]).round(1)

    # Human readable datetime IST
    df["datetime"] = (
        pd.to_datetime(df["time"], unit='s')
          .dt.tz_localize('UTC')
          .dt.tz_convert('Asia/Kolkata')
          .dt.strftime('%Y-%m-%d %H:%M:%S')
    )

    # Cumulative distance
    df["total_distance_km"] = df["distance_step"].cumsum().round(4)

    # Column order
    final_cols = [
        "elapsed_sec", "datetime",
        "lat", "lon", "accuracy_m",
        "speed", "raw_speed", "acc",
        "heading", "mode",
        "distance_step", "total_distance_km"
    ]
    df = df[[c for c in final_cols if c in df.columns]]

    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="GPS Trip Data")

        wb = writer.book
        ws = writer.sheets["GPS Trip Data"]

        # Header styling
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Alternate row colors
        light_fill = PatternFill("solid", fgColor="D6E4F0")
        for i, row in enumerate(ws.iter_rows(min_row=2,
                                              max_row=ws.max_row), 1):
            for cell in row:
                cell.alignment = Alignment(horizontal="center")
                if i % 2 == 0:
                    cell.fill = light_fill

        # Auto column width
        for col in ws.columns:
            max_len = max(
                len(str(cell.value)) if cell.value else 0
                for cell in col
            )
            ws.column_dimensions[
                col[0].column_letter].width = max_len + 4

        # ── Summary Sheet ──
        ws2 = wb.create_sheet("Trip Summary")
        t_col  = "Speed" if "Speed" not in df.columns else "speed"
        summary = [
            ("Trip Start",           df["datetime"].iloc[0]),
            ("Trip End",             df["datetime"].iloc[-1]),
            ("Total Duration (s)",   round(df["elapsed_sec"].iloc[-1], 1)),
            ("Total Distance (km)",  round(df["total_distance_km"].iloc[-1], 3)),
            ("Avg Speed (km/h)",     round(df["speed"].mean(), 2)),
            ("Max Speed (km/h)",     round(df["speed"].max(), 2)),
            ("Max Accel (m/s²)",     round(df["acc"].max(), 4)),
            ("Total Rows (seconds)", len(df)),
        ]
        ws2.append(["Parameter", "Value"])
        h_fill = PatternFill("solid", fgColor="1F4E79")
        for cell in ws2[1]:
            cell.fill = h_fill
            cell.font = Font(color="FFFFFF", bold=True)
        for row in summary:
            ws2.append(list(row))
        ws2.column_dimensions["A"].width = 28
        ws2.column_dimensions["B"].width = 28

    return True

# =========================
# BUTTONS
# =========================
col1, col2, col3 = st.columns(3)

if col1.button("▶ Start Tracking"):
    # ✅ Only reset data on fresh Start — NOT on rerun
    st.session_state.data         = []
    st.session_state.kf_speed     = 0.0
    st.session_state.tick         = 0
    st.session_state.excel_ready  = False
    st.session_state.just_stopped = False
    st.session_state.start_time   = time.time()
    st.session_state.tracking     = True

if col2.button("⏹ Stop Tracking"):
    if st.session_state.tracking:
        st.session_state.tracking     = False
        st.session_state.just_stopped = True

if col3.button("🗑 Clear Data"):
    st.session_state.data         = []
    st.session_state.kf_speed     = 0.0
    st.session_state.tick         = 0
    st.session_state.excel_ready  = False
    st.session_state.just_stopped = False
    if os.path.exists(EXCEL_FILE):
        os.remove(EXCEL_FILE)
    st.rerun()

# =========================
# ✅ WRITE EXCEL ONCE ON STOP
# =========================
if st.session_state.just_stopped:
    st.write(f"📊 Total rows to save: {len(st.session_state.data)}")
    with st.spinner(f"💾 Saving {len(st.session_state.data)} rows..."):
        success = write_excel_on_stop(st.session_state.data)
    if success:
        st.session_state.excel_ready  = True
        st.session_state.just_stopped = False
        st.success(
            f"✅ Excel saved — "
            f"{len(st.session_state.data)} rows "
            f"({len(st.session_state.data)} seconds)"
        )
    else:
        st.warning("⚠️ No data to save.")
        st.session_state.just_stopped = False

# =========================
# GPS — DYNAMIC KEY (fresh every tick)
# =========================
coords = streamlit_js_eval(
    js_expressions="""
    new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                resolve({
                    lat:       pos.coords.latitude,
                    lon:       pos.coords.longitude,
                    acc:       pos.coords.accuracy,
                    gps_speed: pos.coords.speed,
                    heading:   pos.coords.heading,
                    timestamp: pos.timestamp
                });
            },
            (err) => resolve({ error: err.message }),
            {
                enableHighAccuracy: true,
                timeout: 8000,                               # Time for GPS update
                maximumAge: 0
            }
        );
    })
    """,
    key=f"GPS_{st.session_state.tick}"
)

# =========================
# STATUS
# =========================
status = st.empty()
if coords:
    if "error" in coords:
        status.error(f"❌ GPS Error: {coords['error']}")
    else:
        elapsed = int(time.time() - st.session_state.start_time) \
                  if st.session_state.start_time else 0
        status.success(
            f"📍 Lat: {coords.get('lat', 0):.6f} | "
            f"Lon: {coords.get('lon', 0):.6f} | "
            f"Accuracy: {coords.get('acc', 0):.1f}m | "
            f"Tick #{st.session_state.tick} | "
            f"Rows: {len(st.session_state.data)} | "
            f"Elapsed: {elapsed}s"
        )
else:
    status.warning("⏳ Waiting for GPS...")

# =========================
# ✅ APPEND 1 ROW PER SECOND TO SESSION STATE
# =========================
if coords and "error" not in coords and st.session_state.tracking:

    lat       = coords["lat"]
    lon       = coords["lon"]
    acc       = coords.get("acc", 0) or 0
    gps_speed = coords.get("gps_speed")
    heading   = coords.get("heading") or 0
    t         = time.time()

    if len(st.session_state.data) > 0:
        prev = st.session_state.data[-1]
        dist = haversine(prev["lat"], prev["lon"], lat, lon)
        dt   = max(t - prev["time"], 0.1)

        # Speed calculation
        if gps_speed is not None and gps_speed >= 0:
            raw_speed = gps_speed * 3.6
        else:
            raw_speed = (dist / dt) * 3600

        smooth_speed = kalman_filter(raw_speed, st.session_state.kf_speed)
        st.session_state.kf_speed = smooth_speed

        acc_val = ((smooth_speed - prev["speed"]) / 3.6) / dt

        mode = ("Idle"    if smooth_speed < 2
                else "Urban"   if smooth_speed < 40
                else "Highway")

        new_row = {
            "time":          t,
            "lat":           round(lat, 6),
            "lon":           round(lon, 6),
            "accuracy_m":    round(acc, 1),
            "speed":         round(smooth_speed, 2),
            "raw_speed":     round(raw_speed, 2),
            "acc":           round(acc_val, 4),
            "heading":       round(heading, 1),
            "mode":          mode,
            "distance_step": round(dist, 6),
        }

    else:
        # ✅ First row
        new_row = {
            "time":          t,
            "lat":           round(lat, 6),
            "lon":           round(lon, 6),
            "accuracy_m":    round(acc, 1),
            "speed":         0.0,
            "raw_speed":     0.0,
            "acc":           0.0,
            "heading":       round(heading, 1),
            "mode":          "Idle",
            "distance_step": 0.0,
        }

    # ✅ APPEND — this is what grows the list every second
    st.session_state.data.append(new_row)
    st.sidebar.write(f"✅ Row {len(st.session_state.data)} appended")

# =========================
# LIVE DASHBOARD
# =========================
if st.session_state.data:
    df     = pd.DataFrame(st.session_state.data)
    latest = df.iloc[-1]
    total  = df["distance_step"].sum()

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("🚀 Speed (km/h)",  f"{latest['speed']:.1f}")
    m2.metric("⚡ Accel (m/s²)",  f"{latest['acc']:.3f}")
    m3.metric("🗺 Mode",           latest["mode"])
    m4.metric("📏 Distance (km)", f"{total:.4f}")
    m5.metric("🎯 Accuracy (m)",  f"{latest['accuracy_m']:.0f}")
    m6.metric("📝 Rows Logged",   len(df))

    tab1, tab2, tab3 = st.tabs(["📈 Speed", "📉 Accel", "🗺 Map"])
    with tab1:
        st.line_chart(df["speed"])
    with tab2:
        st.line_chart(df["acc"])
    with tab3:
        st.map(df[["lat", "lon"]])

# =========================
# DOWNLOAD after Stop
# =========================
st.divider()
if st.session_state.excel_ready and os.path.exists(EXCEL_FILE):
    with open(EXCEL_FILE, "rb") as f:
        excel_bytes = f.read()
    st.download_button(
        label="📥 Download Trip Excel",
        data=excel_bytes,
        file_name=f"GPS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.caption(f"📊 {len(st.session_state.data)} rows — 1 per second")
else:
    st.info("Press ▶ Start → drive → ⏹ Stop → download Excel")

# =========================
# ✅ AUTO REFRESH — tick increments BEFORE rerun
# =========================
if st.session_state.tracking:
    st.session_state.tick += 1   # ← new key → fresh GPS call
    time.sleep(1)                                                # GPS time 
    st.rerun()

