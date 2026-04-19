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
tabs_list = ["🏠 Dashboard", "📝 Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
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
    
    # Column A: Hours (Students only) or Role (Teachers)
    if c_role != "Teacher":
        user_minutes = all_contribs.get(c_name, 0)
        col_a.metric("Your VIA Hours", f"{user_minutes // 60}h {user_minutes % 60}m")
    else:
        col_a.metric("Role", "Faculty Observer")
        
    # Column B: Upcoming Events
    all_events = st.session_state.data.get("events", [])
    upcoming_events = len([e for e in all_events if e.get("project") == view_proj])
    col_b.metric("Upcoming Events", upcoming_events)
    
    # Column C: Project Status
    col_c.metric(label="Project Status", value="Active", delta="On Track")

    # --- Lower Section: RSVP and Roster ---
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
                            # Unique key includes project and index to avoid collisions
                            with st.form(f"rsvp_form_{i}_{view_proj}"):
                                s = st.segmented_control("Status", ["Attending", "Late", "Not Attending"])
                                r = st.text_input("Note/Reason")
                                if st.form_submit_button("Confirm RSVP"):
                                    e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
                                    new_rsvp = {"event_id": e_id, "name": c_name, "status": s, "note": r}
                                    st.session_state.data["rsvp"] = [x for x in st.session_state.data.get("rsvp", []) if not (x['event_id'] == e_id and x['name'] == c_name)]
                                    st.session_state.data["rsvp"].append(new_rsvp)
                                    save_data()
                                    st.success("RSVP Saved!")
                                    st.rerun()
                    else:
                        st.info("RSVP disabled for cancelled event.")

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
    
    # 1. SUBMISSION FORM (Only for Members/Reps/Chair - Teachers usually don't log hours)
    if c_role != "Teacher":
        with st.expander("➕ Log New Activity"):
            with st.form(key=f"activity_log_form_{view_proj}"):
                ld = st.date_input("Date", value=date.today())
                lm = st.number_input("Minutes", min_value=5, step=5)
                lt = st.text_input("Task Description")
                lp = st.selectbox("Project", ["SKIT", "BROCHURE"])
                if st.form_submit_button("Submit Log"):
                    new_log = {
                        "log_id": f"log_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "user": c_name,
                        "date": str(ld),
                        "minutes": lm,
                        "task": lt,
                        "project": lp,
                        "comments": []  # Initialize empty comments list
                    }
                    st.session_state.data["logs"].append(new_log)
                    st.session_state.data["contributions"][c_name] = st.session_state.data["contributions"].get(c_name, 0) + lm
                    save_data(); st.success("Activity Logged!"); st.rerun()

    st.divider()
    st.subheader("📜 Recent Activity & Teacher Feedback")

    # 2. DISPLAY LOGS WITH COMMENT LOGIC
    all_logs = st.session_state.data.get("logs", [])
    # Filter logs for the current project
    proj_logs = [l for l in all_logs if l.get("project") == view_proj]

    if not proj_logs:
        st.info("No activities logged for this project yet.")
    else:
        # Show logs in reverse order (newest first)
        for i, log in enumerate(reversed(proj_logs)):
            with st.container(border=True):
                col_text, col_stats = st.columns([3, 1])
                
                with col_text:
                    st.markdown(f"**{log['user']}** - {log['task']}")
                    st.caption(f"📅 {log['date']}")
                
                with col_stats:
                    st.info(f"{log['minutes']} mins")

                # --- COMMENTS SECTION ---
                comments = log.get("comments", [])
                if comments:
                    st.markdown("---")
                    st.markdown("**💬 Teacher Comments:**")
                    for c in comments:
                        st.markdown(f"> **{c['teacher']}:** {c['text']}")

                # --- TEACHER ONLY: COMMENT INPUT ---
                if c_role == "Teacher":
                    with st.expander("📝 Add Comment"):
                        with st.form(key=f"comment_form_{i}"):
                            t_comment = st.text_area("Feedback", placeholder="Enter your comments here...")
                            if st.form_submit_button("Post Comment"):
                                if t_comment:
                                    # Create the comment object
                                    new_comment = {
                                        "teacher": c_name, # Records the teacher's name
                                        "text": t_comment,
                                        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                                    }
                                    
                                    # Find the original log in the main database and append the comment
                                    # (Since we are using reversed, we find by log_id or unique index)
                                    for original_log in st.session_state.data["logs"]:
                                        if original_log.get("log_id") == log.get("log_id"):
                                            if "comments" not in original_log:
                                                original_log["comments"] = []
                                            original_log["comments"].append(new_comment)
                                            break
                                    
                                    save_data()
                                    st.success("Comment added!")
                                    st.rerun()

# --- TAB 3: PROGRESS ---
with active_tab[3]:
    st.title("📊 Progress Tracker")
    is_broch_rep = any(m['name'] == c_name and m.get('is_rep') for m in st.session_state.data.get('members', []) if m.get('project') == "BROCHURE")
    
    if is_chair or (is_skit_rep and view_proj=="SKIT") or (is_broch_rep and view_proj=="BROCHURE"):
        with st.form(key=f"manual_time_add_{view_proj}"):
            st.subheader("Add Extra Contribution")
            target = st.selectbox("Member", [m['name'] for m in members] if members else ["No Members Found"])
            h = st.number_input("Hours", min_value=0)
            if st.form_submit_button("Add Time"):
                if target != "No Members Found":
                    st.session_state.data["contributions"][target] = st.session_state.data["contributions"].get(target, 0) + (h*60)
                    save_data(); st.success(f"Added hours to {target}"); st.rerun()

    sum_list = [{"Name": m["name"], "Total": f"{all_contribs.get(m['name'], 0)//60}h {all_contribs.get(m['name'], 0)%60}m"} for m in members]
    if sum_list:
        st.table(pd.DataFrame(sum_list))
    else:
        st.info("No member data available.")

# --- TAB 4: DIRECTORY ---
with active_tab[4]:
    st.title("📁 Official Class Roster & VIA Summary")
    st.info("This list only includes members officially added to the project roster by the Chairman.")
    
    # Switch data source to 'members' instead of 'accounts'
    all_members = st.session_state.data.get("members", [])
    all_contribs = st.session_state.data.get("contributions", {})
    all_logs = st.session_state.data.get("logs", [])
    
    if not all_members:
        st.warning("The roster is currently empty. Please add members in the Admin tab.")
    else:
        summary_data = []
        
        for m in all_members:
            name = m['name']
            project = m['project']
            role_in_project = m.get('sub_role', 'Member')
            
            # 1. Get VIA Time for this specific member
            total_mins = all_contribs.get(name, 0)
            h = total_mins // 60
            mins = total_mins % 60
            via_time_display = f"{h}h {mins}m"
            
            # 2. Get Contribution Details from logs
            tasks = [log['task'] for log in all_logs if log['user'] == name]
            if tasks:
                contribution_detail = " | ".join(tasks[-3:]) 
            else:
                contribution_detail = "No activities logged yet"
                
            summary_data.append({
                "Student Name": name,
                "Project": project,
                "Role": role_in_project,
                "Total VIA Time": via_time_display,
                "Recent Contributions": contribution_detail
            })
        
        # Create the DataFrame
        df_summary = pd.DataFrame(summary_data)
        
        # Add a filter for Project to make it easier for teachers
        proj_filter = st.radio("Filter by Project", ["All", "SKIT", "BROCHURE"], horizontal=True)
        if proj_filter != "All":
            df_summary = df_summary[df_summary["Project"] == proj_filter]

        # Display the data
        st.dataframe(
            df_summary, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Total VIA Time": st.column_config.TextColumn("⏱️ Hours"),
                "Recent Contributions": st.column_config.TextColumn("🛠️ Activity Summary")
            }
        )
    
