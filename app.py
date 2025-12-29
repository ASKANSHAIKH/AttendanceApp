import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date, timezone
import pymysql
import ssl
import os
from io import BytesIO
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from geopy.geocoders import Nominatim

# =======================================================
# 1. APP CONFIGURATION & DARK THEME CSS
# =======================================================
st.set_page_config(
    page_title="National Air Condition",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# FORCE DARK THEME & STATIC COLORS (No Hover Glitches)
st.markdown("""
    <style>
    /* 1. Main Background - Deep Dark Grey */
    .stApp { 
        background-color: #121212 !important; 
    }
    
    /* 2. Text Visibility - Always White */
    h1, h2, h3, h4, h5, h6, p, label, span, div, li { 
        color: #ffffff !important; 
        font-family: sans-serif;
    }
    
    /* 3. Buttons - Static Teal Color (No Hover Animation) */
    .stButton>button {
        width: 100%; 
        border-radius: 8px; 
        height: 50px; 
        font-weight: bold;
        background-color: #00ADB5 !important; /* Cyan/Teal */
        color: white !important; 
        border: none !important;
        transition: none !important; /* REMOVED HOVER EFFECT */
    }
    
    /* Force button to stay same color on hover */
    .stButton>button:hover, .stButton>button:active, .stButton>button:focus {
        background-color: #00ADB5 !important;
        color: white !important;
        box-shadow: none !important;
    }
    
    /* 4. Input Fields - White for Contrast */
    .stTextInput input, .stNumberInput input, .stPasswordInput input, .stSelectbox div {
        background-color: #ffffff !important; 
        color: #000000 !important; 
        border: 1px solid #333;
    }
    
    /* 5. Tabs Styling */
    button[data-baseweb="tab"] {
        color: #ffffff !important;
        background-color: #1e1e1e !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #00ADB5 !important;
        color: white !important;
    }
    
    /* 6. Dashboard Cards */
    .metric-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
        margin-bottom: 15px;
    }
    
    #MainMenu, footer, header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# =======================================================
# 2. DATABASE ENGINE
# =======================================================
def get_db_connection():
    if "connections" not in st.secrets or "tidb" not in st.secrets["connections"]:
        st.error("❌ Database Secrets Missing!")
        return None

    creds = st.secrets["connections"]["tidb"]
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        return pymysql.connect(
            host=creds["DB_HOST"], user=creds["DB_USER"], password=creds["DB_PASSWORD"],
            port=creds["DB_PORT"], database=creds["DB_NAME"], ssl=ssl_ctx, autocommit=True
        )
    except Exception as e: return None

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch: return cursor.fetchall()
            return True
    except Exception as e: return None
    finally:
        if conn: conn.close()

# --- FORCE SYSTEM INIT ---
def init_system():
    queries = [
        """CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10))""",
        """CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))""",
        """CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))""",
        """INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')"""
    ]
    for q in queries: run_query(q, fetch=False)
init_system()

# =======================================================
# 3. UTILS & EXCEL
# =======================================================
def get_ist_time(): return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)

def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return loc.address.split(",")[0] if loc else "Unknown"
    except: return "Loc Unavailable"

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    return output.getvalue()

