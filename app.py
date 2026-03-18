import streamlit as st
import pandas as pd
import time
import io
import os
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from datetime import datetime

st.set_page_config(page_title="Advanced GPS Tracker", layout="wide")

# =========================
# CONSTANTS
# =========================
EXCEL_FILE = "GPS_Live_Data.xlsx"

# =========================
# SESSION STATE
# =========================
defaults = {
    "tracking": False,
    "data": [],
    "kf_speed": 0,
    "tick": 0,
    "excel_ready": False,
    "start_time": None,
    "just_stopped": False       # ✅ flag to trigger Excel write on Stop
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.title("🚗 Advanced GPS Tracker — Live Collect, Excel on Stop")

# =========================
# HAVERSINE
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat/2)**2 +
         cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2)
    return 2 * R * asin(sqrt(a))

# =========================
# KALMAN FILTER
# =========================
def kalman_filter(measured, prev_estimate, Q=0.01, R=0.5):
    K = 1.0 / (1.0 + R)
    return prev_estimate + K * (measured - prev_estimate)

# =========================
# WRITE TO EXCEL — CALLED ONLY ON STOP
# Every second of data is a separate row
# =========================
def write_excel_on_stop(data: list):
    """
    Writes all collected 1-second interval rows to a
    styled Excel file. Called ONCE when user presses Stop.
    """
    if not data:
        return False

    df = pd.DataFrame(data)

    # ── Human-readable timestamp (IST) ──
    df["datetime"] = (
        pd.to_datetime(df["time"], unit='s')
          .dt.tz_localize('UTC')
          .dt.tz_convert('Asia/Kolkata')
          .dt.strftime('%Y-%m-%d %H:%M:%S')
    )

    # ── Cumulative distance ──
    df["total_distance_km"] = df["distance_step"].cumsum().round(4)

    # ── Elapsed seconds from trip start ──
    df["elapsed_sec"] = (df["time"] - df["time"].iloc[0]).round(1)

    # ── Final column order ──
    final_cols = [
        "elapsed_sec", "datetime",
        "lat", "lon", "accuracy_m",
        "speed", "raw_speed", "acc",
        "heading", "mode",
        "distance_step", "total_distance_km"
    ]
    df = df[[c for c in final_cols if c in df.columns]]

    # ── Rename for Excel readability ──
    df.columns = [c.replace("_", " ").title() for c in df.columns]

    # ── Write with styling ──
    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="GPS Trip Data")

        wb = writer.book
        ws = writer.sheets["GPS Trip Data"]

        # Header row styling
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        for cell in ws[1]:
            cell.fill   = header_fill
            cell.font   = header_font
            cell.alignment = Alignment(horizontal="center",
                                       vertical="center")
        ws.row_dimensions[1].height = 20

        # Alternating row fill
        light_fill = PatternFill("solid", fgColor="D6E4F0")
        for i, row in enumerate(
            ws.iter_rows(min_row=2, max_row=ws.max_row), 1
        ):
            if i % 2 == 0:
                for cell in row:
                    cell.fill = light_fill
            # Center-align all data cells
            for cell in row:
                cell.alignment = Alignment(horizontal="center")

        # Auto column widths
        for col in ws.columns:
            max_len = max(
                len(str(cell.value)) if cell.value else 0
                for cell in col
            )
            ws.column_dimensions[col[0].column_letter].width = (
                max_len + 4
            )

        # ── Summary sheet ──
        ws_sum = wb.create_sheet("Trip Summary")
        total_dist  = df["Total Distance Km"].iloc[-1] \
                      if "Total Distance Km" in df.columns else 0
        total_time  = df["Elapsed Sec"].iloc[-1] \
                      if "Elapsed Sec" in df.columns else 0
        avg_speed   = df["Speed"].mean() \
                      if "Speed" in df.columns else 0
        max_speed   = df["Speed"].max() \
                      if "Speed" in df.columns else 0
        max_acc     = df["Acc"].max() \
                      if "Acc" in df.columns else 0

        summary_data = [
            ("Trip Start",        df["Datetime"].iloc[0]
                                  if "Datetime" in df.columns else "N/A"),
            ("Trip End",          df["Datetime"].iloc[-1]
                                  if "Datetime" in df.columns else "N/A"),
            ("Total Duration (s)", round(total_time, 1)),
            ("Total Distance (km)", round(total_dist, 3)),
            ("Avg Speed (km/h)",   round(avg_speed, 2)),
            ("Max Speed (km/h)",   round(max_speed, 2)),
            ("Max Acceleration",   round(max_acc, 4)),
            ("Total Points",       len(df)),
        ]

        # Style summary sheet
        sum_header_fill = PatternFill("solid", fgColor="1F4E79")
        ws_sum.append(["Parameter", "Value"])
        for cell in ws_sum[1]:
            cell.fill = sum_header_fill
            cell.font = Font(color="FFFFFF", bold=True)

        for row in summary_data:
            ws_sum.append(list(row))

        ws_sum.column_dimensions["A"].width = 25
        ws_sum.column_dimensions["B"].width = 25

    return True

