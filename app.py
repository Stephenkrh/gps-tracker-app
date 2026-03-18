import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
import os
from math import radians, cos, sin, asin, sqrt
from openpyxl.styles import PatternFill, Font, Alignment
from datetime import datetime

st.set_page_config(page_title="GPS Tracker", layout="wide")

EXCEL_FILE = "GPS_Live_Data.xlsx"

# =========================
# SESSION STATE
# =========================
if "tracking"      not in st.session_state: st.session_state.tracking      = False
if "data"          not in st.session_state: st.session_state.data          = []
if "kf_speed"      not in st.session_state: st.session_state.kf_speed      = 0.0
if "tick"          not in st.session_state: st.session_state.tick          = 0
if "excel_ready"   not in st.session_state: st.session_state.excel_ready   = False
if "start_time"    not in st.session_state: st.session_state.start_time    = None
if "just_stopped"  not in st.session_state: st.session_state.just_stopped  = False
if "last_lat"      not in st.session_state: st.session_state.last_lat      = None
if "last_lon"      not in st.session_state: st.session_state.last_lon      = None
if "last_acc"      not in st.session_state: st.session_state.last_acc      = None
if "last_speed"    not in st.session_state: st.session_state.last_speed    = None
if "last_heading"  not in st.session_state: st.session_state.last_heading  = None
if "gps_error"     not in st.session_state: st.session_state.gps_error     = None

st.title("🚗 GPS Tracker")

# =========================
# SIDEBAR DEBUG
# =========================
st.sidebar.markdown("### 🔍 Debug Info")
st.sidebar.write(f"Rows in memory: **{len(st.session_state.data)}**")
st.sidebar.write(f"Tick: **{st.session_state.tick}**")
st.sidebar.write(f"Tracking: **{st.session_state.tracking}**")
st.sidebar.write(f"Last Lat: **{st.session_state.last_lat}**")
st.sidebar.write(f"Last Lon: **{st.session_state.last_lon}**")
st.sidebar.write(f"GPS Error: **{st.session_state.gps_error}**")

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
def kalman_filter(measured, prev_estimate, R=0.5):
    K = 1.0 / (1.0 + R)
    return prev_estimate + K * (measured - prev_estimate)

