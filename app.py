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
                # SECRET OVERRIDE: 
                # If they pick VIA Committee + use the Chairman password
                if role_in == "VIA Committee" and pw_in == CHAIRMAN_SECRET_PW:
                    st.session_state.authenticated = True
                    st.session_state.u_name = name_in
                    st.session_state.u_role = "Chairman" # Elevated Role
                    login_success = True
                
                # NORMAL LOGIN:
                elif pw_in == USER_PASSWORDS.get(role_in):
                    st.session_state.authenticated = True
                    st.session_state.u_name = name_in
                    st.session_state.u_role = role_in
                    login_success = True
                else:
                    st.error("Access Denied: Incorrect password.")
                    login_success = False

                if login_success:
                    # Sync with account list in database
                    acc_list = st.session_state.data.get("accounts", [])
                    if not any(a['name'] == name_in for a in acc_list):
                        st.session_state.data["accounts"].append({
                            "name": name_in, 
                            "role": st.session_state.u_role
                        })
                        save_data()
                    st.rerun()
            else:
                st.error("Please enter your name.")
    st.stop()

# --- 5. NAVIGATION & PERMISSIONS ---
c_name = st.session_state.u_name
c_role = st.session_state.u_role

# Define these clearly so all tabs can see them
is_chair = (c_role == "Chairman")
is_teach = (c_role == "Teacher")
is_rep   = "Representative" in c_role  # <--- THIS IS THE MISSING LINE
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
    
    if c_role != "Teacher":
        # Look for Name + Project from sidebar
        u_key = f"{c_name}_{view_proj}"
        user_minutes = st.session_state.data.get('contributions', {}).get(u_key, 0)
        col_a.metric(f"Your {view_proj} Hours", f"{user_minutes // 60}h {user_minutes % 60}m")
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
    
    if c_role != "Teacher":
        with st.expander("➕ Log New Activity"):
            with st.form(key=f"activity_log_form_{view_proj}"):
                ld = st.date_input("Date", value=date.today())
                lm = st.number_input("Minutes", min_value=5, step=5)
                lt = st.text_input("Task Description")
                lp = st.selectbox("Project", ["SKIT", "BROCHURE"]) # The project being worked on
                
                if st.form_submit_button("Submit Log"):
                    # 1. Create the unique key for this specific project role
                    u_key = f"{c_name}_{lp}"
                    
                    # 2. Update the specific project bucket in contributions
                    st.session_state.data["contributions"][u_key] = st.session_state.data["contributions"].get(u_key, 0) + lm
                    
                    # 3. Add to logs
                    new_log = {
                        "log_id": f"log_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "user": c_name,
                        "date": str(ld),
                        "minutes": lm,
                        "task": lt,
                        "project": lp, # Saves the project name
                        "comments": []
                    }
                    st.session_state.data["logs"].append(new_log)
                    save_data()
                    st.success(f"Logged {lm} mins for {lp}!")
                    st.rerun()

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
    st.title("📊 Class Progress Tracker")
    
    all_members = st.session_state.data.get("members", [])
    all_contribs = st.session_state.data.get("contributions", {})
    
    # 1. SUMMARY METRIC
    total_class_mins = sum(all_contribs.values())
    st.metric("Total Class VIA Minutes", f"{total_class_mins} mins")
    
    st.divider()

    # 2. PROJECT-SPECIFIC ADJUSTMENTS (Chairman/Rep Only)
    if is_chair or is_rep:
        st.subheader("⚙️ Project Time Adjustments")
        col_add, col_sub = st.columns(2)
        
        with col_add:
            with st.expander("➕ Add Project Bonus"):
                with st.form("add_time_proj_form"):
                    target_proj = st.selectbox("Select Project", ["SKIT", "BROCHURE"], key="add_proj_sel")
                    proj_names = [m['name'] for m in all_members if m['project'] == target_proj]
                    target_user = st.selectbox("Select Student", proj_names if proj_names else ["No members found"], key="add_user_sel")
                    bonus_mins = st.number_input("Minutes to Add", min_value=1, step=5)
                    reason_add = st.text_input("Reason")
                    
                    if st.form_submit_button("Apply Project Bonus"):
                        if target_user != "No members found" and reason_add:
                            # UNIQUE KEY: Name + Project
                            u_key = f"{target_user}_{target_proj}"
                            st.session_state.data["contributions"][u_key] = st.session_state.data["contributions"].get(u_key, 0) + bonus_mins
                            
                            st.session_state.data["logs"].append({
                                "log_id": f"bonus_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                "user": target_user, "date": str(date.today()), "minutes": bonus_mins,
                                "task": f"BONUS ({target_proj}): {reason_add}", "project": target_proj, "comments": []
                            })
                            save_data(); st.success("Added!"); st.rerun()

        with col_sub:
            with st.expander("➖ Deduct Project Time"):
                with st.form("deduct_time_proj_form"):
                    sub_proj = st.selectbox("Select Project", ["SKIT", "BROCHURE"], key="sub_proj_sel")
                    sub_names = [m['name'] for m in all_members if m['project'] == sub_proj]
                    deduct_user = st.selectbox("Select Student", sub_names if sub_names else ["No members found"], key="sub_user_sel")
                    penalty_mins = st.number_input("Minutes to Deduct", min_value=1, step=5)
                    reason_sub = st.text_input("Reason (Required)")
                    
                    if st.form_submit_button("Apply Deduction"):
                        if deduct_user != "No members found" and reason_sub:
                            u_key = f"{deduct_user}_{sub_proj}"
                            curr = st.session_state.data["contributions"].get(u_key, 0)
                            st.session_state.data["contributions"][u_key] = max(0, curr - penalty_mins)
                            
                            st.session_state.data["logs"].append({
                                "log_id": f"deduct_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                "user": deduct_user, "date": str(date.today()), "minutes": -penalty_mins,
                                "task": f"🛑 DEDUCTION ({sub_proj}): {reason_sub}", "project": sub_proj, "comments": []
                            })
                            save_data(); st.warning("Deducted!"); st.rerun()

    st.divider()
    
    # 3. GROUPED PROGRESS BARS (Only one set of bars now)
    st.subheader("👥 Progress by Project Team")
    if not all_members:
        st.info("Add members in Admin to see progress.")
    else:
        p_skit, p_broch = st.tabs(["🎭 Skit Team", "📄 Brochure Team"])
        
        with p_skit:
            skit_members = [m for m in all_members if m['project'] == "SKIT"]
            for m in skit_members:
                m_key = f"{m['name']}_SKIT"
                m_mins = all_contribs.get(m_key, 0)
                c1, c2 = st.columns([1, 3])
                c1.write(f"**{m['name']}**")
                c2.progress(min(1.0, m_mins/300), text=f"{m_mins//60}h {m_mins%60}m")

        with p_broch:
            broch_members = [m for m in all_members if m['project'] == "BROCHURE"]
            for m in broch_members:
                m_key = f"{m['name']}_BROCHURE"
                m_mins = all_contribs.get(m_key, 0)
                c1, c2 = st.columns([1, 3])
                c1.write(f"**{m['name']}**")
                c2.progress(min(1.0, m_mins/300), text=f"{m_mins//60}h {m_mins%60}m")    
                
