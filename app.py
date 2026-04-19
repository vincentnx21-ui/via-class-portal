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

# --- 6. TABS ---
tabs_list = ["🏠 Dashboard", "✅ Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
if is_chair: tabs_list.append("⚙️ Admin")
active_tab = st.tabs(tabs_list)

st.sidebar.markdown(f"### 👤 {c_name}")
view_proj = st.sidebar.selectbox("📁 Select Project", ["SKIT", "BROCHURE"])
if st.sidebar.button("🔓 Logout"):
    st.session_state.authenticated = False
    st.rerun()

# --- TAB 0: DASHBOARD ---
with active_tab[0]:
    st.title(f"🚀 {view_proj} Project Portal")
    col_a, col_b, col_c = st.columns(3)
    if not is_teach:
        u_key = f"{c_name}_{view_proj}"
        m = st.session_state.data.get('contributions', {}).get(u_key, 0)
        col_a.metric(f"Your {view_proj} Hours", f"{m // 60}h {m % 60}m")
    else: col_a.metric("Role", "Faculty Observer")
    
    events = [e for e in st.session_state.data["events"] if e["project"] == view_proj]
    col_b.metric("Upcoming Events", len([e for e in events if e.get("status") != "Cancelled"]))
    col_c.metric("Project Status", "Active", delta="On Track")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("📅 Event RSVP")
        if not events: st.info("No events scheduled.")
        else:
            for i, e in enumerate(events):
                is_can = e.get("status") == "Cancelled"
                with st.container(border=True):
                    if is_can: st.error(f"🚫 **CANCELLED: {e['type']}**")
                    else:
                        st.write(f"**{e['type']}**")
                        st.caption(f"📍 {e.get('venue','N/A')} | ⏰ {e['start_time']}")
                        with st.expander("Update My RSVP"):
                            f_k = f"rsvp_{view_proj}_{i}"
                            with st.form(f_k):
                                s = st.segmented_control("Status", ["Attending", "Late", "Not Attending"], key=f"s_{f_k}")
                                r = st.text_input("Note", key=f"n_{f_k}")
                                if st.form_submit_button("Confirm RSVP"):
                                    if s:
                                        eid = f"{e['project']}_{e['date']}_{e['start_time']}"
                                        st.session_state.data["rsvp"] = [x for x in st.session_state.data.get("rsvp", []) if not (x['event_id'] == eid and x['name'] == c_name)]
                                        st.session_state.data["rsvp"].append({"event_id": eid, "name": c_name, "status": s, "note": r})
                                        save_data(); st.success("RSVP Saved!"); st.rerun()
                                    else: st.error("Select status!")

    with c2:
        st.subheader("👥 Team Roster")
        mems = [m for m in st.session_state.data["members"] if m["project"] == view_proj]
        if not mems: st.write("No members.")
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

# --- TAB 2: ACTIVITY LOG & TEACHER FEEDBACK ---
with active_tab[2]:
    st.title("🕒 Activity Log")
    if not is_teach:
        with st.expander("➕ Log New Activity"):
            with st.form(f"log_{view_proj}"):
                ld, lm, lt = st.date_input("Date"), st.number_input("Minutes", 5, step=5), st.text_input("Task")
                lp = st.selectbox("Project", ["SKIT", "BROCHURE"], index=0 if view_proj=="SKIT" else 1)
                if st.form_submit_button("Submit"):
                    ukey = f"{c_name}_{lp}"
                    st.session_state.data["contributions"][ukey] = st.session_state.data["contributions"].get(ukey, 0) + lm
                    st.session_state.data["logs"].append({"log_id": f"log_{datetime.now().strftime('%Y%m%d%H%M%S')}", "user": c_name, "date": str(ld), "minutes": lm, "task": lt, "project": lp, "comments": []})
                    save_data(); st.success("Logged!"); st.rerun()
    
    st.divider()
    st.subheader("📜 Recent Activity & Teacher Feedback")
    proj_logs = [l for l in st.session_state.data.get("logs", []) if l.get("project") == view_proj]
    for log in reversed(proj_logs):
        with st.container(border=True):
            ct, cs = st.columns([3, 1])
            ct.markdown(f"**{log['user']}** - {log['task']}\n\n📅 {log['date']}")
            cs.info(f"{log['minutes']} mins")
            for c in log.get("comments", []): st.markdown(f"> **{c['teacher']}:** {c['text']}")
            if is_teach:
                with st.expander("📝 Add Comment"):
                    with st.form(f"cmt_{log['log_id']}"):
                        tc = st.text_area("Feedback")
                        if st.form_submit_button("Post"):
                            for l in st.session_state.data["logs"]:
                                if l.get("log_id") == log["log_id"]:
                                    l.setdefault("comments", []).append({"teacher": c_name, "text": tc, "time": str(datetime.now())})
                            save_data(); st.rerun()

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
                c2.progress(min(1.0, mins/300), text=f"{mins//60}h {mins%60}m")

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
        at1, at2, at3, at4 = st.tabs(["👥 Roster", "📅 Events", "🔐 Accounts", "⚖️ Corrections"])
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
            with st.form("add_e"):
                ep, ty, d = st.selectbox("Project", ["SKIT", "BROCHURE"]), st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"]), st.date_input("Date")
                st_time, v = st.time_input("Start"), st.text_input("Venue")
                if st.form_submit_button("Add Event"):
                    st.session_state.data["events"].append({"project": ep, "type": ty, "date": str(d), "venue": v, "start_time": str(st_time), "status": "Active"})
                    save_data(); st.rerun()

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
