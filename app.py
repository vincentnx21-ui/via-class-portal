import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, date, timedelta
import firebase_admin
from firebase_admin import credentials, db
import copy

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="VIA Portal 2026", layout="wide")

# =========================
# CLEAN UI THEME
# =========================
st.markdown("""
<style>
.stApp {
    background: #0b1220;
    color: #e5e7eb;
}

.block-container {
    padding-top: 2rem;
}

[data-testid="stMetric"] {
    background: #111827;
    padding: 14px;
    border-radius: 12px;
    border: 1px solid #1f2937;
}

.stButton>button {
    background: #0ea5e9;
    color: white;
    border-radius: 10px;
    border: none;
    font-weight: 600;
}

.stButton>button:hover {
    background: #38bdf8;
}
</style>
""", unsafe_allow_html=True)

# =========================
# FIREBASE INIT
# =========================
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
        else:
            cred = credentials.Certificate("serviceAccountKey.json")

        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://via-report-default-rtdb.asia-southeast1.firebasedatabase.app/'
        })
    except Exception as e:
        st.error(f"Firebase error: {e}")
        st.stop()

# =========================
# SESSION STATE
# =========================
if "data" not in st.session_state:
    st.session_state.data = {
        "members": [],
        "accounts": [],
        "logs": [],
        "contributions": {},
        "events": [],
        "attendance": {},
        "system_logs": []
    }

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "page" not in st.session_state:
    st.session_state.page = "dashboard"

# =========================
# HELPERS
# =========================
def normalize_date(d):
    if isinstance(d, str):
        return datetime.fromisoformat(d).date()
    if isinstance(d, datetime):
        return d.date()
    return d

def save_data():
    ref = db.reference("via_master_record")
    ref.set(st.session_state.data)

def log_system(action):
    st.session_state.data["system_logs"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action": action
    })

# =========================
# LOGIN
# =========================
USER_PASSWORDS = {
    "Teacher": "teach2026",
    "VIA Committee": "comm2026",
    "Skit Representative": "skit2026",
    "Brochure Representative": "brochure2026",
    "VIA members": "member2026",
    "Classmates": "class2026"
}

if not st.session_state.authenticated:
    st.title("🚀 VIA Portal Login")

    with st.form("login"):
        name = st.text_input("Name")
        role = st.selectbox("Role", list(USER_PASSWORDS.keys()))
        pw = st.text_input("Password", type="password")

        if st.form_submit_button("Login"):
            if USER_PASSWORDS.get(role) == pw:
                st.session_state.authenticated = True
                st.session_state.u_name = name
                st.session_state.u_role = role
                st.rerun()
            else:
                st.error("Wrong credentials")

    st.stop()

# =========================
# SIDEBAR (CLEAN)
# =========================
with st.sidebar:
    st.markdown(f"""
    <div style="
        background:#111827;
        padding:14px;
        border-radius:12px;
        margin-bottom:10px;
    ">
        <h4>{st.session_state.u_name}</h4>
        <p style="color:#94a3b8;">{st.session_state.u_role}</p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🏠 Dashboard"):
        st.session_state.page = "dashboard"
    if st.button("📅 Events"):
        st.session_state.page = "events"
    if st.button("📊 Progress"):
        st.session_state.page = "progress"
    if st.button("📁 Directory"):
        st.session_state.page = "directory"

    st.markdown("---")

    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.rerun()

# =========================
# CALENDAR (SAFE VERSION)
# =========================
def render_calendar(events):
    today = date.today()
    cal = calendar.monthcalendar(today.year, today.month)

    st.subheader("📅 Calendar")

    for week in cal:
        cols = st.columns(7)

        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                has_event = any(
                    normalize_date(e["date"]).day == day
                    for e in events
                )

                if has_event:
                    cols[i].button(f"🔵 {day}", key=f"cal_{day}")
                elif day == today.day:
                    cols[i].button(f"🟡 {day}", key=f"today_{day}")
                else:
                    cols[i].write(day)

# =========================
# DASHBOARD
# =========================
def dashboard():
    st.title("📊 Dashboard")

    c1, c2, c3 = st.columns(3)
    c1.metric("Events", len(st.session_state.data["events"]))
    c2.metric("Logs", len(st.session_state.data["logs"]))
    c3.metric("Members", len(st.session_state.data["members"]))

    render_calendar(st.session_state.data["events"])

    st.subheader("Recent Events")

    for e in st.session_state.data["events"]:
        st.markdown(f"""
        <div style="
            background:#111827;
            padding:12px;
            border-radius:10px;
            margin-bottom:8px;
        ">
            <b>{e['type']}</b><br>
            <span style="color:#94a3b8;">{e['date']}</span>
        </div>
        """, unsafe_allow_html=True)

# =========================
# EVENTS PAGE
# =========================
def events_page():
    st.title("📅 Events")

    with st.form("add_event"):
        t = st.text_input("Event Type")
        d = st.date_input("Date")

        if st.form_submit_button("Add Event"):
            st.session_state.data["events"].append({
                "type": t,
                "date": d
            })
            save_data()
            st.rerun()

# =========================
# PROGRESS
# =========================
def progress_page():
    st.title("📊 Progress")

    st.metric("Total Contributions", len(st.session_state.data["contributions"]))

# =========================
# DIRECTORY
# =========================
def directory_page():
    st.title("📁 Directory")

    for m in st.session_state.data["members"]:
        st.write(f"👤 {m.get('name', 'Unknown')}")

# =========================
# ROUTER
# =========================
if st.session_state.page == "dashboard":
    dashboard()

elif st.session_state.page == "events":
    events_page()

elif st.session_state.page == "progress":
    progress_page()

elif st.session_state.page == "directory":
    directory_page()
