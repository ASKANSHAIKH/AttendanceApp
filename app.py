import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
from io import BytesIO
import os
import random
import requests
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
page_icon = "logo.png" if os.path.exists("logo.png") else "❄️"
st.set_page_config(page_title="National Air Condition", layout="wide", page_icon=page_icon)

ADMIN_MOBILE = "9978815870"

# --- 2. STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        #MainMenu, footer, header, [data-testid="stToolbar"] {visibility: hidden;}
        .stDeployButton {display:none;}
        .stApp { background-color: #f0f2f6; margin-top: -50px; }
        
        section[data-testid="stSidebar"] { background-color: #0e3b43; }
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label { color: white !important; }
        h1, h2, h3, p, div, span, label, li { color: #0e3b43 !important; font-family: 'Helvetica', sans-serif; }
        
        .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input {
            background-color: white !important; color: black !important; border: 1px solid #ddd; border-radius: 8px;
        }
        
        div[data-baseweb="select"] > div { background-color: white !important; color: black !important; border-color: #ddd !important; }
        div[data-baseweb="select"] span { color: black !important; }
        
        .stButton>button {
            width: 100%; height: 45px; border-radius: 8px; font-weight: 600;
            background: linear-gradient(90deg, #4ba3a8 0%, #2c7a7f 100%);
            color: white !important; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }
        
        .dashboard-card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-top: 5px solid #4ba3a8; margin-bottom: 15px;
        }
        .att-item {
            background: white; padding: 15px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 10px;
        }
        .footer {
            position: fixed; bottom: 0; left: 0; width: 100%;
            background: white; text-align: center; padding: 10px;
            color: #666; font-size: 12px; border-top: 1px solid #ddd;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE (Auto-Healing) ---
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
        if not conn or not conn.is_connected(): st.cache_resource.clear(); conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        if fetch: return cursor.fetchall()
        else: conn.commit(); return True
    except Exception as e: return str(e)

# --- 4. INITIALIZATION (Fixes "Table doesn't exist" Error) ---
def init_app():
    run_query('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10), photo LONGBLOB)''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), punch_photo LONGBLOB, latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''', fetch=False)
    run_query("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')", fetch=False)

# --- 5. UTILS ---
def get_ist_time(): return datetime.utcnow() + timedelta(hours=5, minutes=30)

def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return loc.address.split(",")[0] if loc else "Unknown"
    except: return "Loc Unavailable"

def send_sms(mobile, otp, reason):
    try:
        if "SMS_API_KEY" not in st.secrets: return False
        url = "https://www.fast2sms.com/dev/bulkV2"
        payload = {"route": "q", "message": f"National Air Condition OTP for {reason}: {otp}", "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': st.secrets["SMS_API_KEY"], 'Content-Type': "application/x-www-form-urlencoded"}
        requests.request("POST", url, data=payload, headers=headers); return True
    except: return False

def calculate_salary_logic(emp_id, pay_month, pay_year, base_salary):
    # FIXED LOGIC: 5th to 5th
    if pay_month == 1:
        s_date = date(pay_year - 1, 12, 5)
        e_date = date(pay_year, pay_month, 5)
    else:
        s_date = date(pay_year, pay_month - 1, 5)
        e_date = date(pay_year, pay_month, 5)
        
    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    
    # --- FIX FOR GHOST SALARY ---
    # If no attendance records exist at all, return 0 immediately
    if not att_data or len(att_data) == 0:
        return 0.0, 0.0, []
        
    days = 0; report = []; att_dict = {str(r[0]): r[1] for r in att_data}
    curr = s_date
    while curr <= e_date:
        stat = att_dict.get(str(curr), "Absent")
        cred = 1.0 if stat == 'Present' else (0.5 if stat == 'Half Day' else 0.0)
        
        # Only pay for Sunday if there is at least some attendance data in the month
        if curr.strftime("%A") == 'Sunday': cred = 1.0
        
        days += cred
        report.append([curr, curr.strftime("%A"), stat, cred])
        curr += timedelta(days=1)
        
    salary = (base_salary / 30) * days
    return salary, days, report

# --- MAIN APP ---
init_app()
apply_styling()

if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.title("MENU")

if 'nav' not in st.session_state: st.session_state.nav = 'Technician'
if st.sidebar.button("👨‍🔧 Technician Zone"): st.session_state.nav = 'Technician'
if st.sidebar.button("👮 Admin Panel"): st.session_state.nav = 'Admin'

# --- TECHNICIAN SCREEN ---
if st.session_state.nav == 'Technician':
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown(f"<h3 style='text-align:center;'>Daily Attendance</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; color:grey;'>{get_ist_time().strftime('%d %b %Y | %I:%M %p')}</p>", unsafe_allow_html=True)
        
        loc = get_geolocation()
        lat = loc['coords']['latitude'] if loc else None
        lon = loc['coords']['longitude'] if loc else None
        
        if lat: st.success("📍 GPS Active")
        else: st.warning("Waiting for GPS...")

        rows = run_query("SELECT id, name, designation FROM employees")
        if isinstance(rows, list) and rows:
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
                        res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                        real_pin = res[0][0] if res else "0000"
                        if pin == real_pin:
                            addr = get_address(lat, lon); ist = get_ist_time()
                            status = "Half Day" if ist.time() > time(10,30) else "Present"
                            res = run_query("INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), status, photo.getvalue(), str(lat), str(lon), addr), fetch=False)
                            if res == True: st.balloons(); st.success("Marked!")
                            else: st.error("Already Marked!")
                        else: st.error("Wrong PIN")
            with tab2:
                if st.button("Get OTP"): 
                    otp = random.randint(1000, 9999); st.session_state.otp = otp; send_sms(ADMIN_MOBILE, otp, "PIN Reset")
                    st.success(f"OTP Sent! (Backup: {otp})")
                if 'otp' in st.session_state:
                    u_otp = st.text_input("Enter OTP"); n_pin = st.text_input("New PIN", max_chars=4)
                    if st.button("Update"):
                        if u_otp == str(st.session_state.otp): run_query(f"UPDATE employees SET pin='{n_pin}' WHERE id={emp_id}", fetch=False); st.success("Updated!"); del st.session_state.otp
                        else: st.error("Invalid OTP")
            
            st.markdown("<br><br>", unsafe_allow_html=True)
            if st.button("👮 Admin Login"): st.session_state.nav = 'Admin'; st.rerun()
        else: st.info("No Staff Found. Please Login as Admin to add staff.")

# --- ADMIN SCREEN ---
elif st.session_state.nav == 'Admin':
    if 'auth' not in st.session_state: st.session_state.auth = False
    
    if not st.session_state.auth:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("<br><div class='dashboard-card'><h3 style='text-align:center'>Admin Login</h3></div>", unsafe_allow_html=True)
            pwd = st.text_input("Password", type="password")
            if st.button("Login"):
                res = run_query("SELECT password FROM admin_config WHERE id=1")
                real_pass = res[0][0] if res else "admin"
                if pwd == real_pass: st.session_state.auth = True; st.rerun()
                else: st.error("Denied")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("⬅️ Back"): st.session_state.nav = 'Technician'; st.rerun()
    else:
        st.title("Admin Dashboard")
        if st.sidebar.button("Logout"): st.session_state.auth = False; st.rerun()
        
        menu = st.tabs(["Live Status", "Payroll", "Staff Mgmt"])
        
        with menu[0]:
            dt = get_ist_time().date()
            data = run_query(f"SELECT e.name, a.time_in, a.status, a.address, a.punch_photo FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
            st.metric("Present Today", len(data) if isinstance(data, list) else 0)
            if isinstance(data, list) and data:
                for row in data:
                    st.markdown(f"<div class='att-item'><h3>{row[0]}</h3><p>🕒 {row[1]} | {row[2]}</p><small>📍 {row[3]}</small></div>", unsafe_allow_html=True)
                    st.image(row[4], width=100)
            else: st.info("No attendance yet.")

        with menu[1]:
            emp_data = run_query("SELECT id, name, salary FROM employees")
            if isinstance(emp_data, list) and emp_data:
                df = pd.DataFrame(emp_data, columns=['id', 'name', 'salary'])
                s_emp = st.selectbox("Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                if st.button("Generate Slip"):
                    curr_month = datetime.now().month
                    curr_year = datetime.now().year
                    sal, days, report = calculate_salary_logic(s_emp, curr_month, curr_year, df[df['id']==s_emp]['salary'].values[0])
                    
                    st.success(f"Days: {days} | Salary: ₹{sal:,.0f}")
                    if report:
                        out = BytesIO(); pd.DataFrame(report, columns=['Date','Day','Status','Credit']).to_excel(out, index=False)
                        st.download_button("Download Excel", out.getvalue(), "salary.xlsx")
                    else:
                        st.warning("No data found for this period.")

        with menu[2]:
            c1, c2 = st.columns(2)
            with c1:
                with st.form("add"):
                    n = st.text_input("Name"); d = st.text_input("Role"); s = st.number_input("Salary"); p = st.text_input("PIN")
                    if st.form_submit_button("Add"): run_query("INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)", (n,d,s,p,b''), fetch=False); st.success("Added")
            with c2:
                del_id = st.selectbox("Delete", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0], key='del')
                if st.button("Delete"): run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False); run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False); st.rerun()

st.markdown("<div class='footer'>© National Air Condition | Developed by <b>Askan Shaikh</b></div>", unsafe_allow_html=True)
