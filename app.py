import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date, timezone
import pymysql
import ssl
import os
import requests
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from geopy.geocoders import Nominatim

# =======================================================
# 1. APP CONFIGURATION & STYLING (The "Best UI" Part)
# =======================================================
st.set_page_config(
    page_title="National Air Condition",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Professional Look & Dark Mode Fix
st.markdown("""
    <style>
    /* Force Light Theme Colors */
    .stApp { background-color: #f4f6f9 !important; }
    h1, h2, h3, h4, h5, h6, p, label, span, div { color: #0e3b43 !important; font-family: 'Inter', sans-serif; }
    
    /* Input Fields */
    .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input, .stSelectbox div {
        background-color: white !important; 
        color: #000000 !important;
        border-radius: 8px;
        border: 1px solid #ced4da;
    }
    
    /* Professional Buttons */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 50px;
        font-weight: 600;
        background-color: #0e3b43;
        color: white !important;
        border: none;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #165b65;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Dashboard Cards */
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border-left: 5px solid #0e3b43;
        margin-bottom: 15px;
    }
    
    /* Hide Streamlit Junk */
    #MainMenu, footer, header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# =======================================================
# 2. ROBUST DATABASE ENGINE ("Self-Healing" Connection)
# =======================================================
def get_db_connection():
    # Check if secrets exist
    if "connections" not in st.secrets or "tidb" not in st.secrets["connections"]:
        st.error("❌ Database Secrets Missing! Please check Streamlit Settings.")
        return None

    creds = st.secrets["connections"]["tidb"]
    
    # Secure SSL Context for Cloud DB
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        # Connect with Autocommit (Instant Save)
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
        return None

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch: return cursor.fetchall()
            return True
    except Exception as e:
        st.toast(f"⚠️ Database Warning: {str(e)}", icon="🔧")
        return None
    finally:
        if conn: conn.close()

# --- FORCE SYSTEM INITIALIZATION ---
# This runs on every load to ensure tables ALWAYS exist
def init_system():
    queries = [
        # Employees Table
        """CREATE TABLE IF NOT EXISTS employees (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            name VARCHAR(255), 
            designation VARCHAR(255), 
            salary DOUBLE, 
            pin VARCHAR(10)
        )""",
        # Attendance Table
        """CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            emp_id INT, 
            date DATE, 
            time_in VARCHAR(20), 
            status VARCHAR(50), 
            latitude VARCHAR(50), 
            longitude VARCHAR(50), 
            address TEXT, 
            UNIQUE KEY unique_att (emp_id, date)
        )""",
        # Admin Config
        """CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))""",
        """INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')"""
    ]
    for q in queries:
        run_query(q, fetch=False)

init_system() # <--- Run Self-Healing immediately

# =======================================================
# 3. UTILITY FUNCTIONS
# =======================================================
def get_ist_time():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)

def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return loc.address.split(",")[0] if loc else "Unknown Location"
    except: return "Location Unavailable"

def calculate_payroll(emp_id, month, year, salary):
    # Calculate dates
    if month == 1: s_date, e_date = date(year-1, 12, 5), date(year, month, 5)
    else: s_date, e_date = date(year, month-1, 5), date(year, month, 5)
    
    # Fetch Data
    data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{s_date}' AND '{e_date}'")
    
    if not data: return 0, 0, []
    
    # Logic
    att_map = {r[0]: r[1] for r in data}
    total_days = 0
    report = []
    has_worked_any = len(data) > 0
    
    curr = s_date
    while curr <= e_date:
        status = att_map.get(curr, "Absent")
        credit = 0.0
        
        if status == "Present": credit = 1.0
        elif status == "Half Day": credit = 0.5
        elif curr.strftime("%A") == "Sunday" and has_worked_any: credit = 1.0 # Paid Sunday
        
        total_days += credit
        report.append([curr.strftime("%Y-%m-%d"), curr.strftime("%A"), status, credit])
        curr += timedelta(days=1)
        
    final_pay = (salary / 30) * total_days
    return final_pay, total_days, report

# =======================================================
# 4. MAIN NAVIGATION & UI
# =======================================================
if 'nav' not in st.session_state: st.session_state.nav = 'Home'
if 'auth' not in st.session_state: st.session_state.auth = False

