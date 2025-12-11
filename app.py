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
st.set_page_config(page_title="National Air Condition", layout="wide", page_icon=page_icon)

ADMIN_MOBILE = "9978815870"

# --- 2. DYNAMIC STYLING ENGINE ---
def apply_theme(theme_mode):
    if theme_mode == "Dark":
        # DARK MODE COLORS
        bg_color = "#0E1117"
        card_bg = "#262730"
        text_color = "#FAFAFA"
        input_bg = "#1E1E1E"
        sidebar_bg = "#161B21"
        border_color = "#444"
    else:
        # LIGHT MODE COLORS
        bg_color = "#f0f2f6"
        card_bg = "#ffffff"
        text_color = "#0e3b43"
        input_bg = "#ffffff"
        sidebar_bg = "#0e3b43"
        border_color = "#ddd"

    st.markdown(f"""
        <style>
        /* HIDE DEFAULTS */
        #MainMenu, footer, header, [data-testid="stToolbar"] {{visibility: hidden;}}
        .stDeployButton {{display:none;}}
        
        /* MAIN BACKGROUND */
        .stApp {{ background-color: {bg_color}; }}
        
        /* SIDEBAR */
        section[data-testid="stSidebar"] {{ background-color: {sidebar_bg}; }}
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {{
            color: white !important;
        }}
        
        /* TEXT COLORS */
        h1, h2, h3, p, div, span, label, li {{ color: {text_color} !important; font-family: 'Helvetica', sans-serif; }}
        
        /* INPUT FIELDS */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border: 1px solid {border_color};
            border-radius: 8px;
        }}
        
        /* DROPDOWNS */
        div[data-baseweb="select"] > div {{
            background-color: {input_bg} !important;
            color: {text_color} !important;
            border-color: {border_color} !important;
        }}
        div[data-baseweb="select"] span {{ color: {text_color} !important; }}
        
        /* BUTTONS (Gradient Teal - Always Bright) */
        .stButton>button {{
            width: 100%; height: 45px; border-radius: 8px; font-weight: 600;
            background: linear-gradient(90deg, #4ba3a8 0%, #2c7a7f 100%);
            color: white !important; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }}
        .stButton>button:hover {{ transform: translateY(-2px); }}
        
        /* CARDS */
        .dashboard-card {{
            background: {card_bg}; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-top: 5px solid #4ba3a8;
            margin-bottom: 15px;
        }}
        
        /* ATTENDANCE LIST ITEM */
        .att-item {{
            background: {card_bg}; padding: 15px; border-radius: 8px;
            border: 1px solid {border_color}; margin-bottom: 10px;
        }}
        
        /* FOOTER */
        .footer {{
            position: fixed; bottom: 0; left: 0; width: 100%;
            background: {card_bg}; text-align: center; padding: 10px;
            color: {text_color}; font-size: 12px; border-top: 1px solid {border_color};
        }}
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE ENGINE (CACHED) ---
@st.cache_resource
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
        if not conn or not conn.is_connected():
            st.cache_resource.clear(); conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        if fetch: return cursor.fetchall()
        else: conn.commit(); return True
    except Exception as e: return str(e)

# --- 4. UTILS ---
def get_ist_time(): return datetime.utcnow() + timedelta(hours=5, minutes=30)

def get_address_from_coords(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return location.address.split(",")[0] + ", " + location.address.split(",")[-4] if location else "Unknown"
    except: return "Loc Unavailable"

def send_sms(mobile, otp, reason):
    try:
        if "SMS_API_KEY" not in st.secrets: return False
        url = "https://www.fast2sms.com/dev/bulkV2"
        msg = f"National Air Condition.\nOTP for {reason}: {otp}"
        payload = {"route": "q", "message": msg, "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': st.secrets["SMS_API_KEY"], 'Content-Type': "application/x-www-form-urlencoded"}
        requests.request("POST", url, data=payload, headers=headers); return True
    except: return False

def init_app():
    run_query('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10), photo LONGBLOB)''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), punch_photo LONGBLOB, latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''', fetch=False)
    run_query("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')", fetch=False)

init_app()

# --- 5. UI LAYOUT & SIDEBAR ---
if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.title("MENU")

# Theme Switcher
theme = st.sidebar.select_slider("Theme Mode", options=["Light", "Dark"])
apply_theme(theme)

if 'nav' not in st.session_state: st.session_state.nav = 'Technician'
if st.sidebar.button("👨‍🔧 Technician Zone"): st.session_state.nav = 'Technician'
if st.sidebar.button("👮 Admin Panel"): st.session_state.nav = 'Admin'

# --- 6. TECHNICIAN ZONE ---
if st.session_state.nav == 'Technician':
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown(f"<h3 style='text-align:center;'>Daily Attendance</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center;'>{get_ist_time().strftime('%d %b %Y | %I:%M %p')}</p>", unsafe_allow_html=True)
        
        loc = get_geolocation(); lat = loc['coords']['latitude'] if loc else None; lon = loc['coords']['longitude'] if loc else None
        if lat: st.success("📍 GPS Active")
        else: st.warning("Waiting for GPS...")

        rows = run_query("SELECT id, name, designation FROM employees")
        if rows:
            df = pd.DataFrame(rows, columns=['id', 'name', 'desig'])
            emp_id = st.selectbox("Select Your Name", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
            
            p = df[df['id']==emp_id].iloc[0]
            st.markdown(f"<div class='dashboard-card' style='text-align:center;'><h2>{p['name']}</h2><p>{p['desig']}</p></div>", unsafe_allow_html=True)
            
            tab1, tab2 = st.tabs(["📸 Punch In", "🔑 Reset PIN"])
            with tab1:
                photo = st.camera_input("Selfie")
                pin = st.text_input("Enter PIN", type="password", max_chars=4)
                if st.button("PUNCH IN"):
                    if not lat or not photo: st.error("GPS & Photo Required!")
                    else:
                        real_pin = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")[0][0]
                        if pin == real_pin:
                            addr = get_address_from_coords(lat, lon); ist = get_ist_time()
                            status = "Half Day" if ist.time() > time(10,30) else "Present"
                            res = run_query("INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), status, photo.getvalue(), str(lat), str(lon), addr), fetch=False)
                            if res == True: st.balloons(); st.success("Marked!")
                            else: st.error("Already Marked!")
                        else: st.error("Wrong PIN")
            with tab2:
                if st.button("Get OTP"): otp = random.randint(1000, 9999); st.session_state.otp = otp; send_sms(ADMIN_MOBILE, otp, "PIN Reset"); st.info("Sent!")
                if 'otp' in st.session_state:
                    u_otp = st.text_input("OTP"); n_pin = st.text_input("New PIN", max_chars=4)
                    if st.button("Update"):
                        if u_otp == str(st.session_state.otp): run_query(f"UPDATE employees SET pin='{n_pin}' WHERE id={emp_id}", fetch=False); st.success("Updated!")
                        else: st.error("Invalid OTP")

# --- 7. ADMIN PANEL ---
elif st.session_state.nav == 'Admin':
    if 'auth' not in st.session_state: st.session_state.auth = False
    
    if not st.session_state.auth:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("<br><div class='dashboard-card'><h3 style='text-align:center'>Admin Login</h3></div>", unsafe_allow_html=True)
            pwd = st.text_input("Password", type="password")
            if st.button("Login"):
                if pwd == run_query("SELECT password FROM admin_config WHERE id=1")[0][0]: st.session_state.auth = True; st.rerun()
                else: st.error("Denied")
    else:
        st.title("Admin Dashboard")
        if st.sidebar.button("Logout"): st.session_state.auth = False; st.rerun()
        
        menu = st.tabs(["Live Status", "Payroll", "Staff Mgmt", "Settings"])
        
        with menu[0]:
            dt = get_ist_time().date()
            data = run_query(f"SELECT e.name, a.time_in, a.status, a.address, a.punch_photo FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
            st.metric("Present Today", len(data) if data else 0)
            if data:
                for row in data:
                    st.markdown(f"""
                    <div class='att-item'>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <div>
                                <h3 style='margin:0'>{row[0]}</h3>
                                <p style='margin:0'>🕒 {row[1]} | {row[2]}</p>
                                <small>📍 {row[3]}</small>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.image(row[4], width=100)
            else: st.info("No attendance yet.")

        with menu[1]:
            emp_data = run_query("SELECT id, name, salary FROM employees")
            if emp_data:
                df = pd.DataFrame(emp_data, columns=['id', 'name', 'salary'])
                s_emp = st.selectbox("Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                if st.button("Generate Slip"):
                    s_date = date(datetime.now().year, datetime.now().month-1, 5)
                    e_date = date(datetime.now().year, datetime.now().month, 5)
                    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={s_emp} AND date BETWEEN '{s_date}' AND '{e_date}'")
                    days = 0; report = []; att_dict = {str(r[0]): r[1] for r in att_data}
                    curr = s_date
                    while curr <= e_date:
                        stat = att_dict.get(str(curr), "Absent"); cred = 1.0 if stat == 'Present' else (0.5 if stat == 'Half Day' else 0.0)
                        if curr.strftime("%A") == 'Sunday': cred = 1.0
                        days += cred; report.append([curr, curr.strftime("%A"), stat, cred]); curr += timedelta(days=1)
                    sal = (df[df['id']==s_emp]['salary'].values[0] / 30) * days
                    st.success(f"Days: {days} | Salary: ₹{sal:,.0f}")
                    out = BytesIO(); pd.DataFrame(report, columns=['Date','Day','Status','Credit']).to_excel(out, index=False)
                    st.download_button("Download", out.getvalue(), "salary.xlsx")

        with menu[2]:
            c1, c2 = st.columns(2)
            with c1:
                with st.form("add"):
                    n = st.text_input("Name"); d = st.text_input("Role"); s = st.number_input("Salary"); p = st.text_input("PIN")
                    if st.form_submit_button("Add"): run_query("INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)", (n,d,s,p,b''), fetch=False); st.success("Added")
            with c2:
                del_id = st.selectbox("Delete", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0], key='del')
                if st.button("Delete"): run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False); run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False); st.rerun()

        with menu[3]:
            if st.button("Send OTP"): st.session_state.aotp = random.randint(1000,9999); send_sms(ADMIN_MOBILE, st.session_state.aotp, "Admin Reset")
            if 'aotp' in st.session_state:
                otp_in = st.text_input("OTP"); np = st.text_input("New Pass")
                if st.button("Save"):
                    if otp_in == str(st.session_state.aotp): run_query(f"UPDATE admin_config SET password='{np}' WHERE id=1", fetch=False); st.success("Done")

st.markdown("<div class='footer'>© National Air Condition | Developed by <b>Askan Shaikh</b></div>", unsafe_allow_html=True)
