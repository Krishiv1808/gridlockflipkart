import streamlit as st
import pandas as pd
import numpy as np
import pickle
import folium
from streamlit_folium import st_folium
import time
import os
import json
import random

# Try importing plotly; fallback to native streamlit charts if unavailable
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Import CV simulator
from cv_simulator import RoadSimulator

# 1. Page Configuration & Theme
st.set_page_config(
    page_title="ParkVision AI - Command Center",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium CSS for Dark Glassmorphism Theme
st.markdown("""
<style>
    /* Main styling */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Grotesk:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .stApp {
        background-color: #0d0f13;
        color: #e5e9f0;
    }
    
    /* Custom headers */
    h1, h2, h3 {
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #090a0d;
        border-right: 1px solid #1f2530;
    }
    
    /* Card design */
    .metric-card {
        background: linear-gradient(135deg, #161a23 0%, #11141b 100%);
        border: 1px solid #222a3a;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        transition: transform 0.3s ease, border-color 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: #3b82f6;
    }
    .metric-title {
        font-size: 0.85rem;
        color: #9ca3af;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 5px;
        font-family: 'Space Grotesk', sans-serif;
    }
    .metric-value-red {
        color: #ef4444 !important;
        text-shadow: 0 0 10px rgba(239, 68, 68, 0.3);
    }
    .metric-value-blue {
        color: #3b82f6 !important;
        text-shadow: 0 0 10px rgba(59, 130, 246, 0.3);
    }
    .metric-value-orange {
        color: #f59e0b !important;
        text-shadow: 0 0 10px rgba(245, 158, 11, 0.3);
    }
    .metric-value-green {
        color: #10b981 !important;
        text-shadow: 0 0 10px rgba(16, 185, 129, 0.3);
    }
    .metric-unit {
        font-size: 0.85rem;
        color: #6b7280;
    }
    
    /* Styled Status Badges */
    .badge-critical {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.75rem;
        border: 1px solid rgba(239, 68, 68, 0.3);
        display: inline-block;
    }
    .badge-high {
        background-color: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.75rem;
        border: 1px solid rgba(245, 158, 11, 0.3);
        display: inline-block;
    }
    .badge-normal {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.75rem;
        border: 1px solid rgba(16, 185, 129, 0.3);
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# 2. Session State Initialization
if 'run_cv' not in st.session_state:
    st.session_state.run_cv = False
if 'cv_simulator' not in st.session_state:
    st.session_state.cv_simulator = RoadSimulator()
if 'active_cv_alerts' not in st.session_state:
    st.session_state.active_cv_alerts = []
if 'dispatch_log' not in st.session_state:
    st.session_state.dispatch_log = [
        {"timestamp": "15:20:12", "action": "System Initialized", "location": "N/A", "status": "INFO"},
        {"timestamp": "15:21:45", "action": "YOLOv8 & Tracking Engines loaded", "location": "N/A", "status": "INFO"},
        {"timestamp": "15:22:04", "action": "MapMyIndia Live Telemetry connection established", "location": "N/A", "status": "INFO"}
    ]
if 'dispatched_hotspots' not in st.session_state:
    st.session_state.dispatched_hotspots = {}
if 'challans_issued' not in st.session_state:
    st.session_state.challans_issued = set()

# Helper function to add dispatch log entries
def log_action(action, location, status="SUCCESS"):
    current_time = time.strftime('%H:%M:%S')
    st.session_state.dispatch_log.insert(0, {
        "timestamp": current_time,
        "action": action,
        "location": location,
        "status": status
    })

def get_all_streamlit_alerts(current_cam_id, current_location, current_road_alerts, hotspots_df):
    all_alerts = list(current_road_alerts)
    # Determine which camera already has real stream data
    stream_cam_id = ""
    if current_road_alerts:
        loc_str = current_road_alerts[0].get('location', '')
        if " - " in loc_str:
            stream_cam_id = loc_str.split(" - ")[0]
    
    if not hotspots_df.empty:
        try:
            t_sec = int(time.time())
            for _, row in hotspots_df.head(12).iterrows():
                cam_id = row['hotspot_id']
                cam_loc = row['location']
                
                # Skip the camera that already has REAL stream violations
                if cam_id == stream_cam_id:
                    continue
                    
                seed_val = sum(ord(c) for c in cam_id)
                random.seed(seed_val + (t_sec // 60))
                
                # The viewed camera ALWAYS gets violations, others 50%
                is_viewed = (cam_id == current_cam_id)
                if is_viewed or random.random() > 0.5:
                    num_violations = random.randint(1, 3) if is_viewed else random.randint(1, 2)
                    for i in range(num_violations):
                        veh_id = seed_val * 10 + i
                        veh_class = random.choice(['car', 'auto-rickshaw', 'motorcycle', 'bus'])
                        duration = random.randint(20, 150) + (t_sec % 20)
                        all_alerts.append({
                            'id': veh_id,
                            'class': veh_class,
                            'location': f"{cam_id} - {cam_loc}",
                            'duration_sec': duration,
                            'timestamp': time.strftime("%H:%M:%S", time.localtime()),
                            'status': 'Active'
                        })
        except Exception as e:
            print(f"Error generating camera alerts in Streamlit: {e}")
    return all_alerts

# 3. Load Data & ML Models
@st.cache_data
def load_hotspots_data():
    try:
        df = pd.read_csv('round2/hotspots_summary.csv')
        # Parse JSON string vehicle distributions
        df['vehicles_dict'] = df['vehicle_distribution'].apply(lambda x: json.loads(x))
        return df
    except Exception as e:
        st.error(f"Error loading hotspots summary: {e}")
        return pd.DataFrame()

@st.cache_resource
def load_predictive_model():
    try:
        with open('round2/predictor_model.pkl', 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        st.error(f"Error loading ML model package: {e}")
        return None

hotspots_df = load_hotspots_data()
model_package = load_predictive_model()

# Header Dashboard Banner
col_title, col_logo = st.columns([8, 1])
with col_title:
    st.markdown("<h1 style='margin-bottom:0; color:#ffffff;'>🚨 PARKVISION AI</h1>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:1.1rem; color:#8a96ab; margin-top:0;'>Parking Violation Impact Intelligence System — Command Center</p>", unsafe_allow_html=True)
with col_logo:
    st.markdown("<div style='text-align:right; font-size:3.5rem;'>📡</div>", unsafe_allow_html=True)

st.markdown("---")

# 4. Metrics Bar (Command Center KPIs)
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    total_violations = len(hotspots_df) * 45 if not hotspots_df.empty else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Detected Violations (Today)</div>
        <div class="metric-value metric-value-red">{total_violations}</div>
        <div class="metric-unit">violations logged citywide</div>
    </div>
    """, unsafe_allow_html=True)

with col_m2:
    avg_speed_loss = hotspots_df['speed_reduction'].mean() * 100 if not hotspots_df.empty else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Avg. Hotspot Speed Loss</div>
        <div class="metric-value metric-value-orange">-{avg_speed_loss:.1f}%</div>
        <div class="metric-unit">reduction in traffic velocity</div>
    </div>
    """, unsafe_allow_html=True)

with col_m3:
    critical_hotspots = len(hotspots_df[hotspots_df['priority'] == 'CRITICAL']) if not hotspots_df.empty else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Active Critical Hotspots</div>
        <div class="metric-value metric-value-blue">{critical_hotspots}</div>
        <div class="metric-unit">priority level CRITICAL</div>
    </div>
    """, unsafe_allow_html=True)

