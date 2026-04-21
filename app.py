import streamlit as st
import pandas as pd
from datetime import datetime, time, date
import firebase_admin
from firebase_admin import credentials, db
import time
from collections import defaultdict

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
:root {
    --primary: #0ea5e9;
    --bg-dark: #0f172a;
    --card: #1e293b;
    --accent: #38bdf8;
    --text: #e2e8f0;
    --muted: #94a3b8;
}

/* GLOBAL */
.stApp {
    background: var(--bg-dark);
    color: var(--text);
}

/* CARDS */
div[data-testid="stContainer"] {
    background: var(--card);
    padding: 16px;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.05);
}

/* BUTTONS */
.stButton>button {
    background: var(--primary);
    color: white;
    border-radius: 10px;
    font-weight: 600;
    border: none;
}
.stButton>button:hover {
    background: var(--accent);
    transform: translateY(-1px);
}

/* METRICS */
[data-testid="stMetric"] {
    background: var(--card);
    padding: 10px;
    border-radius: 12px;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background: #020617;
    border-right: 1px solid rgba(255,255,255,0.05);
}

/* HEADERS */
h1, h2, h3 {
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# --- 2. FIREBASE INITIALIZATION ---
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
        st.error(f"Firebase Setup Error: {e}")
        st.stop()

# --- 3. DATA PERSISTENCE ---
def load_data():
    try:
        ref = db.reference("via_master_record")
        data = ref.get()

        if data:
            if "events" in data:
                for event in data["events"]:
                    try:
                        # DATE
                        if isinstance(event.get("date"), str):
                            event["date"] = datetime.fromisoformat(event["date"]).date()

                        # TIME
                        if isinstance(event.get("start_time"), str):
                            event["start_time"] = datetime.strptime(event["start_time"], "%H:%M").time()

                        if "end_time" in event and isinstance(event.get("end_time"), str):
                            event["end_time"] = datetime.strptime(event["end_time"], "%H:%M").time()

                    except Exception as err:
                        print("Event parsing error:", err)
                        continue

            return data

        return {
            "members": [],
            "accounts": [],
            "logs": [],
            "contributions": {},
            "events": [],
            "rsvp": [],
            "attendance": {}
        }

    except Exception as e:
        print("Load error:", e)
        return {
            "members": [],
            "accounts": [],
            "logs": [],
            "contributions": {},
            "events": [],
            "rsvp": [],
            "attendance": {}
        }

def generate_event_reports():
    today = date.today()
    logs = st.session_state.data.setdefault("logs", [])

    for e in st.session_state.data.get("events", []):
        try:
            event_date = datetime.fromisoformat(e["date"]).date() if isinstance(e["date"], str) else e["date"]
        except:
            continue

        if event_date <= today:
            log_id = f"auto_{e['project']}_{e['date']}_{e['start_time']}"

            if not any(l.get("log_id") == log_id for l in logs):
                logs.append({
                    "log_id": log_id,
                    "user": "SYSTEM",
                    "date": str(event_date),
                    "minutes": 0,
                    "task": f"AUTO REPORT: {e['type']} completed",
                    "project": e["project"],
                    "comments": []
                })
                
def save_data():
    try:
        ref = db.reference("via_master_record")
        data_copy = st.session_state.data.copy()

        if "events" in data_copy:
            serializable_events = []

            for e in data_copy["events"]:
                e_copy = e.copy()

                if hasattr(e_copy["date"], "isoformat"):
                    e_copy["date"] = e_copy["date"].isoformat()

                if hasattr(e_copy["start_time"], "strftime"):
                    e_copy["start_time"] = e_copy["start_time"].strftime("%H:%M")

                if "end_time" in e_copy and hasattr(e_copy["end_time"], "strftime"):
                    e_copy["end_time"] = e_copy["end_time"].strftime("%H:%M")

                serializable_events.append(e_copy)

            data_copy["events"] = serializable_events

        data_copy["system_logs"] = st.session_state.data.get("system_logs", [])

        ref.set(data_copy)

    except Exception as e:
        print("Save error:", e)

def log_system_event(action, user):
    if "system_logs" not in st.session_state.data:
        st.session_state.data["system_logs"] = []

    st.session_state.data["system_logs"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user,
        "role": st.session_state.get("u_role", ""),
        "action": action
    })