def calculate_payroll(emp_id, start_month, year, salary):
    s_date = date(year, start_month, 5)
    if start_month == 12: e_date = date(year + 1, 1, 4)
    else: e_date = date(year, start_month + 1, 4)
    
    data = run_query(f"SELECT date, status, time_in, address FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    
    att_map = {}
    if data:
        for r in data: att_map[r[0]] = {'status': r[1], 'time': r[2], 'loc': r[3]}
            
    total_days = 0; report = []; has_worked = len(data) > 0 if data else False
    curr = s_date
    while curr <= e_date:
        stat = "Absent"; t_in = "-"; loc = "-"
        if curr in att_map:
            rec = att_map[curr]
            stat = rec['status']; t_in = rec['time']; loc = rec['loc']
        
        cred = 1.0 if stat == "Present" else (0.5 if stat == "Half Day" else 0.0)
        if curr.strftime("%A") == "Sunday" and has_worked: stat = "Weekly Off"; cred = 1.0
            
        total_days += cred
        report.append({"Date": curr.strftime("%d-%m-%Y"), "Day": curr.strftime("%A"), "Status": stat, "Punch In": t_in, "Location": loc, "Credit": cred})
        curr += timedelta(days=1)
        
    return (salary / 30) * total_days, total_days, report, s_date, e_date

# =======================================================
# 4. MAIN NAVIGATION
# =======================================================
if 'nav' not in st.session_state: st.session_state.nav = 'Home'
if 'auth' not in st.session_state: st.session_state.auth = False

# --- HEADER ---
c1, c2 = st.columns([1, 6])
with c1:
    if os.path.exists("logo.png"): st.image("logo.png", width=100)
    else: st.markdown("<h1>❄️</h1>", unsafe_allow_html=True)
with c2:
    st.markdown("<h2>National Air Condition</h2>", unsafe_allow_html=True)
st.markdown("---")

# --- HOME ---
if st.session_state.nav == 'Home':
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='metric-card'><h3>👷 Technician Zone</h3><p>Punch In for Attendance</p></div>", unsafe_allow_html=True)
        if st.button("ENTER AS TECHNICIAN"): st.session_state.nav = 'Technician'
    with c2:
        st.markdown("<div class='metric-card'><h3>🛡️ Admin Zone</h3><p>Manage Staff & Payroll</p></div>", unsafe_allow_html=True)
        if st.button("ENTER AS ADMIN"): st.session_state.nav = 'Login'

# --- TECHNICIAN ---
elif st.session_state.nav == 'Technician':
    streamlit_js_eval(js_expressions='setTimeout(() => window.location.reload(), 300000)', key='keep_alive')
    if st.button("⬅️ Back"): st.session_state.nav = 'Home'; st.rerun()
    st.markdown("### 📍 Daily Punch-In")
    
    staff = run_query("SELECT id, name FROM employees")
    if staff:
        emp_id = st.selectbox("Select Your Name", [r[0] for r in staff], format_func=lambda x: [r[1] for r in staff if r[0]==x][0])
        pin = st.text_input("Enter 4-Digit PIN", type="password")
        loc = get_geolocation()
        
        if loc and 'coords' in loc:
            st.success("✅ GPS Connected")
            if st.button("PUNCH IN NOW"):
                res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                if res and pin == res[0][0]:
                    ist = get_ist_time(); lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                    s = run_query("INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), "Present", str(lat), str(lon), get_address(lat, lon)), fetch=False)
                    if s: st.balloons(); st.success("Marked Present!")
                    else: st.error("Already Punched In Today")
                else: st.error("Wrong PIN")
        else: st.warning("Waiting for GPS...")
    else: st.info("No staff found.")

# --- LOGIN ---
elif st.session_state.nav == 'Login':
    if st.button("⬅️ Back"): st.session_state.nav = 'Home'; st.rerun()
    st.markdown("### 🔐 Admin Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("LOGIN"):
        res = run_query("SELECT password FROM admin_config WHERE id=1")
        real_pass = res[0][0] if res else "admin"
        if pwd == real_pass: st.session_state.auth = True; st.session_state.nav = 'Dashboard'; st.rerun()
        else: st.error("Wrong Password")

# --- DASHBOARD ---
elif st.session_state.nav == 'Dashboard' and st.session_state.auth:
    if st.button("🚪 Logout", key='logout'): st.session_state.auth = False; st.session_state.nav = 'Home'; st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["📊 Live Status", "👥 Staff Mgmt", "💰 Payroll"])
    
    with tab1:
        st.subheader("Today's Records")
        dt = get_ist_time().date()
        data = run_query(f"SELECT e.name, a.time_in, a.address FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
        if data: st.dataframe(pd.DataFrame(data, columns=['Name', 'Time', 'Location']), use_container_width=True)
        else: st.info("No attendance yet today.")

    with tab2:
        st.subheader("Staff Management")
        st.markdown("**Add New Staff**")
        n = st.text_input("Name")
        s = st.number_input("Salary", step=500)
        p = st.text_input("PIN")
        if st.button("💾 Save Staff"):
            run_query("INSERT INTO employees (name, designation, salary, pin) VALUES (%s, 'Tech', %s, %s)", (n, s, p), fetch=False)
            st.success("Saved!"); st.rerun()
            
        st.markdown("---")
        st.markdown("**Remove Staff**")
        staff = run_query("SELECT id, name FROM employees")
        if staff:
            d = st.selectbox("Delete Staff", [r[0] for r in staff], format_func=lambda x: [r[1] for r in staff if r[0]==x][0])
            if st.button("🗑️ Delete Permanently"):
                run_query(f"DELETE FROM attendance WHERE emp_id={d}", fetch=False)
                run_query(f"DELETE FROM employees WHERE id={d}", fetch=False)
                st.success("Deleted!"); st.rerun()

    with tab3:
        st.subheader("Payroll & Excel Export")
        staff = run_query("SELECT id, name, salary FROM employees")
        if staff:
            c1, c2, c3 = st.columns(3)
            with c1: u = st.selectbox("Staff Member", [r[0] for r in staff], format_func=lambda x: [r[1] for r in staff if r[0]==x][0])
            with c2: m = st.selectbox("Start Month", range(1, 13), index=datetime.now().month-1)
            with c3: y = st.number_input("Year", value=datetime.now().year)
            
            if st.button("Generate Report"):
                bs = [r[2] for r in staff if r[0]==u][0]; en = [r[1] for r in staff if r[0]==u][0]
                pay, days, rep, sd, ed = calculate_payroll(u, m, y, bs)
                
                st.markdown(f"<div class='metric-card'><h3>Pay: ₹{pay:,.0f}</h3><p>{days} Days ({sd.strftime('%d %b')} - {ed.strftime('%d %b')})</p></div>", unsafe_allow_html=True)
                
                df_rep = pd.DataFrame(rep)
                if not df_rep.empty:
                    st.download_button(f"📥 Download Excel", to_excel(df_rep), f"{en}_{sd.strftime('%b')}.xlsx")
                    st.dataframe(df_rep, use_container_width=True)
