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
# 1. APP CONFIGURATION & STYLING
# =======================================================
st.set_page_config(
    page_title="National Air Condition",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# FORCE LIGHT THEME & VISIBILITY
st.markdown("""
    <style>
    .stApp { background-color: #ffffff !important; }
    h1, h2, h3, h4, h5, h6, p, label, span, div, li { color: #0e3b43 !important; font-family: 'Inter', sans-serif; }
    
    /* Big Visible Buttons */
    .stButton>button {
        width: 100%; border-radius: 8px; height: 50px; font-weight: bold;
        background-color: #0e3b43 !important; color: white !important; border: 2px solid #0e3b43;
    }
    
    /* Inputs */
    .stTextInput input, .stNumberInput input, .stPasswordInput input, .stSelectbox div {
        background-color: #f8f9fa !important; color: black !important; border: 1px solid #ccc;
    }
    
    /* TABS STYLING */
    button[data-baseweb="tab"] {
        font-size: 18px !important;
        font-weight: bold !important;
        color: #0e3b43 !important;
        background-color: #f0f2f6 !important;
        margin-right: 5px;
        border-radius: 5px 5px 0 0;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #0e3b43 !important;
        color: white !important;
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
# 3. UTILS & EXCEL LOGIC
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
        df.to_excel(writer, index=False, sheet_name='Attendance_Report')
    processed_data = output.getvalue()
    return processed_data

def calculate_payroll(emp_id, start_month, year, salary):
    # LOGIC: Start 5th of Selected Month -> End 4th of Next Month
    s_date = date(year, start_month, 5)
    
    # Handle Year Rollover (e.g., if start is Dec, end is Jan of next year)
    if start_month == 12:
        e_date = date(year + 1, 1, 4)
    else:
        e_date = date(year, start_month + 1, 4)
    
    # Fetch Attendance
    data = run_query(f"SELECT date, status, time_in, address FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    
    # Process Data
    att_map = {}
    if data:
        for r in data:
            att_map[r[0]] = {'status': r[1], 'time': r[2], 'loc': r[3]}
            
    total_days = 0
    detailed_report = []
    has_worked_any = len(data) > 0 if data else False
    
    curr = s_date
    while curr <= e_date:
        # Defaults
        status = "Absent"
        time_in = "-"
        loc = "-"
        
        # Check if record exists
        if curr in att_map:
            record = att_map[curr]
            status = record['status']
            time_in = record['time']
            loc = record['loc']
        
        # Credit Logic
        credit = 0.0
        if status == "Present": credit = 1.0
        elif status == "Half Day": credit = 0.5
        
        # Paid Sunday Logic
        if curr.strftime("%A") == "Sunday" and has_worked_any: 
            status = "Weekly Off"
            credit = 1.0
            
        total_days += credit
        
        detailed_report.append({
            "Date": curr.strftime("%d-%m-%Y"),
            "Day": curr.strftime("%A"),
            "Status": status,
            "Punch In": time_in,
            "Location": loc,
            "Credit": credit
        })
        
        curr += timedelta(days=1)
        
    final_pay = (salary / 30) * total_days
    return final_pay, total_days, detailed_report, s_date, e_date

# =======================================================
# 4. MAIN NAVIGATION
# =======================================================
if 'nav' not in st.session_state: st.session_state.nav = 'Home'
if 'auth' not in st.session_state: st.session_state.auth = False

# --- HEADER ---
c1, c2 = st.columns([1, 6])
with c1:
    if os.path.exists("logo.png"): st.image("logo.png", width=110)
    else: st.header("❄️")
with c2:
    st.markdown("<h3>National Air Condition</h3>", unsafe_allow_html=True)
st.markdown("---")

# --- HOME ---
if st.session_state.nav == 'Home':
    c1, c2 = st.columns(2)
    with c1:
        if st.button("👷 TECHNICIAN ZONE"): st.session_state.nav = 'Technician'
    with c2:
        if st.button("🛡️ ADMIN ZONE"): st.session_state.nav = 'Login'

# --- TECHNICIAN ---
elif st.session_state.nav == 'Technician':
    streamlit_js_eval(js_expressions='setTimeout(() => window.location.reload(), 300000)', key='keep_alive')
    if st.button("⬅️ Back"): st.session_state.nav = 'Home'; st.rerun()
    st.markdown("### 📍 Punch-In")
    
    staff = run_query("SELECT id, name FROM employees")
    if staff:
        emp_id = st.selectbox("Select Name", [r[0] for r in staff], format_func=lambda x: [r[1] for r in staff if r[0]==x][0])
        pin = st.text_input("Enter PIN", type="password")
        loc = get_geolocation()
        
        if loc and 'coords' in loc:
            st.success("GPS Ready")
            if st.button("PUNCH IN"):
                res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                if res and pin == res[0][0]:
                    ist = get_ist_time(); lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                    s = run_query("INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), "Present", str(lat), str(lon), get_address(lat, lon)), fetch=False)
                    if s: st.balloons(); st.success("Marked!")
                    else: st.error("Already Punched In Today")
                else: st.error("Wrong PIN")
        else: st.warning("Waiting for GPS...")
    else: st.info("No staff found.")

# --- LOGIN ---
elif st.session_state.nav == 'Login':
    if st.button("⬅️ Back"): st.session_state.nav = 'Home'; st.rerun()
    st.markdown("### 🔐 Admin Login")
    pwd = st.text_input("Password", type="password")
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
        st.subheader("Today's Attendance")
        dt = get_ist_time().date()
        data = run_query(f"SELECT e.name, a.time_in, a.address FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
        if data: st.dataframe(pd.DataFrame(data, columns=['Name', 'Time', 'Location']), use_container_width=True)
        else: st.info("No attendance today.")

    with tab2:
        st.subheader("Manage Staff")
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
            d = st.selectbox("Select to Delete", [r[0] for r in staff], format_func=lambda x: [r[1] for r in staff if r[0]==x][0])
            if st.button("🗑️ Delete Permanently"):
                run_query(f"DELETE FROM attendance WHERE emp_id={d}", fetch=False)
                run_query(f"DELETE FROM employees WHERE id={d}", fetch=False)
                st.success("Deleted!"); st.rerun()

    with tab3:
        st.subheader("Payroll & Excel Export")
        staff = run_query("SELECT id, name, salary FROM employees")
        if staff:
            c1, c2, c3 = st.columns(3)
            with c1: u = st.selectbox("Select Technician", [r[0] for r in staff], format_func=lambda x: [r[1] for r in staff if r[0]==x][0])
            with c2: m = st.selectbox("Cycle Start Month", range(1, 13), index=datetime.now().month-1, help="Select Jan for Jan 5 - Feb 4")
            with c3: y = st.number_input("Year", value=datetime.now().year)
            
            if st.button("Calculate & Generate Report"):
                base_sal = [r[2] for r in staff if r[0]==u][0]
                emp_name = [r[1] for r in staff if r[0]==u][0]
                
                pay, days, report_data, start_d, end_d = calculate_payroll(u, m, y, base_sal)
                
                st.markdown(f"""
                <div style='background-color:#e6fffa; padding:15px; border-radius:10px; border-left:5px solid #0e3b43'>
                    <h3 style='margin:0'>Total Pay: ₹ {pay:,.0f}</h3>
                    <p style='margin:0'><b>{days}</b> Days Payable (Cycle: {start_d.strftime('%d %b')} to {end_d.strftime('%d %b')})</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Create DataFrame for Excel
                df_report = pd.DataFrame(report_data)
                excel_file = to_excel(df_report)
                
                # Excel Download Button
                file_name = f"{emp_name}_Attendance_{start_d.strftime('%b%Y')}.xlsx"
                st.download_button(
                    label=f"📥 Download Excel for {emp_name}",
                    data=excel_file,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                st.markdown("### Detailed View")
                st.dataframe(df_report, use_container_width=True)
