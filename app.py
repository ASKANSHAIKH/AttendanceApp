import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
import os
import random
import requests
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# --- 1. APP CONFIGURATION ---
page_icon = "logo.png" if os.path.exists("logo.png") else "❄️"
st.set_page_config(page_title="National Air Condition", layout="wide", page_icon=page_icon)

ADMIN_MOBILE = "9978815870"

# --- 2. PROFESSIONAL STYLING (Corporate Teal Theme) ---
def apply_professional_styling():
    st.markdown("""
        <style>
        /* HIDE STREAMLIT DEFAULT UI */
        #MainMenu, footer, header, [data-testid="stToolbar"] {visibility: hidden;}
        .stDeployButton {display:none;}
        
        /* APP BACKGROUND & FONT */
        .stApp { background-color: #f0f2f6; } /* Light Grey Professional BG */
        
        /* CUSTOM SIDEBAR */
        section[data-testid="stSidebar"] {
            background-color: #0e3b43; /* Dark Teal for Sidebar */
        }
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {
            color: white !important;
        }
        
        /* HEADERS */
        h1, h2, h3 { color: #0e3b43 !important; font-family: 'Helvetica', sans-serif; font-weight: 700; }
        
        /* INPUT FIELDS - CLEAN LOOK */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stPasswordInput input {
            border: 1px solid #ccc; border-radius: 8px; padding: 10px;
        }
        
        /* BUTTONS - GRADIENT TEAL */
        .stButton>button {
            width: 100%; height: 45px; border-radius: 8px; font-weight: 600;
            background: linear-gradient(90deg, #4ba3a8 0%, #2c7a7f 100%);
            color: white !important; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            transform: translateY(-2px); box-shadow: 0 6px 8px rgba(0,0,0,0.15);
        }
        
        /* CARDS FOR DASHBOARD */
        .dashboard-card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-left: 5px solid #4ba3a8;
            margin-bottom: 15px;
        }
        
        /* ATTENDANCE LIST CARD */
        .att-card {
            background: white; padding: 15px; border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px;
            border: 1px solid #eee; display: flex; align-items: center;
        }
        
        /* FOOTER */
        .footer {
            position: fixed; bottom: 0; left: 0; width: 100%;
            background: white; text-align: center; padding: 10px;
            color: #666; font-size: 12px; border-top: 1px solid #eee;
        }
        </style>
    """, unsafe_allow_html=True)

apply_professional_styling()

# --- 3. HIGH-PERFORMANCE DATABASE ENGINE (CACHED) ---
@st.cache_resource(ttl=3600)  # Keeps connection alive for 1 hour
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
            st.cache_resource.clear() # Reset cache if dropped
            conn = get_db_connection()
            
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        
        if fetch:
            result = cursor.fetchall()
            return result
        else:
            conn.commit()
            return True
    except Exception as e:
        return str(e)

