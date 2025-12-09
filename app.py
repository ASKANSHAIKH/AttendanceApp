import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
from io import BytesIO
import os

# --- 1. CSS STYLING ---
def apply_styling():
    st.markdown("""
        <style>
        /* Main Background - Teal */
        .stApp { background-color: #4ba3a8; }
        
        /* Text Colors */
        h1, h2, h3, h4, h5, h6, p, span, label, li, div { color: white !important; }
        
        /* INPUT BOXES - Force White Background & Black Text */
        .stTextInput input, .stNumberInput input, .stPasswordInput input {
            background-color: #ffffff !important; 
            color: #000000 !important; 
            border: 1px solid #ddd;
        }
        
        /* Admin Login Card Style */
        .login-card {
            background-color: white; 
            padding: 30px; 
            border-radius: 10px; 
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            margin: auto;
            border-top: 5px solid #2c3e50;
        }
        .login-card h2, .login-card p { color: #2c3e50 !important; }

        /* Sidebar */
        section[data-testid="stSidebar"] { background-color: #388e93; }
        
        /* Buttons */
        .stButton>button {
            width: 100%; height: 3.5em; border-radius: 8px; font-weight: bold;
            background-color: white !important; color: #4ba3a8 !important; border: none;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE CONNECTION ---
def get_connection():
    # Load secrets from Streamlit Cloud
    if "connections" in st.secrets and "tidb" in st.secrets["connections"]:
        creds = st.secrets["connections"]["tidb"]
        return mysql.connector.connect(
            host=creds["DB_HOST"],
            user=creds["DB_USER"],
            password=creds["DB_PASSWORD"],
            port=creds["DB_PORT"],
            database=creds["DB_NAME"],
            ssl_disabled=False
        )
    else:
        st.error("⚠ Secrets missing! Please check Streamlit Settings.")
        st.stop()

# --- 3. FUNCTIONS ---
def init_db():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS employees 
                     (id INT AUTO_INCREMENT PRIMARY KEY, 
                      name VARCHAR(255), designation VARCHAR(255), 
                      salary DOUBLE, pin VARCHAR(10), photo LONGBLOB)''')
        c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (id INT AUTO_INCREMENT PRIMARY KEY, 
                      emp_id INT, date DATE, time_in VARCHAR(20), 
                      status VARCHAR(50),
                      UNIQUE KEY unique_att (emp_id, date))''')
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"DB Init Error: {e}")

def add_employee(name, designation, salary, pin, photo_bytes):
    try:
        conn = get_connection()
        c = conn.cursor()
        sql = "INSERT INTO employees (name, designation, salary, pin, photo) VALUES (%s, %s, %s, %s, %s)"
        c.execute(sql, (name, designation, salary, pin, photo_bytes))
        conn.commit()
        conn.close()
        return True, "Success"
    except Exception as e:
        return False, str(e)

def get_employee_details(emp_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT photo, pin FROM employees WHERE id=%s", (emp_id,))
        data = c.fetchone()
        conn.close()
        return data if data else (None, None)
    except:
        return (None, None)

def mark_attendance(emp_id, work_date, time_in_obj):
    conn = get_connection()
    c = conn.cursor()
    cutoff = time(10, 30)
    status = "Half Day" if time_in_obj > cutoff else "Present"
    try:
        c.execute("SELECT * FROM attendance WHERE emp_id=%s AND date=%s", (emp_id, work_date))
        if c.fetchone():
            st.error("⚠ Attendance already marked for today.")
        else:
            sql = "INSERT INTO attendance (emp_id, date, time_in, status) VALUES (%s, %s, %s, %s)"
            c.execute(sql, (emp_id, work_date, time_in_obj.strftime("%H:%M"), status))
            conn.commit()
            if status == "Present":
                st.balloons()
                st.success(f"✅ MARKED PRESENT")
            else:
                st.warning(f"⚠ LATE ENTRY (HALF DAY)")
    except Exception as e:
        st.error(f"Error: {e}")
    finally:
        conn.close()

def calculate_salary_logic(emp_id, pay_month, pay_year, base_salary):
    if pay_month == 1:
        start_date = date(pay_year - 1, 12, 5)
        end_date = date(pay_year, pay_month, 4)
    else:
        start_date = date(pay_year, pay_month - 1, 5)
        end_date = date(pay_year, pay_month, 4)
    
    payable_days = 0.0
    report_data = []
    
    query_start = (start_date - timedelta(days=2)).strftime("%Y-%m-%d")
    query_end = (end_date + timedelta(days=2)).strftime("%Y-%m-%d")
    
    conn = get_connection()
    sql = f"SELECT date, status FROM attendance WHERE emp_id={emp_id} AND date BETWEEN '{query_start}' AND '{query_end}'"
    df = pd.read_sql(sql, conn)
    conn.close()
    
    df['date'] = df['date'].astype(str)
    att_map = dict(zip(df['date'], df['status']))

    current_date = start_date
    while current_date <= end_date:
        d_str = current_date.strftime("%Y-%m-%d")
        d_name = current_date.strftime("%A")
        status = att_map.get(d_str, "Absent")
        pay = 0.0; note = ""
        if d_name == 'Sunday':
            prev = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
            next_d = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
            if att_map.get(prev, "Absent") == "Absent" and att_map.get(next_d, "Absent") == "Absent":
                pay = 0.0; note = "Sandwich Cut"
            else:
                pay = 1.0; note = "Paid Wknd"
        else:
            if status == "Present": pay = 1.0
            elif status == "Half Day": pay = 0.5; note = "Late"
            else: pay = 0.0; note = "Absent"
        payable_days += pay
        report_data.append([d_str, d_name, status, pay, note])
        current_date += timedelta(days=1)

    daily_rate = base_salary / 30 
    total_salary = payable_days * daily_rate
    return total_salary, payable_days, report_data, start_date, end_date

# --- UI SETUP ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="logo.png")
else:
    st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="❄")

apply_styling()

# Check Database Secrets
if "connections" in st.secrets:
    init_db()
else:
    st.error("⚠ DB Secrets missing!")
    st.stop()

# --- SIDEBAR ---
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", width=200)

st.sidebar.markdown("## Navigation")
role = st.sidebar.radio("Go To", ["Technician / Staff", "Admin / Manager"])

# ================================
# 1. TECHNICIAN PAGE
# ================================
if role == "Technician / Staff":
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
            
        st.markdown("<h2 style='text-align:center;'>Daily Check-In</h2>", unsafe_allow_html=True)
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT id, name, designation FROM employees")
            rows = c.fetchall()
            conn.close()
            
            if rows:
                emp_df = pd.DataFrame(rows, columns=['id', 'name', 'designation'])
                emp_id = st.selectbox("Select Your Name", emp_df['id'].tolist(), format_func=lambda x: emp_df[emp_df['id']==x]['name'].values[0])
                photo, real_pin = get_employee_details(emp_id)
                details = emp_df[emp_df['id']==emp_id].iloc[0]
                
                # Show Tech Card
                st.markdown(f"""
                <div style="background-color:white; padding:20px; border-radius:15px; text-align:center; border-top:5px solid #2c3e50;">
                    <h3 style="color:#2c3e50 !important;">{details['name']}</h3>
                    <p style="color:#2c3e50 !important;">{details['
