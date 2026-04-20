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
        font-size: 18px; font-weight: bold; color: #1e293b;
        background-color: #e2e8f0; border-radius: 10px 10px 0px 0px;
        padding: 10px 20px; margin-right: 5px; transition: 0.3s;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #1e293b !important; color: white !important;
        border-bottom: 3px solid #007bff;
    }
    div[data-plugin="stTabs"] div[role="tablist"] { border-bottom: none; gap: 0px; }
    button[data-baseweb="tab"]:hover { background-color: #cbd5e1; }
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
                        if "end_time" in e:
                             e["end_time"] = datetime.strptime(e["end_time"], "%H:%M").time()
                    except: 
                        continue # Fixed the syntax error here
            return data
        return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}}
    except Exception as e:
        return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}}

def save_data():
    def generate_event_reports():
        today = date.today()
        logs = st.session_state.data.setdefault("logs", [])

        for e in st.session_state.data.get("events", []):
    
            try:
                event_date = datetime.strptime(e["date"], "%Y-%m-%d").date() if isinstance(e["date"], str) else e["date"]
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
    
    try:
        ref = db.reference("via_master_record")
        data_copy = st.session_state.data.copy()
        if "events" in data_copy:
            serializable_events = []
            for e in data_copy["events"]:
                e_c = e.copy()
                e_c["date"] = e["date"].isoformat() if hasattr(e["date"], 'isoformat') else e["date"]
                e_c["start_time"] = e["start_time"].strftime("%H:%M") if hasattr(e["start_time"], 'strftime') else e["start_time"]
                if "end_time" in e_c:
                    e_c["end_time"] = e["end_time"].strftime("%H:%M") if hasattr(e["end_time"], 'strftime') else e["end_time"]
                serializable_events.append(e_c)
            data_copy["events"] = serializable_events
        ref.set(data_copy)
    except Exception as e:
        st.error(f"Save Error: {e}")

if "data" not in st.session_state:
    st.session_state.data = load_data()

generate_event_reports()
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
    st.title("🛡️ VIA Class Portal 2026")
    with st.form("login"):
        name_in = st.text_input("Name").strip().title()
        role_in = st.selectbox("Role", list(USER_PASSWORDS.keys()))
        pw_in = st.text_input("Password", type="password")
        if st.form_submit_button("Sign In"):
            if role_in == "VIA Committee" and pw_in == CHAIRMAN_SECRET_PW:
                st.session_state.authenticated, st.session_state.u_name, st.session_state.u_role = True, name_in, "Chairman"
            elif pw_in == USER_PASSWORDS.get(role_in):
                st.session_state.authenticated, st.session_state.u_name, st.session_state.u_role = True, name_in, role_in
            else: st.error("Access Denied")

            if st.session_state.authenticated:
                acc_list = st.session_state.data.get("accounts", [])
                if not any(a['name'] == name_in for a in acc_list):
                    st.session_state.data["accounts"].append({"name": name_in, "role": st.session_state.u_role})
                save_data(); st.rerun()
    st.stop()

# --- 5. PERMISSIONS ---
c_name, c_role = st.session_state.u_name, st.session_state.u_role
is_chair, is_teach = (c_role == "Chairman"), (c_role == "Teacher")
is_rep = "Representative" in c_role or any(m['name'] == c_name and m.get('is_rep') for m in st.session_state.data.get('members', []))

# --- SIDEBAR UI (Define this ONCE here) ---
st.sidebar.markdown(f"### 👤 {c_name}")
view_proj = st.sidebar.selectbox("📁 Select Project", ["SKIT", "BROCHURE"])

