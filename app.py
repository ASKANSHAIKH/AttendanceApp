import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date, timezone
import pymysql
import ssl
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="National Air Condition Portal", layout="wide", page_icon="🔧")

# --- 2. DATABASE ENGINE (SELF-HEALING) ---
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
        except Exception: return None
    return None

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    if not conn: return "Connection Failed"
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch: return cursor.fetchall()
            return True
    except pymysql.err.ProgrammingError as e:
        # ERROR 1146: Table doesn't exist -> AUTO FIX
        if e.args[0] == 1146:
            with conn.cursor() as cursor:
                cursor.execute('''CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), designation VARCHAR(255), salary DOUBLE, pin VARCHAR(10))''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, emp_id INT, date DATE, time_in VARCHAR(20), status VARCHAR(50), latitude VARCHAR(50), longitude VARCHAR(50), address TEXT, UNIQUE KEY unique_att (emp_id, date))''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS admin_config (id INT PRIMARY KEY, password VARCHAR(255))''')
                cursor.execute("INSERT IGNORE INTO admin_config (id, password) VALUES (1, 'admin')")
            conn.commit()
            return [] # Return empty list so app doesn't crash
        return str(e)
    except Exception as e: return str(e)
    finally: conn.close()

# --- 3. UTILS ---
def get_ist_time(): return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)

def get_address(lat, lon):
    try:
        geolocator = Nominatim(user_agent="national_air_app")
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=5)
        return loc.address.split(",")[0] if loc else "Loc Unavailable"
    except: return "Loc Unavailable"

# --- MAIN APP ---
if 'nav' not in st.session_state: st.session_state.nav = 'Technician'

# --- STYLE OVERRIDE ---
st.markdown("""<style>.stApp { background-color: white; } h1,h2,p,div,span { color: black !important; }</style>""", unsafe_allow_html=True)

# --- NAVIGATION ---
st.title("National Air Condition Portal")
col1, col2 = st.columns(2)
if col1.button("Technician Zone"): st.session_state.nav = 'Technician'
if col2.button("Admin Zone"): st.session_state.nav = 'Admin'
st.markdown("---")

# ==========================================
# TECHNICIAN ZONE
# ==========================================
if st.session_state.nav == 'Technician':
    st.header("Technician Punch-In")
    
    rows = run_query("SELECT id, name FROM employees")
    
    # SAFE CHECK: Ensure rows is a list before using it
    if isinstance(rows, str): 
        st.info("⚠️ Initializing Database... Refresh the page.")
        rows = [] 
        
    options = rows if isinstance(rows, list) else []
    
    if options:
        emp_id = st.selectbox("Select Your Name", [r[0] for r in options], format_func=lambda x: [r[1] for r in options if r[0]==x][0])
        pin_in = st.text_input("Enter PIN", type="password")
        loc = get_geolocation()
        
        if loc and 'coords' in loc:
            st.success("✅ GPS Active")
            if st.button("PUNCH IN"):
                res = run_query(f"SELECT pin FROM employees WHERE id={emp_id}")
                if res and pin_in == res[0][0]:
                    ist = get_ist_time()
                    lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
                    run_query("INSERT INTO attendance (emp_id, date, time_in, status, latitude, longitude, address) VALUES (%s, %s, %s, %s, %s, %s, %s)", (emp_id, ist.date(), ist.time().strftime("%H:%M"), "Present", str(lat), str(lon), get_address(lat, lon)), fetch=False)
                    st.balloons(); st.success("Marked Present!")
                else: st.error("Wrong PIN")
        else: st.warning("Waiting for GPS...")
    else:
        st.warning("Staff list is empty.")
        with st.expander("➕ Emergency Add Staff"):
            n = st.text_input("Name")
            p = st.text_input("PIN")
            if st.button("Add Staff Now"):
                run_query("INSERT INTO employees (name, designation, salary, pin) VALUES (%s, 'Tech', 15000, %s)", (n, p), fetch=False)
                st.success("Added! Refreshing..."); st.rerun()

# ==========================================
# ADMIN ZONE
# ==========================================
elif st.session_state.nav == 'Admin':
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Login") or st.session_state.get('auth'):
        if pwd == "admin" or st.session_state.get('auth'):
            st.session_state.auth = True
            st.success("Logged In")
            
            st.subheader("Raw Database View")
            data = run_query("SELECT * FROM employees")
            
            if isinstance(data, list):
                if data:
                    df = pd.DataFrame(data, columns=['ID', 'Name', 'Role', 'Salary', 'PIN'])
                    st.dataframe(df)
                else: st.write("Table exists but is empty.")
            else: st.error(f"Error: {data}")

            if st.button("🔴 RESET EVERYTHING"):
                run_query("DROP TABLE IF EXISTS employees", fetch=False)
                run_query("DROP TABLE IF EXISTS attendance", fetch=False)
                st.warning("Reset Done. Refresh Page.")