def render_event_calendar(events, selected_project):
    """Calendar with colored buttons - no emojis, scoped CSS"""
    import calendar
    from datetime import datetime, date, timedelta

    today = date.today()
    current_month = today.month
    current_year = today.year
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    month_events = {}
    reminders = []

    # Filter events
    for e in events:
        try:
            evt_date = e.get("date")
            if isinstance(evt_date, str):
                evt_date = datetime.fromisoformat(evt_date).date()
            elif isinstance(evt_date, datetime):
                evt_date = evt_date.date()

            if evt_date.month == current_month and evt_date.year == current_year and e.get("project") == selected_project:
                day = evt_date.day
                if day not in month_events:
                    month_events[day] = []
                month_events[day].append(e)

                if evt_date == tomorrow:
                    reminders.append(f"⚠️ **Tomorrow**: {e['type']} ({e.get('start_time', 'N/A')})")
                elif evt_date == day_after:
                    reminders.append(f"📅 **Day After**: {e['type']} ({e.get('start_time', 'N/A')})")
        except:
            continue

    month_name = calendar.month_name[current_month]
    cal = calendar.monthcalendar(current_year, current_month)

    if 'cal_day_selected' not in st.session_state:
        st.session_state.cal_day_selected = None

    # --- SCOPED CSS (Only affects calendar) ---
    st.markdown("""
    <style>
    /* Main Container */
    .cal-container {
        background: #0f172a;
        border: 2px solid #334155;
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 16px;
    }
    
    /* Calendar row columns */
    .cal-row > div {
        min-height: 40px;
        display: flex !important;
        align-items: center;
        justify-content: center;
    }
    
    /* Only target buttons INSIDE cal-btn-wrapper class */
    .cal-btn-wrapper button {
        border-radius: 50% !important;
        width: 36px !important;
        height: 36px !important;
        min-height: 36px !important;
        padding: 0 !important;
        margin: 0 auto !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border: 2px solid !important;
    }
    
    /* Date text for non-event days */
    .cal-date-text {
        text-align: center;
        font-size: 13px;
        font-weight: 500;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    </style>
    """, unsafe_allow_html=True)

    # --- START CONTAINER ---
    st.markdown('<div class="cal-container">', unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align:center; margin:0 0 12px 0; color:#38bdf8;'>📅 {month_name} {current_year}</h3>", unsafe_allow_html=True)

    # Reminders
    if reminders:
        for r in reminders:
            st.warning(r, icon="🔔")

    # Headers
    cols = st.columns(7)
    for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        cols[i].markdown(f"<div style='text-align:center; color:#94a3b8; font-size:11px; font-weight:600; padding:8px 0;'>{d}</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # --- GRID ---
    for week in cal:
        row_cols = st.columns(7, gap="small")
        for i, day in enumerate(week):
            if day == 0:
                with row_cols[i]:
                    st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)
            else:
                with row_cols[i]:
                    has_event = day in month_events
                    is_today = day == today.day
                    evt_date_obj = datetime(current_year, current_month, day).date()
                    is_past = evt_date_obj < today

                    if has_event:
                        # Button colors - NO EMOJIS
                        if is_past:
                            bg_color = "#1e293b"
                            border_color = "#64748b"
                            text_color = "#64748b"
                        elif is_today:
                            bg_color = "#334155"
                            border_color = "#ffffff"
                            text_color = "#ffffff"
                        else:
                            bg_color = "#0f172a"
                            border_color = "#38bdf8"
                            text_color = "#38bdf8"

                        # Unique key for this button
                        btn_key = f"cal_btn_{day}_{current_month}_{current_year}"
                        
                        # Wrapper div with specific class
                        st.markdown(f'<div class="cal-btn-wrapper" id="wrapper_{btn_key}">', unsafe_allow_html=True)
                        
                        if st.button(
                            str(day),  # NO EMOJI
                            key=btn_key,
                            use_container_width=True,
                            type="secondary"
                        ):
                            st.session_state.cal_day_selected = day

                        # Apply specific colors to THIS button only
                        st.markdown(f"""
                        <style>
                        #{btn_key} {{
                            background: {bg_color} !important;
                            border-color: {border_color} !important;
                            color: {text_color} !important;
                        }}
                        #{btn_key}:hover {{
                            background: {bg_color} !important;
                            border-color: {text_color} !important;
                            opacity: 0.8;
                        }}
                        </style>
                        """, unsafe_allow_html=True)
                        
                        st.markdown('</div>', unsafe_allow_html=True)

                    else:
                        # No event - just plain text
                        color = "#ffffff" if is_today else "#64748b"
                        weight = "700" if is_today else "500"
                        st.markdown(
                            f"<div class='cal-date-text' style='color:{color}; font-weight:{weight};'>{day}</div>",
                            unsafe_allow_html=True
                        )

    st.markdown('</div>', unsafe_allow_html=True)

    # --- DETAILS PANEL ---
    if st.session_state.get('cal_day_selected') and st.session_state.cal_day_selected in month_events:
        with st.container(border=True):
            st.markdown(f"**📅 {st.session_state.cal_day_selected} {month_name}**")
            for evt in month_events[st.session_state.cal_day_selected]:
                st.markdown(f"🔹 **{evt['type']}**\n\n🕒 {evt.get('start_time', 'N/A')} | 📍 {evt.get('venue', 'N/A')}")
            
            if st.button("✕ Close", key="close_cal", type="secondary"):
                st.session_state.cal_day_selected = None
                st.rerun()
                
if "data" not in st.session_state:
    st.session_state.data = load_data()

if not st.session_state.get("auto_generated"):
    generate_event_reports()
    save_data()
    st.session_state.auto_generated = True

st.session_state._migrated = True

for log in st.session_state.data.get("logs", []):
    for c in log.get("comments", []):
        if "comment_id" not in c:
            c["comment_id"] = str(datetime.now().timestamp())
                
required_keys = ["members", "accounts", "logs", "contributions", "events", "rsvp", "attendance"]
for key in required_keys:
    if key not in st.session_state.data:
        st.session_state.data[key] = {} if key in ["contributions", "attendance"] else []

if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "u_name" not in st.session_state: st.session_state.u_name = ""
if "u_role" not in st.session_state: st.session_state.u_role = ""

# --- 4. AUTHENTICATION ---
USER_PASSWORDS = {
    "Teacher": "teach2026", "VIA Committee": "comm2026",
    "Skit Representative": "skit2026", "Brochure Representative": "brochure2026",
    "VIA members": "member2026", "Classmates": "class2026"
}
CHAIRMAN_SECRET_PW = "chair2026"

if not st.session_state.authenticated:
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(-45deg, #0f172a, #1e293b, #0ea5e9, #1e293b);
        background-size: 400% 400%;
        animation: gradientBG 12s ease infinite;
    }

    @keyframes gradientBG {
        0% {background-position: 0% 50%;}
        50% {background-position: 100% 50%;}
        100% {background-position: 0% 50%;}
    }

    /* CENTER EVERYTHING */
    .block-container {
        padding-top: 6vh;
        max-width: 450px;
        margin: auto;
    }

    /* STYLE INPUTS */
    div[data-baseweb="input"], div[data-baseweb="select"] {
        border-radius: 12px !important;
    }

    /* BUTTON */
    button[kind="primary"] {
        background: #0ea5e9 !important;
        border-radius: 10px !important;
        font-weight: bold;
    }

    button[kind="primary"]:hover {
        transform: scale(1.02);
        transition: 0.2s;
    }

    /* TITLE */
    .title {
        text-align: center;
        color: white;
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 5px;
        animation: popIn 0.8s ease;
    }

    .subtitle {
        text-align: center;
        color: #cbd5e1;
        margin-bottom: 25px;
    }

    @keyframes popIn {
        from {opacity: 0; transform: translateY(20px);}
        to {opacity: 1; transform: translateY(0);}
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='title'>🚀 VIA Portal 2026</div>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>Sign in to continue</div>", unsafe_allow_html=True)

    with st.form("login"):
        name_in = st.text_input("Name").strip().title()
        role_in = st.selectbox("Role", list(USER_PASSWORDS.keys()))
        pw_in = st.text_input("Password", type="password")

        login_btn = st.form_submit_button("Sign In")

        if login_btn:
            if role_in == "VIA Committee" and pw_in == CHAIRMAN_SECRET_PW:
                st.session_state.authenticated = True
                st.session_state.u_name = name_in
                st.session_state.u_role = "Chairman"
        
            elif pw_in == USER_PASSWORDS.get(role_in):
                st.session_state.authenticated = True
                st.session_state.u_name = name_in
                st.session_state.u_role = role_in
        
            else:
                st.error("Access Denied")
                st.stop()

            # ✅ ADD THIS
            log_system_event(f"Logged in as {st.session_state.u_role}", name_in)
            save_data()
        
            with st.spinner("Entering portal..."):
                time.sleep(1)

            st.success("Welcome!")
            st.rerun()
# --- 5. PERMISSIONS ---
c_name, c_role = st.session_state.u_name, st.session_state.u_role
is_chair, is_teach = (c_role == "Chairman"), (c_role == "Teacher")
is_rep = "Representative" in c_role or any(m['name'] == c_name and m.get('is_rep') for m in st.session_state.data.get('members', []))

# --- MODERN SIDEBAR UI ---
st.sidebar.markdown("""
<style>
/* Sidebar container styling */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #020617, #0f172a);
    border-right: 1px solid rgba(255,255,255,0.05);
}

/* Sidebar title */
.sidebar-title {
    font-size: 20px;
    font-weight: 800;
    color: #38bdf8;
    margin-bottom: 8px;
}

/* User card */
.user-card {
    background: rgba(255,255,255,0.03);
    padding: 12px;
    border-radius: 12px;
    border: 1px solid rgba(56,189,248,0.15);
    margin-bottom: 12px;
}

/* Section headers */
.sidebar-section {
    font-size: 12px;
    color: #94a3b8;
    margin-top: 12px;
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Divider */
hr {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.08);
}
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("<div class='sidebar-title'>🎛 Control Panel</div>", unsafe_allow_html=True)

# --- USER INFO CARD ---
st.sidebar.markdown(f"""
<div class="user-card">
    <div style="font-size:16px; font-weight:700;">👤 {c_name}</div>
    <div style="color:#94a3b8; font-size:13px;">{c_role}</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

# --- PROJECT SELECT ---
st.sidebar.markdown("<div class='sidebar-section'>Project View</div>", unsafe_allow_html=True)

view_proj = st.sidebar.radio(
    "",
    ["🎭 SKIT", "📄 BROCHURE"],
    label_visibility="collapsed"
)

view_proj = "SKIT" if "SKIT" in view_proj else "BROCHURE"

st.sidebar.markdown("---")

# --- QUICK ACTIONS ---
st.sidebar.markdown("<div class='sidebar-section'>Actions</div>", unsafe_allow_html=True)

col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("🔄 Refresh"):
        st.rerun()

with col2:
    if st.button("📊 Sync"):
        save_data()
        st.success("Saved!")

st.sidebar.markdown("---")

# --- LOGOUT ---
if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()
    
# --- 6. TABS DEFINITION ---
tabs_list = ["🏠 Dashboard", "✅ Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
if is_chair:
    tabs_list.append("⚙️ Admin")

active_tab = st.tabs(tabs_list)

# --- TAB 0: DASHBOARD ---
with active_tab[0]: 
    st.title(f"🚀 {view_proj} Project Portal")

    # ✅ PREP DATA FIRST
    all_events = [
        e for e in st.session_state.data.get("events", [])
        if e.get("project") == view_proj
    ]    
    today = date.today()

    current_events = []
    history_events = []

    for e in all_events:
        try:
            event_date = e.get("date")

            if isinstance(event_date, str):
                event_date = datetime.fromisoformat(event_date).date()
            elif isinstance(event_date, datetime):
                event_date = event_date.date()
            # else assume it's already date

            if e.get("status") == "Cancelled" or event_date < today:
                history_events.append(e)
            else:
                current_events.append(e)

        except:
            continue

    # ✅ DEFINE MEMBERS BEFORE USING
    mems = [
    m for m in st.session_state.data.get("members", [])
        if (
            m.get("role_type", "PROJECT") == "CLASS"
            or m.get("project") == view_proj
        )
    ]

    # ✅ METRICS
    st.markdown("## 📊 Overview")
    m1, m2, m3, m4 = st.columns(4)

    u_key = f"{c_name}_{view_proj}"
    m = st.session_state.data.get('contributions', {}).get(u_key, 0)

    m1.metric("Your Hours", f"{m // 60}h {m % 60}m")
    m2.metric("Upcoming", len(current_events))
    m3.metric("Completed", len(history_events))
    m4.metric("Team Size", len(mems))
    
    # Main Dashboard Content
        # ... (Metrics code above) ...

    # Main Dashboard Content
    col1, col2 = st.columns([3, 1]) 
    
    with col1:
        # 🆕 1. ADD CALENDAR HERE (Above RSVP)
        st.subheader("🗓️ Event Calendar")
        render_event_calendar(st.session_state.data.get("events", []), view_proj)
        
        st.markdown("---") # Optional divider
        
        # 📅 2. EXISTING RSVP SECTION
        st.subheader("📅 Event RSVP")

        # --- CURRENT EVENTS ---
        if not current_events:
            st.info("📅 No upcoming events. Check back later or contact your rep.")
        else:
            for i, e in enumerate(current_events):
                with st.container():
                    st.markdown(f"""
                    <div style="
                        background:#020617;
                        padding:16px;
                        border-radius:12px;
                        border-left:5px solid #0ea5e9;
                        margin-bottom:10px;
                    ">
                        <h4>{e['type']}</h4>
                        <p style="color:#94a3b8;">
                        📍 {e.get('venue','N/A')} <br>
                        ⏰ {e['start_time']} <br>
                        📅 {e['date']}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.caption("RSVP feature coming soon")
        
        # --- HISTORY ---
        st.divider()
        st.subheader("📜 Event History")
    
        if not history_events:
            st.caption("No past or cancelled events.")
        else:
            for e in reversed(history_events):
                event_date = datetime.fromisoformat(e["date"]).date() if isinstance(e["date"], str) else e["date"]
    
                with st.container(border=True):
                    if e.get("status") == "Cancelled":
                        st.error(f"🚫 **CANCELLED: {e['type']}**")
                    else:
                        st.success(f"✅ **COMPLETED: {e['type']}**")
    
                    st.caption(f"📅 {e['date']} | 📍 {e.get('venue', 'N/A')}")
                    
    with col2:
        st.subheader("👥 Team Roster")
        if not mems: 
            st.info("👥 No members yet. Add from Admin panel.")
        for m in mems:
            st.markdown(f"{'⭐' if m['is_rep'] else '👤'} **{m['name']}**")
            st.caption(f"Focus: {m['sub_role']}")

# --- TAB 1: ATTENDANCE ---
with active_tab[1]:
    st.title("✅ Attendance Tracker")
    evs = [
    e for e in st.session_state.data["events"]
    if e["project"] == view_proj and e.get("status") != "Cancelled"
    ]
    if evs:
        sel_list = [f"{e['type']} ({e['date']})" for e in evs]
        sel = st.selectbox("Select Event", sel_list)
        e = evs[sel_list.index(sel)]
        eid = f"{e['project']}_{e['date']}_{e['start_time']}"
        voters = [rv['name'] for rv in st.session_state.data.get("rsvp", []) if rv['event_id']==eid and rv['status'] in ["Attending", "Late"]]
        
        if not voters: st.warning("No RSVPs.")
        else:
            for n in voters:
                rec = st.session_state.data["attendance"].get(eid, {}).get(n, {"p": False, "d": "Full"})
                col1, col2, col3 = st.columns(3)
                col1.write(n)
                if is_chair or is_teach:
                    p = col2.checkbox("Present", value=rec["p"], key=f"p_{n}_{eid}")
                    d = col3.selectbox("Session", ["Full", "Half"], index=0 if rec["d"]=="Full" else 1, key=f"d_{n}_{eid}")
                    st.session_state.data["attendance"].setdefault(eid, {})[n] = {"p": p, "d": d}
                else:
                    col2.write("✅" if rec["p"] else "❌")
                    col3.write(rec["d"])
            if (is_chair or is_teach) and st.button("Save Attendance"): save_data(); st.success("Saved!")

with active_tab[2]:
    st.title("🕒 Activity Log")

    if is_chair or is_rep:
        with st.expander("➕ Log New Activity"):
            with st.form(f"log_{view_proj}"):
                ld = st.date_input("Date")
                lm = st.number_input("Minutes", 5, step=5)
                lt = st.text_input("Task")
                lp = st.selectbox("Project", ["SKIT", "BROCHURE"], index=0 if view_proj=="SKIT" else 1)

                if st.form_submit_button("Submit"):
                    log_system_event(f"Added log: {lt}", c_name)
                    st.session_state.data["logs"].append({
                    "log_id": f"event_{datetime.now().timestamp()}",
                    "user": c_name,
                    "date": str(date.today()),
                    "minutes": 0,
                    "task": f"Created event: {ty}",
                    "project": ep,
                    "comments": []
                    })
                    save_data()
                    st.success("Logged!")
                    st.rerun()

    st.divider()
    st.subheader("📜 Recent Activity & Teacher Feedback")

    proj_logs = [l for l in st.session_state.data.get("logs", []) if l.get("project") == view_proj]

    for log in reversed(proj_logs):
        with st.container(border=True):

            is_system = log.get("user") == "SYSTEM"

            ct, cs = st.columns([3, 1])
            ct.markdown(f"**{log['user']}** - {log['task']}\n\n📅 {log['date']}")
            cs.info(f"{log['minutes']} mins")

        # 🔒 system notice
        if is_system:
            st.caption("🔒 System-generated report")

        # 🗑️ EDIT/DELETE ONLY IF NOT SYSTEM
        if is_teach and not is_system:
            col1, col2 = st.columns(2)

            if col1.button("🗑️ Delete", key=f"del_{log['log_id']}"):
                log_system_event(f"Deleted activity: {log['task']}", c_name)
            
                st.session_state.data["logs"] = [
                    l for l in st.session_state.data["logs"]
                    if l.get("log_id") != log["log_id"]
                ]
                save_data()
                st.rerun()

            with col2.expander("✏️ Edit"):
                with st.form(f"edit_{log['log_id']}"):
                    new_task = st.text_input("Task", value=log["task"])
                    new_minutes = st.number_input("Minutes", value=log["minutes"], step=5)

                    if st.form_submit_button("Save"):
                        log_system_event(f"Edited activity: {log['task']}", c_name)
                        for l in st.session_state.data["logs"]:
                            if l.get("log_id") == log["log_id"]:
                                l["task"] = new_task
                                l["minutes"] = new_minutes

                        save_data()
                        st.rerun()

        # 💬 COMMENTS
        for c in log.get("comments", []):
            comment_id = c.get("comment_id")
            teacher_name = c.get("teacher", "Unknown")

            st.markdown(f"**{teacher_name}**")
            st.write(c.get("text", ""))

            if is_teach and teacher_name == c_name and comment_id:
                action_col1, action_col2, _ = st.columns([1, 1, 6])

                if action_col1.button("🗑️ Delete", key=f"del_c_{comment_id}"):
                    log_system_event(f"Deleted comment: {c.get('text','')[:30]}", c_name)
                    log["comments"] = [
                        x for x in log["comments"]
                        if x.get("comment_id") != comment_id
                    ]
                    save_data()
                    st.rerun()

                with action_col2.expander("✏️ Edit"):
                    with st.form(f"edit_c_{comment_id}"):
                        new_text = st.text_area("Edit your feedback", value=c.get("text", ""))

                        if st.form_submit_button("Save"):
                            for x in log["comments"]:
                                if x.get("comment_id") == comment_id:
                                    x["text"] = new_text

                            save_data()
                            st.rerun()
                            
# --- TAB 3: PROGRESS ---
with active_tab[3]:
    st.title("📊 Class Progress Tracker")
    all_m, all_c = st.session_state.data.get("members", []), st.session_state.data.get("contributions", {})
    st.metric("Total Class VIA Minutes", f"{sum(all_c.values())} mins")
    
    if is_chair or is_rep:
        st.subheader("⚙️ Project Time Adjustments")
        col1, col2 = st.columns(2)
        with col1:
            with st.expander("➕ Add Project Bonus"):
                with st.form("bonus_f"):
                    tp = st.selectbox("Project", ["SKIT", "BROCHURE"], key="b1")
                    unames = [m['name'] for m in all_m if m['project'] == tp]
                    tu = st.selectbox("Student", unames if unames else ["None"], key="b2")
                    bm = st.number_input("Minutes", 1, step=5)
                    ra = st.text_input("Reason")
                    if st.form_submit_button("Apply Bonus") and tu != "None":
                        selected_member = next(m for m in all_m if m["name"] == tu)
                        ukey = f"{tu}_{selected_member['project']}"
                        st.session_state.data["contributions"][ukey] = st.session_state.data["contributions"].get(ukey, 0) + bm
                        st.session_state.data["logs"].append({"log_id": f"b_{datetime.now().strftime('%H%M%S')}", "user": tu, "date": str(date.today()), "minutes": bm, "task": f"BONUS: {ra}", "project": tp, "comments": []})
                        save_data(); st.rerun()

    ts1, ts2 = st.tabs(["🎭 Skit Team", "📄 Brochure Team"])
    for proj, t in [("SKIT", ts1), ("BROCHURE", ts2)]:
        with t:
            members_proj = [
                m for m in all_m
                if m.get("role_type") == "CLASS" or m.get("project") == proj
            ]
    
            if not members_proj:
                st.info("No members in this project yet.")
            else:
                for m in members_proj:
                    mins = all_c.get(f"{m['name']}_{proj}", 0)
                    progress_val = max(0.0, min(1.0, mins / 300))
    
                    with st.container():
                        st.markdown(f"""
                        <div style="
                            background:#020617;
                            padding:14px;
                            border-radius:10px;
                            margin-bottom:10px;
                        ">
                            <b>{m['name']}</b><br>
                            <span style="color:#94a3b8;">
                            {mins//60}h {mins%60}m / 5h goal
                            </span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                        st.progress(progress_val)

# --- TAB 4: DIRECTORY ---
with active_tab[4]:
    st.title("📁 Official Class Directory")

    all_m = st.session_state.data.get("members", [])
    all_c = st.session_state.data.get("contributions", {})

    # --- STEP 1: DEDUPLICATE PEOPLE ---
    people = {}

    for m in all_m:
        name = m["name"]

        if name not in people:
            people[name] = {
                "projects": set(),
                "roles": set()
            }

        people[name]["projects"].add(m.get("project", "CLASS"))
        people[name]["roles"].add(m.get("sub_role", "N/A"))

    unique_count = len(people)

    # --- STEP 2: METRICS (OLD FORMAT FIXED) ---
    m1, m2, m3 = st.columns(3)

    m1.metric("Total Members", unique_count)

    avg = sum(all_c.values()) // unique_count if unique_count else 0
    m2.metric("Average Time", f"{avg//60}h {avg%60}m")

    m3.metric("Active Projects", "2")

    # --- STEP 3: FILTER UI ---
    f1, f2 = st.columns([2, 1])
    s = f1.text_input("🔍 Search")
    pf = f2.selectbox("Filter", ["All", "SKIT", "BROCHURE", "CLASS"])

    # --- STEP 4: BUILD TABLE (SUM TIME PROPERLY) ---
    summary = []

    for name, data in people.items():

        total_minutes = 0

        for p in data["projects"]:
            total_minutes += all_c.get(f"{name}_{p}", 0)

        summary.append({
            "NAME": name,
            "PROJECTS": " | ".join(data["projects"]),
            "ROLE": " | ".join(data["roles"]),
            "VIA TIME": f"{total_minutes//60}h {total_minutes%60}m",
            "STATUS": "✅ Active" if total_minutes > 0 else "⏳ No Logs"
        })

    df = pd.DataFrame(summary)

    # --- FILTER LOGIC ---
    if s:
        df = df[df["NAME"].str.contains(s, case=False)]

    if pf != "All":
        df = df[df["PROJECTS"].str.contains(pf)]

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "📥 Download CSV",
        df.to_csv(index=False),
        f"VIA_{date.today()}.csv",
        "text/csv"
    )
# --- TAB 5: ADMIN ---
if is_chair:
    with active_tab[5]:
        st.title("⚙️ Chairman Master Control")
        # Update: Added "⚠️ Reset" to the tab list
        at1, at2, at3, at4, at5, at6 = st.tabs([
            "👥 Roster",
            "📅 Events",
            "🔐 Accounts",
            "⚖️ Corrections",
            "⚠️ Reset",
            "🖥️ Terminal"
        ])
        
        with at1:
            st.subheader("➕ Add Member")
        
            with st.form("add_member_form"):
                cn, cp = st.columns(2)
                n = cn.text_input("Name")
                p = cp.selectbox("Project", ["SKIT", "BROCHURE", "CLASS"])
        
                cr, cs = st.columns(2)
                r = cr.checkbox("Rep?")
                s = cs.selectbox("Role", ["Actors", "Prop makers", "Cameraman", "Designer", "Editor", "Writer", "N/A"])
        
                if st.form_submit_button("Add Member"):
                    if not n.strip():
                        st.error("Name cannot be empty")
                    else:
                        role_type = "CLASS" if p == "CLASS" else "PROJECT"
                        st.session_state.data["members"].append({
                            "name": n,
                            "project": None if role_type == "CLASS" else p,
                            "role_type": role_type,
                            "is_rep": r,
                            "sub_role": s
                        })
        
                        log_system_event(f"Added member: {n} ({p}, {s})", c_name)
                        save_data()
                        st.rerun()
        
            st.divider()
            st.subheader("🗑️ Remove Members")
        
            # ✅ THIS MUST ALSO BE INSIDE at1
            for i, m in enumerate(st.session_state.data.get("members", [])):
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
        
                    c1.write(f"**{m['name']}** ({m['project']})")
                    c1.caption(f"Role: {m['sub_role']}")
        
                    if c2.button("🗑️ Delete", key=f"del_member_{i}"):
                        log_system_event(
                            f"Deleted member: {m['name']} ({m['project']})",
                            c_name
                        )
        
                        st.session_state.data["members"].pop(i)
                        save_data()
                        st.rerun()

        with at2:
            st.subheader("🗓️ Manage Events")
            # --- 1. CREATE EVENT FORM ---
            with st.form("add_e"):
                ep, ty, d = st.selectbox("Project", ["SKIT", "BROCHURE"]), st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"]), st.date_input("Date")
                st_time, v = st.time_input("Start"), st.text_input("Venue")
                if st.form_submit_button("Add Event"):
                    log_system_event(f"Created event: {ty}", c_name)
                
                    st.session_state.data["events"].append({
                        "project": ep,
                        "type": ty,
                        "date": d,
                        "start_time": st_time,
                        "venue": v,
                        "status": "Active"
                    })
                
                    save_data()
                    st.success("Event added!")
                    st.rerun()

            st.divider()
            st.subheader("📝 Existing Events")
            
            # --- 2. EDIT & DELETE LOGIC ---
            # Loop through events to display them for management
            for i, ev in enumerate(st.session_state.data.get("events", [])):
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"**{ev['type']}** ({ev['project']})")
                    c1.caption(f"📅 {ev['date']} | 📍 {ev.get('venue', 'N/A')} | 🕒 {ev['start_time']}")
                    
                    # DELETE BUTTON
                    if c2.button("🗑️ Delete", key=f"del_ev_{i}"):

                        # log BEFORE deleting (important so data still exists)
                        log_system_event(
                            f"{c_role} {c_name} deleted event '{ev['type']}' on {ev['date']}",
                            c_name
                        )
                    
                        st.session_state.data["events"].pop(i)
                        save_data()
                        st.rerun()
                    
                    # EDIT EXPANDER
                    with st.expander("✏️ Edit Details"):
                        with st.form(f"edit_ev_{i}"):
                            new_type = st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"], 
                                                 index=["Discussion", "Rehearsal", "Work Session", "Production Day"].index(ev['type']))
                            new_venue = st.text_input("Venue", value=ev.get("venue", ""))
                            new_note = st.text_input("Cancel Note/Status Reason", value=ev.get("note", ""))
                            new_stat = st.selectbox("Status", ["Active", "Cancelled"], 
                                                 index=0 if ev.get("status") == "Active" else 1)
                            
                            if st.form_submit_button("Save Changes"):
                                log_system_event(f"Edited event: {ev['type']} → {new_type}", c_name)
                            
                                st.session_state.data["events"][i]["type"] = new_type
                                st.session_state.data["events"][i]["venue"] = new_venue
                                st.session_state.data["events"][i]["note"] = new_note
                                st.session_state.data["events"][i]["status"] = new_stat
                            
                                save_data()
                                st.rerun()

        with at3:
            for i, a in enumerate(st.session_state.data.get("accounts", [])):
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"**{a['name']}** ({a['role']})")
                    if c2.button("Wipe", key=f"w_{i}"):
                        st.session_state.data["accounts"].pop(i)
                        save_data(); st.rerun()

        with at4:
            st.subheader("⚖️ Manual Time Correction")
            with st.form("adj"):
                c1, c2 = st.columns(2)
                ap = c1.selectbox("Project", ["SKIT", "BROCHURE"])
                an = c2.selectbox("Student", [mx['name'] for mx in st.session_state.data["members"] if mx['project'] == ap] or ["None"])
                am, ar = st.number_input("Minutes", step=5), st.text_input("Reason")
                if st.form_submit_button("🔨 Apply Adjustment") and an != "None":
                    ukey = f"{an}_{ap}"
                    st.session_state.data["contributions"][ukey] = st.session_state.data["contributions"].get(ukey, 0) + am
                    st.session_state.data["logs"].append({"log_id": f"adm_{datetime.now().strftime('%H%M%S')}", "user": an, "date": str(date.today()), "minutes": am, "task": f"ADMIN ADJ: {ar}", "project": ap})
                    save_data(); st.success(f"Adjusted {an}!"); st.rerun()

        # --- NEW RESET LOGIC ---
        with at5:
            st.subheader("🚨 Danger Zone")

            st.warning("This will permanently wipe all hour contributions and the activity log history.")
            
            # Confirmation step to prevent accidental clicks
            confirm = st.text_input("Type 'RESET' to confirm deletion")
            
            if st.button("🔥 Reset All Time Tracker Data", type="primary"):
                if confirm == "RESET":
                    st.session_state.data["contributions"] = {}
                    st.session_state.data["logs"] = []
                    save_data()
                    st.success("All data has been reset!")
                    st.rerun()
                else:
                    st.error("You must type 'RESET' to confirm.")
                    
        with at6:
            st.subheader("🖥️ System Activity Terminal")
            
            logs = st.session_state.data.get("system_logs", [])
            
            if not logs:
                st.info("No system activity yet.")
            else:
                for entry in reversed(logs[-50:]):  # last 50 logs
                    st.code(f"[{entry['time']}] {entry['user']} ({entry.get('role','')}) → {entry['action']}", language="bash")
                    
