from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
import pickle
import cv2
import time
import os
import json
import random
import sqlite3

# Try importing psycopg2 for PostgreSQL support (used on Render/cloud)
try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

app = FastAPI(
    title="ParkVision AI - API Server",
    description="Backend API server for traffic congestion and illegal parking intelligence",
    version="1.0.0"
)

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "parkvision.db")
CSV_PATH = os.path.join(BASE_DIR, "hotspots_summary.csv")
MODEL_PATH = os.path.join(BASE_DIR, "predictor_model.pkl")

# --- Dual-mode Database Layer ---
# If DATABASE_URL env var exists and psycopg2 is installed → PostgreSQL
# Otherwise → SQLite (local development)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL) and HAS_POSTGRES
PH = "%s" if USE_POSTGRES else "?"  # Placeholder for parameterized queries

if USE_POSTGRES:
    print(f"[DB] Using PostgreSQL (DATABASE_URL detected)")
else:
    print(f"[DB] Using SQLite at {DB_PATH}")

def get_db():
    """Returns a database connection (PostgreSQL or SQLite depending on environment)."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        return sqlite3.connect(DB_PATH)

# Global states
global_active_alerts = []

# Initialize Database
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        # PostgreSQL table definitions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id SERIAL PRIMARY KEY,
                hotspot_id TEXT,
                location TEXT,
                unit TEXT,
                timestamp TEXT,
                status TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS challans (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER,
                vehicle_type TEXT,
                location TEXT,
                amount INTEGER,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                role TEXT
            )
        """)
    else:
        # SQLite table definitions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hotspot_id TEXT,
                location TEXT,
                unit TEXT,
                timestamp TEXT,
                status TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS challans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER,
                vehicle_type TEXT,
                location TEXT,
                amount INTEGER,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                role TEXT
            )
        """)
    
    # Pre-populate default users if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute(f"INSERT INTO users (username, password, role) VALUES ({PH}, {PH}, {PH})", ('admin', 'admin123', 'admin'))
        cursor.execute(f"INSERT INTO users (username, password, role) VALUES ({PH}, {PH}, {PH})", ('citizen', 'citizen123', 'citizen'))
    conn.commit()
    conn.close()

init_db()

# Load Predictive ML Model Package
model_package = None
if os.path.exists(MODEL_PATH):
    try:
        with open(MODEL_PATH, 'rb') as f:
            model_package = pickle.load(f)
        print("Predictive ML models loaded successfully.")
    except Exception as e:
        print(f"Error loading ML model: {e}")
else:
    print(f"Warning: Model not found at {MODEL_PATH}")

# Import CV Simulator
from cv_simulator import RoadSimulator

# Generator for CCTV Video Streaming
def gen_frames(camera_id: str):
    global global_active_alerts
    location_name = "Koramangala 18th Main"
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH)
            row = df[df['hotspot_id'] == camera_id]
            if not row.empty:
                location_name = row.iloc[0]['location']
        except Exception as e:
            print(f"Error resolving location for {camera_id}: {e}")
            
    sim = RoadSimulator(camera_id=camera_id, location_name=location_name)
    while True:
        alerts = sim.update()
        global_active_alerts = alerts
        
        frame = sim.draw()
        # Convert RGB to BGR for cv2 JPEG compression
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        ret, buffer = cv2.imencode('.jpg', frame_bgr)
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        # ~12 FPS
        time.sleep(0.08)

# API ENDPOINTS

@app.get("/api/cv_stream")
def cv_stream(camera_id: str = "CAM_021"):
    """Serves the live OpenCV simulated CCTV camera stream."""
    return StreamingResponse(gen_frames(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/alerts")
def get_alerts(camera_id: str = ""):
    """Returns the list of current active parking violations detected by the CCTV stream (all roads)."""
    global global_active_alerts
    
    # Start with the actual real-time alerts of the currently active camera
    combined_alerts = list(global_active_alerts)
    
    # Determine which camera the real stream is generating for
    stream_cam_id = ""
    if len(global_active_alerts) > 0:
        loc_str = global_active_alerts[0]['location']
        if " - " in loc_str:
            stream_cam_id = loc_str.split(" - ")[0]
    
    # The camera the user is currently viewing (from frontend dropdown)
    viewed_cam_id = camera_id if camera_id else stream_cam_id
            
    if not os.path.exists(CSV_PATH):
        return combined_alerts
        
    try:
        df = pd.read_csv(CSV_PATH)
        t_sec = int(time.time())
        
        for _, row in df.head(12).iterrows():
            cam_id = row['hotspot_id']
            cam_loc = row['location']
            
            # Skip the camera that already has REAL stream violations
            if cam_id == stream_cam_id:
                continue
                
            seed_val = sum(ord(c) for c in cam_id)
            random.seed(seed_val + (t_sec // 60))
            
            # The camera the user is viewing ALWAYS gets violations (100%)
            # Other cameras get violations with 50% probability
            is_viewed = (cam_id == viewed_cam_id)
            if is_viewed or random.random() > 0.5:
                num_violations = random.randint(1, 3) if is_viewed else random.randint(1, 2)
                for i in range(num_violations):
                    veh_id = seed_val * 10 + i
                    veh_class = random.choice(['car', 'auto-rickshaw', 'motorcycle', 'bus'])
                    duration = random.randint(20, 150) + (t_sec % 20)
                    combined_alerts.append({
                        'id': veh_id,
                        'class': veh_class,
                        'location': f"{cam_id} - {cam_loc}",
                        'duration_sec': duration,
                        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                        'status': 'Active'
                    })
    except Exception as e:
        print(f"Error generating camera alerts: {e}")
        
    return combined_alerts

@app.get("/api/hotspots")
def get_hotspots():
    """Returns the preprocessed list of 150 hotspots with traffic speed reductions and priority scores."""
    if not os.path.exists(CSV_PATH):
        raise HTTPException(status_code=404, detail="Hotspots dataset not found. Run analyze_data.py first.")
    
    df = pd.read_csv(CSV_PATH)
    # Parse JSON strings in vehicle distribution column
    hotspots = []
    for _, row in df.iterrows():
        hotspot = row.to_dict()
        hotspot['vehicle_distribution'] = json.loads(row['vehicle_distribution'])
        hotspots.append(hotspot)
        
    return hotspots

@app.get("/api/map_key")
def get_map_key():
    """Returns the MapMyIndia API Key if configured in the environment and valid."""
    mmi_key = os.getenv("MAPMYINDIA_API_KEY", "")
    if not mmi_key:
        return {"map_key": ""}
    try:
        import requests
        # Validate by testing if we can reach MapmyIndia with this key
        test_url = f"https://apis.mapmyindia.com/advancedmaps/v1/{mmi_key}/map_load?v=1.5"
        r = requests.head(test_url, timeout=1.0)
        if 200 <= r.status_code < 400:
            return {"map_key": mmi_key}
        else:
            print(f"MapmyIndia key validation returned status {r.status_code}. Falling back.")
            return {"map_key": ""}
    except Exception as e:
        print(f"MapmyIndia validation failed or timed out: {e}. Falling back.")
        return {"map_key": ""}

class DispatchRequest(BaseModel):
    hotspot_id: str
    location: str
    unit: str

@app.post("/api/dispatch")
def create_dispatch(req: DispatchRequest):
    """Logs an enforcement vehicle dispatch to the database."""
    conn = get_db()
    cursor = conn.cursor()
    curr_time = time.strftime('%H:%M:%S')
    cursor.execute(
        f"INSERT INTO dispatches (hotspot_id, location, unit, timestamp, status) VALUES ({PH}, {PH}, {PH}, {PH}, {PH})",
        (req.hotspot_id, req.location, req.unit, curr_time, "Active")
    )
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": f"{req.unit} dispatched to {req.hotspot_id}"}

@app.get("/api/dispatch")
def get_dispatches():
    """Returns all historical dispatches logged in the database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT hotspot_id, location, unit, timestamp, status FROM dispatches ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    dispatches = []
    for r in rows:
        dispatches.append({
            "hotspot_id": r[0],
            "location": r[1],
            "unit": r[2],
            "timestamp": r[3],
            "status": r[4]
        })
    return dispatches