if st.sidebar.button("🔓 Logout", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()

# --- 6. TABS DEFINITION ---
tabs_list = ["🏠 Dashboard", "✅ Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
if is_chair: tabs_list.append("⚙️ Admin")
active_tab = st.tabs(tabs_list)

# --- TAB 0: DASHBOARD ---
with active_tab[0]: 
    st.title(f"🚀 {view_proj} Project Portal")
    
    # Top Metrics
    col_a, col_b, col_c = st.columns(3)
    if is_chair or is_rep:
        u_key = f"{c_name}_{view_proj}"
        m = st.session_state.data.get('contributions', {}).get(u_key, 0)
        col_a.metric(f"Your {view_proj} Hours", f"{m // 60}h {m % 60}m")
    else: 
        col_a.metric("Role", "Faculty Observer")
    
    events = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
    col_b.metric("Upcoming Events", len([e for e in events if e.get("status") != "Cancelled"]))
    col_c.metric("Project Status", "Active", delta="On Track")

    # Main Dashboard Content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📅 Event RSVP")
    # Separate events into 'Current' and 'History'
    all_events = st.session_state.data.get("events", [])
    today = date.today()
    
    current_events = []
    history_events = []

    for e in all_events:
        # Convert date string to date object for comparison if it's a string [cite: 9]
        event_date = datetime.strptime(e["date"], "%Y-%m-%d").date() if isinstance(e["date"], str) else e["date"]
        
        # Logic: History if Cancelled OR if the date has passed [cite: 29, 104]
        if e.get("status") == "Cancelled" or event_date < today:
            history_events.append(e)
        else:
            current_events.append(e)

    # --- DISPLAY CURRENT EVENTS ---
    if not current_events:
        st.info("No upcoming events.")
    else:
        for i, e in enumerate(current_events):
            e_id = f"{e['project']}_{e['date']}_{e['start_time']}"
            with st.container(border=True):
                st.write(f"**{e['type']}**") 
                st.caption(f"📍 {e.get('venue', 'N/A')} | ⏰ {e['start_time']}") 
                
                # RSVP Logic (Existing code) [cite: 32, 34, 35]
                with st.expander("Update My RSVP"):
                    # ... your existing RSVP form code ...
                    pass

    # --- NEW: DISPLAY EVENT HISTORY ---
    st.divider()
    st.subheader("📜 Event History")
    if not history_events:
        st.caption("No past or cancelled events.")
    else:
        for e in reversed(history_events): # Show newest history first
            event_date = datetime.strptime(e["date"], "%Y-%m-%d").date() if isinstance(e["date"], str) else e["date"]
            is_past = event_date < today
            
            with st.container(border=True):
                if e.get("status") == "Cancelled":
                    st.error(f"🚫 **CANCELLED: {e['type']}**") 
                    if e.get("note"): st.caption(f"**Reason for cancellation:** {e['note']}") 
                elif is_past:
                    st.success(f"✅ **COMPLETED: {e['type']}**")
                
                st.caption(f"📅 {e['date']} | 📍 {e.get('venue', 'N/A')}") 
                
    with col2:
        st.subheader("👥 Team Roster")
        mems = [m for m in st.session_state.data["members"] if m["project"] == view_proj]
        if not mems: 
            st.write("No members.")
        for m in mems:
            st.markdown(f"{'⭐' if m['is_rep'] else '👤'} **{m['name']}**")
            st.caption(f"Focus: {m['sub_role']}")

# --- TAB 1: ATTENDANCE ---
with active_tab[1]:
    st.title("✅ Attendance Tracker")
    evs = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
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
                    st.session_state.data["logs"].append({
                        "log_id": f"log_{datetime.now().timestamp()}",
                        "user": c_name,
                        "date": str(ld),
                        "minutes": lm,
                        "task": lt,
                        "project": lp,
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
                        ukey = f"{tu}_{tp}"
                        st.session_state.data["contributions"][ukey] = st.session_state.data["contributions"].get(ukey, 0) + bm
                        st.session_state.data["logs"].append({"log_id": f"b_{datetime.now().strftime('%H%M%S')}", "user": tu, "date": str(date.today()), "minutes": bm, "task": f"BONUS: {ra}", "project": tp, "comments": []})
                        save_data(); st.rerun()

    ts1, ts2 = st.tabs(["🎭 Skit Team", "📄 Brochure Team"])
    for proj, t in [("SKIT", ts1), ("BROCHURE", ts2)]:
        with t:
            for m in [mx for mx in all_m if mx['project'] == proj]:
                mins = all_c.get(f"{m['name']}_{proj}", 0)
                c1, c2 = st.columns([1, 3])
                c1.write(f"**{m['name']}**")
                progress_val = max(0.0, min(1.0, mins / 300))
                c2.progress(progress_val, text=f"{mins//60}h {mins%60}m")

# --- TAB 4: DIRECTORY ---
with active_tab[4]:
    st.title("📁 Official Class Directory")
    all_m, all_c, all_l = st.session_state.data["members"], st.session_state.data["contributions"], st.session_state.data["logs"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Members", len(all_m))
    avg = sum(all_c.values()) // len(all_m) if all_m else 0
    m2.metric("Average Time", f"{avg//60}h {avg%60}m")
    m3.metric("Active Projects", "2")

    if not all_m: st.warning("Roster empty.")
    else:
        summary = []
        for m in all_m:
            ukey = f"{m['name']}_{m['project']}"
            utasks = [lx['task'] for lx in all_l if lx['user'] == m['name'] and lx.get('project') == m['project']]
            summary.append({"NAME": m['name'], "PROJECT": m['project'], "ROLE": m['sub_role'], "VIA TIME": f"{all_c.get(ukey,0)//60}h {all_c.get(ukey,0)%60}m", "LATEST TASKS": " | ".join(utasks[-2:]) if utasks else "None", "STATUS": "✅ Active" if utasks else "⏳ No Logs"})
        
        df = pd.DataFrame(summary)
        f1, f2 = st.columns([2, 1])
        s, pf = f1.text_input("🔍 Search"), f2.selectbox("Filter", ["All", "SKIT", "BROCHURE"])
        if s: df = df[df["NAME"].str.contains(s, False)]
        if pf != "All": df = df[df["PROJECT"] == pf]
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", df.to_csv(index=False), f"VIA_{date.today()}.csv", "text/csv")

# --- TAB 5: ADMIN ---
if is_chair:
    with active_tab[5]:
        st.title("⚙️ Chairman Master Control")
        # Update: Added "⚠️ Reset" to the tab list
        at1, at2, at3, at4, at5 = st.tabs(["👥 Roster", "📅 Events", "🔐 Accounts", "⚖️ Corrections", "⚠️ Reset"])
        
        with at1:
            with st.form("add_m"):
                cn, cp = st.columns(2)
                n, p = cn.text_input("Name"), cp.selectbox("Project", ["SKIT", "BROCHURE"])
                cr, cs = st.columns(2)
                r, s = cr.checkbox("Rep?"), cs.selectbox("Role", ["Actors", "Prop makers", "Cameraman", "Designer", "Editor", "Writer", "N/A"])
                if st.form_submit_button("Add Member"):
                    st.session_state.data["members"].append({"name": n, "project": p, "is_rep": r, "sub_role": s})
                    save_data(); st.rerun()

        with at2:
            st.subheader("🗓️ Manage Events")
            # --- 1. CREATE EVENT FORM ---
            with st.form("add_e"):
                ep, ty, d = st.selectbox("Project", ["SKIT", "BROCHURE"]), st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"]), st.date_input("Date")
                st_time, v = st.time_input("Start"), st.text_input("Venue")
                if st.form_submit_button("Add Event"):
                    st.session_state.data["events"].append({
                        "project": ep, "type": ty, "date": str(d), 
                        "venue": v, "start_time": str(st_time), "status": "Active"
                    })
                    save_data(); st.rerun()

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