# =========================
# BUTTONS
# =========================
col1, col2, col3 = st.columns(3)

if col1.button("▶ Start Tracking"):
    st.session_state.tracking    = True
    st.session_state.tick        = 0
    st.session_state.start_time  = time.time()
    st.session_state.just_stopped = False
    # ✅ Clear old data on new trip start
    st.session_state.data        = []
    st.session_state.kf_speed    = 0
    st.session_state.excel_ready = False

if col2.button("⏹ Stop Tracking"):
    if st.session_state.tracking:
        st.session_state.tracking    = False
        st.session_state.just_stopped = True   # ✅ triggers Excel write below

if col3.button("🗑 Clear Data"):
    st.session_state.data        = []
    st.session_state.kf_speed    = 0
    st.session_state.tick        = 0
    st.session_state.excel_ready = False
    st.session_state.just_stopped = False
    if os.path.exists(EXCEL_FILE):
        os.remove(EXCEL_FILE)
    st.rerun()

# =========================
# ✅ WRITE EXCEL ONCE ON STOP
# =========================
if st.session_state.just_stopped:
    with st.spinner("💾 Saving trip data to Excel..."):
        success = write_excel_on_stop(st.session_state.data)
    if success:
        st.session_state.excel_ready  = True
        st.session_state.just_stopped = False   # reset flag
        st.success(
            f"✅ Excel saved! "
            f"{len(st.session_state.data)} rows "
            f"({len(st.session_state.data)} seconds of data)"
        )
    else:
        st.warning("⚠️ No data to save.")
        st.session_state.just_stopped = False

