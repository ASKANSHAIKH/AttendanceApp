import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
import os
import random
import requests
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
page_icon = "logo.png" if os.path.exists("logo.png") else "❄️"
st.set_page_config(page_title="Attendance Check-In", layout="wide", page_icon=page_icon)

ADMIN_MOBILE = "9978815870"

# --- 2. PROFESSIONAL STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        /* Hide all admin/sidebar navigation elements */
        #MainMenu, footer, header, [data-testid="stToolbar"] {visibility: hidden;}
        .stDeployButton {display:none;}
        section[data-testid="stSidebar"] {display: none;} /* Hide the sidebar completely */
        
        .stApp { background-color: #f0f2f6; margin-top: -50px; }
        h3 { color: #0e3b43 !important; font-family: 'Helvetica', sans-serif; }
        .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input {
            background-color: white !important; color: black !important; border: 1px solid #ddd; border-radius: 8px;
        }
        div[data-baseweb="select"] > div { background-color: white !important; color: black !important; border-color: #ddd !important; }
        .stButton>button {
            width: 100%; height: 45px; border-radius: 8px; font-weight: 600;
            background: linear-gradient(90deg, #4ba3a8 0%, #2c7a7f 100%); color: white !important; border: none;
        }
        .dashboard-card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-top: 5px solid #4ba3a8; margin-bottom: 15px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE ENGINE (CACHED) ---
@st.cache_resource(ttl=3600)
def get_db_connection():
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        return mysql.connector.connect(
            host=creds["DB_HOST"], user=creds["DB_USER"], password=creds["DB_PASSWORD"],
            port=creds["DB_PORT"], database=creds["DB_NAME"], ssl_disabled=False
        )
    return None

def run_query(query, params=None, fetch=True):
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): st.cache_resource.clear(); conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        if fetch: return cursor.fetchall()
        else: conn.commit(); return True
    except Exception as e: return str(e)

# --- 4. UTILS ---
def get_ist_time(): return datetime.utcnow() + timedelta(hours=5, minutes=30)
def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return loc.address.split(",")[0] if loc else "Unknown"
    except: return "Loc Unavailable"

def mark_attendance(emp_id, punch_photo_bytes, lat, lon, addr):
    ist_now = get_ist_time(); work_date = ist_now.date(); time_in_obj = ist_now.time()
    cutoff = time(10, 30); status = "Half Day" if time_in_obj > cutoff else "Present"
    try:
        conn = get_db_connection(); c = conn.cursor()
        c.execute("SELECT * FROM attendance WHERE emp_id=%s AND date=%s", (emp_id, work_date))
        if c.fetchone(): st.error("⚠️ Attendance already marked.")
        else:
            c.execute("""INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", 
                      (emp_id, work_date, time_in_obj.strftime("%H:%M"), status, punch_photo_bytes, lat, lon, addr))
            conn.commit(); st.balloons(); st.success(f"✅ MARKED {status.upper()} @ {time_in_obj.strftime('%I:%M %p')}")
    except Exception as e: st.error(f"Error: {e}")

# --- MAIN APP ---
apply_styling()

col1, col2, col3 = st.columns([1,2,1])
with col2:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown(f"<h3 style='text-align:center;'>Daily Attendance</h3>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:grey;'>{get_ist_time().strftime('%d %b %Y | %I:%M %p')}</p>", unsafe_allow_html=True)
    
    loc = get_geolocation(); lat = loc['coords']['latitude'] if loc else None; lon = loc['coords']['longitude'] if loc else None
    if lat: st.success("📍 GPS Active")
    else: st.warning("Waiting for GPS...")

    rows = run_query("SELECT id, name, designation FROM employees")
    
    if isinstance(rows, list) and rows:
        df = pd.DataFrame(rows, columns=['id', 'name', 'desig'])
        emp_id = st.selectbox("Select Your Name", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
        
        p = df[df['id']==emp_id].iloc[0]
        st.markdown(f"<div class='dashboard-card' style='text-align:center;'><h2>{p['name']}</h2><p>{p['desig']}</p></div>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["📸 Punch In", "🔑 PIN Reset Request"])
        with tab1:
            photo = st.camera_input("Selfie")
            pin = st.text_input("Enter PIN", type="password", max_chars=4)
            if st.button("PUNCH IN"):
                if not lat or not photo: st.error("GPS & Photo Required!")
                else:
                    res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                    real_pin = res[0][0] if res and len(res) > 0 else "0000"
                    if pin == real_pin:
                        addr = get_address(lat, lon)
                        mark_attendance(emp_id, photo.getvalue(), str(lat), str(lon), addr)
                    else: st.error("Wrong PIN")
        with tab2:
            st.warning("PIN Reset requires Admin approval.")
            if st.button("Request Reset"): st.info("Request sent to Admin. Check the Payroll App for the OTP.")

    else: st.info("No Staff Found. Contact Admin.")

st.markdown("<div class='footer'>© National Air Condition | Technician App</div>", unsafe_allow_html=True)
