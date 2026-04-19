import streamlit as st
import pandas as pd
from datetime import datetime, time, date
import firebase_admin
from firebase_admin import credentials, db # Using 'db' for Realtime Database
import json
import os

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    /* Main background */
    .main { background-color: #f5f7f9; }

    /* Style the Tabs */
    button[data-baseweb="tab"] {
        font-size: 18px;
        font-weight: bold;
        color: #1e293b; /* Dark text for unselected */
        background-color: #e2e8f0; /* Light grey for unselected */
        border-radius: 10px 10px 0px 0px;
        padding: 10px 20px;
        margin-right: 5px;
        transition: 0.3s;
    }

    /* Style for the ACTIVE (selected) tab */
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #1e293b !important; /* Dark blue background */
        color: white !important; /* White text */
        border-bottom: 3px solid #007bff;
    }

    /* Remove the default underline Streamlit adds */
    div[data-plugin="stTabs"] div[role="tablist"] {
        border-bottom: none;
        gap: 0px;
    }
    
    /* Hover effect */
    button[data-baseweb="tab"]:hover {
        background-color: #cbd5e1;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FIREBASE INITIALIZATION ---
if not firebase_admin._apps:
    try:
        # Load your credentials
        if "firebase" in st.secrets:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
            
        # DIRECT INITIALIZATION - No variables, no secrets for the URL
        firebase_admin.initialize_app(cred, {
    # It's okay if it ends in .app/ 
    # Just make sure it is the link from the Realtime Database page!
    'databaseURL': 'https://via-report-default-rtdb.asia-southeast1.firebasedatabase.app/'
})
        # ^^^ MAKE SURE the link above starts with https:// and ends with /
        
    except Exception as e:
        st.error(f"Firebase Setup Error: {e}")
        st.stop()
    
# --- 3. DATA PERSISTENCE (REALTIME DB) ---
def load_data():
    try:
        ref = db.reference("via_master_record")
        data = ref.get()
        
        if data:
            # (Keep your existing date/time conversion code here...)
            if "events" in data:
                for e in data["events"]:
                    try:
                        e["date"] = datetime.strptime(e["date"], "%Y-%m-%d").date()
                        e["start_time"] = datetime.strptime(e["start_time"], "%H:%M").time()
                        e["end_time"] = datetime.strptime(e["end_time"], "%H:%M").time()
                    except: continue
            return data
            
        else:
            # --- PASTE THE CODE HERE ---
            # This ensures even a brand new database has all the "drawers" ready
            return {
                "members": [], 
                "accounts": [], 
                "logs": [], 
                "contributions": {}, 
                "events": [], 
                "rsvp": [], 
                "attendance": {}
            }
            # ---------------------------

    except Exception as e:
        st.error(f"Load Error: {e}")
        # Also return the empty structure here so the app doesn't crash on error
        return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}}
        
def save_data():
    try:
        ref = db.reference("via_master_record")
        data_copy = st.session_state.data.copy()
        
        # Format events for JSON storage
        if "events" in data_copy:
            serializable_events = []
            for e in data_copy["events"]:
                e_c = e.copy()
                e_c["date"] = e["date"].isoformat() if hasattr(e["date"], 'isoformat') else e["date"]
                e_c["start_time"] = e["start_time"].strftime("%H:%M") if hasattr(e["start_time"], 'strftime') else e["start_time"]
                e_c["end_time"] = e["end_time"].strftime("%H:%M") if hasattr(e["end_time"], 'strftime') else e["end_time"]
                serializable_events.append(e_c)
            data_copy["events"] = serializable_events
            
        ref.set(data_copy)
    except Exception as e:
        st.error(f"Save Error: {e}")

# Load state into session
if "data" not in st.session_state:
    st.session_state.data = load_data()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "u_name" not in st.session_state:
    st.session_state.u_name = ""
if "u_role" not in st.session_state:
    st.session_state.u_role = ""

# --- 4. AUTHENTICATION ---
USER_PASSWORDS = {
    "Teacher": "teach2026", "Chairman": "chair2026", "VIA Committee": "comm2026",
    "Skit Representative": "skit2026", "Brochure Representative": "brochure2026",
    "VIA members": "member2026", "Classmates": "class2026"
}

if not st.session_state.authenticated:
    st.title("🛡️ VIA Class Portal 2026")
    with st.form("login"):
        name_in = st.text_input("Name").strip().title()
        role_in = st.selectbox("Role", list(USER_PASSWORDS.keys()))
        pw_in = st.text_input("Password", type="password")
        if st.form_submit_button("Sign In"):
            if name_in and pw_in == USER_PASSWORDS.get(role_in):
                st.session_state.authenticated = True
                st.session_state.u_name = name_in
                st.session_state.u_role = role_in
                
                # Persistence: Add to accounts if new
                acc_list = st.session_state.data.get("accounts", [])
                if not any(a['name'] == name_in for a in acc_list):
                    st.session_state.data["accounts"].append({"name": name_in, "role": role_in})
                    save_data()
                st.rerun()
            else: st.error("Access Denied.")
    st.stop()

