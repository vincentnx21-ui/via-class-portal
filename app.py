import streamlit as st
import pandas as pd
from datetime import datetime, time, date
import firebase_admin
from firebase_admin import credentials, db
import json
import os

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    button[data-baseweb="tab"] {
        font-size: 18px;
        font-weight: bold;
        color: #1e293b;
        background-color: #e2e8f0;
        border-radius: 10px 10px 0px 0px;
        padding: 10px 20px;
        margin-right: 5px;
        transition: 0.3s;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #1e293b !important;
        color: white !important;
        border-bottom: 3px solid #007bff;
    }
    div[data-plugin="stTabs"] div[role="tablist"] {
        border-bottom: none;
        gap: 0px;
    }
    button[data-baseweb="tab"]:hover {
        background-color: #cbd5e1;
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
                for e in data["events"]:
                    try:
                        e["date"] = datetime.strptime(e["date"], "%Y-%m-%d").date()
                        e["start_time"] = datetime.strptime(e["start_time"], "%H:%M").time()
                        # Fixed: Potential missing end_time check
                        if "end_time" in e:
                            e["end_time"] = datetime.strptime(e["end_time"], "%H:%M").time()
                    except: continue
            return data
        else:
            return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}}
    except Exception as e:
        st.error(f"Load Error: {e}")
        return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}}
        
def save_data():
    try:
        ref = db.reference("via_master_record")
        data_copy = st.session_state.data.copy()
        if "events" in data_copy:
            serializable_events = []
            for e in data_copy["events"]:
                e_c = e.copy()
                e_c["date"] = e["date"].isoformat() if hasattr(e["date"], 'isoformat') else e["date"]
                e_c["start_time"] = e["start_time"].strftime("%H:%M") if hasattr(e["start_time"], 'strftime') else e["start_time"]
                if "end_time" in e:
                    e_c["end_time"] = e["end_time"].strftime("%H:%M") if hasattr(e["end_time"], 'strftime') else e["end_time"]
                serializable_events.append(e_c)
            data_copy["events"] = serializable_events
        ref.set(data_copy)
    except Exception as e:
        st.error(f"Save Error: {e}")

if "data" not in st.session_state:
    st.session_state.data = load_data()

required_keys = ["members", "accounts", "logs", "contributions", "events", "rsvp", "attendance"]
for key in required_keys:
    if key not in st.session_state.data:
        st.session_state.data[key] = {} if key in ["contributions", "attendance"] else []

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "u_name" not in st.session_state:
    st.session_state.u_name = ""
if "u_role" not in st.session_state:
    st.session_state.u_role = ""

# --- 4. AUTHENTICATION ---
USER_PASSWORDS = {
    "Teacher": "teach2026", 
    "VIA Committee": "comm2026",
    "Skit Representative": "skit2026", 
    "Brochure Representative": "brochure2026",
    "VIA members": "member2026", 
    "Classmates": "class2026"
}
CHAIRMAN_SECRET_PW = "chair2026"

if not st.session_state.authenticated:
    st.title("🛡️ VIA Class Portal 2026")
    with st.form("login"):
        name_in = st.text_input("Name").strip().title()
        role_in = st.selectbox("Role", list(USER_PASSWORDS.keys()))
        pw_in = st.text_input("Password", type="password")
        
        if st.form_submit_button("Sign In"):
            if name_in:
                login_success = False
                if role_in == "VIA Committee" and pw_in == CHAIRMAN_SECRET_PW:
                    st.session_state.authenticated = True
                    st.session_state.u_name = name_in
                    st.session_state.u_role = "Chairman"
                    login_success = True
                elif pw_in == USER_PASSWORDS.get(role_in):
                    st.session_state.authenticated = True
                    st.session_state.u_name = name_in
                    st.session_state.u_role = role_in
                    login_success = True
                else:
                    st.error("Access Denied: Incorrect password.")

                if login_success:
                    acc_list = st.session_state.data.get("accounts", [])
                    if not any(a['name'] == name_in for a in acc_list):
                        st.session_state.data["accounts"].append({"name": name_in, "role": st.session_state.u_role})
                    save_data()
                    st.rerun()
            else:
                st.error("Please enter your name.")
    st.stop()

# --- 5. NAVIGATION & PERMISSIONS ---
c_name = st.session_state.u_name
c_role = st.session_state.u_role
is_chair = (c_role == "Chairman")
is_teach = (c_role == "Teacher")

# Fixed logic to check if user is a representative based on the members roster
is_rep = any(m['name'] == c_name and m.get('is_rep') for m in st.session_state.data.get('members', []))

