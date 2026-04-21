import streamlit as st
import pandas as pd
from datetime import datetime, date, time as dt_time, timedelta
import firebase_admin
from firebase_admin import credentials, db
import copy
import calendar

# =============================
# CONFIG
# =============================
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide")

# =============================
# BASIC UI
# =============================
st.markdown("""
<style>
.stApp {
    background: #0f172a;
    color: #e2e8f0;
}

.stButton>button {
    background: #0ea5e9;
    color: white;
    border-radius: 10px;
    font-weight: 600;
}

div[data-testid="stContainer"] {
    background: #1e293b;
    padding: 14px;
    border-radius: 14px;
}

section[data-testid="stSidebar"] {
    background: #020617;
}
</style>
""", unsafe_allow_html=True)

# =============================
# FIREBASE
# =============================
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://via-report-default-rtdb.asia-southeast1.firebasedatabase.app/'
        })
    except Exception as e:
        st.error(e)
        st.stop()

# =============================
# DATA
# =============================
def load_data():
    try:
        ref = db.reference("via_master_record")
        data = ref.get()
        return data or {
            "members": [],
            "accounts": [],
            "logs": [],
            "contributions": {},
            "events": [],
            "rsvp": [],
            "attendance": {},
            "system_logs": []
        }
    except:
        return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}, "system_logs": []}

def save_data():
    ref = db.reference("via_master_record")
    ref.set(st.session_state.data)

# =============================
# SESSION INIT
# =============================
if "data" not in st.session_state:
    st.session_state.data = load_data()

if "auth" not in st.session_state:
    st.session_state.auth = False

if "role" not in st.session_state:
    st.session_state.role = ""

if "name" not in st.session_state:
    st.session_state.name = ""

# =============================
# AUTH SYSTEM (CHAIRMAN FIXED)
# =============================
PASSWORDS = {
    "Teacher": "teach2026",
    "VIA Committee": "chair2026",   # ADMIN (Chairman)
    "Skit Representative": "skit2026",
    "Brochure Representative": "brochure2026",
    "VIA members": "member2026",
    "Classmates": "class2026"
}

if not st.session_state.auth:
    st.title("🚀 VIA Portal Login")

    name = st.text_input("Name").strip().title()
    role = st.selectbox("Role", list(PASSWORDS.keys()))
    pw = st.text_input("Password", type="password")

    if st.button("Login"):
        if pw == PASSWORDS.get(role):
            st.session_state.auth = True
            st.session_state.role = role
            st.session_state.name = name
            st.rerun()
        else:
            st.error("Wrong credentials")

    st.stop()

# =============================
# ROLE FLAGS
# =============================
is_admin = st.session_state.role == "VIA Committee"
is_teacher = st.session_state.role == "Teacher"

# =============================
# SIDEBAR
# =============================
st.sidebar.title("🎛 VIA Panel")
st.sidebar.write(f"👤 {st.session_state.name}")
st.sidebar.write(f"Role: {st.session_state.role}")

project = st.sidebar.radio("Project", ["SKIT", "BROCHURE"])
view_proj = project

if st.sidebar.button("Save"):
    save_data()
    st.success("Saved!")

if st.sidebar.button("Logout"):
    st.session_state.auth = False
    st.rerun()

# =============================
# CALENDAR
# =============================
def render_calendar(events, project):
    st.subheader("📅 Calendar")

    today = date.today()
    cal = calendar.monthcalendar(today.year, today.month)

    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                active = any(
                    e.get("project") == project and
                    str(e.get("date"))[:10] == date(today.year, today.month, day).isoformat()
                    for e in events
                )

                cols[i].markdown(f"🔵 {day}" if active else str(day))

# =============================
# DASHBOARD
# =============================
st.title(f"🚀 {view_proj} Dashboard")

events = st.session_state.data.get("events", [])

render_calendar(events, view_proj)

st.markdown("---")