# --- TAB 4: DIRECTORY ---
with active_tab[4]:
    st.title("📁 Official Class Directory")
    
    # 1. TOP LEVEL STATS
    all_members = st.session_state.data.get("members", [])
    all_contribs = st.session_state.data.get("contributions", {})
    all_logs = st.session_state.data.get("logs", [])
    
    m_col1, m_col2, m_col3 = st.columns(3)
    
    # Calculate Total Class Minutes (Sum of all project-specific keys)
    total_mins = sum(all_contribs.values())
    num_members = len(all_members)
    
    if num_members > 0:
        avg_mins_total = total_mins // num_members
        avg_h = avg_mins_total // 60
        avg_m = avg_mins_total % 60
        avg_display = f"{avg_h}h {avg_m}m"
    else:
        avg_display = "0h 0m"

    # Display Metrics
    m_col1.metric("Total Members", num_members)
    m_col2.metric("Average Time", avg_display)
    m_col3.metric("Active Projects", "2") 
    
    st.divider()

    if not all_members:
        st.warning("The roster is empty. Add members in the Admin tab to see them here.")
    else:
        # 2. DATA PROCESSING (Modified for Project Uniqueness)
        summary_data = []
        for m in all_members:
            name = m['name']
            proj = m['project'] # 'SKIT' or 'BROCHURE'
            
            # --- UPDATED LOGIC HERE ---
            # 1. Time calculation using the unique Name_Project key
            unique_key = f"{name}_{proj}"
            t_mins = all_contribs.get(unique_key, 0)
            time_fmt = f"{t_mins // 60}h {t_mins % 60}m"
            
            # 2. Filter logs for this specific user AND this specific project
            # This ensures John's Skit row doesn't show his Brochure tasks.
            u_tasks = [l['task'] for l in all_logs if l['user'] == name and l.get('project') == proj]
            recent = " | ".join(u_tasks[-2:]) if u_tasks else "No activity yet"
            # --------------------------
            
            summary_data.append({
                "NAME": name,
                "PROJECT": proj,
                "ROLE": m.get('sub_role', 'Member'),
                "VIA TIME": time_fmt,
                "LATEST TASKS": recent,
                "STATUS": "✅ Active" if u_tasks else "⏳ No Logs"
            })
        
        df = pd.DataFrame(summary_data)

        # 3. SEARCH & FILTER
        f1, f2 = st.columns([2, 1])
        search = f1.text_input("🔍 Search Classmate", placeholder="Type a name...")
        p_filter = f2.selectbox("Filter Project", ["All Projects", "SKIT", "BROCHURE"])

        if search:
            df = df[df["NAME"].str.contains(search, case=False)]
        if p_filter != "All Projects":
            df = df[df["PROJECT"] == p_filter]

        # 4. DATAFRAME DISPLAY
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "NAME": st.column_config.TextColumn("👤 Name"),
                "PROJECT": st.column_config.TextColumn("📁 Project"),
                "ROLE": st.column_config.TextColumn("🎭 Role"),
                "VIA TIME": st.column_config.TextColumn("⏱️ Total Time"),
                "LATEST TASKS": st.column_config.TextColumn("📝 Latest Work"),
                "STATUS": st.column_config.TextColumn("📌 Status")
            }
        )

        # 5. CSV DOWNLOAD
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Directory as CSV",
            data=csv,
            file_name=f"VIA_Directory_{date.today()}.csv",
            mime='text/csv',
        )
        
