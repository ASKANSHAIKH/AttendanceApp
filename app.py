import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date, timezone
import pymysql
import ssl
import os
import random
import requests
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="National Air Condition Portal", layout="wide", page_icon="❄️")

ADMIN_MOBILE = "9978815870"

# --- 2. STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        .stApp { background-color: #ffffff; }
        h1, h2, h3, p, div, span, label { color: black !important; }
        .stButton>button {
            width: 100%; border-radius: 5px; height: 45px; font-weight: bold;
            background-color: #0e3b43; color: white;
        }
        .success-box { padding: 10px; background-color: #d4edda; color: #155724; border-radius: 5px; margin-bottom: 10px; }
        .error-box { padding: 10px; background-color: #f8d7da; color: #721c24; border-radius: 5px; margin-bottom: 10px; }
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE ENGINE ---
def get_db_connection():
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            return pymysql.connect(
                host=creds["DB_HOST"], user=creds["DB_USER"], password=creds["DB_PASSWORD"],
                port=creds["DB_PORT"], database=creds["DB_NAME"], ssl=ssl_ctx, autocommit=True
            )
        except Exception as e: return None
    return None

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch: return cursor.fetchall()
            return True
    except Exception as e: return str(e)
    finally: conn.close()

# --- 4. CORE LOGIC ---
def get_ist_time(): return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)

def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return loc.address.split(",")[0] if loc else "Loc Unavailable"
    except: return "Loc Unavailable"

def send_sms(mobile, otp, reason):
    try:
        if "SMS_API_KEY" not in st.secrets: return False
        url = "https://www.fast2sms.com/dev/bulkV2"
        payload = {"route": "q", "message": f"OTP: {otp}", "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': st.secrets["SMS_API_KEY"], 'Content-Type': "application/x-www-form-urlencoded"}
        requests.request("POST", url, data=payload, headers=headers); return True
    except: return False

def calculate_salary_logic(emp_id, pay_month, pay_year, base_salary):
    if pay_month == 1: s_date, e_date = date(pay_year - 1, 12, 5), date(pay_year, pay_month, 5)
    else: s_date, e_date = date(pay_year, pay_month - 1, 5), date(pay_year, pay_month, 5)
    
    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    if not att_data or isinstance(att_data, str): return 0.0, 0.0, []

    days = 0; report = []; att_dict = {str(r[0]): r[1] for r in att_data}; has_worked = len(att_data) > 0
    curr = s_date
    while curr <= e_date:
        stat = att_dict.get(str(curr), "Absent")
        cred = 1.0 if stat == 'Present' else (0.5 if stat == 'Half Day' else 0.0)
        if curr.strftime("%A") == 'Sunday': cred = 1.0 if has_worked else 0.0
        days += cred; report.append([curr, curr.strftime("%A"), stat, cred]); curr += timedelta(days=1)
    
    return (base_salary / 30) * days, days, report

# --- MAIN APP ---
apply_styling()

if 'nav' not in st.session_state: st.session_state.nav = 'Role Select'
if 'auth' not in st.session_state: st.session_state.auth = False

# RESTORE LOGO
if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
else: st.sidebar.header("❄️ National Air")

# SIDEBAR NAV
def sidebar_nav():
    if st.session_state.auth:
        st.sidebar.markdown("---")
        if st.sidebar.button("Live Status"): st.session_state.nav = 'Admin - Live'
        if st.sidebar.button("Staff Mgmt"): st.session_state.nav = 'Admin - Staff'
        if st.sidebar.button("Payroll"): st.session_state.nav = 'Admin - Payroll'
        st.sidebar.markdown("---")
        if st.sidebar.button("Logout"): st.session_state.auth = False; st.session_state.nav = 'Role Select'; st.rerun()
    elif st.session_state.nav != 'Role Select':
        if st.sidebar.button("⬅️ Back"): st.session_state.nav = 'Role Select'; st.rerun()
sidebar_nav()

# --- 1. ROLE SELECT ---
if st.session_state.nav == 'Role Select':
    st.title("National Air Condition Portal")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("TECHNICIAN PUNCH-IN"): st.session_state.nav = 'Technician - Punch'; st.rerun()
    with c2:
        if st.button("ADMIN LOGIN"): st.session_state.nav = 'Admin - Login'; st.rerun()

# --- 2. TECHNICIAN ---
elif st.session_state.nav == 'Technician - Punch':
    streamlit_js_eval(js_expressions='setTimeout(() => window.location.reload(), 300000)', key='keep_alive')
    st.header("Technician Attendance")
    
    # SYSTEM CHECK
    rows = run_query("SELECT id, name FROM employees")
    if isinstance(rows, str): st.error(f"System Error: {rows}")
    elif not rows: st.warning("Staff list is empty. Please contact Admin.")
    
    # DROPDOWN (Even if empty)
    options = rows if isinstance(rows, list) else []
    
    if options:
        emp_id = st.selectbox("Select Name", [r[0] for r in options], format_func=lambda x: [r[1] for r in options if r[0]==x][0])
        pin = st.text_input("Enter PIN", type="password")
        
        loc = get_geolocation()
        if loc and 'coords' in loc:
            st.success("GPS Ready")
            if st.button("PUNCH IN"):
                res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                if res and pin == res[0][0]:
                    ist = get_ist_time(); lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                    run_query("INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), "Present", str(lat), str(lon), get_address(lat, lon)), fetch=False)
                    st.balloons(); st.success("Marked!")
                else: st.error("Wrong PIN")
        else: st.warning("Waiting for GPS...")
    else:
        st.info("No staff found in database.")

# --- 3. ADMIN LOGIN ---
elif st.session_state.nav == 'Admin - Login':
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Login"):
        # Auto-create admin table if missing
        run_query('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''', fetch=False)
        run_query("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')", fetch=False)
        
        res = run_query("SELECT password FROM admin_config WHERE id=1")
        if res and pwd == res[0][0]: st.session_state.auth = True; st.session_state.nav = 'Admin - Live'; st.rerun()
        else: st.error("Wrong Password")

# --- 4. ADMIN PANEL ---
elif st.session_state.auth:
    if st.session_state.nav == 'Admin - Live':
        st.header("Live Status")
        dt = get_ist_time().date()
        data = run_query(f"SELECT e.name, a.time_in, a.address FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
        if data and isinstance(data, list):
            st.dataframe(pd.DataFrame(data, columns=['Name', 'Time', 'Location']), use_container_width=True)
        else: st.info("No attendance today.")

    elif st.session_state.nav == 'Admin - Staff':
        st.header("Staff Management")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Staff")
            n = st.text_input("Name"); d = st.text_input("Role"); s = st.number_input("Salary", value=0); p = st.text_input("PIN")
            if st.button("Save Staff"):
                # Table check
                run_query('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10))''', fetch=False)
                res = run_query("INSERT INTO employees (name, designation, salary, pin) VALUES (%s, %s, %s, %s)", (n,d,s,p), fetch=False)
                if res == True: st.success("Saved!"); st.rerun()
                else: st.error(f"Error: {res}")
        
        with c2:
            st.subheader("Remove Staff")
            rows = run_query("SELECT id, name FROM employees")
            if rows and isinstance(rows, list):
                del_id = st.selectbox("Select Staff", [r[0] for r in rows], format_func=lambda x: [r[1] for r in rows if r[0]==x][0])
                if st.button("Delete Selected"):
                    run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False)
                    run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False)
                    st.warning("Deleted"); st.rerun()
            else: st.info("List is empty")
            
        st.markdown("---")
        st.subheader("⚠️ DANGER ZONE")
        if st.button("🔴 FACTORY RESET DATABASE"):
            run_query("DROP TABLE IF EXISTS employees", fetch=False)
            run_query("DROP TABLE IF EXISTS attendance", fetch=False)
            run_query('''CREATE TABLE employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10))''', fetch=False)
            run_query('''CREATE TABLE attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''', fetch=False)
            st.success("Database has been reset. You can now Add Staff.")

    elif st.session_state.nav == 'Admin - Payroll':
        st.header("Payroll")
        rows = run_query("SELECT id, name, salary FROM employees")
        if rows and isinstance(rows, list):
            df = pd.DataFrame(rows, columns=['id', 'name', 'salary'])
            s_emp = st.selectbox("Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
            if st.button("Calculate"):
                sal, days, rep = calculate_salary_logic(s_emp, datetime.now().month-1, datetime.now().year, df[df['id']==s_emp]['salary'].values[0])
                st.success(f"Pay: ₹{sal:,.0f} ({days} days)")