# =========================
# WRITE EXCEL ON STOP
# =========================
def write_excel_on_stop(data: list):
    if not data:
        return False
    df = pd.DataFrame(data)
    df["elapsed_sec"]      = (df["time"] - df["time"].iloc[0]).round(1)
    df["datetime"]         = (
        pd.to_datetime(df["time"], unit='s')
          .dt.tz_localize('UTC')
          .dt.tz_convert('Asia/Kolkata')
          .dt.strftime('%Y-%m-%d %H:%M:%S')
    )
    df["total_distance_km"] = df["distance_step"].cumsum().round(4)

    cols = ["elapsed_sec","datetime","lat","lon","accuracy_m",
            "speed","raw_speed","acc","heading","mode",
            "distance_step","total_distance_km"]
    df = df[[c for c in cols if c in df.columns]]

    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="GPS Trip Data")
        wb = writer.book
        ws = writer.sheets["GPS Trip Data"]

        hf = PatternFill("solid", fgColor="1F4E79")
        hfont = Font(color="FFFFFF", bold=True, size=11)
        for cell in ws[1]:
            cell.fill = hf
            cell.font = hfont
            cell.alignment = Alignment(horizontal="center")

        lf = PatternFill("solid", fgColor="D6E4F0")
        for i, row in enumerate(
                ws.iter_rows(min_row=2, max_row=ws.max_row), 1):
            for cell in row:
                cell.alignment = Alignment(horizontal="center")
                if i % 2 == 0:
                    cell.fill = lf

        for col in ws.columns:
            w = max(len(str(c.value)) if c.value else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = w + 4

        ws2 = wb.create_sheet("Trip Summary")
        summary = [
            ("Trip Start",           df["datetime"].iloc[0]),
            ("Trip End",             df["datetime"].iloc[-1]),
            ("Total Duration (s)",   round(df["elapsed_sec"].iloc[-1], 1)),
            ("Total Distance (km)",  round(df["total_distance_km"].iloc[-1], 3)),
            ("Avg Speed (km/h)",     round(df["speed"].mean(), 2)),
            ("Max Speed (km/h)",     round(df["speed"].max(), 2)),
            ("Max Accel (m/s²)",     round(df["acc"].max(), 4)),
            ("Total Rows",           len(df)),
        ]
        ws2.append(["Parameter", "Value"])
        for cell in ws2[1]:
            cell.fill = hf
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
    for key in ["data","kf_speed","tick","excel_ready",
                "just_stopped","last_lat","last_lon",
                "last_acc","last_speed","last_heading","gps_error"]:
        st.session_state[key] = [] if key == "data" else None if key in [
            "last_lat","last_lon","last_acc",
            "last_speed","last_heading","gps_error"
        ] else False if key in ["excel_ready","just_stopped"] else 0
    if os.path.exists(EXCEL_FILE):
        os.remove(EXCEL_FILE)
    st.rerun()

# =========================
# WRITE EXCEL ON STOP
# =========================
if st.session_state.just_stopped:
    with st.spinner(f"💾 Saving {len(st.session_state.data)} rows..."):
        ok = write_excel_on_stop(st.session_state.data)
    st.session_state.excel_ready  = ok
    st.session_state.just_stopped = False
    if ok:
        st.success(f"✅ Saved {len(st.session_state.data)} rows to Excel")
    else:
        st.warning("⚠️ No data to save")

# =========================
# ✅ GPS VIA CUSTOM HTML COMPONENT
# Writes GPS into a hidden Streamlit text_input
# which Python reads back — bypasses streamlit_js_eval
# =========================
gps_placeholder = st.empty()

with gps_placeholder:
    components.html(
        f"""
        <script>
        function sendGPS() {{
            if (!navigator.geolocation) {{
                document.getElementById('gps_out').value = 
                    'ERROR:Geolocation not supported';
                triggerChange();
                return;
            }}

            navigator.geolocation.getCurrentPosition(
                function(pos) {{
                    var data = [
                        pos.coords.latitude.toFixed(7),
                        pos.coords.longitude.toFixed(7),
                        (pos.coords.accuracy   || 0).toFixed(1),
                        (pos.coords.speed      || 0).toFixed(3),
                        (pos.coords.heading    || 0).toFixed(1),
                        (pos.coords.altitude   || 0).toFixed(1),
                        pos.timestamp
                    ].join(',');

                    // ✅ Send to parent Streamlit window via postMessage
                    window.parent.postMessage({{
                        type: 'gps_data',
                        payload: data
                    }}, '*');

                    // ✅ Also show in iframe for debug
                    document.getElementById('status').innerText 
                        = '✅ GPS: ' + data;
                }},
                function(err) {{
                    var msgs = {{
                        1: 'Permission denied — allow location in browser',
                        2: 'Position unavailable — check signal',
                        3: 'Timeout — move outdoors'
                    }};
                    window.parent.postMessage({{
                        type: 'gps_error',
                        payload: 'ERROR:' + (msgs[err.code] || err.message)
                    }}, '*');
                    document.getElementById('status').innerText 
                        = '❌ ' + (msgs[err.code] || err.message);
                }},
                {{
                    enableHighAccuracy: true,
                    timeout: 15000,
                    maximumAge: 2000
                }}
            );
        }}

        // Fire immediately and every 2 seconds
        sendGPS();
        setInterval(sendGPS, 2000);
        </script>

        <div style="font-family:monospace; padding:8px;
                    background:#1e1e1e; color:#00ff88;
                    border-radius:6px; font-size:12px;">
            <span id="status">⏳ Requesting GPS permission...</span>
        </div>
        """,
        height=60,
    )

# ✅ Read GPS from query params passed via st.query_params
# Use a hidden text_input updated by JS postMessage listener
# ---- GPS component that pushes data back to Python ----
gps_raw = components.html(
    """
    <script>
    function sendGPS() {
        if (!navigator.geolocation) {
            const data = 'ERROR:Geolocation not supported';
            window.parent.postMessage(
              { isStreamlitMessage: true, type: 'streamlit:setComponentValue', value: data },
              '*'
            );
            return;
        }

        navigator.geolocation.getCurrentPosition(
            function(pos) {
                var data = [
                    pos.coords.latitude.toFixed(7),
                    pos.coords.longitude.toFixed(7),
                    (pos.coords.accuracy   || 0).toFixed(1),
                    (pos.coords.speed      || 0).toFixed(3),
                    (pos.coords.heading    || 0).toFixed(1),
                    (pos.coords.altitude   || 0).toFixed(1),
                    pos.timestamp
                ].join(',');

                window.parent.postMessage(
                  { isStreamlitMessage: true, type: 'streamlit:setComponentValue', value: data },
                  '*'
                );
            },
            function(err) {
                var msgs = {
                    1: 'Permission denied — allow location in browser',
                    2: 'Position unavailable — check signal',
                    3: 'Timeout — move outdoors'
                };
                const data = 'ERROR:' + (msgs[err.code] || err.message);
                window.parent.postMessage(
                  { isStreamlitMessage: true, type: 'streamlit:setComponentValue', value: data },
                  '*'
                );
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 2000 }
        );
    }
    sendGPS();
    setInterval(sendGPS, 2000);
    </script>
    """,
    height=0,
)

# ---- Parse gps_raw instead of st.query_params ----
coords = None
if gps_raw:
    if isinstance(gps_raw, str) and gps_raw.startswith("ERROR:"):
        st.session_state.gps_error = gps_raw.replace("ERROR:", "")
    else:
        try:
            parts = gps_raw.split(",")
            coords = {
                "lat":       float(parts[0]),
                "lon":       float(parts[1]),
                "acc":       float(parts[2]),
                "gps_speed": float(parts[3]),
                "heading":   float(parts[4]),
                "altitude":  float(parts[5]),
            }
            st.session_state.gps_error = None
        except Exception as e:
            st.session_state.gps_error = f"Parse error: {e}"

# ✅ Read GPS from URL query params (set by JS above)
gps_raw = st.query_params.get("gps", None)

st.sidebar.write(f"GPS Raw Param: `{gps_raw}`")

# =========================
# PARSE GPS STRING
# =========================
coords = None
if gps_raw:
    if gps_raw.startswith("ERROR:"):
        st.session_state.gps_error = gps_raw.replace("ERROR:", "")
    else:
        try:
            parts = gps_raw.split(",")
            coords = {
                "lat":       float(parts[0]),
                "lon":       float(parts[1]),
                "acc":       float(parts[2]),
                "gps_speed": float(parts[3]),
                "heading":   float(parts[4]),
                "altitude":  float(parts[5]),
            }
            st.session_state.gps_error = None
        except Exception as e:
            st.session_state.gps_error = f"Parse error: {e}"

# =========================
# STATUS BAR
# =========================
status = st.empty()
if st.session_state.gps_error:
    status.error(f"❌ GPS Error: {st.session_state.gps_error}")
elif coords:
    elapsed = int(time.time() - st.session_state.start_time) \
              if st.session_state.start_time else 0
    status.success(
        f"✅ GPS Lock | "
        f"Lat: {coords['lat']:.6f} | "
        f"Lon: {coords['lon']:.6f} | "
        f"Accuracy: {coords['acc']:.1f}m | "
        f"Tick #{st.session_state.tick} | "
        f"Elapsed: {elapsed}s"
    )
else:
    status.warning(
        "⏳ Waiting for GPS... "
        "**Allow location permission in your browser**"
    )

# =========================
# APPEND ROW EVERY TICK
# =========================
if coords and st.session_state.tracking:
    lat       = coords["lat"]
    lon       = coords["lon"]
    acc       = coords["acc"]
    gps_speed = coords["gps_speed"]
    heading   = coords["heading"]
    t         = time.time()

    if st.session_state.data:
        prev  = st.session_state.data[-1]
        dist  = haversine(prev["lat"], prev["lon"], lat, lon)
        dt    = max(t - prev["time"], 0.1)

        raw_speed    = (gps_speed * 3.6 if gps_speed > 0
                        else (dist / dt) * 3600)
        smooth_speed = kalman_filter(raw_speed, st.session_state.kf_speed)
        st.session_state.kf_speed = smooth_speed
        acc_val = ((smooth_speed - prev["speed"]) / 3.6) / dt
        mode    = ("Idle" if smooth_speed < 2
                   else "Urban" if smooth_speed < 40
                   else "Highway")

        new_row = {
            "time": t, "lat": round(lat,6), "lon": round(lon,6),
            "accuracy_m": round(acc,1),
            "speed": round(smooth_speed,2), "raw_speed": round(raw_speed,2),
            "acc": round(acc_val,4), "heading": round(heading,1),
            "mode": mode, "distance_step": round(dist,6),
        }
    else:
        new_row = {
            "time": t, "lat": round(lat,6), "lon": round(lon,6),
            "accuracy_m": round(acc,1), "speed": 0.0, "raw_speed": 0.0,
            "acc": 0.0, "heading": round(heading,1),
            "mode": "Idle", "distance_step": 0.0,
        }

    st.session_state.data.append(new_row)
    st.sidebar.write(f"✅ Row {len(st.session_state.data)} appended")

# =========================
# LIVE DASHBOARD
# =========================
if st.session_state.data:
    df     = pd.DataFrame(st.session_state.data)
    latest = df.iloc[-1]
    total  = df["distance_step"].sum()

    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("🚀 Speed",    f"{latest['speed']:.1f} km/h")
    m2.metric("⚡ Accel",    f"{latest['acc']:.3f} m/s²")
    m3.metric("🗺 Mode",      latest["mode"])
    m4.metric("📏 Distance", f"{total:.4f} km")
    m5.metric("🎯 Accuracy", f"{latest['accuracy_m']:.0f} m")
    m6.metric("📝 Rows",     len(df))

    t1,t2,t3 = st.tabs(["📈 Speed","📉 Accel","🗺 Map"])
    with t1: st.line_chart(df["speed"])
    with t2: st.line_chart(df["acc"])
    with t3: st.map(df[["lat","lon"]])

# =========================
# DOWNLOAD
# =========================
st.divider()
if st.session_state.excel_ready and os.path.exists(EXCEL_FILE):
    with open(EXCEL_FILE,"rb") as f:
        st.download_button(
            "📥 Download Trip Excel", f.read(),
            f"GPS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    st.caption(f"📊 {len(st.session_state.data)} rows — 1 per 2 seconds")
else:
    st.info("▶ Start → drive → ⏹ Stop → download Excel")

# =========================
# AUTO REFRESH EVERY 2 SECONDS
# =========================
if st.session_state.tracking:
    st.session_state.tick += 1
    time.sleep(2)
    st.rerun()