# --- TAB 5: ADMIN ---

if st.session_state.u_role == "Chairman":
    with active_tab[5]:
        st.title("⚙️ Chairman Master Control")
        t1, t2, t3, t4 = st.tabs(["👥 Roster", "📅 Events", "🔐 Accounts", "⚖️ Corrections"])
        
        # --- SUB-TAB 1: ROSTER ---
        with t1:
            st.subheader("➕ Add Official Member")
            with st.form(key="admin_roster_entry_form", clear_on_submit=True):
                col_n, col_p = st.columns(2)
                n = col_n.text_input("Full Name").strip().title()
                p = col_p.selectbox("Assign Project", ["SKIT", "BROCHURE"])
                
                col_r, col_s = st.columns(2)
                r = col_r.checkbox("Is Representative?")
                s = col_s.selectbox(
                    "Specific Role", 
                    ["Actors", "Prop makers", "Cameraman", "Designer", "Editor", "Writer", "N/A"],
                    index=3 
                )
                
                if st.form_submit_button("Add to Roster"):
                    if n:
                        st.session_state.data["members"].append({
                            "name": n, "project": p, "is_rep": r, "sub_role": s
                        })
                        save_data()
                        st.success(f"✅ {n} added as {s}!")
                        st.rerun()
                    else:
                        st.error("Please enter a name.")

            st.divider()
            st.subheader("🗑️ Manage Roster")
            col_skit, col_broch = st.columns(2)
            
            with col_skit:
                st.write("🎭 **SKIT TEAM**")
                skit_list = [x for x in st.session_state.data["members"] if x['project'] == "SKIT"]
                if not skit_list:
                    st.caption("No members in Skit.")
                else:
                    for i, m in enumerate(skit_list):
                        if st.button(f"Remove {m['name']}", key=f"del_skit_{i}"):
                            # Modified to remove specific name AND project match to avoid accidental double-deletion
                            st.session_state.data["members"] = [x for x in st.session_state.data["members"] if not (x['name'] == m['name'] and x['project'] == "SKIT")]
                            save_data(); st.rerun()
            
            with col_broch:
                st.write("📄 **BROCHURE TEAM**")
                broch_list = [x for x in st.session_state.data["members"] if x['project'] == "BROCHURE"]
                if not broch_list:
                    st.caption("No members in Brochure.")
                else:
                    for i, m in enumerate(broch_list):
                        if st.button(f"Remove {m['name']}", key=f"del_broch_{i}"):
                            st.session_state.data["members"] = [x for x in st.session_state.data["members"] if not (x['name'] == m['name'] and x['project'] == "BROCHURE")]
                            save_data(); st.rerun()

        # --- SUB-TAB 2: EVENTS ---
        with t2:
            st.subheader("🗓️ Create Event")
            with st.form("admin_event_create"):
                ep = st.selectbox("Project", ["SKIT", "BROCHURE"])
                type_ev = st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"])
                d_ev = st.date_input("Date")
                s_ev = st.time_input("Start Time")
                if st.form_submit_button("Add Event"):
                    st.session_state.data["events"].append({
                        "project": ep, "type": type_ev, "date": str(d_ev), 
                        "start_time": str(s_ev), "status": "Active"
                    })
                    save_data(); st.success("Event Created"); st.rerun()
            
            st.divider()
            for i, ev in enumerate(st.session_state.data.get("events", [])):
                with st.expander(f"Edit: {ev['type']} ({ev['date']})"):
                    with st.form(f"ed_ev_form_{i}"):
                        note = st.text_input("Cancel Note", value=ev.get("note", ""))
                        stat = st.selectbox("Status", ["Active", "Cancelled"], index=0 if ev.get("status")=="Active" else 1)
                        if st.form_submit_button("Save Changes"):
                            st.session_state.data["events"][i]["note"] = note
                            st.session_state.data["events"][i]["status"] = stat
                            save_data(); st.rerun()
                    if st.button("Delete Permanently", key=f"f_del_ev_{i}"):
                        st.session_state.data["events"].pop(i)
                        save_data(); st.rerun()

        # --- SUB-TAB 3: ACCOUNTS ---
        with t3:
            st.subheader("👤 Manage Website Accounts")
            for i, a in enumerate(st.session_state.data.get("accounts", [])):
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"**{a['name']}** ({a['role']})")
                    if c2.button("Wipe", key=f"acc_del_{i}"):
                        st.session_state.data["accounts"].pop(i)
                        save_data(); st.rerun()

        # --- NEW SUB-TAB 4: CORRECTIONS (Add/Reduce Time) ---
        with t4:
            st.subheader("⚖️ Manual Time Correction")
            st.info("Positive numbers add time. Negative numbers (e.g., -30) reduce time.")
            
            with st.form("admin_manual_adj"):
                col1, col2 = st.columns(2)
                adj_p = col1.selectbox("Project Team", ["SKIT", "BROCHURE"])
                
                # Get names only for the selected project
                names_in_proj = [m['name'] for m in st.session_state.data["members"] if m['project'] == adj_p]
                adj_n = col2.selectbox("Select Student", names_in_proj if names_in_proj else ["None"])
                
                adj_m = st.number_input("Minutes to Change", step=5)
                adj_reason = st.text_input("Reason (e.g., 'Correction for error' or 'Bonus for extra help')")
                
                if st.form_submit_button("🔨 Apply Adjustment"):
                    if adj_n != "None" and adj_m != 0:
                        u_key = f"{adj_n}_{adj_p}"
                        
                        # Update database
                        st.session_state.data["contributions"][u_key] = st.session_state.data["contributions"].get(u_key, 0) + adj_m
                        
                        # Create log entry for transparency
                        st.session_state.data["logs"].append({
                            "log_id": f"admin_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "user": adj_n,
                            "date": str(date.today()),
                            "minutes": adj_m,
                            "task": f"ADMIN ADJ: {adj_reason}",
                            "project": adj_p
                        })
                        
                        save_data()
                        st.success(f"Adjusted {adj_n}'s {adj_p} time by {adj_m} mins.")
                        st.rerun()