class ChallanRequest(BaseModel):
    vehicle_id: int
    vehicle_type: str
    location: str
    amount: int

@app.post("/api/challan")
def issue_challan(req: ChallanRequest):
    """Issues an E-Challan for a violating vehicle."""
    conn = get_db()
    cursor = conn.cursor()
    curr_time = time.strftime('%H:%M:%S')
    cursor.execute(
        f"INSERT INTO challans (vehicle_id, vehicle_type, location, amount, timestamp) VALUES ({PH}, {PH}, {PH}, {PH}, {PH})",
        (req.vehicle_id, req.vehicle_type, req.location, req.amount, curr_time)
    )
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": f"Challan of Rs.{req.amount} issued to Vehicle #{req.vehicle_id}"}

@app.get("/api/challans")
def get_challans():
    """Returns all historical E-Challans."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT vehicle_id, vehicle_type, location, amount, timestamp FROM challans ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    challans = []
    for r in rows:
        challans.append({
            "vehicle_id": r[0],
            "vehicle_type": r[1],
            "location": r[2],
            "amount": r[3],
            "timestamp": r[4]
        })
    return challans

class UserAuthRequest(BaseModel):
    username: str
    password: str

class UserRegisterRequest(BaseModel):
    username: str
    password: str
    role: str

@app.post("/api/register")
def register_user(req: UserRegisterRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO users (username, password, role) VALUES ({PH}, {PH}, {PH})", (req.username, req.password, req.role))
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    conn.close()
    return {"status": "SUCCESS", "message": "User registered successfully"}

@app.post("/api/login")
def login_user(req: UserAuthRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT role FROM users WHERE username = {PH} AND password = {PH}", (req.username, req.password))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"status": "SUCCESS", "role": row[0]}
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password")

class PredictionRequest(BaseModel):
    hotspot_id: str
    day_of_week: str
    hour: int

@app.post("/api/predict")
def predict_congestion(req: PredictionRequest):
    """Runs real-time machine learning prediction using our LightGBM model package."""
    global model_package
    if model_package is None:
        raise HTTPException(status_code=503, detail="Predictive model package not loaded on server.")
        
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if req.day_of_week not in days:
        raise HTTPException(status_code=400, detail="Invalid day of week. Use capitalization (e.g. Monday).")
        
    day_idx = days.index(req.day_of_week)
    hs_num = int(req.hotspot_id.split('_')[1])
    
    # Calculate features
    h_sin = np.sin(2 * np.pi * req.hour / 24.0)
    h_cos = np.cos(2 * np.pi * req.hour / 24.0)
    d_sin = np.sin(2 * np.pi * day_idx / 7.0)
    d_cos = np.cos(2 * np.pi * day_idx / 7.0)
    month = 6  # Simulated current month
    
    input_df = pd.DataFrame([{
        'hotspot_num': hs_num,
        'hour': req.hour,
        'day_of_week': day_idx,
        'month': month,
        'hour_sin': h_sin,
        'hour_cos': h_cos,
        'day_sin': d_sin,
        'day_cos': d_cos
    }])
    
    # Run predictions
    model_v = model_package['model_violations']
    model_s = model_package['model_speed']
    
    pred_v = max(0.0, float(model_v.predict(input_df)[0]))
    pred_s = float(np.clip(model_s.predict(input_df)[0], 0.05, 0.95))
    
    predicted_speed = 40.0 * (1 - pred_s)
    # Estimate traffic delay (mins) based on peak/off-peak volume
    traffic_volume = 300 if (8 <= req.hour <= 11 or 17 <= req.hour <= 20) else 100
    est_delay = min(45.0, max(0.0, traffic_volume * (1.0 / max(1.0, predicted_speed) - 1.0 / 40.0) * 0.5 * 60))
    
    # 24-hour predictions for charts
    hourly_trends = []
    for h in range(24):
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
        h_v = max(0.0, float(model_v.predict(temp_input)[0]))
        h_s_val = float(np.clip(model_s.predict(temp_input)[0], 0.05, 0.95))
        hourly_trends.append({
            "hour": h,
            "violations": round(h_v, 2),
            "speed_reduction_pct": round(h_s_val * 100, 2)
        })
        
    return {
        "hotspot_id": req.hotspot_id,
        "hour": req.hour,
        "day_of_week": req.day_of_week,
        "expected_violations": round(pred_v, 2),
        "speed_reduction_pct": round(pred_s * 100, 2),
        "predicted_speed_kmh": round(predicted_speed, 1),
        "estimated_delay_mins": round(est_delay, 1),
        "hourly_trends": hourly_trends
    }

# Mount Static Files (serves index.html at root '/')
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    print(f"Warning: static directory not found at {STATIC_DIR}")
