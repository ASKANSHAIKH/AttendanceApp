import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
from io import BytesIO
import os
import random
import requests
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
page_icon = "logo.png" if os.path.exists("logo.png") else "❄️"
st.set_page_config(page_title="National Air Condition Portal", layout="wide", page_icon=page_icon)

ADMIN_MOBILE = "9978815870"

# --- 2. PROFESSIONAL STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        /* HIDE UNNECESSARY STREAMLIT UI */
        #MainMenu, footer, header, [data-testid="stToolbar"] {visibility: hidden;}
        .stDeployButton {display:none;}
        
        .stApp { background-color: #f0f2f6; margin-top: -50px; }
        
        section[data-testid="stSidebar"] { background-color: #0e3b43; }
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label { color: white !important; }
        h1, h2, h3, p, div, span, label, li { color: #0e3b43 !important; font-family: 'Helvetica', sans-serif; }
        
        /* Input & Dropdown Styling */
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

# --- 3. DATABASE ENGINE (CACHED FOR STABILITY) ---
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

# --- 4. AUTO-REPAIR INITIALIZATION ---
def init_app():
    # Ensures all necessary tables exist
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
    # Logic: 5th of Previous Month -> 5th of Current Month
    if pay_month == 1:
        s_date = date(pay_year - 1, 12, 5)
        e_date = date(pay_year, pay_month, 5)
    else:
        s_date = date(pay_year, pay_month - 1, 5)
        e_date = date(pay_year, pay_month, 5)
        
    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    
    if not att_data or isinstance(att_data, str): 
        return 0.0, 0.0, []
        
    days = 0; report = []; att_dict = {str(r[0]): r[1] for r in att_data}
    has_worked = len(att_data) > 0 # Check if they punched in at least once

    curr = s_date
    while curr <= e_date:
        stat = att_dict.get(str(curr), "Absent")
        cred = 1.0 if stat == 'Present' else (0.5 if stat == 'Half Day' else 0.0)
        
        # Paid Sunday Logic: Only pay if they worked at least once
        if curr.strftime("%A") == 'Sunday':
            cred = 1.0 if has_worked else 0.0
        
        days += cred
        # Date is kept as datetime object for clean export
        report.append([curr, curr.strftime("%A"), stat, cred])
        curr += timedelta(days=1)
        
    salary = (base_salary / 30) * days
    return salary, days, report

# --- MAIN APP ---
init_app()
apply_styling()

if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.title("MENU")

# --- NAVIGATION CONTROLS (Single App) ---
if 'nav' not in st.session_state: st.session_state.nav = 'Role Select'
if 'auth' not in st.session_state: st.session_state.auth = False

# Sidebar Navigation for Admin (once logged in)
def sidebar_nav_buttons():
    if st.session_state.auth:
        st.sidebar.markdown("---")
        st.sidebar.header("Admin Menu")
        if st.sidebar.button("Live Status"): st.session_state.nav = 'Admin - Live'
        if st.sidebar.button("Payroll"): st.session_state.nav = 'Admin - Payroll'
        if st.sidebar.button("Staff Mgmt"): st.session_state.nav = 'Admin - Staff'
        if st.sidebar.button("Maintenance"): st.session_state.nav = 'Admin - Maint'
        st.sidebar.markdown("---")
        if st.sidebar.button("Logout"): st.session_state.auth = False; st.session_state.nav = 'Role Select'
    elif st.session_state.nav != 'Role Select':
        if st.sidebar.button("⬅️ Change Role / Back"): st.session_state.nav = 'Role Select'

sidebar_nav_buttons()

# --------------------------------------------------------------------------------------------------
# 1. ROLE SELECTION SCREEN
# --------------------------------------------------------------------------------------------------
if st.session_state.nav == 'Role Select':
    st.title("Welcome to the National Air Condition Portal")
    st.subheader("Please select your role to proceed.")
    
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("<div class='dashboard-card' style='height:200px;'><h3>Technician / Staff</h3><p>Punch in for daily attendance.</p></div>", unsafe_allow_html=True)
        if st.button("Go to PUNCH IN"):
            st.session_state.nav = 'Technician - Punch'
            st.rerun()

    with col2:
        st.markdown("<div class='dashboard-card' style='height:200px;'><h3>Admin / Payroll</h3><p>Access management, reports, and payroll.</p></div>", unsafe_allow_html=True)
        if st.button("Go to ADMIN LOGIN"):
            st.session_state.nav = 'Admin - Login'
            st.rerun()

# --------------------------------------------------------------------------------------------------
# 2. TECHNICIAN ZONE (Punch In and PIN Reset)
# --------------------------------------------------------------------------------------------------
elif st.session_state.nav == 'Technician - Punch':
    # --- AUTO-REFRESH LOGIC (240 seconds = 4 minutes) ---
    streamlit_js_eval(js_expressions='window.location.reload()', key='refresh_inactivity', timeout=240)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
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
            
            tab1, tab2 = st.tabs(["📸 Punch In", "🔑 Reset PIN Request"])
            with tab1:
                # --- PHOTO FEATURE REMOVED FOR STABILITY ---
                st.info("Live Photo disabled for app stability.")
                
                pin = st.text_input("Enter PIN", type="password", max_chars=4)
                if st.button("PUNCH IN"):
                    if not lat: st.error("GPS Location Required!")
                    else:
                        res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                        real_pin = res[0][0] if res and len(res) > 0 else "0000"
                        if pin == real_pin:
                            addr = get_address(lat, lon); ist = get_ist_time()
                            status = "Half Day" if ist.time() > time(10,30) else "Present"
                            # Store empty bytes instead of photo data
                            res = run_query("INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), status, b'', str(lat), str(lon), addr), fetch=False)
                            if res == True: st.balloons(); st.success("Marked!")
                            else: st.error("Already Marked!")
                        else: st.error("Wrong PIN")
            with tab2:
                if st.button("Request PIN Reset"): 
                    st.session_state.reset_emp_id = emp_id # Store who requested it
                    otp = random.randint(1000, 9999); st.session_state.otp = otp
                    send_sms(ADMIN_MOBILE, otp, f"PIN Reset for {p['name']}")
                    st.success(f"Request sent! Ask your Admin for the OTP. (Backup Code: {otp})")
                    
                if st.session_state.get('otp', False):
                    st.markdown("---")
                    st.subheader("Enter OTP from Admin")
                    u_otp = st.text_input("OTP"); n_pin = st.text_input("New PIN", type='password', max_chars=4)
                    if st.button("Finalize New PIN"):
                        if u_otp == str(st.session_state.otp): 
                            run_query(f"UPDATE employees SET pin='{n_pin}' WHERE id={st.session_state.reset_emp_id}", fetch=False)
                            st.success("PIN Updated!"); del st.session_state.otp; st.session_state.nav = 'Role Select'; st.rerun()
                        else: st.error("Invalid OTP")
        else: st.info("No Staff Found. Contact Admin to add staff.")

# --------------------------------------------------------------------------------------------------
# 3. ADMIN LOGIN
# --------------------------------------------------------------------------------------------------
elif st.session_state.nav == 'Admin - Login':
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<br><div class='dashboard-card'><h3 style='text-align:center'>Admin Login</h3></div>", unsafe_allow_html=True)
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            res = run_query("SELECT password FROM admin_config WHERE id=1")
            real_pass = res[0][0] if res and len(res) > 0 else "admin"
            if pwd == real_pass: 
                st.session_state.auth = True; st.session_state.nav = 'Admin - Live'; st.rerun()
            else: st.error("Access Denied")
            
        st.markdown("---")
        if st.button("Forgot Password?"): 
            otp = random.randint(1000, 9999); st.session_state.admin_otp = otp
            send_sms(ADMIN_MOBILE, otp, "Admin Reset")
            st.success(f"OTP Sent to Admin Mobile! (Backup: {otp})")
        
        if 'admin_otp' in st.session_state:
            otp_in = st.text_input("Enter OTP"); np = st.text_input("New Password", type='password')
            if st.button("Reset Password"):
                if otp_in == str(st.session_state.admin_otp): 
                    run_query(f"UPDATE admin_config SET password='{np}' WHERE id=1", fetch=False); st.success("Updated! Login now."); del st.session_state.admin_otp; st.rerun()
                else: st.error("Invalid OTP")
            
# --------------------------------------------------------------------------------------------------
# 4. ADMIN DASHBOARD - LIVE STATUS
# --------------------------------------------------------------------------------------------------
elif st.session_state.nav == 'Admin - Live' and st.session_state.auth:
    st.title("Admin Dashboard: Live Status")
    
    dt = get_ist_time().date()
    # Note: punch_photo is still selected but not displayed
    data = run_query(f"SELECT e.name, a.time_in, a.status, a.address, a.punch_photo FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
    st.metric("Present Today", len(data) if isinstance(data, list) else 0)
    
    if isinstance(data, list) and data:
        for row in data:
            st.markdown(f"<div class='att-item'><h3>{row[0]}</h3><p>🕒 {row[1]} | {row[2]}</p><small>📍 {row[3]}</small></div>", unsafe_allow_html=True)
            # st.image(row[4], width=100) <--- PHOTO DISPLAY REMOVED HERE
    else: st.info("No attendance yet.")

# --------------------------------------------------------------------------------------------------
# 5. ADMIN DASHBOARD - PAYROLL
# --------------------------------------------------------------------------------------------------
elif st.session_state.nav == 'Admin - Payroll' and st.session_state.auth:
    st.title("Admin Dashboard: Payroll & Reports")
    
    c1, c2 = st.columns(2)
    with c1: p_month = st.selectbox("Month", range(1,13), index=datetime.now().month-1)
    with c2: p_year = st.number_input("Year", value=datetime.now().year)
    
    # PIN RESET MANAGEMENT DISPLAY
    if st.session_state.get('otp', False):
        st.markdown("---")
        st.markdown("### 🔑 Technician PIN Reset Code")
        st.warning(f"Technician OTP: **{st.session_state.otp}** - Give this code to the technician.")
    
    st.markdown("---")
    
    emp_data = run_query("SELECT id, name, salary, pin FROM employees")

    if isinstance(emp_data, list) and emp_data:
        df = pd.DataFrame(emp_data, columns=['id', 'name', 'salary', 'pin'])
        
        # --- INDIVIDUAL SLIP ---
        st.markdown("#### Individual Slip")
        s_emp = st.selectbox("Select Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
        current_pin = df[df['id']==s_emp]['pin'].values[0]
        st.caption(f"Current PIN: **{current_pin}**")
        
        if st.button("Calculate Individual"):
            base = df[df['id']==s_emp]['salary'].values[0]
            sal, days, report = calculate_salary_logic(s_emp, p_month, p_year, base)
            st.success(f"Payable Days: {days} | Net Salary: ₹{sal:,.0f}")
            if report:
                # FIX: Convert the date column to Indian format string before exporting
                df_report = pd.DataFrame(report, columns=['Date', 'Day', 'Status', 'Credit'])
                df_report['Date'] = df_report['Date'].dt.strftime('%Y-%m-%d')
                
                out = BytesIO(); df_report.to_excel(out, index=False)
                st.download_button("Download Staff Slip", out.getvalue(), "staff_slip.xlsx")
        
        st.markdown("---")
        
        # --- MASTER REPORT (ALL STAFF) ---
        st.markdown("#### Master Report (All Employees)")
        if st.button("Download Monthly Master Data"):
            master_data = []
            for index, row in df.iterrows():
                eid = row['id']; ename = row['name']; esal = row['salary']
                net_sal, work_days, _ = calculate_salary_logic(eid, p_month, p_year, esal)
                master_data.append([ename, esal, work_days, net_sal])
            m_df = pd.DataFrame(master_data, columns=['Name', 'Base Salary', 'Days Worked', 'Net Pay'])
            m_out = BytesIO(); m_df.to_excel(m_out, index=False)
            st.download_button("📥 DOWNLOAD FULL EXCEL", m_out.getvalue(), f"Master_Report_{p_month}_{p_year}.xlsx")

# --------------------------------------------------------------------------------------------------
# 6. ADMIN DASHBOARD - STAFF MGMT
# --------------------------------------------------------------------------------------------------
elif st.session_state.nav == 'Admin - Staff' and st.session_state.auth:
    st.title("Admin Dashboard: Staff Management")
    
    emp_data = run_query("SELECT id, name, designation, salary FROM employees")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Add New Staff")
        with st.form("add"):
            n = st.text_input("Name"); d = st.text_input("Role"); s = st.number_input("Salary", step=500.0); p = st.text_input("PIN")
            if st.form_submit_button("Add New Staff"): 
                run_query("INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)", (n,d,s,p,b''), fetch=False); st.success("Added")
    with c2:
        st.subheader("Delete Staff")
        if isinstance(emp_data, list) and emp_data:
            df = pd.DataFrame(emp_data, columns=['id', 'name', 'desig', 'salary'])
            del_id = st.selectbox("Select Employee to Delete", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0], key='del')
            
            if st.button("DELETE USER PERMANENTLY"): 
                run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False)
                run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False)
                st.success("Deleted!"); st.rerun()

# --------------------------------------------------------------------------------------------------
# 7. ADMIN DASHBOARD - MAINTENANCE
# --------------------------------------------------------------------------------------------------
elif st.session_state.nav == 'Admin - Maint' and st.session_state.auth:
    st.title("Admin Dashboard: System Maintenance")
    st.warning("Use this section only if the app is slow or crashing frequently (Aborted error).")
    
    if st.button("🧹 Clear Application Cache & Reconnect Database"):
        st.cache_resource.clear()
        st.success("Cache cleared! The application will refresh and connect to a new database session. Stability should improve.")
        st.rerun()

    st.markdown("---")
    st.markdown("### Admin Password Reset")
    if st.button("Send Password Reset OTP"): 
        otp = random.randint(1000, 9999); st.session_state.admin_otp = otp
        send_sms(ADMIN_MOBILE, otp, "Admin Reset")
        st.success(f"OTP Sent! (Backup: {otp})")
    
    if 'admin_otp' in st.session_state:
        otp_in = st.text_input("Enter OTP"); np = st.text_input("New Password", type='password')
        if st.button("Finalize New Admin Password"):
            if otp_in == str(st.session_state.admin_otp): 
                run_query(f"UPDATE admin_config SET password='{np}' WHERE id=1", fetch=False); st.success("Password Updated!"); del st.session_state.admin_otp; st.rerun()
            else: st.error("Invalid OTP")

# --------------------------------------------------------------------------------------------------
# 8. FALLBACK / DENIED ACCESS
# --------------------------------------------------------------------------------------------------
else:
    st.session_state.auth = False
    st.session_state.nav = 'Role Select'
    st.rerun()

st.markdown("<div class='footer'>© National Air Condition | Developed by <b>Askan Shaikh</b></div>", unsafe_allow_html=True)