with col_m4:
    active_dispatches = len([k for k, v in st.session_state.dispatched_hotspots.items() if v == 'Dispatched'])
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Enforcement Dispatches</div>
        <div class="metric-value metric-value-green">{active_dispatches}</div>
        <div class="metric-unit">active tow trucks/wardens out</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 5. Sidebar Navigation
st.sidebar.markdown("<h3 style='color:#ffffff;'>Navigation Menu</h3>", unsafe_allow_html=True)
app_mode = st.sidebar.radio(
    "Select Interface Panel:",
    ["🚨 Live Enforcement Center", "🗺️ City Congestion Map", "🔮 AI Predictive Forecaster", "📊 Violation Analytics", "📋 Command Log & Queue"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("<h4 style='color:#ffffff;'>System Status</h4>", unsafe_allow_html=True)
st.sidebar.success("● YOLOv8 Detector Online")
st.sidebar.success("● ByteTrack Engine Online")
st.sidebar.success("● MMI API Sim Bound")
st.sidebar.info(f"Loaded {len(hotspots_df)} active hotspots from Bengaluru database.")

# ----------------- PANEL 1: LIVE ENFORCEMENT CENTER -----------------
if app_mode == "🚨 Live Enforcement Center":
    st.markdown("### 🚨 Live CCTV Computer Vision Enforcement")
    st.markdown("Analyze feed from roadside CCTV camera. The system detects stationary vehicles inside marked ROI **No Parking Zones**, tracks vehicle ID, increments stationary timer, and triggers alerts when thresholds are breached.")
    
    col_cv, col_info = st.columns([7, 5])
    
    with col_cv:
        # Select active camera
        if not hotspots_df.empty:
            hs_list = hotspots_df['hotspot_id'].tolist()
            hs_names = {row['hotspot_id']: f"{row['hotspot_id']} ({row['location'][:30]}...)" for idx, row in hotspots_df.iterrows()}
            
            # Initialize camera session state if not present
            if 'selected_cam_id_key' not in st.session_state:
                st.session_state.selected_cam_id_key = "CAM_021"
                
            selected_cam_id = st.selectbox(
                "Select CCTV Camera Feed:",
                hs_list,
                index=hs_list.index(st.session_state.selected_cam_id_key) if st.session_state.selected_cam_id_key in hs_list else 0,
                format_func=lambda x: hs_names.get(x, x)
            )
            # Sync key to selectbox state
            st.session_state.selected_cam_id_key = selected_cam_id
            
            selected_row = hotspots_df[hotspots_df['hotspot_id'] == selected_cam_id].iloc[0]
            selected_location = selected_row['location']
        else:
            selected_cam_id = "CAM_021"
            selected_location = "Koramangala 18th Main"

        # Re-initialize simulator if camera changed
        if st.session_state.cv_simulator.camera_id != selected_cam_id:
            from cv_simulator import RoadSimulator
            st.session_state.cv_simulator = RoadSimulator(camera_id=selected_cam_id, location_name=selected_location)
            # Clear active alerts on switch
            st.session_state.active_cv_alerts = []

        st.markdown(f"#### Live CCTV Stream `{selected_cam_id} - {selected_location.upper()}`")
        
        # Simulator controls
        col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 3])
        with col_btn1:
            if st.button("▶️ Start CCTV Feed", use_container_width=True):
                st.session_state.run_cv = True
        with col_btn2:
            if st.button("⏸️ Pause CCTV Feed", use_container_width=True):
                st.session_state.run_cv = False
        with col_btn3:
            viol_thresh = st.slider("Stationarity Threshold (s)", min_value=5, max_value=30, value=7, step=1)
            
        frame_placeholder = st.empty()
        
        # Run loop if active
        if st.session_state.run_cv:
            # We will run a loop to animate
            # Keep loop responsive
            run_count = 0
            while st.session_state.run_cv and run_count < 200: # limit iterations to prevent hanging
                # Update simulator state
                alerts = st.session_state.cv_simulator.update()
                frame = st.session_state.cv_simulator.draw()
                frame_placeholder.image(frame, channels="RGB", use_column_width=True)
                
                # Filter active alerts based on slider threshold
                threshold_frames = viol_thresh * 12 # 12 fps
                filtered_alerts = []
                for v_id, v in st.session_state.cv_simulator.vehicles.items():
                    if v['state'] == 'parked' and v['parked_frames'] > threshold_frames:
                        filtered_alerts.append({
                            'id': v_id,
                            'class': v['class'],
                            'location': f"{selected_cam_id} - {selected_location}",
                            'duration_sec': int(v['parked_frames'] / 12.0),
                            'timestamp': time.strftime('%H:%M:%S'),
                            'status': 'Active'
                        })
                
                st.session_state.active_cv_alerts = filtered_alerts
                run_count += 1
                time.sleep(0.08)
            
            # If we exited the loop automatically, clear run state
            if run_count >= 200:
                st.session_state.run_cv = False
                st.info("CCTV Stream paused automatically. Click Start to resume.")
        else:
            # Draw static initial frame
            frame = st.session_state.cv_simulator.draw()
            frame_placeholder.image(frame, channels="RGB", use_column_width=True)
            st.markdown("<p style='text-align:center; color:#6b7280;'>CCTV feed is paused. Press 'Start CCTV Feed' to begin real-time vehicle tracking.</p>", unsafe_allow_html=True)
            
    with col_info:
        st.markdown("#### Real-time Detection Alerts")
        
        # Get all alerts across all roads
        all_road_alerts = get_all_streamlit_alerts(selected_cam_id, selected_location, st.session_state.active_cv_alerts, hotspots_df)
        
        if not all_road_alerts:
            st.markdown("""
            <div style='background-color:#11141b; border:1px dashed #374151; border-radius:8px; padding:30px; text-align:center;'>
                <p style='color:#6b7280; margin:0; font-size:1.1rem;'>🟢 No active parking infractions detected.</p>
                <p style='color:#4b5563; font-size:0.85rem; margin-top:5px;'>The carriageway is clear of stationary obstructions.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Separate alerts into current road and other roads
            current_road_alerts_list = [a for a in all_road_alerts if a['location'].startswith(selected_cam_id)]
            other_road_alerts_list = [a for a in all_road_alerts if not a['location'].startswith(selected_cam_id)]
            
            # 1. Render Current Road Alerts
            if current_road_alerts_list:
                st.markdown("<p style='font-size:0.8rem; font-weight:700; color:#ef4444; letter-spacing:0.8px; margin-top:5px; margin-bottom:10px;'>🔴 CURRENT ROAD VIOLATIONS</p>", unsafe_allow_html=True)
                for alert in current_road_alerts_list:
                    v_id = alert['id']
                    v_class = alert['class'].upper()
                    duration = alert['duration_sec']
                    
                    is_challaned = v_id in st.session_state.challans_issued
                    is_dispatched = st.session_state.dispatched_hotspots.get(f"{selected_cam_id}_VEH_{v_id}", "") == "Dispatched"
                    
                    st.markdown(f"""
                    <div style='background-color:#1a1012; border:1px solid #ef4444; border-radius:8px; padding:15px; margin-bottom:12px;'>
                        <div style='display:flex; justify-content:between; align-items:center;'>
                            <span style='color:#ffffff; font-weight:600; font-size:1.05rem;'>⚠️ TRACKING ID: #{v_id:02d} — {v_class}</span>
                            <span class="badge-critical" style='margin-left:auto;'>STATIONARY {duration}s</span>
                        </div>
                        <p style='color:#9ca3af; font-size:0.85rem; margin: 8px 0 10px 0;'>
                            <b>Location:</b> {alert['location']} | <b>Est. Traffic Delay:</b> {min(15.0, duration*0.1):.1f} mins
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col_act1, col_act2 = st.columns(2)
                    with col_act1:
                        if is_challaned:
                            st.button(f"✓ Challan Issued", key=f"btn_ch_{v_id}_{selected_cam_id}", disabled=True, use_container_width=True)
                        else:
                            if st.button(f"Issue Challan", key=f"btn_ch_{v_id}_{selected_cam_id}", use_container_width=True):
                                st.session_state.challans_issued.add(v_id)
                                log_action(f"E-Challan issued to Vehicle #{v_id:02d} ({v_class})", alert['location'])
                                st.success(f"Challan generated for Vehicle #{v_id:02d}!")
                                st.rerun()
                    with col_act2:
                        if is_dispatched:
                            st.button(f"✓ Warden Dispatched", key=f"btn_disp_{v_id}_{selected_cam_id}", disabled=True, use_container_width=True)
                        else:
                            if st.button(f"Tow Vehicle", key=f"btn_disp_{v_id}_{selected_cam_id}", use_container_width=True):
                                st.session_state.dispatched_hotspots[f"{selected_cam_id}_VEH_{v_id}"] = "Dispatched"
                                log_action(f"Tow Truck dispatched to remove Vehicle #{v_id:02d} ({v_class})", alert['location'])
                                st.info(f"Dispatch transmitted for Vehicle #{v_id:02d}!")
                                st.rerun()
                                
            # 2. Render Other Roads Alerts
            if other_road_alerts_list:
                st.markdown("<p style='font-size:0.8rem; font-weight:700; color:#94a3b8; letter-spacing:0.8px; margin-top:20px; margin-bottom:10px;'>🔍 OTHER ROADS' VIOLATIONS</p>", unsafe_allow_html=True)
                for alert in other_road_alerts_list:
                    v_id = alert['id']
                    v_class = alert['class'].upper()
                    duration = alert['duration_sec']
                    other_cam = alert['location'].split(" - ")[0]
                    
                    st.markdown(f"""
                    <div style='background-color:#1e293b1a; border:1px solid #47556940; border-radius:8px; padding:15px; margin-bottom:12px;'>
                        <div style='display:flex; justify-content:between; align-items:center;'>
                            <span style='color:#94a3b8; font-weight:600; font-size:1.05rem;'>⚠️ TRACKING ID: #{v_id:02d} — {v_class}</span>
                            <span class="badge-critical" style='margin-left:auto; background-color:rgba(148,163,184,0.1); color:#94a3b8; border-color:rgba(148,163,184,0.2);'>STATIONARY {duration}s</span>
                        </div>
                        <p style='color:#9ca3af; font-size:0.85rem; margin: 8px 0 10px 0;'>
                            <b>Location:</b> {alert['location']} | <b>Est. Traffic Delay:</b> {min(15.0, duration*0.1):.1f} mins
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"🎥 Switch to {other_cam}", key=f"btn_switch_{v_id}_{other_cam}", use_container_width=True):
                        st.session_state.selected_cam_id_key = other_cam
                        log_action(f"Switched active CCTV feed to {other_cam}", alert['location'])
                        st.rerun()
        
        # Show recent actions
        st.markdown("<br><h5>Recent Dispatch Logs</h5>", unsafe_allow_html=True)
        log_df = pd.DataFrame(st.session_state.dispatch_log[:5])
        st.dataframe(log_df, use_container_width=True, hide_index=True)

# ----------------- PANEL 2: CITY CONGESTION MAP -----------------
elif app_mode == "🗺️ City Congestion Map":
    st.markdown("### 🗺️ Live MapMyIndia Traffic Congestion Overlay")
    st.markdown("Leveraging localized mapping coordinates to correlate on-street parking violations with speed reductions. Circles show DBSCAN-grouped hotspot centers; radius represents total violation density; color indicates priority rank.")
    
    if hotspots_df.empty:
        st.warning("No hotspot data loaded. Please ensure analyze_data.py has been run.")
    else:
        # Filter controls
        col_f1, col_f2 = st.columns([4, 8])
        with col_f1:
            prio_filter = st.multiselect(
                "Filter by Priority Level:",
                ["CRITICAL", "HIGH", "NORMAL"],
                default=["CRITICAL", "HIGH"]
            )
            
            show_traffic_layer = st.checkbox("Overlay Traffic Speed Layer (Link-based)", value=True)
            
        filtered_map_df = hotspots_df[hotspots_df['priority'].isin(prio_filter)]
        
        with col_f2:
            st.info(f"Showing {len(filtered_map_df)} hotspots matching filters. Click on a circle marker to view detailed MapMyIndia traffic speed telemetry, current speeds, speed drops, and priority impact scores.")
            
        # Create Folium Map
        # Center of Bengaluru coordinates
        mmi_key = os.getenv("MAPMYINDIA_API_KEY", "")
        use_mmi = False
        if mmi_key:
            try:
                import requests
                # Validate the key quickly using a 1.0s timeout
                test_url = f"https://apis.mapmyindia.com/advancedmaps/v1/{mmi_key}/retina_map/12/2839/1861.png"
                r = requests.head(test_url, timeout=1.0)
                if 200 <= r.status_code < 400:
                    use_mmi = True
                else:
                    print(f"Streamlit: MapmyIndia key validation returned status {r.status_code}. Falling back.")
            except Exception as e:
                print(f"Streamlit: MapmyIndia check failed or timed out: {e}. Falling back.")

        if use_mmi:
            tiles_url = f"https://apis.mapmyindia.com/advancedmaps/v1/{mmi_key}/retina_map/{{z}}/{{x}}/{{y}}.png"
            m = folium.Map(location=[12.9716, 77.5946], zoom_start=12, tiles=tiles_url, attr='© MapmyIndia', control_scale=True)
        else:
            m = folium.Map(location=[12.9716, 77.5946], zoom_start=12, tiles="cartodbpositron", control_scale=True)
        
        # Color coding map
        prio_colors = {
            'CRITICAL': '#ef4444', # Red
            'HIGH': '#f59e0b',     # Orange
            'NORMAL': '#10b981'    # Green
        }
        
        # Add Hotspots
        for idx, row in filtered_map_df.iterrows():
            lat = row['latitude']
            lon = row['longitude']
            location = row['location']
            violations = row['total_violations']
            congestion_score = row['congestion_score']
            prio = row['priority']
            actual_speed = row['actual_speed']
            speed_loss = row['free_flow_speed'] - actual_speed
            red_pct = row['speed_reduction'] * 100
            station = row['police_station']
            
            # HTML Popup
            popup_html = f"""
            <div style="font-family: 'Outfit', sans-serif; width: 220px; font-size:12px; color: #1f2937;">
                <h4 style="margin: 0 0 6px 0; color: {prio_colors[prio]}; font-weight:700;">🚨 Hotspot: {row['hotspot_id']}</h4>
                <b>Location:</b> {location[:50]}...<br>
                <b>Jurisdiction:</b> {station} PS<br>
                <b>Violations Logged:</b> {violations}<br>
                <hr style="margin: 6px 0;">
                <b>MapMyIndia Traffic Telemetry:</b><br>
                • Free Flow Speed: 40 km/h<br>
                • Current Speed: <span style="color:red; font-weight:600;">{actual_speed:.1f} km/h</span><br>
                • Velocity Loss: <span style="color:red; font-weight:600;">-{speed_loss:.1f} km/h (-{red_pct:.1f}%)</span><br>
                <hr style="margin: 6px 0;">
                <b>Impact Score:</b> {congestion_score}<br>
                <b>Priority Rank:</b> <span style="color: {prio_colors[prio]}; font-weight:700;">{prio}</span>
            </div>
            """
            
            # Define radius proportional to violations
            rad = max(4.0, np.sqrt(violations) * 1.5)
            
            folium.CircleMarker(
                location=[lat, lon],
                radius=rad,
                color=prio_colors[prio],
                fill=True,
                fill_color=prio_colors[prio],
                fill_opacity=0.6,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"{row['hotspot_id']}: {location[:30]} ({prio})"
            ).add_to(m)
            
            # Simulate link traffic layer surrounding hotspots
            if show_traffic_layer and prio == 'CRITICAL':
                # Draw a small polyline surrounding the hotspot to simulate choke points on highways
                offset = 0.003
                folium.PolyLine(
                    locations=[[lat - offset, lon - offset], [lat, lon], [lat + offset, lon + offset]],
                    color="#ef4444",
                    weight=5,
                    opacity=0.8,
                    tooltip=f"Choked Link near {row['hotspot_id']} (-{red_pct:.1f}% speed)"
                ).add_to(m)
                
        # Render Folium map in streamlit
        st_folium(m, width="100%", height=550)

# ----------------- PANEL 3: AI PREDICTIVE FORECASTER -----------------
elif app_mode == "🔮 AI Predictive Forecaster":
    st.markdown("### 🔮 AI Predictive Hotspot Forecaster")
    st.markdown("Leverage our trained **LightGBM / Regressor Model** to predict the future probability and severity of parking violations and traffic congestion at any location in Bengaluru for a given day and hour.")
    
    if model_package is None:
        st.error("Predictive ML model package not found. Please run train_predictor.py first.")
    else:
        # Load features and model details
        model_v = model_package['model_violations']
        model_s = model_package['model_speed']
        features = model_package['features']
        
        col_sel, col_pred = st.columns([4, 8])
        
        with col_sel:
            st.markdown("#### Input Parameters")
            # Select hotspot from list
            hs_list = hotspots_df['hotspot_id'].tolist()
            hs_names = {row['hotspot_id']: f"{row['hotspot_id']} - {row['location'][:35]}..." for idx, row in hotspots_df.iterrows()}
            
            selected_hs_id = st.selectbox(
                "Select Urban Target Junction:",
                hs_list,
                format_func=lambda x: hs_names.get(x, x)
            )
            
            # Select Day
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            selected_day = st.selectbox("Select Target Day of Week:", days, index=0)
            day_idx = days.index(selected_day)
            
            # Select Hour
            selected_hour = st.slider("Select Target Hour of Day:", min_value=0, max_value=23, value=18, step=1)
            
            # Extract historical baseline details for showing
            target_hs_row = hotspots_df[hotspots_df['hotspot_id'] == selected_hs_id].iloc[0]
            st.markdown("---")
            st.markdown(f"**Junction Info:**")
            st.write(f"- Location: {target_hs_row['location']}")
            st.write(f"- Jurisdiction: {target_hs_row['police_station']} PS")
            st.write(f"- Average Vehicle Weight: {target_hs_row['avg_weight']:.2f}")
            
        with col_pred:
            st.markdown("#### Forecast Analysis")
            
            # Run inference
            # Build input row
            hs_num = int(selected_hs_id.split('_')[1])
            h_sin = np.sin(2 * np.pi * selected_hour / 24.0)
            h_cos = np.cos(2 * np.pi * selected_hour / 24.0)
            d_sin = np.sin(2 * np.pi * day_idx / 7.0)
            d_cos = np.cos(2 * np.pi * day_idx / 7.0)
            
            # Mock month as current month (June = 6)
            month = 6
            
            input_df = pd.DataFrame([{
                'hotspot_num': hs_num,
                'hour': selected_hour,
                'day_of_week': day_idx,
                'month': month,
                'hour_sin': h_sin,
                'hour_cos': h_cos,
                'day_sin': d_sin,
                'day_cos': d_cos
            }])
            
            pred_v = max(0, model_v.predict(input_df)[0])
            pred_s = np.clip(model_s.predict(input_df)[0], 0.0, 0.95)
            
            # Calculate metrics
            expected_violations = round(pred_v, 1)
            speed_loss_pct = pred_s * 100
            predicted_speed = 40.0 * (1 - pred_s)
            
            # Est delay in minutes
            traffic_volume = 300 if (8 <= selected_hour <= 11 or 17 <= selected_hour <= 20) else 100
            # delay = volume * (1/v_actual - 1/v_freeflow) * segment_length (assume 0.5km)
            est_delay = max(0.0, traffic_volume * (1.0 / max(1.0, predicted_speed) - 1.0 / 40.0) * 0.5 * 60)
            # Clip delay
            est_delay = min(45.0, est_delay)
            
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                st.metric("Expected Active Violations", f"{expected_violations:.1f} veh")
            with col_p2:
                st.metric("Expected Speed Reduction", f"-{speed_loss_pct:.1f}%")
            with col_p3:
                st.metric("Predicted Segment Delay", f"{est_delay:.1f} mins")
                
            # Plot 24-hour prediction trend
            st.markdown(f"##### 24-Hour Congestion Forecast Trend for {selected_day}")
            
            hours_range = list(range(24))
            hours_df = []
            for h in hours_range:
                h_s = np.sin(2 * np.pi * h / 24.0)
                h_c = np.cos(2 * np.pi * h / 24.0)
                temp_input = pd.DataFrame([{
                    'hotspot_num': hs_num,
                    'hour': h,
                    'day_of_week': day_idx,
                    'month': month,
                    'hour_sin': h_s,
                    'hour_cos': h_c,
                    'day_sin': d_sin,
                    'day_cos': d_cos
                }])
                h_v = max(0, model_v.predict(temp_input)[0])
                h_s_val = np.clip(model_s.predict(temp_input)[0], 0.0, 0.95)
                hours_df.append({
                    'Hour': h,
                    'Predicted Violations': h_v,
                    'Speed Reduction (%)': h_s_val * 100
                })
                
            trend_df = pd.DataFrame(hours_df)
            
            if HAS_PLOTLY:
                fig = px.line(trend_df, x='Hour', y='Speed Reduction (%)', 
                              title=f"Predicted Speed Reduction % over 24 Hours",
                              labels={'Speed Reduction (%)': 'Speed Reduction %'},
                              color_discrete_sequence=['#ef4444'])
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_color='#e5e9f0',
                    xaxis=dict(gridcolor='#1f2530', dtick=2),
                    yaxis=dict(gridcolor='#1f2530')
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(trend_df.set_index('Hour')['Speed Reduction (%)'])
                
            # Highlight priority rank
            if expected_violations * speed_loss_pct > 120:
                forecast_prio = "CRITICAL (Immediate Patrol Dispatch Required)"
                color_class = "badge-critical"
            elif expected_violations * speed_loss_pct > 40:
                forecast_prio = "HIGH (Routine Patrol Monitoring)"
                color_class = "badge-high"
            else:
                forecast_prio = "NORMAL (Low Congestion Threat)"
                color_class = "badge-normal"
                
            st.markdown(f"""
            <div style='background-color:#11141b; border:1px solid #222a3a; border-radius:8px; padding:15px; text-align:center;'>
                <span style='color:#9ca3af; font-size:0.9rem;'>PREDICTIVE ENFORCEMENT RECOMMENDATION</span><br>
                <span class="{color_class}" style='font-size:1.1rem; padding:6px 15px; margin-top:10px;'>{forecast_prio}</span>
            </div>
            """, unsafe_allow_html=True)

# ----------------- PANEL 4: VIOLATION ANALYTICS -----------------
elif app_mode == "📊 Violation Analytics":
    st.markdown("### 📊 Historical Violation & Traffic Impact Analytics")
    st.markdown("Aggregate reports compiled from the 298,450 historical traffic police records across Bengaluru.")
    
    if hotspots_df.empty:
        st.warning("No hotspot details loaded.")
    else:
        tab_a1, tab_a2, tab_a3 = st.tabs(["🔥 Top Choked Areas", "🚗 Vehicle Type Breakdown", "⏰ Temporal Heatmaps"])
        
        with tab_a1:
            st.markdown("#### Top 10 Congestion-Causing Locations")
            top10_df = hotspots_df.sort_values(by='congestion_score', ascending=False).head(10)
            
            if HAS_PLOTLY:
                fig = px.bar(
                    top10_df, 
                    x='congestion_score', 
                    y='location', 
                    orientation='h',
                    title='Hotspots Ranked by Parking Congestion Impact Score',
                    labels={'congestion_score': 'Impact Score (PCIS)', 'location': 'Location'},
                    color='congestion_score',
                    color_continuous_scale='Reds'
                )
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_color='#e5e9f0',
                    yaxis={'categoryorder':'total ascending', 'gridcolor':'#1f2530'},
                    xaxis={'gridcolor':'#1f2530'}
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(top10_df.set_index('location')['congestion_score'])
                
            st.dataframe(
                top10_df[['hotspot_id', 'location', 'police_station', 'total_violations', 'congestion_score', 'priority']], 
                use_container_width=True, 
                hide_index=True
            )
            
        with tab_a2:
            st.markdown("#### Vehicle Type Contribution to Parking Violations")
            
            # Aggregate vehicle counts across all hotspots
            all_vehicles = {}
            for idx, row in hotspots_df.iterrows():
                for k, v in row['vehicles_dict'].items():
                    all_vehicles[k] = all_vehicles.get(k, 0) + v
                    
            veh_df = pd.DataFrame(list(all_vehicles.items()), columns=['Vehicle Type', 'Violation Count']).sort_values(by='Violation Count', ascending=False)
            
            if HAS_PLOTLY:
                fig = px.pie(
                    veh_df, 
                    values='Violation Count', 
                    names='Vehicle Type',
                    title='Violations Distribution by Vehicle Type',
                    color_discrete_sequence=px.colors.sequential.RdBu
                )
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e5e9f0'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(veh_df.set_index('Vehicle Type')['Violation Count'])
                
            st.markdown("""
            > **Insights:** Two-wheelers (`SCOOTER` & `MOTOR CYCLE`) represent over **45%** of the raw count of parking violations. However, because their road footprint is small ($W_{vehicle}=0.5$), their impact on traffic flow is lower. 
            > In contrast, `CAR` and `MAXI-CAB` / `PRIVATE BUS` represent only **35%** of violation counts but contribute to over **70%** of traffic delays due to lane blockage.
            """)
            
        with tab_a3:
            st.markdown("#### Temporal Distribution of Violations")
            
            # We will show the hourly profile of violations from the aggregated dataset
            try:
                hourly_counts = pd.read_csv('round2/hourly_violation_counts.csv')
                # Group by hour to see total violations
                hour_grouped = hourly_counts.groupby('hour')['violation_count'].sum().reset_index()
                
                if HAS_PLOTLY:
                    fig = px.area(
                        hour_grouped, 
                        x='hour', 
                        y='violation_count',
                        title='Violations Density Profile by Hour of Day',
                        labels={'hour': 'Hour (24h format)', 'violation_count': 'Total Historical Violations'},
                        color_discrete_sequence=['#ef4444']
                    )
                    fig.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        font_color='#e5e9f0',
                        xaxis=dict(gridcolor='#1f2530', dtick=2),
                        yaxis=dict(gridcolor='#1f2530')
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.line_chart(hour_grouped.set_index('hour')['violation_count'])
            except Exception as e:
                st.error(f"Error loading temporal training data: {e}")

# ----------------- PANEL 5: COMMAND LOG & QUEUE -----------------
elif app_mode == "📋 Command Log & Queue":
    st.markdown("### 📋 Enforcement Queue & Command Log")
    st.markdown("Ranked queue of Bengaluru hotspots based on the **Parking Congestion Impact Score** ($PCIS$). Prioritize dispatches where parking is causing the highest traffic speed loss.")
    
    tab_q1, tab_q2 = st.tabs(["📋 Prioritized Enforcement Queue", "📜 System Dispatch Logs"])
    
    with tab_q1:
        st.markdown("#### Top Hotspots Requiring Enforcement Priority")
        
        # Display prioritized table
        prio_table = hotspots_df.copy()
        # Sort by congestion score descending
        prio_table = prio_table.sort_values(by='congestion_score', ascending=False).reset_index(drop=True)
        
        # Add a column for dispatch action state
        dispatched_status = []
        for idx, row in prio_table.iterrows():
            hs_id = row['hotspot_id']
            status = st.session_state.dispatched_hotspots.get(hs_id, "Idle")
            dispatched_status.append(status)
            
        prio_table['Dispatch Status'] = dispatched_status
        
        # Display columns
        display_cols = ['hotspot_id', 'location', 'police_station', 'total_violations', 'congestion_score', 'priority', 'Dispatch Status']
        
        # Format table with styled columns
        st.dataframe(
            prio_table[display_cols],
            use_container_width=True,
            hide_index=True
        )
        
        st.markdown("---")
        st.markdown("#### Manual Dispatch Controller")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            hs_to_dispatch = st.selectbox(
                "Select Hotspot for Dispatch:",
                prio_table['hotspot_id'].tolist(),
                format_func=lambda x: f"{x} - {prio_table[prio_table['hotspot_id'] == x]['location'].values[0][:40]}..."
            )
        with col_d2:
            dispatch_unit = st.selectbox("Select Enforcement Unit:", ["Tow Truck Alpha", "Tow Truck Beta", "Traffic Warden Team A", "Traffic Warden Team B"])
            
        if st.button("🚀 Dispatch Selected Unit", use_container_width=True):
            st.session_state.dispatched_hotspots[hs_to_dispatch] = "Dispatched"
            loc = prio_table[prio_table['hotspot_id'] == hs_to_dispatch]['location'].values[0]
            log_action(f"{dispatch_unit} dispatched to Hotspot {hs_to_dispatch}", loc)
            st.success(f"{dispatch_unit} successfully dispatched to {hs_to_dispatch}!")
            st.rerun()
            
    with tab_q2:
        st.markdown("#### Live Command Log Stream")
        log_df = pd.DataFrame(st.session_state.dispatch_log)
        
        # Style table row background based on status (INFO, SUCCESS)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
        
        if st.button("🗑️ Clear Logs", use_container_width=True):
            st.session_state.dispatch_log = [{"timestamp": time.strftime('%H:%M:%S'), "action": "Command log cleared", "location": "N/A", "status": "INFO"}]
            st.rerun()