# --- HEADER WITH LOGO ---
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if os.path.exists("logo.png"): st.image("logo.png", width=100)
    else: st.header("❄️")
with col_title:
    st.markdown("<h1>National Air Condition</h1>", unsafe_allow_html=True)
    st.markdown("<p style='margin-top: -15px;'>Attendance & Payroll Portal</p>", unsafe_allow_html=True)

st.markdown("---")

# =======================================================
# VIEW 1: HOME SCREEN (Role Selection)
# =======================================================
if st.session_state.nav == 'Home':
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        <div class='metric-card'>
            <h3>👷 Technician Zone</h3>
            <p>Punch in for daily attendance using GPS.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("ENTER AS TECHNICIAN"): st.session_state.nav = 'Technician'
        
    with c2:
        st.markdown("""
        <div class='metric-card'>
            <h3>🛡️ Admin Zone</h3>
            <p>Manage staff, view reports, and payroll.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("ENTER AS ADMIN"): st.session_state.nav = 'Login'

# =======================================================
# VIEW 2: TECHNICIAN PUNCH-IN
# =======================================================
elif st.session_state.nav == 'Technician':
    # Keep Alive Timer (5 mins)
    streamlit_js_eval(js_expressions='setTimeout(() => window.location.reload(), 300000)', key='keep_alive')
    
    if st.button("⬅️ Back to Home"): st.session_state.nav = 'Home'; st.rerun()
    
    st.markdown("### 📍 Daily Attendance Punch-In")
    
    # 1. Fetch Staff List
    staff_data = run_query("SELECT id, name FROM employees")
    
    if not staff_data or len(staff_data) == 0:
        st.warning("⚠️ Staff list is empty. Please contact Admin to add your profile.")
    else:
        # 2. Selection Form
        options = staff_data
        emp_id = st.selectbox("Select Your Name", [r[0] for r in options], format_func=lambda x: [r[1] for r in options if r[0]==x][0])
        pin_in = st.text_input("Enter 4-Digit PIN", type="password", max_chars=4)
        
        # 3. GPS Logic
        loc = get_geolocation()
        if loc and 'coords' in loc:
            lat = loc['coords']['latitude']
            lon = loc['coords']['longitude']
            st.success("✅ GPS Connected & Ready")
            
            if st.button("PUNCH IN NOW"):
                # Verify PIN
                verify = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                if verify and verify[0][0] == pin_in:
                    ist = get_ist_time()
                    address = get_address(lat, lon)
                    
                    # Insert Attendance
                    save = run_query(
                        "INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (emp_id, ist.date(), ist.time().strftime("%H:%M"), "Present", str(lat), str(lon), address),
                        fetch=False
                    )
                    
                    if save == True:
                        st.balloons()
                        st.success(f"✅ Attendance Marked for {ist.strftime('%d-%m-%Y')} at {ist.strftime('%H:%M')}")
                    else:
                        st.error("⚠️ You have already punched in today.")
                else:
                    st.error("❌ Incorrect PIN. Please try again.")
        else:
            st.warning("⏳ Waiting for GPS... Please allow location access.")

# =======================================================
# VIEW 3: ADMIN LOGIN
# =======================================================
elif st.session_state.nav == 'Login':
    if st.button("⬅️ Back"): st.session_state.nav = 'Home'; st.rerun()
    
    st.markdown("### 🔐 Admin Login")
    pwd = st.text_input("Enter Password", type="password")
    
    if st.button("LOGIN"):
        # Check DB for password, fallback to 'admin' if table empty
        res = run_query("SELECT password FROM admin_config WHERE id=1")
        real_pass = res[0][0] if res else "admin"
        
        if pwd == real_pass:
            st.session_state.auth = True
            st.session_state.nav = 'Dashboard'
            st.rerun()
        else:
            st.error("❌ Access Denied")

# =======================================================
# VIEW 4: ADMIN DASHBOARD
# =======================================================
elif st.session_state.nav == 'Dashboard' and st.session_state.auth:
    # Sidebar Navigation
    with st.sidebar:
        st.header("Admin Menu")
        if st.button("📊 Live Dashboard"): st.session_state.sub_nav = 'Live'
        if st.button("👥 Staff Management"): st.session_state.sub_nav = 'Staff'
        if st.button("💰 Payroll"): st.session_state.sub_nav = 'Payroll'
        st.divider()
        if st.button("🚪 Logout"): 
            st.session_state.auth = False
            st.session_state.nav = 'Home'
            st.rerun()

    # Default Sub-Nav
    if 'sub_nav' not in st.session_state: st.session_state.sub_nav = 'Live'

    # --- TAB 1: LIVE STATUS ---
    if st.session_state.sub_nav == 'Live':
        st.header("📊 Today's Attendance")
        dt = get_ist_time().date()
        
        data = run_query(f"""
            SELECT e.name, a.time_in, a.address 
            FROM attendance a 
            JOIN employees e ON a.emp_id=e.id 
            WHERE a.date='{dt}'
        """)
        
        if data:
            st.success(f"✅ {len(data)} Staff Present Today")
            df = pd.DataFrame(data, columns=['Name', 'Time In', 'Location'])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("ℹ️ No attendance records found for today.")

    # --- TAB 2: STAFF MANAGEMENT ---
    elif st.session_state.sub_nav == 'Staff':
        st.header("👥 Staff Management")
        
        tab1, tab2 = st.tabs(["➕ Add New Staff", "🗑️ Remove Staff"])
        
        with tab1:
            with st.form("add_staff"):
                col_a, col_b = st.columns(2)
                with col_a:
                    n = st.text_input("Full Name")
                    r = st.text_input("Role (e.g. Technician)")
                with col_b:
                    s = st.number_input("Monthly Salary", min_value=0, step=500)
                    p = st.text_input("4-Digit PIN", max_chars=4)
                
                if st.form_submit_button("💾 Save Employee"):
                    if n and p:
                        res = run_query("INSERT INTO employees (name, designation, salary, pin) VALUES (%s, %s, %s, %s)", (n, r, s, p), fetch=False)
                        if res == True: st.success(f"✅ Added {n} successfully!"); st.rerun()
                        else: st.error("❌ Failed to save.")
                    else:
                        st.warning("⚠️ Name and PIN are required.")

        with tab2:
            staff_list = run_query("SELECT id, name FROM employees")
            if staff_list:
                to_del = st.selectbox("Select Staff to Remove", [r[0] for r in staff_list], format_func=lambda x: [r[1] for r in staff_list if r[0]==x][0])
                if st.button("🗑️ PERMANENTLY DELETE"):
                    run_query(f"DELETE FROM attendance WHERE emp_id={to_del}", fetch=False)
                    run_query(f"DELETE FROM employees WHERE id={to_del}", fetch=False)
                    st.success("✅ Deleted successfully!")
                    st.rerun()
            else:
                st.info("No staff to delete.")
                
        # Show Current List
        st.subheader("Current Staff List")
        all_staff = run_query("SELECT name, designation, pin, salary FROM employees")
        if all_staff:
            st.dataframe(pd.DataFrame(all_staff, columns=['Name', 'Role', 'PIN', 'Salary']), use_container_width=True)

    # --- TAB 3: PAYROLL ---
    elif st.session_state.sub_nav == 'Payroll':
        st.header("💰 Payroll Calculator")
        
        staff_list = run_query("SELECT id, name, salary FROM employees")
        if staff_list:
            c1, c2, c3 = st.columns(3)
            with c1: selected_emp = st.selectbox("Select Employee", [r[0] for r in staff_list], format_func=lambda x: [r[1] for r in staff_list if r[0]==x][0])
            with c2: p_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1)
            with c3: p_year = st.number_input("Year", value=datetime.now().year)
            
            if st.button("🧮 Calculate Salary"):
                # Get base salary
                base_salary = [r[2] for r in staff_list if r[0]==selected_emp][0]
                pay, days, report = calculate_payroll(selected_emp, p_month, p_year, base_salary)
                
                st.markdown(f"""
                <div class='metric-card'>
                    <h2>₹ {pay:,.0f}</h2>
                    <p>Total Payable for {days} Days</p>
                </div>
                """, unsafe_allow_html=True)
                
                if report:
                    df_rep = pd.DataFrame(report, columns=['Date', 'Day', 'Status', 'Credit'])
                    st.dataframe(df_rep, use_container_width=True)
        else:
            st.info("Add staff first to calculate payroll.")

# Fallback
else:
    st.session_state.nav = 'Home'
    st.rerun()
