import streamlit as st
import pandas as pd
from datetime import datetime, time, date
import firebase_admin
from firebase_admin import credentials, db # Using 'db' for Realtime Database
import json
import os

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide")

# --- 2. FIREBASE INITIALIZATION ---
if not firebase_admin._apps:
    try:
        # Handle Credentials
        if "firebase" in st.secrets:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
            
        # STEP 1: Define the URL clearly
        # Make sure this link is YOURS from the Firebase Console
        URL = "https://via-report-default-rtdb.asia-southeast1.firebasedatabase.app/" 

        st.write(f"Testing URL: {URL}")
        
        # STEP 2: Initialize
        firebase_admin.initialize_app(cred, {
            'databaseURL': URL  # <-- The 'URL' must match the variable above
        })
    except Exception as e:
        st.error(f"Firebase Setup Error: {e}")
        st.stop()
        
# --- 3. DATA PERSISTENCE (REALTIME DB) ---
def load_data():
    try:
        ref = db.reference("via_master_record")
        data = ref.get()
        if data:
            # Convert date/time strings back to Python objects
            if "events" in data:
                for e in data["events"]:
                    try:
                        e["date"] = datetime.strptime(e["date"], "%Y-%m-%d").date()
                        e["start_time"] = datetime.strptime(e["start_time"], "%H:%M").time()
                        e["end_time"] = datetime.strptime(e["end_time"], "%H:%M").time()
                    except: continue
            return data
        else:
            # First time setup
            return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}}
    except Exception as e:
        st.error(f"Load Error: {e}")
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

# --- 5. NAVIGATION ---
c_name, c_role = st.session_state.u_name, st.session_state.u_role
is_chair = (c_role == "Chairman")
is_teach = (c_role == "Teacher")
is_skit_rep = (c_role == "Skit Representative")
is_broch_rep = (c_role == "Brochure Representative")

st.sidebar.title(f"👤 {c_name}")
if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()

view_proj = st.sidebar.radio("Project View", ["SKIT", "BROCHURE"])
nav = ["Dashboard", "Attendance", "Activity Log", "Contribution Tracker"]
if is_chair: nav.append("Management Center")
page = st.sidebar.radio("Menu", nav)

# --- DASHBOARD & RSVP ---
if page == "Dashboard":
    st.title(f"🚀 {view_proj} Project")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📅 RSVP & Events")
        events = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
        for i, e in enumerate(events):
            e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
            vote = next((r for r in st.session_state.data["rsvp"] if r['name'] == c_name and r['event_id'] == e_id), None)
            with st.expander(f"{e['type']} - {e['date']} @ {e['venue']}"):
                with st.form(f"v_{i}"):
                    s = st.radio("Status", ["Attending", "Not Attending", "Late"], index=0)
                    r = st.text_input("Reason", value=vote['reason'] if vote else "N/A")
                    if st.form_submit_button("Submit RSVP"):
                        st.session_state.data["rsvp"] = [rv for rv in st.session_state.data["rsvp"] if not (rv['name']==c_name and rv['event_id']==e_id)]
                        st.session_state.data["rsvp"].append({"event_id":e_id, "name":c_name, "status":s, "reason":r})
                        save_data(); st.rerun()
                if is_chair or (is_skit_rep and view_proj=="SKIT"):
                    st.write("**Responses:**")
                    st.table(pd.DataFrame([rv for rv in st.session_state.data["rsvp"] if rv['event_id']==e_id]))
    with col2:
        st.subheader("👥 Roster")
        for m in [m for m in st.session_state.data["members"] if m["project"] == view_proj]:
            st.write(f"**{m['name']}** {'(REP)' if m['is_rep'] else ''}")
            st.caption(f"Role: {m['sub_role']}")

# --- ATTENDANCE ---
elif page == "Attendance":
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

# --- CONTRIBUTION TRACKER ---
elif page == "Contribution Tracker":
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