# --- TAB 5: ADMIN ---
if is_chair:
    with active_tab[5]: # This must be 5 now!
        st.title("⚙️ Admin Control")
        t1, t2, t3 = st.tabs(["Roster", "Events", "Accounts"])
        
        with t1:
            st.subheader("➕ Add New Member")
            with st.form(key="admin_add_member_form", clear_on_submit=True):
                col_n, col_p = st.columns(2)
                n = col_n.text_input("Name").strip().title()
                p = col_p.selectbox("Project", ["SKIT", "BROCHURE"])
                
                col_r, col_s = st.columns(2)
                r = col_r.checkbox("Representative?")
                s = col_s.selectbox("Role", ["Actors", "Prop makers", "Cameraman", "Designer", "Writer", "N/A"])
                
                if st.form_submit_button("Save Member"):
                    if n:
                        st.session_state.data["members"].append({"name": n, "project": p, "is_rep": r, "sub_role": s})
                        save_data(); st.success(f"Added {n}!"); st.rerun()
            
            st.divider()
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
            st.subheader("Create Event")
            with st.form("admin_event_create"):
                p = st.selectbox("Proj", ["SKIT", "BROCHURE"])
                type_ev = st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session"])
                d_ev = st.date_input("Date")
                s_ev = st.time_input("Start")
                if st.form_submit_button("Add Event"):
                    st.session_state.data["events"].append({"project": p, "type": type_ev, "date": d_ev, "start_time": s_ev, "status": "Active"})
                    save_data(); st.success("Event Created"); st.rerun()
            
            st.divider()
            for i, ev in enumerate(st.session_state.data.get("events", [])):
                with st.expander(f"Edit: {ev['type']} ({ev['date']})"):
                    with st.form(f"ed_ev_form_{i}"):
                        note = st.text_input("Cancel Note", value=ev.get("note", ""))
                        stat = st.selectbox("Status", ["Active", "Cancelled"], index=0 if ev.get("status")=="Active" else 1)
                        if st.form_submit_button("Save"):
                            st.session_state.data["events"][i]["note"] = note
                            st.session_state.data["events"][i]["status"] = stat
                            save_data(); st.rerun()
                    if st.button("Delete Permanently", key=f"f_del_ev_{i}"):
                        st.session_state.data["events"].pop(i); save_data(); st.rerun()

        with t3:
            st.subheader("Manage Accounts")
            for i, a in enumerate(st.session_state.data.get("accounts", [])):
                c1, c2 = st.columns([4, 1])
                c1.write(f"{a['name']} ({a['role']})")
                if c2.button("Delete", key=f"acc_del_{i}"):
                    st.session_state.data["accounts"].pop(i); save_data(); st.rerun()
