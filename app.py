import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
from io import BytesIO
import os
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# --- 1. CSS STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        .stApp { background-color: #4ba3a8; }
        h1, h2, h3, h4, h5, h6, p, span, div, label, li { color: white !important; }
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTimeInput input, .stPasswordInput input {
            background-color: #ffffff !important; color: #000000 !important; border-radius: 5px; border: 1px solid #ddd;
        }
        div[data-baseweb="input"] { background-color: #ffffff !important; }
        div[data-baseweb="select"] > div { background-color: #ffffff !important; color: black !important; }
        .login-card {
            background-color: white; padding: 30px; border-radius: 10px; text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin: auto; border-top: 5px solid #2c3e50;
        }
        .login-card h2, .login-card p { color: #2c3e50 !important; }
        .tech-card {
            background-color: white; padding: 20px; border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); text-align: center; border-top: 8px solid #2c3e50; margin-bottom: 20px;
        }
        .tech-card h3, .tech-card p { color: #2c3e50 !important; }
        section[data-testid="stSidebar"] { background-color: #388e93; }
        .stButton>button {
            width: 100%; height: 3.5em; border-radius: 8px; font-weight: bold;
            background-color: white !important; color: #4ba3a8 !important; border: none;
        }
        .delete-btn > button { background-color: #e74c3c !important; color: white !important; }
        </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE CONNECTION ---
def get_connection():
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        return mysql.connector.connect(
            host=creds["DB_HOST"], user=creds["DB_USER"], password=creds["DB_PASSWORD"],
            port=creds["DB_PORT"], database=creds["DB_NAME"], ssl_disabled=False
        )
    else:
        st.error("⚠ Database Secrets Missing in Streamlit Cloud!")
        st.stop()

# --- 3. FUNCTIONS ---
def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        return loc.address if loc else "Unknown Location"
    except: return "Location Error"

def add_employee(name, designation, salary, pin):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)", 
                  (name, designation, salary, pin, b''))
        conn.commit(); conn.close()
        return True, "Success"
    except Exception as e: return False, str(e)

def delete_employee(emp_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM attendance WHERE emp_id=%s", (emp_id,))
        c.execute("DELETE FROM employees WHERE id=%s", (emp_id,))
        conn.commit(); conn.close()
        return True
    except: return False

def mark_attendance(emp_id, work_date, time_in_obj, photo, lat, lon, addr):
    conn = get_connection()
    c = conn.cursor()
    status = "Half Day" if time_in_obj > time(10, 30) else "Present"
    try:
        c.execute("SELECT * FROM attendance WHERE emp_id=%s AND date=%s", (emp_id, work_date))
        if c.fetchone():
            st.error("⚠ Already Punched In Today!")
        else:
            c.execute("""INSERT INTO attendance (emp_id, date, time_in, status, punch_photo, latitude, longitude, address) 
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", 
                      (emp_id, work_date, time_in_obj.strftime("%H:%M"), status, photo, lat, lon, addr))
            conn.commit()
            if status == "Present": st.balloons(); st.success(f"✅ Success! Location: {addr}")
            else: st.warning(f"⚠ Late Entry (Half Day) marked at {addr}")
    except Exception as e: st.error(f"Error: {e}")
    finally: conn.close()

def calculate_salary(emp_id, month, year, base_salary):
    start_date = date(year, month-1, 5) if month > 1 else date(year-1, 12, 5)
    end_date = date(year, month, 4)
    conn = get_connection()
    df = pd.read_sql(f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{start_date}' AND '{end_date}'", conn)
    conn.close()
    
    df['date'] = df['date'].astype(str)
    att_map = dict(zip(df['date'], df['status']))
    
    payable_days = 0.0
    report = []
    curr = start_date
    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        status = att_map.get(d_str, "Absent")
        pay = 0.0; note = ""
        
        if curr.strftime("%A") == 'Sunday':
            prev = (curr - timedelta(days=1)).strftime("%Y-%m-%d")
            next_d = (curr + timedelta(days=1)).strftime("%Y-%m-%d")
            if att_map.get(prev,"Absent") == "Absent" and att_map.get(next_d,"Absent") == "Absent":
                pay = 0.0; note = "Sandwich Cut"
            else: pay = 1.0; note = "Paid Wknd"
        else:
            if status == "Present": pay = 1.0
            elif status == "Half Day": pay = 0.5; note = "Late"
            else: pay = 0.0; note = "Absent"
            
        payable_days += pay
        report.append([d_str, curr.strftime("%A"), status, pay, note])
        curr += timedelta(days=1)
        
    return payable_days * (base_salary/30), payable_days, report

# --- APP START ---
if os.path.exists("logo.png"): st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="logo.png")
else: st.set_page_config(page_title="National Air Condition", layout="wide")

apply_styling()

if os.path.exists("logo.png"): st.sidebar.image("logo.png", width=200)
st.sidebar.title("Attendance")
role = st.sidebar.radio("Mode", ["Technician", "Admin"])

# --- TECHNICIAN VIEW ---
if role == "Technician":
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<h2 style='text-align:center;'>Daily Check-In</h2>", unsafe_allow_html=True)
        
        # GPS
        loc = get_geolocation()
        lat, lon = (loc['coords']['latitude'], loc['coords']['longitude']) if loc else (None, None)
        if lat: st.success("📍 Location Found")
        else: st.warning("⏳ Getting Location... Allow Permission")

        try:
            conn = get_connection(); c = conn.cursor()
            c.execute("SELECT id, name, designation FROM employees")
            rows = c.fetchall(); conn.close()
            
            if rows:
                df = pd.DataFrame(rows, columns=['id', 'name', 'desig'])
                emp_id = st.selectbox("Select Name", df['id'].tolist(), format_func=lambda x: df[df['id']==x]['name'].values[0])
                details = df[df['id']==emp_id].iloc[0]
                
                st.markdown(f"<div class='tech-card'><h3>{details['name']}</h3><p>{details['desig']}</p></div>", unsafe_allow_html=True)
                
                photo = st.camera_input("Take Selfie")
                if photo and lat:
                    if st.button("PUNCH IN"):
                        addr = get_address(lat, lon)
                        mark_attendance(emp_id, date.today(), datetime.now().time(), photo.getvalue(), str(lat), str(lon), addr)
            else: st.info("No Staff Found.")
        except Exception as e: st.error(f"Connection Error: {e}")

# --- ADMIN VIEW ---
elif role == "Admin":
    if 'auth' not in st.session_state: st.session_state.auth = False
    
    if not st.session_state.auth:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown("<br><div class='login-card'><h2>Admin Login</h2></div>", unsafe_allow_html=True)
            if st.text_input("Password", type="password") == "admin":
                st.session_state.auth = True; st.rerun()
    else:
        if st.button("Logout"): st.session_state.auth = False; st.rerun()
        t1, t2, t3, t4 = st.tabs(["📊 Live Status", "💰 Payroll", "➕ Add Staff", "❌ Remove Staff"])
        
        with t1:
            try:
                conn = get_connection()
                # Join to show names with attendance
                df = pd.read_sql(f"SELECT e.name, a.time_in, a.status, a.address, a.latitude, a.longitude FROM attendance a JOIN employees e ON a.emp_id=e.id WHERE a.date='{date.today()}'", conn)
                conn.close()
                if not df.empty:
                    for i, row in df.iterrows():
                        st.markdown(f"""
                        <div style="background:white; padding:15px; margin-bottom:10px; border-radius:10px;">
                            <b style="color:black; font-size:18px;">{row['name']}</b><br>
                            <span style="color:black">Time: {row['time_in']} | Status: {row['status']}</span><br>
                            <a href="https://maps.google.com/?q={row['latitude']},{row['longitude']}" target="_blank" style="color:blue; text-decoration:none;">📍 {row['address']}</a>
                        </div>
                        """, unsafe_allow_html=True)
                else: st.info("No attendance today.")
            except: st.error("Database Error")
            
        with t2:
            try:
                conn = get_connection(); c = conn.cursor()
                c.execute("SELECT id, name, salary FROM employees"); rows = c.fetchall(); conn.close()
                if rows:
                    df = pd.DataFrame(rows, columns=['id', 'name', 'salary'])
                    sid = st.selectbox("Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                    month = st.number_input("Month", 1, 12, datetime.now().month)
                    if st.button("Calculate"):
                        sal, days, data = calculate_salary(sid, month, datetime.now().year, df[df['id']==sid]['salary'].values[0])
                        st.success(f"Salary: ₹{sal:,.0f} ({days} days)")
                        out = BytesIO()
                        with pd.ExcelWriter(out, engine='openpyxl') as w: pd.DataFrame(data, columns=['Date','Day','Status','Credit','Note']).to_excel(w, index=False)
                        st.download_button("Download Slip", out.getvalue(), "slip.xlsx")
            except: st.error("Calc Error")
            
        with t3:
            with st.form("add"):
                n = st.text_input("Name"); d = st.text_input("Designation"); s = st.number_input("Salary", value=20000); p = st.text_input("PIN", max_chars=4)
                if st.form_submit_button("Save"):
                    if n and d and p: 
                        add_employee(n, d, s, p); st.success("Added!")
                    else: st.error("Fill all fields")
                    
        with t4:
            try:
                conn = get_connection(); c = conn.cursor()
                c.execute("SELECT id, name FROM employees"); rows = c.fetchall(); conn.close()
                if rows:
                    df = pd.DataFrame(rows, columns=['id', 'name'])
                    did = st.selectbox("Delete Staff", df['id'], format_func=lambda x: df[df['id']==x]['name'].values[0])
                    if st.button("DELETE PERMANENTLY"):
                        delete_employee(did); st.success("Deleted"); st.rerun()
            except: pass

st.markdown("<div class='footer'>© National Air Condition</div>", unsafe_allow_html=True)
