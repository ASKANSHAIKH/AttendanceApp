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

# --- 1. CONFIGURATION & PAGE SETUP (MUST BE FIRST) ---
# This sets the Browser Tab Title and the Small Icon (Favicon)
if os.path.exists("logo.png"):
    st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="logo.png")
else:
    st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="❄️")

ADMIN_MOBILE = "9978815870" 

# --- 2. CSS STYLING (THE CLEAN LOOK) ---
def apply_styling():
    st.markdown("""
        <style>
        /* --- HIDE STREAMLIT UI ELEMENTS --- */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        [data-testid="stToolbar"] {visibility: hidden;} 
        .stDeployButton {display:none;}
        
        /* Main Background - Teal */
        .stApp { background-color: #4ba3a8; margin-top: -50px; }
        
        /* Text Colors */
        h1, h2, h3, h4, h5, h6, p, span, div, label, li { color: white !important; }
        
        /* Input Boxes */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTimeInput input, .stPasswordInput input {
            background-color: #ffffff !important; color: #000000 !important; border-radius: 5px; border: 1px solid #ddd;
        }
        div[data-baseweb="input"] { background-color: #ffffff !important; }
        div[data-baseweb="select"] > div { background-color: #ffffff !important; color: black !important; }
        
        /* Login Card */
        .login-card {
            background-color: white; padding: 30px; border-radius: 10px; text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin: auto; border-top: 5px solid #2c3e50;
        }
        .login-card h2, .login-card p { color: #2c3e50 !important; }
        
        /* Tech Card */
        .tech-card {
            background-color: white; padding: 20px; border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); text-align: center; border-top: 8px solid #2c3e50; margin-bottom: 20px;
        }
        .tech-card h3, .tech-card p { color: #2c3e50 !important; }
        
        /* Sidebar & Buttons */
        section[data-testid="stSidebar"] { background-color: #388e93; }
        .stButton>button {
            width: 100%; height: 3.5em; border-radius: 8px; font-weight: bold;
            background-color: white !important; color: #4ba3a8 !important; border: none;
        }
        .delete-btn > button { background-color: #e74c3c !important; color: white !important; }
        
        /* Footer */
        .footer {
            text-align: center; margin-top: 50px; padding: 20px; 
            color: white; border-top: 1px solid rgba(255,255,255,0.2); font-size: 14px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE CONNECTION ---
def get_connection():
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        return mysql.connector.connect(
            host=creds["DB_HOST"], user=creds["DB_USER"], password=creds["DB_PASSWORD"],
            port=creds["DB_PORT"], database=creds["DB_NAME"], ssl_disabled=False
        )
    else: st.error("⚠️ Secrets Missing!"); st.stop()

def init_db():
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10), photo LONGBLOB)''')
        c.execute('''CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), punch_photo LONGBLOB, latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''')
        c.execute('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''')
        c.execute("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')")
        conn.commit(); conn.close()
    except Exception as e: st.error(f"DB Init Error: {e}")

# --- 4. FUNCTIONS ---
def send_otp_sms(mobile, otp, reason):
    try:
        api_key = st.secrets["SMS_API_KEY"]
        url = "https://www.fast2sms.com/dev/bulkV2"
        message = f"National Air Condition Verification.\nYour OTP for {reason} is {otp}."
        payload = {"route": "q", "message": message, "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': api_key, 'Content-Type': "application/x-www-form-urlencoded"}
        response = requests.request("POST", url, data=payload, headers=headers)
        return response.status_code == 200
    except: return False

def get_admin_password():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT password FROM admin_config WHERE id=1"); pwd = c.fetchone()[0]; conn.close()
    return pwd

def update_admin_password(new_pass):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE admin_config SET password=%s WHERE id=1", (new_pass,)); conn.commit(); conn.close()

def update_employee_pin(emp_id, new_pin):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE employees SET pin=%s WHERE id=%s", (new_pin, emp_id)); conn.commit(); conn.close()

def get_address_from_coords(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        return location.address if location else "Unknown Location"
    except: return "Location not found"

def add_employee(name, designation, salary, pin):
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)", (name, designation, salary, pin, b''))
        conn.commit(); conn.close(); return True, "Success"
    except Exception as e: return False, str(e)

def delete_employee(emp_id):
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("DELETE FROM attendance WHERE emp_id=%s", (emp_id,))
        c.execute("DELETE FROM employees WHERE id=%s", (emp_id,)); conn.commit(); conn.close(); return True
    except: return False

def mark_attendance(emp_id, work_date, time_in_obj, punch_photo_bytes, lat, lon, addr):
    conn = get_connection(); c = conn.cursor()
    cutoff = time(10, 30); status = "Half Day" if time_in_obj > cutoff else "Present"
    try:
        c.execute("SELECT * FROM attendance WHERE emp_id=%s AND date=%s", (emp_id, work_date))
        if c.fetchone(): st.error("⚠️ Attendance already marked.")
        else:
            c.execute("""INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", (emp_id, work_date, time_in_obj.strftime("%H:%M"), status, punch_photo_bytes, lat, lon, addr))
            conn.commit(); st.balloons(); st.success(f"✅ MARKED {status.upper()} @ {addr}")
    except Exception as e: st.error(f"Error: {e}")
    finally: conn.close()

def calculate_salary_logic(emp_id, pay_month, pay_year, base_salary):
    start = date(pay_year, pay_month-1, 5) if pay_month > 1 else date(pay_year-1, 12, 5); end = date(pay_year, pay_month, 4)
    conn = get_connection(); df = pd.read_sql(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{start}' AND '{end}'", conn); conn.close()
    df['date'] = df['date'].astype(str); att_map = dict(zip(df['date'], df['status']))
    pay_days = 0.0; report = []; curr = start
    while curr <= end:
        d_str = curr.strftime("%Y-%m-%d"); status = att_map.get(d_str, "Absent"); pay = 0.0; note = ""
        if curr.strftime("%A") == 'Sunday':
            prev = (curr - timedelta(days=1)).strftime("%Y-%m-%d"); next_d = (curr + timedelta(days=1)).strftime("%Y-%m-%d")
            if att_map.get(prev,"Absent")=="Absent" and att_map.get(next_d,"Absent")=="Absent": pay=0.0; note="Sandwich Cut"
            else: pay=1.0; note="Paid Wknd"
        else:
            if status == "Present": pay=1.0
            elif status == "Half Day": pay=0.5; note="Late"
            else: pay=0.0; note="Absent"
        pay_days += pay; report.append([d_str, curr.strftime("%A"), status, pay, note]); curr += timedelta(days=1)
    return pay_days * (base_salary/30), pay_days, report

# --- UI LOGIC ---
apply_styling()
if "connections" in st.secrets: init_db()

if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.markdown("## Navigation")
role = st.sidebar.radio("Go To", ["Technician / Staff", "Admin / Manager"])

# ---------------- TECHNICIAN ----------------
if role == "Technician / Staff":
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<h2 style='text-align:center;'>Daily Check-In</h2>", unsafe_allow_html=True)
        
        loc = get_geolocation(); lat = loc['coords']['latitude'] if loc else None; lon = loc['coords']['longitude'] if loc else None
        if lat: st.success("📍 Location Active")
        else: st.warning("⏳ Waiting for GPS...")

        try:
            conn = get_connection(); c = conn.cursor(); c.execute("SELECT id, name, designation FROM employees"); rows = c.fetchall(); conn.close()
            if rows:
                df = pd.DataFrame(rows, columns=['id', 'name', 'desig'])
                emp_id = st.selectbox("Select Name", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                st.markdown(f"<div class='tech-card'><h3>{df[df['id']==emp_id]['name'].values[0]}</h3><p>{df[df['id']==emp_id]['desig'].values[0]}</p></div>", unsafe_allow_html=True)
                
                tab_punch, tab_reset = st.tabs(["📸 Punch In", "🔑 Forgot PIN?"])
                
                with tab_punch:
                    photo = st.camera_input("Selfie")
                    st.write("### 🔒 Security Check")
                    pin = st.text_input("Enter PIN", type="password", max_chars=4, key="tech_pin")
                    if st.button("PUNCH IN"):
                        # Get PIN safely
                        conn = get_connection(); c = conn.cursor(); c.execute("SELECT pin FROM employees WHERE id=%s", (emp_id,)); real_pin = c.fetchone()[0]; conn.close()
                        
                        if pin == real_pin and photo and lat:
                            addr = get_address_from_coords(lat, lon)
                            mark_attendance(emp_id, date.today(), datetime.now().time(), photo.getvalue(), str(lat), str(lon), addr)
                        elif pin != real_pin: st.error("❌ Wrong PIN")
                        elif not photo: st.error("📷 Photo Required")
                        elif not lat: st.error("📍 Location Required")

                with tab_reset:
                    st.info(f"OTP sent to Admin: {ADMIN_MOBILE}")
                    if st.button("Request PIN Reset OTP"):
                        otp = random.randint(1000, 9999)
                        st.session_state.reset_otp = otp
                        st.session_state.reset_emp_id = emp_id
                        if send_otp_sms(ADMIN_MOBILE, otp, "PIN Reset"): st.success("✅ OTP Sent!")
                        else: st.error("❌ SMS Failed")
                    
                    if 'reset_otp' in st.session_state:
                        entered_otp = st.text_input("Enter OTP from Admin", max_chars=4)
                        new_pin_set = st.text_input("New PIN", max_chars=4, type="password")
                        if st.button("Set New PIN"):
                            if str(entered_otp) == str(st.session_state.reset_otp):
                                update_employee_pin(st.session_state.reset_emp_id, new_pin_set)
                                st.success("PIN Updated!")
                                del st.session_state.reset_otp
                            else: st.error("Invalid OTP")
            else: st.info("No Staff Found")
        except Exception as e: st.error(f"DB Error: {e}")

# ---------------- ADMIN ----------------
elif role == "Admin / Manager":
    if 'admin_auth' not in st.session_state: st.session_state.admin_auth = False
    
    if not st.session_state.admin_auth:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("<br><div class='login-card'><h2>Admin Login</h2></div>", unsafe_allow_html=True)
            l_tab1, l_tab2 = st.tabs(["Login", "Forgot Password?"])
            with l_tab1:
                pwd = st.text_input("Password", type="password")
                if st.button("Login"):
                    if pwd == get_admin_password(): st.session_state.admin_auth = True; st.rerun()
                    else: st.error("❌ Wrong Password")
            with l_tab2:
                if st.button("Send Reset OTP"):
                    otp = random.randint(1000, 9999); st.session_state.admin_otp = otp
                    if send_otp_sms(ADMIN_MOBILE, otp, "Admin Password Reset"): st.success(f"✅ OTP Sent to {ADMIN_MOBILE}")
                    else: st.error("❌ SMS Failed")
                if 'admin_otp' in st.session_state:
                    a_otp = st.text_input("Enter OTP"); new_a_pass = st.text_input("New Admin Password", type="password")
                    if st.button("Update Password"):
                        if str(a_otp) == str(st.session_state.admin_otp):
                            update_admin_password(new_a_pass); st.success("Password Updated!"); del st.session_state.admin_otp
                        else: st.error("Invalid OTP")
    else:
        st.title("Admin Dashboard"); 
        if st.button("Logout"): st.session_state.admin_auth = False; st.rerun()
        
        t1, t2, t3, t4 = st.tabs(["📊 Live Status", "💰 Payroll", "➕ Add", "❌ Delete"])
        with t1:
            try:
                conn = get_connection()
                df = pd.read_sql(f"SELECT e.name, a.time_in, a.status, a.address, a.latitude, a.longitude, a.punch_photo FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{date.today()}'", conn); conn.close()
                if not df.empty:
                    for i, r in df.iterrows():
                        with st.container():
                            c1, c2 = st.columns([3, 1])
                            with c1:
                                st.markdown(f"### {r['name']}")
                                st.markdown(f"**🕒 Time:** {r['time_in']}")
                                st.markdown(f"**📍 Location:** [{r['address']}](https://www.google.com/maps/search/?api=1&query={r['latitude']},{r['longitude']})")
                                if r['status'] == "Half Day": st.warning("⚠️ LATE ENTRY (Half Day)")
                                else: st.success("✅ PRESENT")
                            with c2:
                                if r['punch_photo']: st.image(r['punch_photo'], width=120, caption="Live Selfie")
                            st.markdown("---")
                else: st.info("No Data Today")
            except Exception as e: st.error(f"Error: {e}")
            
        with t2:
            try:
                conn = get_connection(); c = conn.cursor(); c.execute("SELECT id, name, salary FROM employees"); rows = c.fetchall(); conn.close()
                if rows:
                    df = pd.DataFrame(rows, columns=['id', 'name', 'salary'])
                    s = st.selectbox("Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                    if st.button("Calculate"):
                        sal, days, rep = calculate_salary_logic(s, datetime.now().month, datetime.now().year, df[df['id']==s]['salary'].values[0])
                        st.success(f"Pay: ₹{sal:,.0f}"); 
            except: pass
        with t3:
            with st.form("add"):
                n = st.text_input("Name"); d = st.text_input("Designation"); s = st.number_input("Salary", value=20000); p = st.text_input("PIN", max_chars=4)
                if st.form_submit_button("Save"): add_employee(n, d, s, p); st.success("Added!")
        with t4:
            try:
                conn = get_connection(); c = conn.cursor(); c.execute("SELECT id, name FROM employees"); rows = c.fetchall(); conn.close()
                if rows:
                    df = pd.DataFrame(rows, columns=['id', 'name'])
                    d_id = st.selectbox("Delete", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                    if st.button("PERMANENTLY DELETE"): delete_employee(d_id); st.success("Deleted"); st.rerun()
            except: pass

st.markdown("<div class='footer'>© National Air Condition<br>Website created by <b>Askan Shaikh</b></div>", unsafe_allow_html=True)
