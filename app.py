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

# Ensure all required data keys exist so the rest of the app doesn't crash
required_keys = ["members", "accounts", "logs", "contributions", "events", "rsvp", "attendance"]
for key in required_keys:
    if key not in st.session_state.data:
        # Create the missing folder (as a list or dict depending on the key)
        st.session_state.data[key] = {} if key in ["contributions", "attendance"] else []

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
c_name = st.session_state.u_name
c_role = st.session_state.u_role

# ADD THESE LINES HERE to fix the NameError
is_chair = (c_role == "Chairman")
is_teach = (c_role == "Teacher")
# Check if they are a representative (adjust 'is_rep' to match your data key)
is_skit_rep = any(m['name'] == c_name and m.get('is_rep') for m in st.session_state.data.get('members', []) if m.get('project') == "SKIT")

# Define tabs
tabs_list = ["🏠 Dashboard", "📝 Attendance", "🕒 Activity Log", "📊 Progress"]
if is_chair:
    tabs_list.append("⚙️ Admin")

active_tab = st.tabs(tabs_list)
# --- SIDEBAR UI ---
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
    all_contribs = st.session_state.data.get('contributions', {})
    user_minutes = all_contribs.get(c_name, 0)
    
    all_events = st.session_state.data.get("events", [])
    upcoming_events = len([e for e in all_events if e.get("project") == view_proj])
    
    col_a.metric("Your VIA Hours", f"{user_minutes // 60}h")
    col_b.metric("Upcoming Events", upcoming_events)
    col_c.metric("Project Status", "Active", delta="On Track")

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📅 Event RSVP")
        events = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
        
        if not events:
            st.info("No events scheduled yet.")
        else:
            for i, e in enumerate(events):
                is_cancelled = e.get("status") == "Cancelled"
                with st.container(border=True):
                    if is_cancelled:
                        st.error(f"🚫 **CANCELLED: {e['type']}**")
                        if e.get("note"): st.warning(f"**Reason:** {e['note']}")
                    else:
                        st.write(f"**{e['type']}**")
                    
                    st.caption(f"📍 {e['venue']} | ⏰ {e['start_time']}")

                    if not is_cancelled:
                        with st.expander("Update My RSVP"):
                            with st.form(f"rsvp_form_{i}"):
                                s = st.segmented_control("Status", ["Attending", "Late", "Not Attending"])
                                r = st.text_input("Note/Reason")
                                if st.form_submit_button("Confirm RSVP"):
                                    e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
                                    new_rsvp = {"event_id": e_id, "name": c_name, "status": s, "note": r}
                                    st.session_state.data["rsvp"] = [x for x in st.session_state.data.get("rsvp", []) if not (x['event_id'] == e_id and x['name'] == c_name)]
                                    st.session_state.data["rsvp"].append(new_rsvp)
                                    save_data(); st.success("RSVP Saved!"); st.rerun()
                    else:
                        st.info("RSVP disabled for cancelled event.")

    with col2:
        st.subheader("👥 Team Roster")
        members = [m for m in st.session_state.data["members"] if m["project"] == view_proj]
        for m in members:
            st.markdown(f"{'⭐' if m['is_rep'] else '👤'} **{m['name']}**")
            st.caption(f"Focus: {m['sub_role']}")

# --- TAB 1: ATTENDANCE ---
with active_tab[1]:
    st.title("✅ Attendance Tracker")
    evs = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
    if evs:
        sel = st.selectbox("Select Event", [f"{e['type']} ({e['date']})" for e in evs])
        idx = [f"{e['type']} ({e['date']})" for e in evs].index(sel)
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
                    p = c2.checkbox("Present", value=rec["p"], key=f"p_{n}_{e_id}")
                    d = c3.selectbox("Session", ["Full", "Half"], index=0 if rec["d"]=="Full" else 1, key=f"d_{n}_{e_id}")
                    if e_id not in st.session_state.data["attendance"]: st.session_state.data["attendance"][e_id] = {}
                    st.session_state.data["attendance"][e_id][n] = {"p": p, "d": d}
                else:
                    c2.write("✅" if rec["p"] else "❌")
                    c3.write(rec["d"])
            if (is_chair or is_teach) and st.button("Save Attendance"): 
                save_data(); st.success("Saved!")

