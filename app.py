import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta, date
import mysql.connector
from io import BytesIO
import os
import random
import requests
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# --- 1. CONFIGURATION & PAGE SETUP ---
if os.path.exists("logo.png"):
    st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="logo.png")
else:
    st.set_page_config(page_title="National Air Condition", layout="wide", page_icon="❄️")

ADMIN_MOBILE = "9978815870" 

# --- 2. CSS STYLING (UPDATED DROPDOWNS) ---
def apply_styling():
    st.markdown("""
        <style>
        /* --- HIDE STREAMLIT UI --- */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        [data-testid="stToolbar"] {visibility: hidden;} 
        .stDeployButton {display:none;}
        
        /* Main Background - Teal */
        .stApp { background-color: #4ba3a8; margin-top: -50px; }
        
        /* General Text Colors */
        h1, h2, h3, h4, h5, h6, p, span, div, label, li { color: white !important; }
        
        /* --- INPUT BOXES --- */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTimeInput input, .stPasswordInput input {
            background-color: #ffffff !important; 
            color: #000000 !important; 
            border-radius: 5px; 
            border: 1px solid #ddd;
        }
        
        /* --- DROPDOWN (SELECTBOX) STYLING --- */
        /* The main box (closed) */
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #000000 !important;
            border-color: #ddd !important;
            border-radius: 5px;
        }
        /* The text inside the box */
        div[data-baseweb="select"] span {
            color: #000000 !important;
        }
        /* The arrow icon */
        div[data-baseweb="select"] svg {
            fill: #000000 !important;
        }
        /* The popup list (open) */
        ul[data-baseweb="menu"] {
            background-color: #ffffff !important;
        }
        /* The options in the list */
        li[data-baseweb="option"] {
            color: #000000 !important;
        }
        
        /* --- CARDS --- */
        .login-card {
            background-color: white; padding: 30px; border-radius: 10px; text-align: center;
            box-shadow: 0 4px