# =========================
# GPS — FRESH EVERY TICK via dynamic key
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
                    altitude:  pos.coords.altitude,
                    heading:   pos.coords.heading,
                    timestamp: pos.timestamp
                });
            },
            (err) => resolve({ error: err.message }),
            {
                enableHighAccuracy: true,
                timeout: 6000,
                maximumAge: 0        // ✅ always fresh GPS hardware read
            }
        );
    })
    """,
    key=f"GPS_{st.session_state.tick}"
)

# =========================
# STATUS BAR
# =========================
status = st.empty()
if coords:
    if "error" in coords:
        status.error(f"❌ GPS Error: {coords['error']}")
    else:
        elapsed = int(time.time() - st.session_state.start_time) \
                  if st.session_state.start_time else 0
        status.success(
            f"📍 GPS Active | "
            f"Lat: {coords.get('lat', 0):.6f} | "
            f"Lon: {coords.get('lon', 0):.6f} | "
            f"Accuracy: {coords.get('acc', 0):.1f}m | "
            f"Tick: #{st.session_state.tick} | "
            f"Elapsed: {elapsed}s"
        )
else:
    status.warning("⏳ Waiting for GPS signal...")

# =========================
# ✅ COLLECT 1 ROW PER SECOND — no Excel write here
# =========================
if coords and "error" not in coords and st.session_state.tracking:

    lat       = coords["lat"]
    lon       = coords["lon"]
    acc       = coords.get("acc", 0)
    gps_speed = coords.get("gps_speed")
    heading   = coords.get("heading", 0) or 0
    t         = time.time()

    if st.session_state.data:
        prev = st.session_state.data[-1]
        dist = haversine(prev["lat"], prev["lon"], lat, lon)
        dt   = max(t - prev["time"], 0.1)

        # Speed
        if gps_speed is not None and gps_speed >= 0:
            raw_speed = gps_speed * 3.6
        else:
            raw_speed = (dist / dt) * 3600

        smooth_speed = kalman_filter(
            raw_speed, st.session_state.kf_speed
        )
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
        new_row = {
            "time":          t,
            "lat":           round(lat, 6),
            "lon":           round(lon, 6),
            "accuracy_m":    round(acc, 1),
            "speed":         0,
            "raw_speed":     0,
            "acc":           0,
            "heading":       round(heading, 1),
            "mode":          "Idle",
            "distance_step": 0,
        }

    # ✅ Append to memory only — NO Excel write
    st.session_state.data.append(new_row)

# =========================
# LIVE DASHBOARD
# =========================
if st.session_state.data:
    df      = pd.DataFrame(st.session_state.data)
    latest  = df.iloc[-1]
    total_d = df["distance_step"].sum()

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("🚀 Speed (km/h)",  f"{latest['speed']:.1f}")
    m2.metric("⚡ Accel (m/s²)",  f"{latest['acc']:.3f}")
    m3.metric("🗺 Mode",           latest["mode"])
    m4.metric("📏 Distance (km)", f"{total_d:.3f}")
    m5.metric("🎯 Accuracy (m)",  f"{latest['accuracy_m']:.0f}")
    m6.metric("📝 Points",        len(df))

    tab1, tab2, tab3 = st.tabs(["📈 Speed", "📉 Acceleration", "🗺 Map"])
    with tab1:
        st.line_chart(df["speed"], use_container_width=True)
    with tab2:
        st.line_chart(df["acc"],   use_container_width=True)
    with tab3:
        st.map(df[["lat", "lon"]])

# =========================
# DOWNLOAD — only after Stop & Excel written
# =========================
st.divider()
if st.session_state.excel_ready and os.path.exists(EXCEL_FILE):
    with open(EXCEL_FILE, "rb") as f:
        excel_bytes = f.read()

    filename = (
        f"GPS_Trip_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    st.download_button(
        label="📥 Download Trip Excel",
        data=excel_bytes,
        file_name=filename,
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )
    st.caption(
        f"📊 Contains {len(st.session_state.data)} rows "
        f"— one per second of trip"
    )
elif not st.session_state.tracking and not st.session_state.excel_ready:
    st.info("⏸ Press ▶ Start to begin. Excel downloads after ⏹ Stop.")

# =========================
# AUTO REFRESH EVERY SECOND (only while tracking)
# =========================
if st.session_state.tracking:
    st.session_state.tick += 1
    time.sleep(1)
    st.rerun()
```

---

## What Changed

| Behaviour | Before | Now |
|---|---|---|
| Excel write | Every second | **Only on Stop** ✅ |
| Data collection | Every second | Every second ✅ |
| Each row = 1 second | ✅ | ✅ |
| Download button | Always visible | **Only appears after Stop** ✅ |
| Summary sheet | None | **Auto-generated on Stop** ✅ |
| New trip clears old data | No | **Yes, on Start** ✅ |

## Excel Output Structure
```
Sheet 1: GPS Trip Data     ← one row per second
┌──────────────┬──────────┬─────────┬───────┬────────┬─────┐
│ Elapsed Sec  │ Datetime │  Lat    │  Lon  │ Speed  │ ... │
│      0       │ 14:01:00 │ 13.0827 │ 80.27 │  0.00  │ ... │
│      1       │ 14:01:01 │ 13.0828 │ 80.27 │  5.20  │ ... │
│      2       │ 14:01:02 │ 13.0829 │ 80.27 │ 12.40  │ ... │
└──────────────┴──────────┴─────────┴───────┴────────┴─────┘

Sheet 2: Trip Summary      ← written on Stop
┌─────────────────────┬───────────┐
│ Total Distance (km) │   12.34   │
│ Avg Speed (km/h)    │   38.20   │
│ Max Speed (km/h)    │   72.10   │
└─────────────────────┴───────────┘