# --- TAB 2: ACTIVITY LOG ---
with active_tab[2]:
    st.title("🕒 Activity Log")
    with st.expander("➕ Log New Activity"):
        with st.form("log_form"):
            ld = st.date_input("Date", value=date.today())
            lm = st.number_input("Minutes", min_value=5, step=5)
            lt = st.text_input("Task Description")
            lp = st.selectbox("Project", ["SKIT", "BROCHURE"])
            if st.form_submit_button("Submit Log"):
                st.session_state.data["logs"].append({"user": c_name, "date": str(ld), "minutes": lm, "task": lt, "project": lp})
                all_contribs[c_name] = all_contribs.get(c_name, 0) + lm
                save_data(); st.rerun()

# --- TAB 3: PROGRESS ---
with active_tab[3]:
    st.title("📊 Progress Tracker")
    is_broch_rep = any(m['name'] == c_name and m.get('is_rep') for m in st.session_state.data.get('members', []) if m.get('project') == "BROCHURE")
    
    if is_chair or (is_skit_rep and view_proj=="SKIT") or (is_broch_rep and view_proj=="BROCHURE"):
        with st.form(key=f"time_add_{view_proj}"):
            st.subheader("Add Extra Contribution")
            target = st.selectbox("Member", [m['name'] for m in members])
            h = st.number_input("Hours", min_value=0)
            if st.form_submit_button("Add Time"):
                st.session_state.data["contributions"][target] = st.session_state.data["contributions"].get(target, 0) + (h*60)
                save_data(); st.rerun()

    sum_list = [{"Name": m["name"], "Total": f"{all_contribs.get(m['name'], 0)//60}h"} for m in members]
    st.table(pd.DataFrame(sum_list))

# --- TAB 4: ADMIN ---
if is_chair:
    with active_tab[4]:
        st.title("⚙️ Admin Control")
        t1, t2, t3 = st.tabs(["Roster", "Events", "Accounts"])
        
        with t1:
            st.subheader("Manage Roster")
            col_skit, col_broch = st.columns(2)
            with col_skit:
                st.write("🎭 **SKIT**")
                for i, m in enumerate([x for x in st.session_state.data["members"] if x['project']=="SKIT"]):
                    if st.button(f"Delete {m['name']}", key=f"ds_{i}"):
                        st.session_state.data["members"] = [x for x in st.session_state.data["members"] if x['name'] != m['name']]
                        save_data(); st.rerun()
            with col_broch:
                st.write("📄 **BROCHURE**")
                for i, m in enumerate([x for x in st.session_state.data["members"] if x['project']=="BROCHURE"]):
                    if st.button(f"Delete {m['name']}", key=f"db_{i}"):
                        st.session_state.data["members"] = [x for x in st.session_state.data["members"] if x['name'] != m['name']]
                        save_data(); st.rerun()

        with t2:
            with st.form("e_man"):
                p = st.selectbox("Proj", ["SKIT", "BROCHURE"])
                type_ev = st.selectbox("Type", ["Discussion", "Rehearsal"])
                d_ev = st.date_input("Date")
                s_ev = st.time_input("Start")
                if st.form_submit_button("Add Event"):
                    st.session_state.data["events"].append({"project": p, "type": type_ev, "date": d_ev, "start_time": s_ev, "status": "Active"})
                    save_data(); st.rerun()
            
            st.divider()
            for i, ev in enumerate(st.session_state.data.get("events", [])):
                with st.expander(f"Edit: {ev['type']} ({ev['date']})"):
                    with st.form(f"ed_ev_{i}"):
                        note = st.text_input("Cancel Note", value=ev.get("note", ""))
                        stat = st.selectbox("Status", ["Active", "Cancelled"], index=0 if ev.get("status")=="Active" else 1)
                        if st.form_submit_button("Save"):
                            st.session_state.data["events"][i]["note"] = note
                            st.session_state.data["events"][i]["status"] = stat
                            save_data(); st.rerun()
                    if st.button("Delete Permanently", key=f"f_del_{i}"):
                        st.session_state.data["events"].pop(i); save_data(); st.rerun()

        with t3:
            for i, a in enumerate(st.session_state.data.get("accounts", [])):
                st.write(f"{a['name']} ({a['role']})")
                if st.button("Delete Account", key=f"acc_del_{i}"):
                    st.session_state.data["accounts"].pop(i); save_data(); st.rerun()