# --- 4. UTILITY FUNCTIONS ---
def get_ist_time():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def get_address_from_coords(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return location.address.split(",")[0] + ", " + location.address.split(",")[-4] if location else "Unknown Location"
    except:
        return "Location unavailable"

def send_sms(mobile, otp, reason):
    try:
        if "SMS_API_KEY" not in st.secrets: return False
        url = "https://www.fast2sms.com/dev/bulkV2"
        msg = f"National Air Condition.\nOTP for {reason}: {otp}"
        payload = {"route": "q", "message": msg, "language": "english", "flash": 0, "numbers": mobile}
        headers = {'authorization': st.secrets["SMS_API_KEY"], 'Content-Type': "application/x-www-form-urlencoded"}
        requests.request("POST", url, data=payload, headers=headers)
        return True
    except: return False

# --- 5. INITIALIZATION ---
def init_app():
    # Create tables if not exist (Only runs once)
    run_query('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10), photo LONGBLOB)''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), punch_photo LONGBLOB, latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''', fetch=False)
    run_query('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''', fetch=False)
    run_query("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')", fetch=False)

init_app()

# --- 6. NAVIGATION & SIDEBAR ---
if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.title("MENU")

if 'nav' not in st.session_state: st.session_state.nav = 'Technician'

# Custom Navigation Buttons in Sidebar
if st.sidebar.button("👨‍🔧 Technician Zone"): st.session_state.nav = 'Technician'
if st.sidebar.button("👮 Admin Panel"): st.session_state.nav = 'Admin'

# --- 7. TECHNICIAN ZONE ---
if st.session_state.nav == 'Technician':
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown(f"<h3 style='text-align:center; color:#4ba3a8;'>Daily Attendance</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; color:grey;'>{get_ist_time().strftime('%d %b %Y | %I:%M %p')}</p>", unsafe_allow_html=True)
        
        # GPS
        loc = get_geolocation()
        lat = loc['coords']['latitude'] if loc else None
        lon = loc['coords']['longitude'] if loc else None
        
        if lat: st.success("📍 GPS Active")
        else: st.warning("waiting for location...")

        # Load Staff Cache
        rows = run_query("SELECT id, name, designation FROM employees")
        if rows:
            df = pd.DataFrame(rows, columns=['id', 'name', 'desig'])
            emp_id = st.selectbox("Select Your Name", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
            
            # Show Staff Card
            person = df[df['id']==emp_id].iloc[0]
            st.markdown(f"""
            <div class='dashboard-card' style='text-align:center;'>
                <h2 style='margin:0;'>{person['name']}</h2>
                <p style='color:grey; margin:0;'>{person['desig']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            tab1, tab2 = st.tabs(["📸 Punch In", "🔑 Reset PIN"])
            
            with tab1:
                photo = st.camera_input("Selfie")
                pin = st.text_input("Enter PIN", type="password", max_chars=4)
                
                if st.button("PUNCH IN"):
                    if not lat or not photo:
                        st.error("Location and Photo required!")
                    else:
                        real_pin = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")[0][0]
                        if pin == real_pin:
                            addr = get_address_from_coords(lat, lon)
                            ist = get_ist_time()
                            status = "Half Day" if ist.time() > time(10,30) else "Present"
                            
                            res = run_query("INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
                                      (emp_id, ist.date(), ist.time().strftime("%H:%M"), status, photo.getvalue(), str(lat), str(lon), addr), fetch=False)
                            
                            if res == True: st.balloons(); st.success("Attendance Marked Successfully!")
                            else: st.error("Already marked today!")
                        else:
                            st.error("Wrong PIN!")

            with tab2:
                if st.button("Send Reset OTP"):
                    otp = random.randint(1000, 9999); st.session_state.otp = otp
                    send_sms(ADMIN_MOBILE, otp, "PIN Reset")
                    st.info("OTP Sent to Admin.")
                
                if 'otp' in st.session_state:
                    u_otp = st.text_input("OTP"); n_pin = st.text_input("New PIN", max_chars=4)
                    if st.button("Update PIN"):
                        if str(u_otp) == str(st.session_state.otp):
                            run_query(f"UPDATE employees SET pin='{n_pin}' WHERE id={emp_id}", fetch=False)
                            st.success("PIN Updated!")
                        else: st.error("Invalid OTP")

# --- 8. ADMIN PANEL ---
elif st.session_state.nav == 'Admin':
    if 'auth' not in st.session_state: st.session_state.auth = False
    
    if not st.session_state.auth:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("<br><div class='dashboard-card'><h3 style='text-align:center'>Admin Login</h3></div>", unsafe_allow_html=True)
            pwd = st.text_input("Password", type="password")
            if st.button("Login"):
                real_pass = run_query("SELECT password FROM admin_config WHERE id=1")[0][0]
                if pwd == real_pass: st.session_state.auth = True; st.rerun()
                else: st.error("Access Denied")
    else:
        st.title("Admin Dashboard")
        if st.sidebar.button("Logout"): st.session_state.auth = False; st.rerun()
        
        menu = st.tabs(["Live Status", "Payroll", "Staff Mgmt", "Settings"])
        
        # LIVE STATUS
        with menu[0]:
            dt = get_ist_time().date()
            data = run_query(f"SELECT e.name, a.time_in, a.status, a.address, a.punch_photo FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{dt}'")
            
            col1, col2 = st.columns(2)
            col1.metric("Date", str(dt))
            col2.metric("Present Today", len(data) if data else 0)
            
            if data:
                for row in data:
                    with st.container():
                        c1, c2 = st.columns([1, 4])
                        with c1: st.image(row[4], width=80)
                        with c2:
                            st.markdown(f"**{row[0]}**")
                            st.caption(f"🕒 {row[1]} | 📍 {row[3]}")
                            if row[2] == 'Present': st.success("Present")
                            else: st.warning("Half Day")
                        st.markdown("---")
            else: st.info("No attendance yet.")

        # PAYROLL
        with menu[1]:
            st.subheader("Salary Calculator")
            emp_data = run_query("SELECT id, name, salary FROM employees")
            if emp_data:
                df = pd.DataFrame(emp_data, columns=['id', 'name', 'salary'])
                s_emp = st.selectbox("Select Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                
                if st.button("Generate Slip"):
                    s_date = date(datetime.now().year, datetime.now().month-1, 5)
                    e_date = date(datetime.now().year, datetime.now().month, 5)
                    
                    att_data = run_query(f"SELECT date, status FROM attendance WHERE emp_id={s_emp} AND date BETWEEN '{s_date}' AND '{e_date}'")
                    
                    # Calculation Logic
                    days = 0; report = []
                    att_dict = {str(r[0]): r[1] for r in att_data}
                    
                    curr = s_date
                    while curr <= e_date:
                        status = att_dict.get(str(curr), "Absent")
                        credit = 1.0 if status == 'Present' else (0.5 if status == 'Half Day' else 0.0)
                        if curr.strftime("%A") == 'Sunday': credit = 1.0 # Paid Sunday
                        
                        days += credit
                        report.append([curr, curr.strftime("%A"), status, credit])
                        curr += timedelta(days=1)
                        
                    salary = (df[df['id']==s_emp]['salary'].values[0] / 30) * days
                    st.success(f"Payable Days: {days} | Net Salary: ₹{salary:,.0f}")
                    
                    # Excel
                    out = BytesIO()
                    pd.DataFrame(report, columns=['Date','Day','Status','Credit']).to_excel(out, index=False)
                    st.download_button("Download Excel", out.getvalue(), "salary.xlsx")

        # STAFF MGMT
        with menu[2]:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Add Staff")
                with st.form("add"):
                    n = st.text_input("Name"); d = st.text_input("Role"); s = st.number_input("Salary", step=500); p = st.text_input("PIN", max_chars=4)
                    if st.form_submit_button("Create"):
                        if run_query("INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)", (n,d,s,p,b''), fetch=False):
                            st.success("Added!")
            
            with c2:
                st.subheader("Remove Staff")
                del_id = st.selectbox("Select to Delete", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0], key='del')
                if st.button("DELETE USER"):
                    run_query(f"DELETE FROM attendance WHERE emp_id={del_id}", fetch=False)
                    run_query(f"DELETE FROM employees WHERE id={del_id}", fetch=False)
                    st.success("Deleted!")
                    st.rerun()

        # SETTINGS (Admin Password)
        with menu[3]:
            st.subheader("Change Admin Password")
            if st.button("Send OTP"):
                otp = random.randint(1000,9999); st.session_state.aotp = otp
                send_sms(ADMIN_MOBILE, otp, "Admin Reset")
            
            if 'aotp' in st.session_state:
                otp_in = st.text_input("OTP"); new_pass = st.text_input("New Password")
                if st.button("Update"):
                    if str(otp_in) == str(st.session_state.aotp):
                        run_query(f"UPDATE admin_config SET password='{new_pass}' WHERE id=1", fetch=False)
                        st.success("Updated!"); st.rerun()

# --- FOOTER ---
st.markdown("<div class='footer'>© National Air Condition | Developed by <b>Askan Shaikh</b></div>", unsafe_allow_html=True)
