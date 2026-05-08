import streamlit as st
import pandas as pd
from datetime import datetime, time, date
import firebase_admin
from firebase_admin import credentials, db
import time
from zoneinfo import ZoneInfo
import hashlib

SG_TZ = ZoneInfo("Asia/Singapore")

# ============================================================================
# 🔐 CHAIRMAN BOOTSTRAP CREDENTIALS
# ============================================================================
CHAIRMAN_EMAIL = "chairman.via@school.edu.sg"
CHAIRMAN_PASSWORD = "VIA2026Chair!"
CHAIRMAN_ROLES = [
    {"role_type": "VIA Committee", "project": "CLASS", "is_rep": True, "sub_role": "Chairman"}
]
MAX_ROLES_PER_USER = 3

# ============================================================================
# 🔐 PASSWORD UTILS
# ============================================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# ============================================================================
# 🔐 PERMISSIONS HELPER (Boolean-Based)
# ============================================================================
class Permissions:
    def __init__(self, user_roles: list[dict]):
        self.roles = user_roles or []
    
    def can_access_project(self, project: str) -> bool:
        return any(r.get("project") == project or r.get("project") == "CLASS" for r in self.roles)
    
    def is_chairman(self) -> bool:
        return any(r.get("role_type") == "VIA Committee" for r in self.roles)
    
    def is_teacher(self) -> bool:
        return any(r.get("role_type") == "Teacher" for r in self.roles)
    
    def is_representative(self, project: str = None) -> bool:
        if project:
            return any(r.get("is_rep", False) and r.get("project") == project for r in self.roles)
        return any(r.get("is_rep", False) or "Representative" in r.get("role_type", "") for r in self.roles)
    
    def can_edit_logs(self) -> bool:
        return self.is_chairman() or self.is_teacher() or self.is_representative()
    
    def can_manage_attendance(self) -> bool:
        return self.is_chairman() or self.is_teacher()
    
    def can_view_admin_panel(self) -> bool:
        return self.is_chairman()
    
    def can_adjust_time(self) -> bool:
        return self.is_chairman() or self.is_representative()
    
    def can_delete_content(self) -> bool:
        return self.is_chairman() or self.is_teacher()
    
    def get_accessible_projects(self) -> list[str]:
        projects = list(set(r.get("project") for r in self.roles if r.get("project") and r.get("project") != "CLASS"))
        if any(r.get("project") == "CLASS" for r in self.roles):
            projects.append("CLASS")
        return projects if projects else ["CLASS"]

