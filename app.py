import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date, timezone
import pymysql
import ssl
from io import BytesIO
import os
import random
import requests
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="National Air Condition Portal", layout="wide")

ADMIN_MOBILE = "9978815870"

# --- 2. STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        #MainMenu, footer, header, [data-testid="stToolbar"] {visibility: hidden;}
        .stDeployButton {display:none;}
        .stApp { background-color: #ffffff !important; margin-top: -50px; }
        p, h1, h2, h3, h4, h5, h6, span, div, label, li, a { color: #000000 !important; }
        .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input {
            background-color: #f0f2f6 !important; color: #000000 !important; border: 1px solid #999; font-weight: bold;
        }
        .stButton>button {
            width: 100%; height: 50px; border-radius: 8px; font-weight: bold;
            background: linear-gradient(90deg, #0e3b43 0%, #1b6ca8 100%);
            color: white !important; border: none;
        }
        .dashboard-card {
            background: #f8f9fa !important; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.15); border: 1px solid #ddd; margin-bottom: 15px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE ENGINE (DIRECT) ---
def get_db_connection():
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            # Autocommit=True ensures data is saved INSTANTLY
            return pymysql.connect(
                host=creds["DB_HOST"],
                user=creds["DB_USER"],
                password=creds["DB_PASSWORD"],
                port=creds["DB_PORT"],
                database=creds["DB_NAME"],
                ssl=ssl_ctx,
                autocommit=True
            )
        except Exception as e:
            st.error(f"❌ DB Connection Error: {e}")
            return None
    st.error("❌ Secrets not found!")
    return None

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch:
                return cursor.fetchall()
            else:
                return True
    except Exception as e:
        st.error(f"❌ Query Error: {e}")
        return None
    finally:
        if conn: conn.close()

# --- 4. UTILS ---
def get_ist_time():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)

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
        payload = {"route": "q", "message": f"OTP: {otp}", "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': st.secrets["SMS_API_KEY"], 'Content-Type': "application/x-www-form-urlencoded"}
        requests.request("POST", url, data=payload, headers=headers); return True
    except: return False

def calculate_salary_logic(emp_id, pay_month, pay_year, base_salary):
    if pay_month == 1: s_date, e_date = date(pay_year - 1, 12, 5), date(pay_year, pay_month, 5)
    else: s_date, e_date = date(pay_year, pay_month - 1, 5), date(pay_year, pay_month, 5)
        
    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    if not att_data: return 0.0, 0.0, []
        
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

# Sidebar
def sidebar_nav():
    if st.session_state.auth:
        st.sidebar.markdown("---")
        st.sidebar.header("Admin Menu")
        if st.sidebar.button("Live Status", key='l'): st.session_state.nav = 'Admin - Live'
        if st.sidebar.button("Payroll", key='p'): st.session_state.nav = 'Admin - Payroll'
        if st.sidebar.button("Staff Mgmt", key='s'): st.session_state.nav = 'Admin - Staff'
        if st.sidebar.button("Logout", key='o'): st.session_state.auth = False; st.session_state.nav = 'Role Select'; st.rerun()
    elif st.session_state.nav != 'Role Select':
        if st.sidebar.button("⬅️ Back", key='b'): st.session_state.nav = 'Role Select'; st.rerun()
sidebar_nav()

# --- 1. ROLE SELECT ---
if st.session_state.nav == 'Role Select':
    st.title("National Air Condition Portal")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='dashboard-card'><h3>Technician</h3></div>", unsafe_allow_html=True)
        if st.button("TECHNICIAN ENTER"): st.session_state.nav = 'Technician - Punch'; st.rerun()
    with c2:
        st.markdown("<div class='dashboard-card'><h3>Admin</h3></div>", unsafe_allow_html=True)
        if st.button("ADMIN LOGIN"): st.session_state.nav = 'Admin - Login'; st.rerun()

# --- 2. TECHNICIAN ---
elif st.session_state.nav == 'Technician - Punch':
    streamlit_js_eval(js_expressions='setTimeout(() => window.location.reload(), 300000)', key='keep_alive')
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown(f"<h3 style='text-align:center;'>Attendance</h3>", unsafe_allow_html=True)
        loc = get_geolocation()
        if loc and 'coords' in loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            st.success("✅ GPS Connected")
            
            rows = run_query("SELECT id, name FROM employees")
            if isinstance(rows, list) and rows:
                df = pd.DataFrame(rows, columns=['id', 'name'])
                emp_id = st.selectbox("Select Name", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                pin = st.text_input("Enter PIN", type="password", max_chars=4)
                if st.button("PUNCH IN"):
                    res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                    if res and pin == res[0][0]:
                        ist = get_ist_time(); addr = get_address(lat, lon)
                        check = run_query("INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), "Present", str(lat), str(lon), addr), fetch=False)
                        if check == True: st.balloons(); st.success("Marked Present!")
                        else: st.error("Already Marked Today!")
                    else: st.error("Wrong PIN")
            else: st.warning("Staff list is empty. Ask Admin to Add Staff.")
        else: st.warning("Waiting for GPS...")

# --- 3. ADMIN ---
elif st.session_state.nav == 'Admin - Login':
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            res = run_query("SELECT password FROM admin_config WHERE id=1")
            # Auto-create admin if missing
            if not res: 
                run_query("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')", fetch=False)
                res = [('admin',)]
            
            if res and pwd == res[0][0]: st.session_state.auth = True; st.session_state.nav = 'Admin - Live'; st.rerun()
            else: st.error("Wrong Password")

elif st.session_state.auth:
    if st.session_state.nav == 'Admin - Live':
        st.title("Live Status")
        dt = get_ist_time().date()
        data = run_query(f"SELECT e.name, a.time_in, a.address FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
        if isinstance(data, list) and data:
            st.metric("Present Today", len(data))
            for row in data: st.markdown(f"<div class='att-item'><h3>{row[0]}</h3><p>🕒 {row[1]}</p><small>📍 {row[2]}</small></div>", unsafe_allow_html=True)
        else: st.info("No attendance today.")

    elif st.session_state.nav == 'Admin - Staff':
        st.title("Staff Management")
        
        # --- TEST BUTTON ---
        if st.button("⚠️ Test Database Connection"):
            test = run_query("SELECT 1")
            if test: st.success("✅ Database is Connected!")
            else: st.error("❌ Database Connection Failed.")
            
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Staff")
            # REMOVED st.form for direct feedback
            n = st.text_input("Name")
            d = st.text_input("Role")
            s = st.number_input("Salary", step=500.0)
            p = st.text_input("PIN")
            
            if st.button("Save New Staff"):
                if n and p:
                    # Auto-create table if missing
                    run_query('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10))''', fetch=False)
                    
                    res = run_query("INSERT INTO employees (name, designation, salary, pin) VALUES (%s, %s, %s, %s)", (n,d,s,p), fetch=False)
                    if res == True: 
                        st.success(f"✅ Saved {n}!")
                        st.rerun() # Refresh to update list
                    else: st.error("Failed to save.")
                else:
                    st.warning("Name and PIN are required.")
                    
        with c2:
            st.subheader("Remove Staff")
            rows = run_query("SELECT id, name FROM employees")
            if isinstance(rows, list) and rows:
                del_id = st.selectbox("Select to Delete", [r[0] for r in rows], format_func=lambda x: [r[1] for r in rows if r[0]==x][0])
                if st.button("DELETE PERMANENTLY"): 
                    run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False)
                    run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False)
                    st.success("Deleted!")
                    st.rerun()

    elif st.session_state.nav == 'Admin - Payroll':
        st.title("Payroll")
        emp_data = run_query("SELECT id, name, salary FROM employees")
        if isinstance(emp_data, list) and emp_data:
            df = pd.DataFrame(emp_data, columns=['id', 'name', 'salary'])
            s_emp = st.selectbox("Select Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
            if st.button("Calculate"):
                sal, days, report = calculate_salary_logic(s_emp, datetime.now().month-1, datetime.now().year, df[df['id']==s_emp]['salary'].values[0])
                st.success(f"Days: {days} | Pay: ₹{sal:,.0f}")