c1, c2, c3 = st.columns(3)
c1.metric("Members", len(st.session_state.data["members"]))
c2.metric("Events", len(events))
c3.metric("Logs", len(st.session_state.data["logs"]))

st.subheader("📜 Activity Logs")

for log in reversed(st.session_state.data.get("logs", [])[-20:]):
    st.write(f"{log['user']} - {log['task']}")

# =============================
# ADMIN PANEL (FULL RESTORED)
# =============================
if is_admin:
    st.markdown("---")
    st.header("⚙️ Chairman Admin Panel")

    tabs = st.tabs([
        "👥 Roster",
        "📅 Events",
        "🔐 Accounts",
        "⚖️ Corrections",
        "⚠️ Reset",
        "🖥️ Terminal"
    ])

    # ---------------- ROSTER ----------------
    with tabs[0]:
        st.subheader("Add Member")

        with st.form("add_member"):
            name = st.text_input("Name")
            project = st.selectbox("Project", ["SKIT", "BROCHURE", "CLASS"])
            is_rep = st.checkbox("Rep")
            role = st.selectbox("Role", ["Actor", "Editor", "Designer", "Writer"])

            if st.form_submit_button("Add"):
                st.session_state.data["members"].append({
                    "name": name,
                    "project": project,
                    "is_rep": is_rep,
                    "sub_role": role
                })
                save_data()
                st.rerun()

        st.divider()

        for i, m in enumerate(st.session_state.data["members"]):
            c1, c2 = st.columns([4,1])
            c1.write(m["name"])

            if c2.button("Delete", key=f"rm_{i}"):
                st.session_state.data["members"].pop(i)
                save_data()
                st.rerun()

    # ---------------- EVENTS ----------------
    with tabs[1]:
        st.subheader("Add Event")

        with st.form("event"):
            p = st.selectbox("Project", ["SKIT", "BROCHURE"])
            t = st.text_input("Type")
            d = st.date_input("Date")
            tm = st.time_input("Time")
            v = st.text_input("Venue")

            if st.form_submit_button("Add"):
                st.session_state.data["events"].append({
                    "project": p,
                    "type": t,
                    "date": str(d),
                    "time": str(tm),
                    "venue": v
                })
                save_data()
                st.rerun()

    # ---------------- ACCOUNTS ----------------
    with tabs[2]:
        st.subheader("Accounts")

        for i, a in enumerate(st.session_state.data["accounts"]):
            c1, c2 = st.columns([4,1])
            c1.write(a.get("name",""))

            if c2.button("Delete", key=f"acc_{i}"):
                st.session_state.data["accounts"].pop(i)
                save_data()
                st.rerun()

    # ---------------- CORRECTIONS ----------------
    with tabs[3]:
        st.subheader("Time Adjustments")

        with st.form("adj"):
            p = st.selectbox("Project", ["SKIT", "BROCHURE"])
            m = [x["name"] for x in st.session_state.data["members"] if x["project"] == p]
            u = st.selectbox("User", m if m else ["None"])
            mins = st.number_input("Minutes")

            if st.form_submit_button("Apply"):
                if u != "None":
                    key = f"{u}_{p}"
                    st.session_state.data["contributions"][key] = \
                        st.session_state.data["contributions"].get(key, 0) + mins
                    save_data()
                    st.rerun()

    # ---------------- RESET ----------------
    with tabs[4]:
        st.warning("Danger Zone")

        confirm = st.text_input("Type RESET")

        if st.button("Reset Data"):
            if confirm == "RESET":
                st.session_state.data["logs"] = []
                st.session_state.data["contributions"] = {}
                save_data()
                st.success("Reset done")
                st.rerun()

    # ---------------- TERMINAL ----------------
    with tabs[5]:
        st.subheader("System Logs")

        for l in reversed(st.session_state.data.get("system_logs", [])[-50:]):
            st.code(f"{l}")
