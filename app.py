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

# --- 2. PROFESSIONAL STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        #MainMenu, footer, header, [data-testid="stToolbar"] {visibility: hidden;}
        .stDeployButton {display:none;}
        
        .stApp { background-color: #f0f2f6; margin-top: -50px; }
        h1, h2, h3, h4, h5, h6, p, label, div, span { color: #0e3b43 !important; }
        
        .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input {
            background-color: white !important; color: black !important; border: 1px solid #ddd;
        }
        
        .stButton>button {
            width: 100%; height: 45px; border-radius: 8px; font-weight: 600;
            background: linear-gradient(90deg, #4ba3a8 0%, #2c7a7f 100%);
            color: white !important; border: none;
        }
        
        .dashboard-card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-top: 5px solid #4ba3a8; margin-bottom: 15px;
        }
        .att-item {
            background: white; padding: 15px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 10px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE ENGINE (SSL & ERROR REPORTING) ---
def get_db_connection():
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            return pymysql.connect(
                host=creds["DB_HOST"],
                user=creds["DB_USER"],
                password=creds["DB_PASSWORD"],
                port=creds["DB_PORT"],
                database=creds["DB_NAME"],
                ssl=ssl_ctx
            )
        except Exception as e:
            return None
    return None

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    if not conn:
        return "DB Connection Failed. Check Secrets."
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch:
                return cursor.fetchall()
            else:
                conn.commit()
                return True
    except Exception as e:
        return str(e)  # Return the actual error message
    finally:
        if conn: conn.close()

# --- 4. AUTO-REPAIR ---
def init_app():
    # Attempt to fix tables if missing
    run_query('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10))''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''', fetch=False)
    run_query("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')", fetch=False)

# --- 5. UTILS ---
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
        payload = {"route": "q", "message": f"National Air Condition OTP: {otp}", "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': st.secrets["SMS_API_KEY"], 'Content-Type': "application/x-www-form-urlencoded"}
        requests.request("POST", url, data=payload, headers=headers); return True
    except: return False

def calculate_salary_logic(emp_id, pay_month, pay_year, base_salary):
    if pay_month == 1:
        s_date = date(pay_year - 1, 12, 5)
        e_date = date(pay_year, pay_month, 5)
    else:
        s_date = date(pay_year, pay_month - 1, 5)
        e_date = date(pay_year, pay_month, 5)
        
    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    
    if isinstance(att_data, str) or not att_data: 
        return 0.0, 0.0, []
        
    days = 0; report = []; att_dict = {str(r[0]): r[1] for r in att_data}
    has_worked = len(att_data) > 0

    curr = s_date
    while curr <= e_date:
        stat = att_dict.get(str(curr), "Absent")
        cred = 1.0 if stat == 'Present' else (0.5 if stat == 'Half Day' else 0.0)
        
        # Paid Sunday Logic
        if curr.strftime("%A") == 'Sunday':
            cred = 1.0 if has_worked else 0.0
        
        days += cred
        report.append([curr, curr.strftime("%A"), stat, cred])
        curr += timedelta(days=1)
        
    salary = (base_salary / 30) * days
    return salary, days, report

# --- MAIN APP ---
apply_styling()
init_app()

if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.title("MENU")

if 'nav' not in st.session_state: st.session_state.nav = 'Role Select'
if 'auth' not in st.session_state: st.session_state.auth = False

def sidebar_nav_buttons():
    if st.session_state.auth:
        st.sidebar.markdown("---")
        st.sidebar.header("Admin Menu")
        if st.sidebar.button("Live Status", key='btn_live'): st.session_state.nav = 'Admin - Live'
        if st.sidebar.button("Payroll", key='btn_payroll'): st.session_state.nav = 'Admin - Payroll'
        if st.sidebar.button("Staff Mgmt", key='btn_staff'): st.session_state.nav = 'Admin - Staff'
        if st.sidebar.button("Maintenance", key='btn_maint'): st.session_state.nav = 'Admin - Maint'
        st.sidebar.markdown("---")
        if st.sidebar.button("Logout", key='btn_logout'): 
            st.session_state.auth = False; st.session_state.nav = 'Role Select'; st.rerun()
    elif st.session_state.nav != 'Role Select':
        if st.sidebar.button("⬅️ Back to Home", key='btn_back'): 
            st.session_state.nav = 'Role Select'; st.rerun()

sidebar_nav_buttons()

# --- 1. ROLE SELECT ---
if st.session_state.nav == 'Role Select':
    st.title("National Air Condition Portal")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<div class='dashboard-card'><h3>Technician</h3><p>Punch in for daily attendance.</p></div>", unsafe_allow_html=True)
        if st.button("Go to PUNCH IN"): st.session_state.nav = 'Technician - Punch'; st.rerun()
    with col2:
        st.markdown("<div class='dashboard-card'><h3>Admin</h3><p>Manage staff and payroll.</p></div>", unsafe_allow_html=True)
        if st.button("Go to ADMIN LOGIN"): st.session_state.nav = 'Admin - Login'; st.rerun()

# --- 2. TECHNICIAN ZONE ---
elif st.session_state.nav == 'Technician - Punch':
    streamlit_js_eval(js_expressions='setTimeout(() => window.location.reload(), 300000)', key='keep_alive')
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown(f"<h3 style='text-align:center;'>Daily Attendance</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; color:grey;'>{get_ist_time().strftime('%d %b %Y | %I:%M %p')}</p>", unsafe_allow_html=True)
        
        loc = get_geolocation()
        if loc and 'coords' in loc:
            lat = loc['coords']['latitude']; lon = loc['coords']['longitude']
            st.success("📍 GPS Active")

            rows = run_query("SELECT id, name, designation FROM employees")
            
            # --- DEBUG: CHECK FOR ERRORS ---
            if isinstance(rows, str): 
                st.error(f"❌ DATABASE ERROR: {rows}")
                st.info("💡 Hint: You might need to delete old tables or check TiDB console.")
            # -------------------------------
            
            elif isinstance(rows, list) and rows:
                df = pd.DataFrame(rows, columns=['id', 'name', 'desig'])
                emp_id = st.selectbox("Select Your Name", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                
                p = df[df['id']==emp_id].iloc[0]
                st.markdown(f"<div class='dashboard-card' style='text-align:center;'><h2>{p['name']}</h2><p>{p['desig']}</p></div>", unsafe_allow_html=True)
                
                tab1, tab2 = st.tabs(["Punch In", "Reset PIN"])
                with tab1:
                    pin = st.text_input("Enter PIN", type="password", max_chars=4)
                    if st.button("PUNCH IN"):
                        res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                        if isinstance(res, str): st.error(res)
                        else:
                            real_pin = res[0][0] if res else "0000"
                            if pin == real_pin:
                                addr = get_address(lat, lon); ist = get_ist_time()
                                
                                # --- UPDATED LOGIC: ALWAYS PRESENT ---
                                status = "Present" 
                                # -------------------------------------
                                
                                res = run_query("INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), status, str(lat), str(lon), addr), fetch=False)
                                if res == True: st.balloons(); st.success("Marked Present!")
                                else: st.error("Already Marked Today!")
                            else: st.error("Wrong PIN")
                with tab2:
                    if st.button("Request PIN Reset"):
                        st.session_state.reset_emp_id = emp_id
                        otp = random.randint(1000, 9999); st.session_state.otp = otp
                        send_sms(ADMIN_MOBILE, otp, f"PIN Reset: {p['name']}")
                        st.success(f"OTP Sent: {otp}")
                    if st.session_state.get('otp', False):
                        u_otp = st.text_input("OTP"); n_pin = st.text_input("New PIN", type='password', max_chars=4)
                        if st.button("Update PIN"):
                            if u_otp == str(st.session_state.otp): 
                                run_query(f"UPDATE employees SET pin='{n_pin}' WHERE id={st.session_state.reset_emp_id}", fetch=False)
                                st.success("Updated!"); del st.session_state.otp; st.rerun()
                            else: st.error("Invalid OTP")
            else: st.warning("Staff list is empty. Please ask Admin to add staff.")
        else: st.warning("Waiting for GPS...")

# --- 3. ADMIN LOGIN ---
elif st.session_state.nav == 'Admin - Login':
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<br><div class='dashboard-card'><h3 style='text-align:center'>Admin Login</h3></div>", unsafe_allow_html=True)
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            res = run_query("SELECT password FROM admin_config WHERE id=1")
            if isinstance(res, str): st.error(res)
            elif pwd == (res[0][0] if res else "admin"): 
                st.session_state.auth = True; st.session_state.nav = 'Admin - Live'; st.rerun()
            else: st.error("Access Denied")

# --- 4. ADMIN DASHBOARD ---
elif st.session_state.auth:
    if st.session_state.nav == 'Admin - Live':
        st.title("Live Status")
        dt = get_ist_time().date()
        data = run_query(f"SELECT e.name, a.time_in, a.status, a.address FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
        
        if isinstance(data, str): st.error(data)
        elif isinstance(data, list) and data:
            st.metric("Present Today", len(data))
            for row in data:
                st.markdown(f"<div class='att-item'><h3>{row[0]}</h3><p>🕒 {row[1]} | {row[2]}</p><small>📍 {row[3]}</small></div>", unsafe_allow_html=True)
        else: st.info("No attendance yet today.")

    elif st.session_state.nav == 'Admin - Payroll':
        st.title("Payroll")
        c1, c2 = st.columns(2)
        with c1: p_month = st.selectbox("Month", range(1,13), index=datetime.now().month-1)
        with c2: p_year = st.number_input("Year", value=datetime.now().year)
        
        emp_data = run_query("SELECT id, name, salary, pin FROM employees")
        if isinstance(emp_data, list) and emp_data:
            df = pd.DataFrame(emp_data, columns=['id', 'name', 'salary', 'pin'])
            s_emp = st.selectbox("Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
            
            if st.button("Calculate"):
                base = df[df['id']==s_emp]['salary'].values[0]
                sal, days, report = calculate_salary_logic(s_emp, p_month, p_year, base)
                st.success(f"Payable Days: {days} | Net Salary: ₹{sal:,.0f}")
                if report:
                    df_r = pd.DataFrame(report, columns=['Date', 'Day', 'Status', 'Credit'])
                    df_r['Date'] = df_r['Date'].dt.strftime('%Y-%m-%d')
                    st.download_button("Download Slip", BytesIO(df_r.to_excel(index=False).encode('utf-8') if hasattr(df_r.to_excel(index=False), 'encode') else b'Error'), "slip.csv")

    elif st.session_state.nav == 'Admin - Staff':
        st.title("Staff Mgmt")
        c1, c2 = st.columns(2)
        with c1:
            with st.form("add"):
                n = st.text_input("Name"); d = st.text_input("Role"); s = st.number_input("Salary", step=500.0); p = st.text_input("PIN")
                if st.form_submit_button("Add"): 
                    res = run_query("INSERT INTO employees (name, designation, salary, pin) VALUES (%s, %s, %s, %s)", (n,d,s,p), fetch=False)
                    if res == True: st.success("Added")
                    else: st.error(str(res))
        with c2:
            emp_data = run_query("SELECT id, name FROM employees")
            if isinstance(emp_data, list) and emp_data:
                del_id = st.selectbox("Delete", [x[0] for x in emp_data], format_func=lambda x: [y[1] for y in emp_data if y[0]==x][0])
                if st.button("DELETE"): 
                    run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False)
                    run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False)
                    st.rerun()

    elif st.session_state.nav == 'Admin - Maint':
        st.title("Maintenance")
        if st.button("Clear Cache"): st.cache_resource.clear(); st.rerun()

else:
    st.session_state.auth = False
    st.session_state.nav = 'Role Select'
    st.rerun()

st.markdown("<div class='footer'>© National Air Condition | Developed by <b>Askan Shaikh</b></div>", unsafe_allow_html=True)