# --- 5. NAVIGATION (The Tab Menu) ---
c_name, c_role = st.session_state.u_name, st.session_state.u_role

st.sidebar.markdown(f"### 👤 {c_name}")
view_proj = st.sidebar.selectbox("📁 Select Project", ["SKIT", "BROCHURE"])

if st.sidebar.button("🔓 Logout", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()

# This creates the horizontal menu buttons at the top (No dots!)
tabs_list = ["🏠 Dashboard", "📝 Attendance", "🕒 Activity Log", "📊 Progress"]
if c_role == "Chairman":
    tabs_list.append("⚙️ Admin")

# active_tab is now a list of "containers"
active_tab = st.tabs(tabs_list)

# --- 6. PAGE CONTENT (Wrapped in Tabs) ---

# --- DASHBOARD TAB ---
with active_tab[0]:
    if page == "Dashboard":
        st.title(f"🚀 {view_proj} Project Portal")
    
    # --- QUICK STATS ---
    col_a, col_b, col_c = st.columns(3)
    
    # SAFE CALCULATION: This prevents the KeyError
    # It looks for 'contributions'. If missing, it uses an empty dictionary {}
    all_contribs = st.session_state.data.get('contributions', {})
    
    # Now we get the specific user's minutes. If they aren't there, use 0.
    user_minutes = all_contribs.get(c_name, 0)
    total_hours = user_minutes // 60
    
    # Safe check for events too
    all_events = st.session_state.data.get("events", [])
    upcoming_events = len([e for e in all_events if e.get("project") == view_proj])
    
    with col_a:
        st.metric("Your VIA Hours", f"{total_hours}h")
    with col_b:
        st.metric("Upcoming Events", upcoming_events)
    with col_c:
        st.metric("Project Status", "Active", delta="On Track")

    # --- MAIN CONTENT ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📅 Event RSVP")
        events = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
        
        if not events:
            st.info("No events scheduled yet.")
        else:
            for i, e in enumerate(events):
                e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
                # Expander for cleaner look
                with st.container(border=True):
                    st.write(f"**{e['type']}**")
                    st.caption(f"📍 {e['venue']} | ⏰ {e['start_time']}")
                    
                    # Simplified RSVP form
                    with st.expander("Update My RSVP"):
                        with st.form(f"v_{i}"):
                            s = st.segmented_control("Status", ["Attending", "Late", "Not Attending"])
                            r = st.text_input("Note/Reason", placeholder="e.g. Bringing props")
                            if st.form_submit_button("Confirm"):
                                # ... (Keep your existing save logic here) ...
                                save_data(); st.rerun()

    with col2:
        st.subheader("👥 Team Roster")
        members = [m for m in st.session_state.data["members"] if m["project"] == view_proj]
        for m in members:
            role_icon = "⭐" if m['is_rep'] else "👤"
            st.markdown(f"{role_icon} **{m['name']}**")
            st.caption(f"Focus: {m['sub_role']}")
    st.title(f"🚀 {view_proj} Dashboard")
    # ... (the stat cards, the RSVP form, etc.)

# --- ATTENDANCE TAB ---
with active_tab[1]:
    st.title("✅ Attendance")
    evs = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
    if evs:
        sel = st.selectbox("Select Event", [f"{e['type']} ({e['date']})" for e in evs])
        e = evs[[f"{e['type']} ({e['date']})" for e in evs].index(sel)]
        e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
        voters = [rv['name'] for rv in st.session_state.data["rsvp"] if rv['event_id']==e_id and rv['status'] in ["Attending", "Late"]]
        can_mark = is_chair or is_teach or (is_skit_rep and view_proj=="SKIT")
        
        for n in voters:
            rec = st.session_state.data["attendance"].get(e_id, {}).get(n, {"p": False, "d": "Full"})
            c1, c2, c3 = st.columns(3)
            c1.write(n)
            if can_mark:
                p = c2.checkbox("Present", value=rec["p"], key=f"p_{n}_{e_id}")
                d = c3.selectbox("Session", ["Full", "Half"], index=0 if rec["d"]=="Full" else 1, key=f"d_{n}_{e_id}")
                if e_id not in st.session_state.data["attendance"]: st.session_state.data["attendance"][e_id] = {}
                st.session_state.data["attendance"][e_id][n] = {"p": p, "d": d}
            else:
                c2.write("✅" if rec["p"] else "❌")
                c3.write(rec["d"])
        if can_mark and st.button("Save Attendance"): save_data(); st.success("Updated in Database")
    st.title("📝 Attendance Tracker")
    # ...

# --- ACTIVITY LOG TAB ---
with active_tab[2]:
    st.title("🕒 Activity Log")
    st.info("Submit your hours here. The Chairman will verify these for VIA records.")

    # 1. FORM TO SUBMIT NEW LOG
    with st.expander("➕ Log New Activity", expanded=True):
        with st.form("log_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                log_date = st.date_input("Date of Activity", value=date.today())
                log_hours = st.number_input("Minutes spent", min_value=5, step=5, help="Enter total minutes")
            with col2:
                log_task = st.text_input("What did you do?", placeholder="e.g. Painted the backdrop")
                log_proj = st.selectbox("Project", ["SKIT", "BROCHURE"])
            
            if st.form_submit_button("Submit Log"):
                new_entry = {
                    "user": c_name,
                    "date": str(log_date),
                    "minutes": log_hours,
                    "task": log_task,
                    "project": log_proj,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                
                # Save to st.session_state
                if "logs" not in st.session_state.data:
                    st.session_state.data["logs"] = []
                st.session_state.data["logs"].append(new_entry)
                
                # Update total contributions
                contribs = st.session_state.data.get("contributions", {})
                contribs[c_name] = contribs.get(c_name, 0) + log_hours
                st.session_state.data["contributions"] = contribs
                
                save_data()
                st.success("Activity logged successfully!")
                st.rerun()

    st.markdown("---")

    # 2. VIEW PREVIOUS LOGS
    st.subheader("📜 Your Recent Entries")
    
    # Filter logs for the current user and selected project
    all_logs = st.session_state.data.get("logs", [])
    user_logs = [l for l in all_logs if l.get("user") == c_name and l.get("project") == view_proj]

    if not user_logs:
        st.write("No logs found for this project yet.")
    else:
        # Convert to DataFrame for a nice table look
        df_logs = pd.DataFrame(user_logs)
        # Clean up column names for display
        df_logs = df_logs[["date", "minutes", "task"]].sort_values(by="date", ascending=False)
        st.table(df_logs)

# --- CONTRIBUTION TRACKER TAB ---
with active_tab[3]:
    st.title("⏳ Time Management")
    if is_chair or (is_skit_rep and view_proj=="SKIT") or (is_broch_rep and view_proj=="BROCHURE"):
        st.subheader("Add Contribution")
        proj_members = [m["name"] for m in st.session_state.data["members"] if m["project"] == view_proj]
        if proj_members:
            with st.form("time_input"):
                target = st.selectbox("Select Member", proj_members)
                c_h, c_m = st.columns(2)
                h = c_h.number_input("Hours", 0, 24)
                m = c_m.number_input("Minutes", 0, 59)
                if st.form_submit_button("Add Time"):
                    total = (h * 60) + m
                    st.session_state.data["contributions"][target] = st.session_state.data["contributions"].get(target, 0) + total
                    save_data(); st.rerun()

    sum_list = [{"Name": m["name"], "Total": f"{st.session_state.data['contributions'].get(m['name'],0)//60}h {st.session_state.data['contributions'].get(m['name'],0)%60}m"} 
               for m in st.session_state.data["members"] if m["project"] == view_proj]
    if sum_list: st.table(pd.DataFrame(sum_list))
    st.title("📊 Progress Tracker")
    # ...

# --- ADMIN TAB ---
if c_role == "Chairman":
    with active_tab[4]:
        # PASTE ALL YOUR MANAGEMENT CENTER CODE HERE
        st.title("⚙️ Admin Control")
        # ...

# --- MANAGEMENT CENTER ---
elif page == "Management Center" and is_chair:
    st.title("👑 Chairman Control")
    t1, t2, t3 = st.tabs(["Roster", "Events", "Accounts"])
    with t1:
        with st.form("m_man"):
            n, p = st.text_input("Name"), st.selectbox("Project", ["SKIT", "BROCHURE"])
            r = st.checkbox("Representative")
            s = st.selectbox("Role", ["Actors", "Prop makers", "Cameraman", "N/A"]) if p=="SKIT" else "Designer"
            if st.form_submit_button("Save Member"):
                st.session_state.data["members"] = [x for x in st.session_state.data["members"] if x['name'] != n]
                st.session_state.data["members"].append({"name": n, "project": p, "is_rep": r, "sub_role": s})
                save_data(); st.rerun()
    with t2:
        with st.form("e_man"):
            p, t, d = st.selectbox("Project", ["SKIT", "BROCHURE"]), st.selectbox("Type", ["Discussion", "Rehearsal"]), st.date_input("Date")
            s, et, v = st.time_input("Start"), st.time_input("End"), st.text_input("Venue")
            if st.form_submit_button("Add Event"):
                st.session_state.data["events"].append({"project": p, "type": t, "date": d, "start_time": s, "end_time": et, "venue": v})
                save_data(); st.rerun()
    with t3:
        for i, a in enumerate(st.session_state.data.get("accounts", [])):
            c1, c2 = st.columns([4, 1])
            c1.write(f"{a['name']} ({a['role']})")
            if c2.button("Delete Account", key=f"da_{i}"):
                st.session_state.data["accounts"].pop(i); save_data(); st.rerun()