# ============================================================================
# 🎛️ CONFIGURATION & CSS
# ============================================================================
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide", page_icon="🚀")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --primary: #3b82f6; --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --text-secondary: #94a3b8; --border: #334155; --radius: 12px; }
* { box-sizing: border-box; font-family: 'Inter', sans-serif; }
.stApp { background: var(--bg) !important; color: var(--text) !important; }
.main .block-container { padding: 2rem 3rem; max-width: 1400px; }
div[data-testid="stContainer"], .stCard { background: var(--card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; padding: 1.5rem !important; }
.user-card { background: linear-gradient(135deg, #334155 0%, #1e293b 100%); padding: 1.25rem; border-radius: var(--radius); border: 1px solid var(--border); margin-bottom: 1rem; }
.role-badge { display: inline-block; background: #334155; color: #f1f5f9; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; margin: 2px; border: 1px solid #475569; }
.role-badge.rep { background: linear-gradient(135deg, #3b82f6, #06b6d4); border: none; font-weight: 600; }
.stButton > button { background: #3b82f6 !important; color: white !important; border-radius: 8px !important; padding: 0.75rem 1.5rem !important; font-weight: 500 !important; }
.stButton > button:hover { background: #2563eb !important; }
input, textarea, select { background: #1e293b !important; color: #f1f5f9 !important; border: 1px solid #334155 !important; border-radius: 8px !important; padding: 0.75rem !important; }
.stTabs [data-baseweb="tab"] { color: #94a3b8 !important; background: transparent !important; }
.stTabs [aria-selected="true"] { color: white !important; background: #3b82f6 !important; }
.terminal-line { font-family: monospace; background: #111827; padding: 6px 10px; border-radius: 6px; margin: 4px 0; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 🔌 FIREBASE & DATA HANDLING
# ============================================================================
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {'databaseURL': 'https://via-report-default-rtdb.asia-southeast1.firebasedatabase.app/'})
    except Exception as e:
        st.error(f"Firebase Setup Error: {e}")
        st.stop()

def load_data():
    try:
        ref = db.reference("via_master_record")
        data = ref.get() or {}
        # ✅ SAFE: Backfill missing keys for legacy accounts
        if "accounts" in data:
            for acc in data["accounts"]:
                acc.setdefault("email", "legacy@unknown.sg")
                acc.setdefault("roles", [])
                acc.setdefault("status", "active")
        if "events" in data:
            for e in data["events"]:
                if isinstance(e.get("date"), str):
                    try: e["date"] = datetime.fromisoformat(e["date"]).date()
                    except: e["date"] = date.today()
                if isinstance(e.get("start_time"), str):
                    try: e["start_time"] = datetime.strptime(e["start_time"], "%H:%M").time()
                    except: pass
        return data
    except Exception as e:
        return {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}, "signup_enabled": False}

def save_data():
    try:
        ref = db.reference("via_master_record")
        data = st.session_state.data.copy()
        if "events" in data:
            for e in data["events"]:
                if hasattr(e.get("date"), "isoformat"): e["date"] = e["date"].isoformat()
                if hasattr(e.get("start_time"), "strftime"): e["start_time"] = e["start_time"].strftime("%H:%M")
        ref.set(data)
    except Exception as e:
        print("Save error:", e)

def log_system_event(action, user):
    st.session_state.data.setdefault("system_logs", []).append({
        "log_id": f"sys_{datetime.now(SG_TZ).strftime('%H%M%S')}",
        "user": user, "action": action,
        "time": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

# ============================================================================
# 📅 CALENDAR RENDERER
# ============================================================================
def render_event_calendar(events, selected_project):
    import calendar
    today = date.today()
    month, year = today.month, today.year
    month_events = {}
    for e in events:
        try:
            d = e.get("date")
            if isinstance(d, str): d = datetime.fromisoformat(d).date()
            if d.month == month and d.year == year and e.get("project") == selected_project:
                month_events.setdefault(d.day, []).append(e)
        except: continue

    st.markdown(f"<h3 style='text-align:center;color:#3b82f6;'>📅 {calendar.month_name[month]} {year}</h3>", unsafe_allow_html=True)
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day != 0:
                    if day in month_events:
                        if st.button(str(day), key=f"cal_{day}_{month}", type="secondary"):
                            st.session_state.cal_day = day
                    else:
                        st.markdown(f"<p style='text-align:center;color:#f1f5f9;margin:5px 0;'>{day}</p>", unsafe_allow_html=True)

    if st.session_state.get("cal_day") and st.session_state.cal_day in month_events:
        st.markdown(f"<h4 style='margin:15px 0;'>📅 Events on {st.session_state.cal_day} {calendar.month_name[month]}</h4>", unsafe_allow_html=True)
        for e in month_events[st.session_state.cal_day]:
            st.markdown(f"""<div style="background:#1e293b;padding:10px;border-radius:8px;border-left:4px solid #3b82f6;margin-bottom:8px;">
                <b>{e['type']}</b><br><span style="color:#94a3b8">⏰ {e.get('start_time', 'N/A')}</span>
            </div>""", unsafe_allow_html=True)
        if st.button("✕ Close", key="close_cal"):
            st.session_state.cal_day = None
            st.rerun()

# ============================================================================
# 🚀 APP INITIALIZATION
# ============================================================================
if "data" not in st.session_state:
    st.session_state.data = load_data()
    for k in ["members", "accounts", "logs", "events", "rsvp", "system_logs"]:
        st.session_state.data.setdefault(k, [])
    st.session_state.data.setdefault("contributions", {})
    st.session_state.data.setdefault("attendance", {})
    st.session_state.data.setdefault("signup_enabled", False)

if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "perms" not in st.session_state: st.session_state.perms = None

# ============================================================================
# 🔐 AUTHENTICATION
# ============================================================================
if not st.session_state.authenticated:
    st.markdown("""<div style="text-align:center;margin:3rem 0;"><h1 style="font-size:2.5rem;">🚀 VIA Portal 2026</h1><p style="color:#94a3b8;">Secure Student & Committee Access</p></div>""", unsafe_allow_html=True)
    
    signup_enabled = st.session_state.data.get("signup_enabled", False)
    mode = st.radio("", ["🔐 Sign In", "📝 Sign Up"] if signup_enabled else ["🔐 Sign In"], horizontal=True, label_visibility="collapsed")

    if mode == "🔐 Sign In":
        with st.form("login"):
            email = st.text_input("Student Gmail", placeholder="name@school.edu.sg").strip().lower()
            pw = st.text_input("Password", type="password", placeholder="Enter password")
            if st.form_submit_button("Sign In", use_container_width=True):
                if not email or not pw:
                    st.error("Please enter email and password")
                    st.stop()

                if email == CHAIRMAN_EMAIL and pw == CHAIRMAN_PASSWORD:
                    acc = next((a for a in st.session_state.data["accounts"] if a.get("email") == CHAIRMAN_EMAIL), None)
                    if not acc:
                        acc = {"name": "VIA Chairman", "email": CHAIRMAN_EMAIL, "roles": CHAIRMAN_ROLES.copy(), 
                               "password_hash": hash_password(CHAIRMAN_PASSWORD), "status": "active", 
                               "created_at": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S")}
                        st.session_state.data["accounts"].append(acc)
                        st.session_state.data["members"].append({"name": "VIA Chairman", "project": None, "role_type": "CLASS", "is_rep": True, "sub_role": "Chairman"})
                        save_data()
                    
                    st.session_state.authenticated = True
                    st.session_state.u_name = acc["name"]
                    st.session_state.u_email = acc["email"]
                    st.session_state.u_roles = acc["roles"]
                    st.session_state.perms = Permissions(acc["roles"])
                    log_system_event("CHAIRMAN BOOTSTRAP LOGIN", acc["name"])
                    st.rerun()

                acc = next((a for a in st.session_state.data["accounts"] if a.get("email") == email), None)
                if not acc:
                    st.error("Account not found. Please sign up first.")
                    st.stop()
                if not verify_password(pw, acc.get("password_hash", "")):
                    st.error("Invalid password")
                    st.stop()
                if acc.get("status") == "pending":
                    st.warning("Your account is awaiting Chairman approval. Please try again later.")
                    st.stop()

                st.session_state.authenticated = True
                st.session_state.u_name = acc["name"]
                st.session_state.u_email = acc["email"]
                st.session_state.u_roles = acc.get("roles", [])
                st.session_state.perms = Permissions(acc.get("roles", []))
                log_system_event(f"LOGIN: {acc['name']}", acc["name"])
                save_data()
                st.rerun()

    elif mode == "📝 Sign Up":
        with st.form("signup"):
            email = st.text_input("Student Gmail", placeholder="name@school.edu.sg").strip().lower()
            name = st.text_input("Full Name", placeholder="As registered").strip().title()
            pw = st.text_input("Create Password", type="password", placeholder="Min 6 chars")
            confirm = st.text_input("Confirm Password", type="password")
            if st.form_submit_button("Create Account", use_container_width=True):
                if len(pw) < 6 or pw != confirm:
                    st.error("Passwords must match and be 6+ characters")
                elif any(a.get("email") == email for a in st.session_state.data["accounts"]):
                    st.error("Email already registered")
                else:
                    st.session_state.data["accounts"].append({
                        "name": name, "email": email, "password_hash": hash_password(pw),
                        "roles": [], "status": "pending", "created_at": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_data()
                    st.success("Account created! Please wait for Chairman approval.")
                    time.sleep(2)
                    st.rerun()
    st.stop()

# ============================================================================
# 🖥️ MAIN APP (POST-AUTH)
# ============================================================================
c_name = st.session_state.u_name
perms = st.session_state.perms

if not perms.roles:
    st.warning(f"🔐 Your account `{c_name}` has no roles assigned yet. Contact the Chairman to activate access.", icon="⚠️")
    if st.button("🚪 Logout"): st.session_state.authenticated = False; st.rerun()
    st.stop()

badges = "".join([
    f'<span class="role-badge{" rep" if r.get("is_rep") else ""}>{r.get("role_type","").replace(" Representative","")} • {r.get("sub_role","")}</span>' 
    for r in perms.roles
])
st.sidebar.markdown(f"""<div class="user-card"><div style="font-size:1.1rem;font-weight:600;">👤 {c_name}</div><div style="margin:6px 0;display:flex;flex-wrap:wrap;gap:4px;">{badges}</div><div style="font-size:0.8rem;color:#94a3b8;">📧 {st.session_state.u_email}</div></div>""", unsafe_allow_html=True)

projects = perms.get_accessible_projects() or ["CLASS"]
view_proj = projects[0]
if len(projects) > 1: view_proj = st.sidebar.radio("Project View", projects, index=0)

st.sidebar.button("🔄 Refresh", use_container_width=True, on_click=lambda: st.rerun())
st.sidebar.button("🚪 Logout", use_container_width=True, type="primary", on_click=lambda: st.session_state.update({"authenticated": False}))

tabs = ["🏠 Dashboard", "✅ Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
if perms.can_view_admin_panel(): tabs.append("⚙️ Admin")
active = st.tabs(tabs)

# --- DASHBOARD ---
with active[0]:
    st.title(f"🚀 {view_proj} Portal")
    today = date.today()
    events = [e for e in st.session_state.data.get("events", []) if e.get("project") == view_proj]
    current, past = [], []
    for e in events:
        d = e.get("date") if isinstance(e.get("date"), date) else (datetime.fromisoformat(e["date"]).date() if isinstance(e.get("date"), str) else date.today())
        (past if d < today or e.get("status") == "Cancelled" else current).append(e)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Upcoming", len(current))
    c2.metric("Completed", len(past))
    c3.metric("Team", len([m for m in st.session_state.data.get("members", []) if m.get("project") == view_proj or m.get("role_type")=="CLASS"]))
    c4.metric("Your Hours", f"{st.session_state.data.get('contributions', {}).get(f'{c_name}_{view_proj}', 0)//60}h")

    st.subheader("🗓️ Calendar")
    render_event_calendar(events, view_proj)
    st.divider()
    st.subheader("📅 RSVP")
    for e in current:
        eid = f"{e['project']}_{e['date']}_{e['start_time']}"
        rsvp = next((r for r in st.session_state.data.get("rsvp", []) if r["event_id"]==eid and r["name"]==c_name), None)
        with st.container(border=True):
            st.markdown(f"**{e['type']}** • {e['date']} @ {e['start_time']}")
            c1, c2 = st.columns([2, 3])
            status = c1.selectbox("Status", ["Attending", "Late", "Not Attending"], index=["Attending", "Late", "Not Attending"].index(rsvp["status"] if rsvp else "Attending"), key=f"s_{eid}")
            reason = c2.text_input("Reason", value=rsvp.get("reason","") if rsvp else "", key=f"r_{eid}")
            if c1.button("Submit RSVP", key=f"btn_{eid}"):
                st.session_state.data["rsvp"] = [r for r in st.session_state.data.get("rsvp", []) if not (r["event_id"]==eid and r["name"]==c_name)]
                st.session_state.data["rsvp"].append({"event_id": eid, "name": c_name, "status": status, "reason": reason})
                save_data(); st.success("RSVP Saved"); st.rerun()

# --- ATTENDANCE ---
with active[1]:
    st.title("✅ Attendance Tracker")
    evs = [e for e in st.session_state.data.get("events", []) if e.get("project") == view_proj and e.get("status") != "Cancelled"]
    if evs:
        sel = st.selectbox("Event", [f"{e['type']} ({e['date']})" for e in evs])
        e = evs[[f"{x['type']} ({x['date']})" for x in evs].index(sel)]
        eid = f"{e['project']}_{e['date']}_{e['start_time']}"
        voters = [r['name'] for r in st.session_state.data.get("rsvp", []) if r["event_id"]==eid and r["status"] in ["Attending", "Late"]]
        if voters:
            for n in voters:
                rec = st.session_state.data.get("attendance", {}).get(eid, {}).get(n, {"p": False, "d": "Full"})
                c1, c2, c3 = st.columns(3)
                c1.write(n)
                if perms.can_manage_attendance():
                    p = c2.checkbox("Present", value=rec["p"], key=f"p_{n}")
                    d = c3.selectbox("Session", ["Full", "Half"], index=0 if rec["d"]=="Full" else 1, key=f"d_{n}")
                    st.session_state.data.setdefault("attendance", {}).setdefault(eid, {})[n] = {"p": p, "d": d}
                else:
                    c2.write("✅" if rec["p"] else "❌")
                    c3.write(rec["d"])
            if perms.can_manage_attendance() and st.button("💾 Save Attendance"):
                save_data(); st.success("Saved"); st.rerun()
        else: st.info("No RSVPs yet.")

# --- ACTIVITY LOG ---
with active[2]:
    st.title("🕒 Activity Log")
    if perms.can_edit_logs():
        with st.expander("➕ Log Activity"):
            with st.form("log_form"):
                c1, c2 = st.columns(2)
                d = c1.date_input("Date", value=date.today())
                t = c2.text_input("Task")
                m = c1.number_input("Minutes", min_value=5, step=5, value=30)
                p_opts = [p for p in ["SKIT", "BROCHURE"] if perms.can_access_project(p)] or ["CLASS"]
                p = c2.selectbox("Project", p_opts)
                if st.form_submit_button("Submit"):
                    if t:
                        st.session_state.data["logs"].append({"log_id": f"log_{time.time()}", "user": c_name, "date": str(d), "minutes": m, "task": t, "project": p, "comments": []})
                        save_data(); st.success("Logged"); st.rerun()
                    else: st.error("Task required")
    st.divider()
    logs = [l for l in st.session_state.data.get("logs", []) if l.get("project") == view_proj]
    for l in reversed(logs):
        with st.container(border=True):
            st.markdown(f"**{l['user']}** • {l['task']} ({l['minutes']} mins)")
            if perms.can_delete_content() and st.button("🗑️ Delete Log", key=f"del_{l['log_id']}"):
                st.session_state.data["logs"] = [x for x in st.session_state.data["logs"] if x["log_id"] != l["log_id"]]
                log_system_event(f"Deleted log: {l['task']}", c_name)
                save_data(); st.rerun()
            
            if perms.is_teacher():
                st.divider()
                st.markdown("**💬 Teacher Feedback**")
                for idx, c in enumerate(l.get("comments", [])):
                    col1, col2 = st.columns([4, 1])
                    col1.write(f"**{c.get('teacher', 'Unknown')}**: {c.get('text', '')}")
                    if c.get("teacher") == c_name and col2.button("🗑️", key=f"del_c_{idx}_{l['log_id']}"):
                        l["comments"].pop(idx)
                        log_system_event("Deleted teacher comment", c_name)
                        save_data(); st.rerun()
                with st.expander("✏️ Add/Update Comment"):
                    new_comment = st.text_area("Feedback", value="", key=f"comm_{l['log_id']}")
                    if st.button("Post/Update", key=f"post_{l['log_id']}"):
                        if not new_comment.strip(): st.error("Comment cannot be empty")
                        else:
                            existing_idx = next((i for i, c in enumerate(l.get("comments", [])) if c.get("teacher") == c_name), -1)
                            if existing_idx >= 0:
                                l["comments"][existing_idx]["text"] = new_comment
                                log_system_event("Updated teacher feedback", c_name)
                            else:
                                l.setdefault("comments", []).append({"teacher": c_name, "text": new_comment, "comment_id": str(time.time())})
                                log_system_event("Added teacher feedback", c_name)
                            save_data(); st.success("Comment saved"); st.rerun()

# --- PROGRESS ---
with active[3]:
    st.title("📊 Progress Tracker")
    members = st.session_state.data.get("members", [])
    contribs = st.session_state.data.get("contributions", {})
    total = sum(contribs.values())
    st.metric("Total Class Minutes", total)
    
    if perms.can_adjust_time():
        with st.expander("⏱️ Manual Time Correction (+/-)"):
            with st.form("time_adj"):
                sel_user = st.selectbox("Student", [m["name"] for m in members] if members else ["No members"])
                adj_proj = st.selectbox("Project", ["SKIT", "BROCHURE", "CLASS"])
                adj_mins = st.number_input("Minutes (+ or -)", step=5)
                adj_reason = st.text_input("Reason")
                if st.form_submit_button("Apply Correction"):
                    if sel_user == "No members": st.error("No students available")
                    else:
                        key = f"{sel_user}_{adj_proj}"
                        contribs[key] = contribs.get(key, 0) + adj_mins
                        log_system_event(f"TIME CORRECTED: {adj_mins} mins for {sel_user} ({adj_proj})", c_name)
                        save_data(); st.success("Time adjusted"); st.rerun()

    st.divider()
    data = []
    for m in members:
        proj = m.get("project") or "CLASS"
        key = f"{m['name']}_{proj}"
        mins = contribs.get(key, 0)
        data.append({"Name": m["name"], "Project": proj, "Role": m.get("sub_role", "N/A"), "Hours": f"{mins//60}h"})
    df = pd.DataFrame(data)
    search = st.text_input("🔍 Search")
    if search: df = df[df["Name"].str.contains(search, case=False)]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("📥 Download CSV", df.to_csv(index=False), f"VIA_Directory_{date.today()}.csv", "text/csv")

# --- DIRECTORY (was missing tab index) ---
with active[4]:
    st.title("📁 Member Directory")
    members = [m for m in st.session_state.data.get("members", []) if m.get("project") == view_proj or m.get("role_type") == "CLASS"]
    if members:
        df = pd.DataFrame([{
            "Name": m.get("name", "Unknown"),
            "Role": m.get("sub_role", "N/A"),
            "Project": m.get("project", "CLASS"),
            "Representative": "✅" if m.get("is_rep") else "❌"
        } for m in members])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No members assigned to this project yet.")

# --- ADMIN ---
if perms.can_view_admin_panel():
    with active[5]:
        st.title("⚙️ Admin Control")
        sub_tabs = st.tabs(["🎭 Role Assignment", "📅 Events", "🖥️ System Terminal", "⚠️ Reset"])
        
        with sub_tabs[0]:
            st.info(f"Assign up to {MAX_ROLES_PER_USER} roles per user.")
            accounts = st.session_state.data.get("accounts", [])
            if not accounts: st.warning("No user accounts found.")
            else:
                account_options = [f"{a.get('name', 'Unknown')} ({a.get('email', 'No Email')})" for a in accounts]
                sel_user = st.selectbox("Select User", account_options)
                user = next(a for a in accounts if f"{a.get('name', 'Unknown')} ({a.get('email', 'No Email')})" == sel_user)
                roles = user.get("roles", [])
                
                st.subheader("Current Roles")
                for i, r in enumerate(roles):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"<span class='role-badge{' rep' if r.get('is_rep') else ''}'>{r['role_type']} • {r['sub_role']} ({r['project']})</span>", unsafe_allow_html=True)
                    if c2.button("🗑️ Remove", key=f"rm_{i}"):
                        roles.pop(i); user["roles"] = roles; 
                        log_system_event(f"ROLE REMOVED: {r['role_type']} from {user.get('name', 'Unknown')}", c_name)
                        save_data(); st.rerun()
                
                st.divider()
                st.subheader("Assign Role")
                if len(roles) >= MAX_ROLES_PER_USER: st.warning("Max roles reached. Remove one first.")
                else:
                    with st.form("assign"):
                        p = st.selectbox("Project", ["CLASS", "SKIT", "BROCHURE"])
                        r_type = st.selectbox("Role Type", ["VIA Committee", "Teacher", "VIA members"] if p=="CLASS" else ["VIA members", "Skit Representative", "Brochure Representative"])
                        is_rep = st.checkbox("Representative?")
                        sub = st.selectbox("Sub-Role", ["N/A", "Lead", "Prop Maker", "Designer", "Writer", "Cameraman"])
                        if st.form_submit_button("✅ Assign"):
                            if any(r.get("project")==p and r.get("role_type")==r_type for r in roles):
                                st.error("Role already exists for this project")
                            else:
                                roles.append({"role_type": r_type, "project": p, "is_rep": is_rep, "sub_role": sub, "assigned_by": c_name})
                                user["roles"] = roles
                                log_system_event(f"ROLE ASSIGNED: {r_type} ({p}) to {user.get('name', 'Unknown')}", c_name)
                                save_data(); st.success("Role assigned"); st.rerun()

        with sub_tabs[1]:
            st.subheader("Add Event")
            with st.form("event"):
                p = st.selectbox("Project", ["SKIT", "BROCHURE"])
                t = st.selectbox("Type", ["Rehearsal", "Meeting", "Work Session", "Production"])
                d = st.date_input("Date")
                tm = st.time_input("Time")
                v = st.text_input("Venue")
                if st.form_submit_button("Add"):
                    st.session_state.data["events"].append({"project": p, "type": t, "date": d, "start_time": tm, "venue": v, "status": "Active"})
                    log_system_event(f"EVENT CREATED: {t} ({p})", c_name)
                    save_data(); st.success("Added"); st.rerun()
            st.divider()
            st.subheader("Manage Events")
            for i, e in enumerate(st.session_state.data.get("events", [])):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.write(f"**{e['type']}** ({e['project']}) • {e['date']} @ {e['start_time']}")
                    if c2.button("✏️ Edit", key=f"edit_ev_{i}"):
                        with st.form(f"edit_{i}"):
                            n_type = st.selectbox("Type", ["Rehearsal", "Meeting", "Work Session", "Production"], index=["Rehearsal", "Meeting", "Work Session", "Production"].index(e["type"]))
                            n_venue = st.text_input("Venue", value=e.get("venue", ""))
                            n_stat = st.selectbox("Status", ["Active", "Cancelled"], index=0 if e.get("status")=="Active" else 1)
                            if st.form_submit_button("Save"):
                                e["type"] = n_type; e["venue"] = n_venue; e["status"] = n_stat
                                log_system_event(f"EVENT EDITED: {e['type']}", c_name)
                                save_data(); st.rerun()
                    if c3.button("🗑️ Delete", key=f"del_ev_{i}"):
                        st.session_state.data["events"].pop(i)
                        log_system_event(f"EVENT DELETED: {e['type']}", c_name)
                        save_data(); st.rerun()

        with sub_tabs[2]:
            st.title("🖥️ System Activity Terminal")
            logs = st.session_state.data.get("system_logs", [])
            if not logs: st.info("No system activity recorded yet.")
            else:
                for log in reversed(logs[-100:]):
                    icon = "🟢" if "LOGIN" in log["action"] else "🔴" if "LOGOUT" in log["action"] else "🔵" if "ROLE" in log["action"] else "🟡"
                    st.markdown(f"""<div class="terminal-line"><span style="color:#94a3b8">`{log['time']}`</span> {icon} <b style="color:#f1f5f9">{log['user']}</b>: {log['action']}</div>""", unsafe_allow_html=True)

        with sub_tabs[3]:
            st.warning("🚨 Danger Zone")
            st.toggle("🔓 Allow Public Sign-Ups", value=st.session_state.data.get("signup_enabled", False), key="signup_toggle")
            if st.session_state.signup_toggle != st.session_state.data.get("signup_enabled", False):
                st.session_state.data["signup_enabled"] = st.session_state.signup_toggle
                save_data()
            if st.button("🔥 Clear All Data"):
                st.session_state.data = {"members": [], "accounts": [], "logs": [], "contributions": {}, "events": [], "rsvp": [], "attendance": {}, "signup_enabled": False, "system_logs": []}
                log_system_event("FULL DATABASE RESET", c_name)
                save_data(); st.success("Cleared"); st.rerun()