tabs_list = ["🏠 Dashboard", "✅ Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
if is_chair:
    tabs_list.append("⚙️ Admin")

active_tab = st.tabs(tabs_list)

st.sidebar.markdown(f"### 👤 {c_name}")
view_proj = st.sidebar.selectbox("📁 Select Project", ["SKIT", "BROCHURE"])

if st.sidebar.button("🔓 Logout", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()
    
# --- 6. PAGE CONTENT ---

# --- TAB 0: DASHBOARD ---
with active_tab[0]: 
    st.title(f"🚀 {view_proj} Project Portal")
    col_a, col_b, col_c = st.columns(3)
    
    if c_role != "Teacher":
        u_key = f"{c_name}_{view_proj}"
        user_minutes = st.session_state.data.get('contributions', {}).get(u_key, 0)
        col_a.metric(f"Your {view_proj} Hours", f"{user_minutes // 60}h {user_minutes % 60}m")
    else:
        col_a.metric("Role", "Faculty Observer")
        
    all_events = st.session_state.data.get("events", [])
    upcoming_events = len([e for e in all_events if e.get("project") == view_proj and e.get("status") != "Cancelled"])
    col_b.metric("Upcoming Events", upcoming_events)
    col_c.metric(label="Project Status", value="Active", delta="On Track")

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📅 Event RSVP")
        proj_events = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
        
        if not proj_events:
            st.info("No events scheduled yet.")
        else:
            for i, e in enumerate(proj_events):
                is_cancelled = e.get("status") == "Cancelled"
                with st.container(border=True):
                    if is_cancelled:
                        st.error(f"🚫 **CANCELLED: {e['type']}**")
                        if e.get("note"): st.warning(f"**Reason:** {e['note']}")
                    else:
                        st.write(f"**{e['type']}**")
                        venue = e.get('venue', 'N/A') 
                        st.caption(f"📍 {venue} | ⏰ {e['start_time']}")

                        # FIXED: Moved RSVP logic INSIDE the container and loop
                        with st.expander("Update My RSVP"):
                            form_key = f"form_rsvp_{view_proj}_{i}"
                            with st.form(key=form_key):
                                s = st.segmented_control("Status", ["Attending", "Late", "Not Attending"], key=f"status_{form_key}")
                                r = st.text_input("Note/Reason", key=f"note_{form_key}")
                                if st.form_submit_button("Confirm RSVP"):
                                    if s is None:
                                        st.error("Please select a status!")
                                    else:
                                        e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
                                        new_rsvp = {"event_id": e_id, "name": c_name, "status": s, "note": r}
                                        current_rsvps = st.session_state.data.get("rsvp", [])
                                        st.session_state.data["rsvp"] = [x for x in current_rsvps if not (x['event_id'] == e_id and x['name'] == c_name)]
                                        st.session_state.data["rsvp"].append(new_rsvp)
                                        save_data()
                                        st.success("RSVP Saved!")
                                        st.rerun()

    with col2:
        st.subheader("👥 Team Roster")
        members = [m for m in st.session_state.data["members"] if m["project"] == view_proj]
        if not members:
            st.write("No members assigned yet.")
        for m in members:
            st.markdown(f"{'⭐' if m['is_rep'] else '👤'} **{m['name']}**")
            st.caption(f"Focus: {m['sub_role']}")

# --- TAB 1: ATTENDANCE ---
with active_tab[1]:
    st.title("✅ Attendance Tracker")
    evs = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
    if evs:
        sel_list = [f"{e['type']} ({e['date']})" for e in evs]
        sel = st.selectbox("Select Event", sel_list)
        idx = sel_list.index(sel)
        e = evs[idx]
        e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
        
        voters = [rv['name'] for rv in st.session_state.data.get("rsvp", []) if rv['event_id']==e_id and rv['status'] in ["Attending", "Late"]]
        
        if not voters:
            st.warning("No one has RSVP'd 'Attending' for this event yet.")
        else:
            for n in voters:
                rec = st.session_state.data["attendance"].get(e_id, {}).get(n, {"p": False, "d": "Full"})
                c1, c2, c3 = st.columns(3)
                c1.write(n)
                if is_chair or is_teach:
                    p = c2.checkbox("Present", value=rec["p"], key=f"at_p_{n}_{e_id}")
                    d = c3.selectbox("Session", ["Full", "Half"], index=0 if rec["d"]=="Full" else 1, key=f"at_d_{n}_{e_id}")
                    if e_id not in st.session_state.data["attendance"]: st.session_state.data["attendance"][e_id] = {}
                    st.session_state.data["attendance"][e_id][n] = {"p": p, "d": d}
                else:
                    c2.write("✅" if rec["p"] else "❌")
                    c3.write(rec["d"])
            if (is_chair or is_teach) and st.button("Save Attendance"): 
                save_data()
                st.success("Saved!")

# --- TAB 2: ACTIVITY LOG ---
with active_tab[2]:
    st.title("🕒 Activity Log")
    if c_role != "Teacher":
        with st.expander("➕ Log New Activity"):
            with st.form(key=f"activity_log_form"):
                ld = st.date_input("Date", value=date.today())
                lm = st.number_input("Minutes", min_value=5, step=5)
                lt = st.text_input("Task Description")
                lp = st.selectbox("Project", ["SKIT", "BROCHURE"], index=0 if view_proj == "SKIT" else 1)
                
                if st.form_submit_button("Submit Log"):
                    u_key = f"{c_name}_{lp}"
                    st.session_state.data["contributions"][u_key] = st.session_state.data["contributions"].get(u_key, 0) + lm
                    new_log = {
                        "log_id": f"log_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "user": c_name, "date": str(ld), "minutes": lm, "task": lt, "project": lp, "comments": []
                    }
                    st.session_state.data["logs"].append(new_log)
                    save_data()
                    st.success(f"Logged {lm} mins for {lp}!")
                    st.rerun()

    st.divider()
    proj_logs = [l for l in st.session_state.data.get("logs", []) if l.get("project") == view_proj]
    if not proj_logs:
        st.info("No activities logged for this project yet.")
    else:
        for i, log in enumerate(reversed(proj_logs)):
            with st.container(border=True):
                col_t, col_s = st.columns([3, 1])
                with col_t:
                    st.markdown(f"**{log['user']}** - {log['task']}")
                    st.caption(f"📅 {log['date']}")
                with col_s:
                    st.info(f"{log['minutes']} mins")
                
                for c in log.get("comments", []):
                    st.markdown(f"> **{c['teacher']}:** {c['text']}")

                if is_teach:
                    with st.expander("📝 Add Comment"):
                        with st.form(key=f"cmt_{log['log_id']}"):
                            t_comment = st.text_area("Feedback")
                            if st.form_submit_button("Post"):
                                if t_comment:
                                    new_c = {"teacher": c_name, "text": t_comment, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
                                    for l in st.session_state.data["logs"]:
                                        if l.get("log_id") == log["log_id"]:
                                            l.setdefault("comments", []).append(new_c)
                                    save_data()
                                    st.rerun()

# --- TAB 3: PROGRESS ---
with active_tab[3]:
    st.title("📊 Class Progress")
    all_members = st.session_state.data.get("members", [])
    all_contribs = st.session_state.data.get("contributions", {})
    
    st.metric("Total Class Minutes", f"{sum(all_contribs.values())} mins")
    
    if is_chair or is_rep:
        st.subheader("⚙️ Manual Adjustments")
        col_add, col_sub = st.columns(2)
        with col_add:
            with st.expander("➕ Bonus"):
                with st.form("bonus_f"):
                    t_p = st.selectbox("Project", ["SKIT", "BROCHURE"])
                    t_u = st.selectbox("Student", [m['name'] for m in all_members if m['project'] == t_p] or ["N/A"])
                    t_m = st.number_input("Mins", min_value=1)
                    if st.form_submit_button("Apply") and t_u != "N/A":
                        u_key = f"{t_u}_{t_p}"
                        st.session_state.data["contributions"][u_key] = st.session_state.data["contributions"].get(u_key, 0) + t_m
                        save_data(); st.rerun()

    p_skit, p_broch = st.tabs(["🎭 Skit Team", "📄 Brochure Team"])
    for team, tab in [("SKIT", p_skit), ("BROCHURE", p_broch)]:
        with tab:
            for m in [m for m in all_members if m['project'] == team]:
                m_mins = all_contribs.get(f"{m['name']}_{team}", 0)
                c1, c2 = st.columns([1, 3])
                c1.write(f"**{m['name']}**")
                c2.progress(min(1.0, m_mins/300), text=f"{m_mins//60}h {m_mins%60}m")

# --- TAB 4: DIRECTORY ---
with active_tab[4]:
    st.title("📁 Class Directory")
    summary_data = []
    for m in st.session_state.data["members"]:
        u_key = f"{m['name']}_{m['project']}"
        mins = st.session_state.data["contributions"].get(u_key, 0)
        summary_data.append({
            "NAME": m['name'], "PROJECT": m['project'], "ROLE": m['sub_role'], 
            "TIME": f"{mins//60}h {mins%60}m", "STATUS": "✅ Active"
        })
    if summary_data:
        df = pd.DataFrame(summary_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No members found.")

# --- TAB 5: ADMIN ---
if is_chair:
    with active_tab[5]:
        st.title("⚙️ Master Control")
        t1, t2, t3 = st.tabs(["👥 Roster", "📅 Events", "🔐 Accounts"])
        with t1:
            with st.form("add_mem"):
                n = st.text_input("Full Name")
                p = st.selectbox("Project", ["SKIT", "BROCHURE"])
                r = st.checkbox("Representative?")
                s = st.selectbox("Role", ["Actors", "Prop makers", "Designer", "N/A"])
                if st.form_submit_button("Add"):
                    st.session_state.data["members"].append({"name": n, "project": p, "is_rep": r, "sub_role": s})
                    save_data(); st.rerun()
        with t2:
            with st.form("add_ev"):
                ep = st.selectbox("Proj", ["SKIT", "BROCHURE"])
                ty = st.selectbox("Type", ["Discussion", "Rehearsal"])
                dt = st.date_input("Date")
                if st.form_submit_button("Create Event"):
                    st.session_state.data["events"].append({"project": ep, "type": ty, "date": str(dt), "status": "Active", "start_time": "14:00"})
                    save_data(); st.rerun()
