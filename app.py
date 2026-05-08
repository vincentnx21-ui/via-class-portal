import streamlit as st
import pandas as pd
from datetime import datetime, time, date
import firebase_admin
from firebase_admin import credentials, db
import time
from collections import defaultdict
from zoneinfo import ZoneInfo
import hashlib

SG_TZ = ZoneInfo("Asia/Singapore")

# ============================================================================
# 🔐 PASSWORD UTILITIES
# ============================================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# ============================================================================
# 🍞 TOAST FUNCTION
# ============================================================================
def show_theme_toast(message: str, icon: str = "✨", duration: int = 3000):
    toast_key = f"toast_{datetime.now(SG_TZ).timestamp()}"
    st.markdown(f"""
    <div id="{toast_key}" class="custom-toast">
        <span class="toast-icon">{icon}</span>
        <span>{message}</span>
    </div>
    <script>
        setTimeout(() => {{
            const el = document.getElementById('{toast_key}');
            if (el) el.remove();
        }}, {duration});
    </script>
    """, unsafe_allow_html=True)

# ============================================================================
# 🔐 PERMISSIONS HELPER (Boolean-Based Role Checks)
# ============================================================================
class Permissions:
    """Centralized boolean permission checks for role-based access control"""
    
    def __init__(self, user_roles: list[dict]):
        self.roles = user_roles or []
    
    # ─── PROJECT ACCESS ─────────────────────────────────────────────────────
    def can_access_project(self, project: str) -> bool:
        """Check if user has access to a specific project"""
        return any(
            role.get("project") == project or role.get("project") == "CLASS"
            for role in self.roles
        )
    
    def has_any_project_access(self) -> bool:
        """Check if user has access to at least one project"""
        return any(role.get("project") for role in self.roles)
    
    # ─── ROLE TYPE CHECKS ───────────────────────────────────────────────────
    def is_chairman(self) -> bool:
        """Boolean: Is user a VIA Committee member?"""
        return any(r.get("role_type") == "VIA Committee" for r in self.roles)
    
    def is_teacher(self) -> bool:
        """Boolean: Is user a Teacher?"""
        return any(r.get("role_type") == "Teacher" for r in self.roles)
    
    def is_representative(self, project: str = None) -> bool:
        """Boolean: Is user a representative? Optionally filter by project."""
        if project:
            return any(
                r.get("is_rep", False) and r.get("project") == project
                for r in self.roles
            )
        return any(r.get("is_rep", False) or "Representative" in r.get("role_type", "") 
                  for r in self.roles)
    
    def is_regular_member(self) -> bool:
        """Boolean: Is user a regular VIA member (not rep/teacher/chair)?"""
        return any(r.get("role_type") == "VIA members" for r in self.roles)
    
    # ─── PERMISSION COMBINATIONS ────────────────────────────────────────────
    def can_edit_logs(self) -> bool:
        """Boolean: Can user create/edit activity logs?"""
        return self.is_chairman() or self.is_teacher() or self.is_representative()
    
    def can_manage_attendance(self) -> bool:
        """Boolean: Can user mark attendance?"""
        return self.is_chairman() or self.is_teacher()
    
    def can_view_admin_panel(self) -> bool:
        """Boolean: Can user access admin features?"""
        return self.is_chairman()
    
    def can_assign_bonus_time(self) -> bool:
        """Boolean: Can user award bonus minutes?"""
        return self.is_chairman() or self.is_representative()
    
    def can_delete_content(self) -> bool:
        """Boolean: Can user delete logs/comments?"""
        return self.is_chairman() or self.is_teacher()
    
    def can_manage_user_roles(self) -> bool:
        """Boolean: Can user manage other users' roles?"""
        return self.is_chairman()
    
    # ─── UTILITY ────────────────────────────────────────────────────────────
    def get_accessible_projects(self) -> list[str]:
        """Return list of projects user can access"""
        projects = list(set(
            role.get("project") for role in self.roles 
            if role.get("project") and role.get("project") != "CLASS"
        ))
        if any(r.get("project") == "CLASS" for r in self.roles):
            projects.append("CLASS")
        return projects
    
    def get_primary_project(self) -> str:
        """Return user's primary project (first non-CLASS project, or CLASS)"""
        for role in self.roles:
            if role.get("project") and role.get("project") != "CLASS":
                return role["project"]
        return "CLASS"
    
    def get_role_display_names(self) -> list[str]:
        """Return formatted role names for display"""
        display = []
        for r in self.roles:
            proj = r.get("project", "CLASS")
            role_name = r.get("role_type", "Member")
            sub = r.get("sub_role", "")
            if sub and sub != "N/A":
                display.append(f"{role_name} • {sub} ({proj})")
            else:
                display.append(f"{role_name} ({proj})")
        return display

# ============================================================================
# --- PRE-REGISTERED STUDENT DATA (CHAIRMAN-MANAGED) ---
# ============================================================================
# Format: { "student@gmail.com": { "name": "Full Name", "approved": False } }
# Chairman assigns roles AFTER student signs up via Admin panel
STUDENT_REGISTRY = {
    # === EXAMPLE: Pre-approved students (optional) ===
    # Chairman can still override roles in Admin panel
    "alice.tan@student.edu.sg": {"name": "Alice Tan", "approved": True},
    "bob.lim@student.edu.sg": {"name": "Bob Lim", "approved": True},
    "teacher.ng@student.edu.sg": {"name": "Teacher Ng", "approved": True},
    "chairman.via@student.edu.sg": {"name": "VIA Chairman", "approved": True},
    # Add more students as needed...
}

# ============================================================================
# --- ROLE CONFIGURATION ---
# ============================================================================
ROLE_TYPES = [
    "VIA Committee",      # Chairman role
    "Teacher",            # Teacher role
    "Skit Representative", # Project rep
    "Brochure Representative",
    "VIA members",        # Regular member
]

PROJECT_OPTIONS = ["SKIT", "BROCHURE", "CLASS"]

SUB_ROLES = {
    "SKIT": ["Lead Actor", "Supporting Actor", "Prop Maker", "Cameraman", "Director", "Script Writer", "Editor", "N/A"],
    "BROCHURE": ["Designer", "Writer", "Editor", "Photographer", "Layout Artist", "N/A"],
    "CLASS": ["N/A"],
}

MAX_ROLES_PER_USER = 3  # ← Configurable limit

# ============================================================================
# --- 1. CONFIGURATION ---
# ============================================================================
st.set_page_config(page_title="VIA Class Portal 2026", layout="wide", page_icon="🚀")

# ============================================================================
# --- MODERN DARK THEME CSS ---
# ============================================================================
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
    --primary: #3b82f6;
    --primary-hover: #2563eb;
    --accent: #06b6d4;
    --bg: #0f172a;
    --bg-secondary: #1e293b;
    --bg-tertiary: #334155;
    --card: #1e293b;
    --card-hover: #334155;
    --text: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border: #334155;
    --border-light: #475569;
    --success: #10b981;
    --warning: #f59e0b;
    --error: #ef4444;
    --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    --shadow-lg: 0 20px 25px -5px rgba(0, 0, 0, 0.4);
    --radius: 12px;
    --radius-sm: 8px;
}}

* {{ box-sizing: border-box; }}

html, body, [class*="css"], .stApp {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
}}

.main .block-container {{
    padding: 2rem 3rem !important;
    max-width: 1400px !important;
}}

h1, h2, h3, h4, h5, h6 {{
    color: var(--text) !important;
    font-weight: 600 !important;
    letter-spacing: -0.025em !important;
}}

h1 {{ font-size: 2.25rem !important; }}
h2 {{ font-size: 1.875rem !important; }}
h3 {{ font-size: 1.5rem !important; }}

p, span, div, label, li {{
    color: var(--text) !important;
    line-height: 1.6 !important;
}}

.stCaption, small, .stMarkdown p {{
    color: var(--text-secondary) !important;
    font-size: 0.875rem !important;
}}

div[data-testid="stContainer"], .stCard, .cal-container {{
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.5rem !important;
    box-shadow: var(--shadow) !important;
    transition: all 0.3s ease !important;
}}

div[data-testid="stContainer"]:hover {{
    border-color: var(--border-light) !important;
    box-shadow: var(--shadow-lg) !important;
}}

section[data-testid="stSidebar"] {{
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
    padding: 1.5rem !important;
}}

section[data-testid="stSidebar"] * {{
    color: var(--text) !important;
}}

.user-card {{
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--card) 100%) !important;
    padding: 1.25rem !important;
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    margin-bottom: 1.5rem !important;
    box-shadow: var(--shadow) !important;
}}

.sidebar-title {{
    font-size: 1.125rem !important;
    font-weight: 600 !important;
    color: var(--text) !important;
    margin-bottom: 1rem !important;
    padding-bottom: 0.75rem !important;
    border-bottom: 2px solid var(--border) !important;
}}

.sidebar-section {{
    font-size: 0.75rem !important;
    color: var(--text-muted) !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-weight: 600 !important;
}}

input, textarea, select {{
    color: var(--text) !important;
    background-color: var(--bg-secondary) !important;
    border: 2px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.75rem 1rem !important;
    font-size: 0.875rem !important;
    transition: all 0.2s ease !important;
}}

input:focus, textarea:focus, select:focus {{
    border-color: var(--primary) !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
}}

input::placeholder, textarea::placeholder {{
    color: var(--text-muted) !important;
}}

.stButton > button {{
    background: var(--primary) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.75rem 1.5rem !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3) !important;
}}

.stButton > button:hover {{
    background: var(--primary-hover) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.4) !important;
}}

.stButton > button[kind="secondary"] {{
    background: var(--bg-secondary) !important;
    color: var(--text) !important;
    border: 2px solid var(--border) !important;
    box-shadow: none !important;
}}

.stButton > button[kind="secondary"]:hover {{
    background: var(--bg-tertiary) !important;
    border-color: var(--border-light) !important;
}}

[data-testid="stMetric"] {{
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.5rem !important;
    box-shadow: var(--shadow) !important;
    transition: all 0.3s ease !important;
}}

[data-testid="stMetric"]:hover {{
    transform: translateY(-2px) !important;
    box-shadow: var(--shadow-lg) !important;
}}

[data-testid="stMetricValue"] {{
    color: var(--text) !important;
    font-size: 2rem !important;
    font-weight: 700 !important;
}}

[data-testid="stMetricLabel"] {{
    color: var(--text-secondary) !important;
    font-size: 0.875rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}}

div[data-baseweb="select"] > div,
div[data-baseweb="popover"],
div[data-baseweb="menu"],
div[role="option"] {{
    background-color: var(--bg-secondary) !important;
    color: var(--text) !important;
    border: 2px solid var(--border) !important;
}}

div[role="option"]:hover,
div[role="option"][aria-selected="true"] {{
    background-color: var(--primary) !important;
    color: white !important;
}}

[data-testid="stDataFrame"] {{
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}}

[data-testid="stDataFrame"] thead {{
    background: var(--bg-secondary) !important;
    border-bottom: 2px solid var(--border) !important;
}}

[data-testid="stDataFrame"] tbody tr {{
    border-bottom: 1px solid var(--border) !important;
}}

[data-testid="stDataFrame"] tbody tr:hover {{
    background: var(--bg-secondary) !important;
}}

.stAlert, .stInfo, .stSuccess, .stWarning, .stError {{
    background: var(--card) !important;
    border-left: 4px solid var(--primary) !important;
    color: var(--text) !important;
    border-radius: var(--radius-sm) !important;
}}

.stWarning {{ border-left-color: var(--warning) !important; }}
.stError {{ border-left-color: var(--error) !important; }}
.stSuccess {{ border-left-color: var(--success) !important; }}

.stProgress > div > div {{
    background: linear-gradient(90deg, var(--primary) 0%, var(--accent) 100%) !important;
    border-radius: 9999px !important;
}}

.stProgress > div {{
    background: var(--bg-secondary) !important;
    border-radius: 9999px !important;
    height: 8px !important;
}}

.stTabs [data-baseweb="tab-list"] {{
    background: var(--bg-secondary) !important;
    border-bottom: 2px solid var(--border) !important;
    border-radius: var(--radius) var(--radius) 0 0 !important;
    padding: 0.5rem !important;
}}

.stTabs [data-baseweb="tab"] {{
    color: var(--text-secondary) !important;
    background: transparent !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.75rem 1.25rem !important;
    font-weight: 500 !important;
}}

.stTabs [aria-selected="true"] {{
    color: var(--text) !important;
    background: var(--primary) !important;
}}

.streamlit-expanderHeader {{
    background: var(--card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    padding: 1rem !important;
}}

.streamlit-expanderHeader:hover {{
    background: var(--card-hover) !important;
}}

.streamlit-expanderContent {{
    background: var(--card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-top: none !important;
    padding: 1rem !important;
}}

hr, .stDivider {{
    border-color: var(--border) !important;
    opacity: 0.5 !important;
    margin: 1.5rem 0 !important;
}}

div[data-baseweb="radio"] label,
div[data-baseweb="checkbox"] label {{
    color: var(--text) !important;
}}

div[data-baseweb="radio"] input,
div[data-baseweb="checkbox"] input {{
    accent-color: var(--primary) !important;
}}

pre, code {{
    background: var(--bg-secondary) !important;
    color: var(--accent) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}}

.custom-toast {{
    position: fixed;
    top: 20px;
    right: 20px;
    background: var(--card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1rem 1.5rem !important;
    box-shadow: var(--shadow-lg) !important;
    z-index: 9999 !important;
    font-weight: 500 !important;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    animation: slideIn 0.3s ease, fadeOut 0.3s ease 2.7s forwards;
}}

@keyframes slideIn {{
    from {{ opacity: 0; transform: translateX(100px); }}
    to {{ opacity: 1; transform: translateX(0); }}
}}

@keyframes fadeOut {{
    from {{ opacity: 1; transform: translateX(0); }}
    to {{ opacity: 0; transform: translateX(100px); }}
}}

.empty-state {{
    text-align: center !important;
    padding: 3rem !important;
    color: var(--text-muted) !important;
    background: var(--card) !important;
    border-radius: var(--radius) !important;
    border: 2px dashed var(--border) !important;
}}

::-webkit-scrollbar {{
    width: 8px !important;
    height: 8px !important;
}}

::-webkit-scrollbar-track {{
    background: var(--bg-secondary) !important;
}}

::-webkit-scrollbar-thumb {{
    background: var(--border-light) !important;
    border-radius: 4px !important;
}}

::-webkit-scrollbar-thumb:hover {{
    background: var(--primary) !important;
}}

.login-container {{
    max-width: 450px;
    margin: 2rem auto;
    padding: 2rem;
}}

.login-card {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 2.5rem;
    box-shadow: 0 20px 40px rgba(0,0,0,0.4);
}}

.login-title {{
    text-align: center;
    margin-bottom: 0.5rem;
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}

.login-subtitle {{
    text-align: center;
    color: #94a3b8;
    margin-bottom: 2rem;
    font-size: 0.95rem;
}}

.role-badge {{
    display: inline-block;
    background: var(--bg-tertiary);
    color: var(--text);
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    margin: 2px;
    border: 1px solid var(--border);
}}

.role-badge.representative {{
    background: linear-gradient(135deg, var(--primary), var(--accent));
    border: none;
    font-weight: 600;
}}

@media (max-width: 768px) {{
    .main .block-container {{
        padding: 1rem !important;
    }}
}}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# --- 2. FIREBASE INITIALIZATION ---
# ============================================================================
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

# ============================================================================
# --- 3. DATA PERSISTENCE ---
# ============================================================================
def load_data():
    try:
        ref = db.reference("via_master_record")
        data = ref.get()
        if data:
            if "events" in data:
                for event in data["events"]:
                    try:
                        if isinstance(event.get("date"), str):
                            try:
                                event["date"] = datetime.fromisoformat(event["date"]).date()
                            except (ValueError, TypeError):
                                event["date"] = date.today()
                        if isinstance(event.get("start_time"), str):
                            event["start_time"] = datetime.strptime(event["start_time"], "%H:%M").time()
                        if "end_time" in event and isinstance(event.get("end_time"), str):
                            event["end_time"] = datetime.strptime(event["end_time"], "%H:%M").time()
                    except Exception as err:
                        print("Event parsing error:", err)
                        continue
            return data
        return {
            "members": [], "accounts": [], "logs": [], "contributions": {},
            "events": [], "rsvp": [], "attendance": {}, "signup_enabled": False
        }
    except Exception as e:
        print("Load error:", e)
        return {
            "members": [], "accounts": [], "logs": [], "contributions": {},
            "events": [], "rsvp": [], "attendance": {}, "signup_enabled": False
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
                    "log_id": log_id, "user": "SYSTEM", "date": str(event_date),
                    "minutes": 0, "task": f"AUTO REPORT: {e['type']} completed",
                    "project": e["project"], "comments": []
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
        "log_id": f"b_{datetime.now(SG_TZ).strftime('%H%M%S')}",
        "user": user, "action": action,
        "time": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

def render_event_calendar(events, selected_project):
    import calendar
    from datetime import datetime, date, timedelta
    today = date.today()
    current_month = today.month
    current_year = today.year
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    month_events = {}
    reminders = []
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
    if reminders:
        for r in reminders:
            st.warning(r, icon="🔔")
    st.markdown(f"<h3 style='text-align: center; color: var(--primary); margin: 20px 0;'>📅 {month_name} {current_year}</h3>", unsafe_allow_html=True)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header_cols = st.columns(7)
    for i, name in enumerate(day_names):
        with header_cols[i]:
            st.markdown(f"<div style='text-align: center; font-weight: 600; color: var(--text-secondary); padding-bottom: 10px; border-bottom: 2px solid var(--border);'>{name}</div>", unsafe_allow_html=True)
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    for week in cal:
        week_cols = st.columns(7)
        for i, day in enumerate(week):
            with week_cols[i]:
                st.markdown("<div style='height: 55px;'>&nbsp;</div>", unsafe_allow_html=True)
                if day != 0:
                    has_event = day in month_events
                    if has_event:
                        if st.button(str(day), key=f"cal_btn_{day}_{current_month}", type="secondary"):
                            st.session_state.cal_day_selected = day
                    else:
                        st.markdown(f"<p style='text-align: center; color: var(--text); font-size: 14px; margin-top: 10px;'>{day}</p>", unsafe_allow_html=True)
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    if st.session_state.get('cal_day_selected') and st.session_state.cal_day_selected in month_events:
        st.markdown(f"<h4 style='color: var(--text); margin: 20px 0 10px 0;'>📅 Events on {st.session_state.cal_day_selected} {month_name}</h4>", unsafe_allow_html=True)
        for evt in month_events[st.session_state.cal_day_selected]:
            with st.container():
                st.markdown(f"""
                <div style="background: var(--card); padding: 15px; border-radius: 10px; border-left: 4px solid var(--primary); margin-bottom: 10px; border: 1px solid var(--border);">
                    <h5 style="color: var(--text); margin: 0 0 10px 0;">{evt['type']}</h5>
                    <p style="color: var(--text-secondary); margin: 0;">
                        📍 {evt.get('venue', 'N/A')} <br>
                        ⏰ {evt['start_time'].strftime('%I:%M %p') if hasattr(evt['start_time'], 'strftime') else evt.get('start_time', 'N/A')}
                    </p>
                </div>
                """, unsafe_allow_html=True)
        if st.button("✕ Close", key="close_cal", type="secondary"):
            st.session_state.cal_day_selected = None
            st.rerun()

# ============================================================================
# --- APP INITIALIZATION ---
# ============================================================================
if "data" not in st.session_state:
    st.session_state.data = load_data()
    for acc in st.session_state.data.get("accounts", []):
        if "password_hash" not in acc and "password" in acc:
            acc["password_hash"] = hash_password(acc["password"])
            del acc["password"]
        elif "password_hash" not in acc:
            acc["password_hash"] = None
            acc["is_legacy"] = True
    for m in st.session_state.data.get("members", []):
        m.setdefault("name", "Unknown")
        m.setdefault("project", None)
        m.setdefault("role_type", "PROJECT")
        m.setdefault("is_rep", False)
        m.setdefault("sub_role", "N/A")

if not st.session_state.get("auto_generated"):
    generate_event_reports()
    save_data()
    st.session_state.auto_generated = True

st.session_state._migrated = True

for log in st.session_state.data.get("logs", []):
    for c in log.get("comments", []):
        if "comment_id" not in c:
            c["comment_id"] = str(datetime.now(SG_TZ).timestamp())

required_keys = ["members", "accounts", "logs", "contributions", "events", "rsvp", "attendance", "signup_enabled"]
for key in required_keys:
    if key not in st.session_state.data:
        st.session_state.data[key] = {} if key in ["contributions", "attendance"] else [] if key != "signup_enabled" else False

if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "u_name" not in st.session_state: st.session_state.u_name = ""
if "u_role" not in st.session_state: st.session_state.u_role = ""
if "u_email" not in st.session_state: st.session_state.u_email = ""
if "u_roles" not in st.session_state: st.session_state.u_roles = []
if "u_primary_role" not in st.session_state: st.session_state.u_primary_role = ""
if "perms" not in st.session_state: st.session_state.perms = None  # ← NEW

# ============================================================================
# --- 4. AUTHENTICATION (CHAIRMAN-MANAGED ROLES) ---
# ============================================================================
USER_PASSWORDS = {
    "Teacher": "teach2026", "VIA Committee": "comm2026",
    "Skit Representative": "skit2026", "Brochure Representative": "brochure2026",
    "VIA members": "member2026", "Classmates": "class2026"
}
CHAIRMAN_SECRET_PW = "chair2026"

if not st.session_state.authenticated:
    st.markdown("""
    <div class="login-container">
        <div class="login-card">
            <h1 class="login-title">🚀 VIA Portal 2026</h1>
            <p class="login-subtitle">Sign in with your official student Gmail</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    signup_enabled = st.session_state.data.get("signup_enabled", False)
    auth_mode = st.radio("Choose Action", ["🔐 Sign In", "📝 Sign Up"] if signup_enabled else ["🔐 Sign In"], horizontal=True, label_visibility="collapsed")

    if auth_mode == "🔐 Sign In":
        with st.form("login", clear_on_submit=False):
            email_in = st.text_input("Student Gmail", placeholder="e.g., yourname@student.edu.sg").strip().lower()
            pw_in = st.text_input("Password", type="password", placeholder="Enter your password")
            login_btn = st.form_submit_button("Sign In", use_container_width=True)

            if login_btn:
                if not email_in or not pw_in:
                    st.error("❌ Please enter both Gmail and password")
                    st.stop()
                
                # Look up student account
                user_account = next((acc for acc in st.session_state.data.get("accounts", [])
                                   if acc.get("email", "").lower() == email_in), None)
                
                if not user_account:
                    st.error("❌ Account not found. Please sign up first or contact your Chairman.")
                    st.stop()
                
                # Verify password
                if not verify_password(pw_in, user_account.get("password_hash", "")):
                    st.error("❌ Invalid password")
                    st.stop()
                
                # ✅ Authentication successful - load roles from account
                st.session_state.authenticated = True
                st.session_state.u_name = user_account["name"]
                st.session_state.u_email = email_in
                st.session_state.u_roles = user_account.get("roles", [])  # ← Load assigned roles
                st.session_state.u_primary_role = user_account.get("roles", [{}])[0].get("role_type", "VIA members") if user_account.get("roles") else "VIA members"
                
                # Initialize permissions
                st.session_state.perms = Permissions(st.session_state.u_roles)
                
                log_system_event(f"LOGIN → {user_account['name']} signed in with {email_in}", user_account["name"])
                save_data()

                with st.spinner("Entering portal..."):
                    time.sleep(1)

                st.success(f"Welcome, {user_account['name']}!")
                st.rerun()

    elif auth_mode == "📝 Sign Up" and signup_enabled:
        st.info("🔐 Create your account using your official student Gmail. Your roles will be assigned by the Chairman after approval.")
        with st.form("signup", clear_on_submit=False):
            su_email = st.text_input("Student Gmail", placeholder="e.g., yourname@student.edu.sg").strip().lower()
            su_name = st.text_input("Full Name (as registered)", placeholder="Enter your full name").strip().title()
            su_pw = st.text_input("Create Password", type="password", key="signup_pw", placeholder="Min 6 characters")
            su_pw_confirm = st.text_input("Confirm Password", type="password", key="signup_pw_confirm", placeholder="Re-enter password")
            signup_btn = st.form_submit_button("Create Account", use_container_width=True)

            if signup_btn:
                if not su_email or not su_pw:
                    st.error("❌ Gmail and password are required")
                elif su_pw != su_pw_confirm:
                    st.error("❌ Passwords do not match")
                elif len(su_pw) < 6:
                    st.error("❌ Password must be at least 6 characters")
                elif su_email in STUDENT_REGISTRY and STUDENT_REGISTRY[su_email].get("approved", False):
                    st.error("❌ This email is already pre-registered. Please sign in instead.")
                else:
                    # Prevent duplicate accounts
                    existing = next((acc for acc in st.session_state.data.get("accounts", [])
                                   if acc.get("email", "").lower() == su_email), None)
                    if existing:
                        st.error("❌ Account already exists. Please sign in instead.")
                    else:
                        # Create account with EMPTY roles (Chairman assigns later)
                        new_account = {
                            "name": su_name, 
                            "email": su_email,
                            "password_hash": hash_password(su_pw),
                            "roles": [],  # ← Empty until Chairman assigns
                            "status": "pending_approval",  # ← New field
                            "created_at": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                            "created_by": "SELF"
                        }
                        st.session_state.data.setdefault("accounts", []).append(new_account)
                        
                        log_system_event(f"SIGNUP → {su_name} created account (pending approval)", su_name)
                        save_data()
                        st.success(f"✅ Account created! Please wait for Chairman to assign your roles.")
                        time.sleep(3)
                        st.rerun()

    st.stop()

# ============================================================================
# --- POST-AUTH: Multi-Role Handling ---
# ============================================================================
if st.session_state.authenticated:
    c_name = st.session_state.u_name
    user_roles = st.session_state.get("u_roles", [])
    perms = st.session_state.perms  # ← Use Permissions instance
    
    # Check if user has been assigned any roles yet
    if not user_roles and not perms.is_chairman():
        st.warning(f"🔐 Your account is pending role assignment. Please contact the Chairman to activate your access.", icon="⚠️")
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.rerun()
        st.stop()
    
    # Project view selector for multi-project users
    projects_available = perms.get_accessible_projects()
    
    if len(projects_available) > 1:
        st.sidebar.markdown("---")
        st.sidebar.markdown("<div class='sidebar-section'>🎯 Project View</div>", unsafe_allow_html=True)
        view_proj_options = [f"🎭 SKIT" if p=="SKIT" else f"📄 BROCHURE" if p=="BROCHURE" else f"📚 CLASS" for p in projects_available]
        view_proj = st.sidebar.radio("", view_proj_options, label_visibility="collapsed", index=0)
        view_proj = "SKIT" if "SKIT" in view_proj else "BROCHURE" if "BROCHURE" in view_proj else "CLASS"
    elif projects_available:
        view_proj = projects_available[0]
    else:
        view_proj = "CLASS"
    
    # Update sidebar user card to show ALL assigned roles with badges
    role_badges_html = "".join([
        f'<span class="role-badge{" representative" if r.get("is_rep") else ""}">{r.get("role_type").replace(" Representative", "")} • {r.get("sub_role", "")}</span>'
        for r in user_roles
    ]) if user_roles else '<span class="role-badge">No roles assigned</span>'
    
    st.sidebar.markdown(f"""
    <div class="user-card">
        <div style="font-size:16px; font-weight:700;">👤 {c_name}</div>
        <div style="margin: 8px 0; display: flex; flex-wrap: wrap; gap: 4px;">{role_badges_html}</div>
        <div style="color: var(--text-muted); font-size:11px; margin-top:4px;">📧 {st.session_state.get('u_email', '')}</div>
    </div>
    """, unsafe_allow_html=True)

    # ============================================================================
    # --- 5. SIDEBAR ACTIONS ---
    # ============================================================================
    st.sidebar.markdown("---")
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
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        log_system_event(f"LOGOUT → {c_name} signed out", c_name)
        save_data()
        st.session_state.authenticated = False
        st.rerun()

    # ============================================================================
    # --- 6. TABS DEFINITION ---
    # ============================================================================
    tabs_list = ["🏠 Dashboard", "✅ Attendance", "🕒 Activity Log", "📊 Progress", "📁 Directory"]
    
    # Boolean guard for admin tab using Permissions class
    if perms.can_view_admin_panel():
        tabs_list.append("⚙️ Admin")
    
    active_tab = st.tabs(tabs_list)

    # ============================================================================
    # --- TAB 0: DASHBOARD ---
    # ============================================================================
    with active_tab[0]:
        st.title(f"🚀 {view_proj} Project Portal")
        all_events = [e for e in st.session_state.data.get("events", []) if e.get("project") == view_proj]
        today = date.today()
        current_events, history_events = [], []
        for e in all_events:
            try:
                event_date = e.get("date")
                if isinstance(event_date, str):
                    event_date = datetime.fromisoformat(event_date).date()
                elif isinstance(event_date, datetime):
                    event_date = event_date.date()
                if e.get("status") == "Cancelled" or event_date < today:
                    history_events.append(e)
                else:
                    current_events.append(e)
            except:
                continue
        mems = [m for m in st.session_state.data.get("members", []) if m.get("role_type", "PROJECT") == "CLASS" or m.get("project") == view_proj]

        st.markdown("## 📊 Overview")
        m1, m2, m3, m4 = st.columns(4)
        u_key = f"{c_name}_{view_proj}"
        m = st.session_state.data.get('contributions', {}).get(u_key, 0)

        with m1:
            st.markdown(f"""
            <div style="text-align: center; padding: 1.5rem;">
                <div style="font-size: 2.5rem; font-weight: 700; color: var(--primary);">{m // 60}h {m % 60}m</div>
                <div style="color: var(--text-secondary); font-size: 0.875rem; margin-top: 0.5rem;">Your Hours</div>
            </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
            <div style="text-align: center; padding: 1.5rem;">
                <div style="font-size: 2.5rem; font-weight: 700; color: var(--success);">{len(current_events)}</div>
                <div style="color: var(--text-secondary); font-size: 0.875rem; margin-top: 0.5rem;">Upcoming</div>
            </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown(f"""
            <div style="text-align: center; padding: 1.5rem;">
                <div style="font-size: 2.5rem; font-weight: 700; color: var(--accent);">{len(history_events)}</div>
                <div style="color: var(--text-secondary); font-size: 0.875rem; margin-top: 0.5rem;">Completed</div>
            </div>
            """, unsafe_allow_html=True)
        with m4:
            st.markdown(f"""
            <div style="text-align: center; padding: 1.5rem;">
                <div style="font-size: 2.5rem; font-weight: 700; color: var(--warning);">{len(mems)}</div>
                <div style="color: var(--text-secondary); font-size: 0.875rem; margin-top: 0.5rem;">Team Size</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        col1, col2 = st.columns([3, 1])

        with col1:
            st.subheader("🗓️ Event Calendar")
            render_event_calendar(st.session_state.data.get("events", []), view_proj)
            st.markdown("---")
            st.subheader("📅 Event RSVP")
            if not current_events:
                st.info("📅 No upcoming events. Check back later or contact your rep.")
            else:
                for i, e in enumerate(current_events):
                    with st.container():
                        st.markdown(f"""
                        <div style="background: var(--card); padding:16px; border-radius:12px; border-left:5px solid var(--primary); margin-bottom:10px; border: 1px solid var(--border);">
                            <h4 style="margin: 0 0 10px 0;">{e['type']}</h4>
                            <p style="color: var(--text-secondary); margin: 0;">
                            📍 {e.get('venue','N/A')} <br>
                            ⏰ {e['start_time'].strftime("%I:%M %p") if hasattr(e['start_time'], 'strftime') else e.get('start_time', 'N/A')} <br>
                            📅 {e['date']}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                    eid = f"{e['project']}_{e['date']}_{e['start_time']}"
                    existing = next((rv for rv in st.session_state.data.get("rsvp", []) if rv["event_id"] == eid and rv["name"] == c_name), None)
                    status_default = existing["status"] if existing else "Attending"
                    reason_default = existing.get("reason", "") if existing else ""

                    col_r1, col_r2 = st.columns([1, 2])
                    with col_r1:
                        status = st.selectbox("Status", ["Attending", "Late", "Not Attending"], index=["Attending", "Late", "Not Attending"].index(status_default), key=f"status_{eid}_{i}")
                    with col_r2:
                        reason = st.text_input("Reason (optional)", value=reason_default, key=f"reason_{eid}_{i}")

                    if st.button("Submit RSVP", key=f"rsvp_btn_{eid}_{i}"):
                        st.session_state.data["rsvp"] = [rv for rv in st.session_state.data.get("rsvp", []) if not (rv["event_id"] == eid and rv["name"] == c_name)]
                        st.session_state.data["rsvp"].append({"event_id": eid, "name": c_name, "status": status, "reason": reason})
                        log_system_event(f"RSVP: {status} for {e['type']}", c_name)
                        save_data()
                        st.success("RSVP updated!")
                        st.rerun()

            st.divider()
            st.subheader("📜 Event History")
            if not history_events:
                st.caption("No past or cancelled events.")
            else:
                for e in reversed(history_events):
                    event_date = datetime.fromisoformat(e["date"]).date() if isinstance(e["date"], str) else e["date"]
                    with st.container(border=True):
                        if e.get("status") == "Cancelled":
                            st.markdown(f"""
                            <div style="background: var(--error); color: white; padding: 8px 12px; border-radius: 6px; display: inline-block; font-weight: 600; margin-bottom: 8px;">🚫 CANCELLED: {e['type']}</div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div style="background: var(--success); color: white; padding: 8px 12px; border-radius: 6px; display: inline-block; font-weight: 600; margin-bottom: 8px;">✅ COMPLETED: {e['type']}</div>
                            """, unsafe_allow_html=True)
                        st.caption(f"📅 {e['date']} | 📍 {e.get('venue', 'N/A')}")

        with col2:
            st.subheader("👥 Team Roster")
            if not mems:
                st.info("👥 No members yet. Add from Admin panel.")
            for m in mems:
                rep_badge = "⭐" if m.get('is_rep') else "👤"
                st.markdown(f"{rep_badge} **{m.get('name')}**")
                sub_role = m.get('sub_role', 'N/A')
                if sub_role and sub_role != "N/A":
                    st.caption(f"Focus: {sub_role}")

    # ============================================================================
    # --- TAB 1: ATTENDANCE ---
    # ============================================================================
    with active_tab[1]:
        st.title("✅ Attendance Tracker")
        evs = [e for e in st.session_state.data["events"] if e["project"] == view_proj and e.get("status") != "Cancelled"]
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
                    # Boolean permission check for attendance editing
                    if perms.can_manage_attendance():
                        p = col2.checkbox("Present", value=rec["p"], key=f"p_{n}_{eid}")
                        d = col3.selectbox("Session", ["Full", "Half"], index=0 if rec["d"]=="Full" else 1, key=f"d_{n}_{eid}")
                        st.session_state.data["attendance"].setdefault(eid, {})[n] = {"p": p, "d": d}
                    else:
                        col2.write("✅" if rec["p"] else "❌")
                        col3.write(rec["d"])
                # Boolean guard for save button
                if perms.can_manage_attendance() and st.button("Save Attendance"):
                    save_data()
                    st.success("Saved!")

    # ============================================================================
    # --- TAB 2: ACTIVITY LOG ---
    # ============================================================================
    with active_tab[2]:
        st.title("🕒 Activity Log")

        # Boolean guard for log creation form
        if perms.can_edit_logs():
            with st.expander("➕ Log New Activity", expanded=False):
                with st.form(f"log_{view_proj}", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        ld = st.date_input("Date", value=date.today())
                        lt = st.text_input("Task", placeholder="What did you work on?")
                    with col2:
                        lm = st.number_input("Minutes", min_value=5, step=5, value=30)
                        # Only show projects user has access to
                        lp_options = [p for p in ["SKIT", "BROCHURE"] if perms.can_access_project(p)]
                        lp = st.selectbox("Project", lp_options if lp_options else ["CLASS"], index=0 if view_proj=="SKIT" else 1 if lp_options else 0)

                    if st.form_submit_button("Submit Log", use_container_width=True):
                        if lt.strip():
                            log_system_event(f"Added log: {lt}", c_name)
                            st.session_state.data["logs"].append({
                                "log_id": f"event_{datetime.now(SG_TZ).timestamp()}",
                                "user": c_name, "date": str(ld), "minutes": lm,
                                "task": lt, "project": lp, "comments": []
                            })
                            save_data()
                            st.success("✅ Activity logged successfully!")
                            st.rerun()
                        else:
                            st.error("Please enter a task description")

        st.divider()
        st.subheader("📜 Recent Activity & Teacher Feedback")
        proj_logs = [l for l in st.session_state.data.get("logs", []) if l.get("project") == view_proj]

        for log in reversed(proj_logs):
            with st.container(border=True):
                is_system = log.get("user") == "SYSTEM"
                ct, cs = st.columns([3, 1])
                ct.markdown(f"**{log['user']}** - {log['task']}\n\n📅 {log['date']}")
                cs.info(f"{log['minutes']} mins")

            if is_system:
                st.caption("🔒 System-generated report")

            # Boolean guard for teacher-only actions
            if perms.is_teacher() and not is_system:
                col1, col2 = st.columns(2)
                if col1.button("🗑️ Delete", key=f"del_{log['log_id']}"):
                    log_system_event(f"Deleted activity: {log['task']}", c_name)
                    st.session_state.data["logs"] = [l for l in st.session_state.data["logs"] if l.get("log_id") != log["log_id"]]
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

            for c in log.get("comments", []):
                comment_id = c.get("comment_id")
                teacher_name = c.get("teacher", "Unknown")
                st.markdown(f"**{teacher_name}**")
                st.write(c.get("text", ""))

                if perms.is_teacher() and teacher_name == c_name and comment_id:
                    action_col1, action_col2, _ = st.columns([1, 1, 6])
                    if action_col1.button("🗑️ Delete", key=f"del_c_{comment_id}"):
                        log_system_event(f"Deleted comment: {c.get('text','')[:30]}", c_name)
                        log["comments"] = [x for x in log["comments"] if x.get("comment_id") != comment_id]
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

    # ============================================================================
    # --- TAB 3: PROGRESS ---
    # ============================================================================
    with active_tab[3]:
        st.title("📊 Class Progress Tracker")
        all_m, all_c = st.session_state.data.get("members", []), st.session_state.data.get("contributions", {})
        st.metric("Total Class VIA Minutes", f"{sum(all_c.values())} mins")

        # Boolean guard for bonus time assignment
        if perms.can_assign_bonus_time():
            st.subheader("⚙️ Project Time Adjustments")
            col1, col2 = st.columns(2)
            with col1:
                with st.expander("➕ Add Project Bonus"):
                    with st.form("bonus_f"):
                        # Only show projects user can access
                        tp_options = [p for p in ["SKIT", "BROCHURE"] if perms.can_access_project(p)]
                        tp = st.selectbox("Project", tp_options if tp_options else ["CLASS"], key="b1")
                        unames = [m.get('name', 'Unknown') for m in all_m if m.get('project') == tp or tp == "CLASS"]
                        tu = st.selectbox("Student", unames if unames else ["None"], key="b2")
                        bm = st.number_input("Minutes", 1, step=5)
                        ra = st.text_input("Reason")
                        if st.form_submit_button("Apply Bonus") and tu != "None":
                            selected_member = next((m for m in all_m if m.get("name") == tu), None)
                            if selected_member:
                                proj = selected_member.get("project") or tp
                                ukey = f"{tu}_{proj}"
                                st.session_state.data["contributions"][ukey] = st.session_state.data["contributions"].get(ukey, 0) + bm
                                st.session_state.data["logs"].append({
                                    "log_id": f"b_{datetime.now(SG_TZ).strftime('%H%M%S')}",
                                    "user": tu, "date": str(date.today()), "minutes": bm,
                                    "task": f"BONUS: {ra}", "project": proj, "comments": []
                                })
                                save_data()
                                st.rerun()
                            else:
                                st.error("Student not found")

        ts1, ts2 = st.tabs(["🎭 Skit Team", "📄 Brochure Team"])
        for proj, t in [("SKIT", ts1), ("BROCHURE", ts2)]:
            with t:
                members_proj = [m for m in all_m if m.get("role_type") == "CLASS" or m.get("project") == proj]
                if not members_proj:
                    st.info("No members in this project yet.")
                else:
                    for m in members_proj:
                        mins = all_c.get(f"{m.get('name')}_{proj}", 0)
                        total_h = mins // 60
                        total_m = mins % 60
                        with st.container():
                            st.markdown(f"""
                            <div style="background: var(--card); padding:14px; border-radius:10px; margin-bottom:10px; border: 1px solid var(--border);">
                                <b style="color: var(--text);">{m.get('name')}</b><br>
                                <span style="color: var(--text-secondary);">⏱️ {total_h}h {total_m}m logged</span>
                            </div>
                            """, unsafe_allow_html=True)
                        class_avg = sum(all_c.values()) / len(all_m) if all_m else 300
                        progress_val = max(0.0, min(1.0, mins / max(class_avg, 1)))
                        st.progress(progress_val)

    # ============================================================================
    # --- TAB 4: DIRECTORY ---
    # ============================================================================
    with active_tab[4]:
        st.title("📁 Official Class Directory")
        all_m = st.session_state.data.get("members", [])
        all_c = st.session_state.data.get("contributions", {})

        people = {}
        for m in all_m:
            name = m["name"]
            if name not in people:
                people[name] = {"projects": set(), "roles": set()}
            people[name]["projects"].add(m.get("project", "CLASS"))
            people[name]["roles"].add(m.get("sub_role", "N/A"))

        unique_count = len(people)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Members", unique_count)
        avg = sum(all_c.values()) // unique_count if unique_count else 0
        m2.metric("Average Time", f"{avg//60}h {avg%60}m")
        m3.metric("Active Projects", "2")

        f1, f2 = st.columns([2, 1])
        s = f1.text_input("🔍 Search", placeholder="Search by name...")
        pf = f2.selectbox("Filter", ["All", "SKIT", "BROCHURE", "CLASS"])

        summary = []
        for name, data in people.items():
            total_minutes = sum(all_c.get(f"{name}_{p}", 0) for p in data["projects"])
            summary.append({
                "NAME": name,
                "PROJECTS": " | ".join(sorted({str(p) if p else "CLASS" for p in data["projects"]})),
                "ROLE": " | ".join(sorted({str(r) if r else "N/A" for r in data["roles"]})),
                "VIA TIME": f"{total_minutes//60}h {total_minutes%60}m",
                "STATUS": "✅ Active" if total_minutes > 0 else "⏳ No Logs"
            })

        df = pd.DataFrame(summary)
        if s:
            df = df[df["NAME"].str.contains(s, case=False)]
        if pf != "All":
            df = df[df["PROJECTS"].str.contains(pf)]

        if df.empty:
            st.markdown("""
            <div class="empty-state">
                <h3>📭 No Results Found</h3>
                <p>Try adjusting your search or filter criteria</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button("📥 Download CSV", df.to_csv(index=False), f"VIA_{date.today()}.csv", "text/csv")

    # ============================================================================
    # --- TAB 5: ADMIN (Chairman Only) ---
    # ============================================================================
    if perms.can_view_admin_panel():
        with active_tab[5]:
            st.title("⚙️ Chairman Master Control")
            at1, at2, at3, at4, at5, at6, at7, at8 = st.tabs([
                "👥 Roster", "📅 Events", "🔐 Accounts", "⚖️ Corrections",
                "⚠️ Reset", "🖥️ Terminal", "👤 User Manager", "🎭 Role Assignment"  # ← NEW TAB
            ])

            with at1:
                st.subheader("➕ Add Member")
                with st.form("add_member_form"):
                    cn, cp = st.columns(2)
                    n = cn.text_input("Name")
                    p = cp.selectbox("Project", PROJECT_OPTIONS)
                    cr, cs = st.columns(2)
                    r = cr.checkbox("Rep?")
                    s_options = SUB_ROLES.get(p, SUB_ROLES["CLASS"])
                    s = cs.selectbox("Role", s_options)
                    if st.form_submit_button("Add Member"):
                        if not n.strip():
                            st.error("Name cannot be empty")
                        else:
                            role_type = "CLASS" if p == "CLASS" else ("Skit Representative" if p=="SKIT" and r else "Brochure Representative" if p=="BROCHURE" and r else "VIA members")
                            st.session_state.data["members"].append({
                                "name": n, "project": None if role_type == "CLASS" else p,
                                "role_type": role_type, "is_rep": r, "sub_role": s
                            })
                            log_system_event(f"Added member: {n} ({p}, {s})", c_name)
                            save_data()
                            st.rerun()

                st.divider()
                st.subheader("🗑️ Remove Members")
                for i, m in enumerate(st.session_state.data.get("members", [])):
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        proj_display = m.get("project") if m.get("project") else "CLASS"
                        c1.write(f"**{m.get('name','Unknown')}** ({proj_display})")
                        c1.caption(f"Role: {m.get('sub_role','N/A')}")
                        if c2.button("🗑️ Delete", key=f"del_member_{i}"):
                            log_system_event(f"Deleted member: {m.get('name')} ({m.get('project')})", c_name)
                            st.session_state.data["members"].pop(i)
                            save_data()
                            st.rerun()

            with at2:
                st.subheader("🗓️ Manage Events")
                with st.form("add_e"):
                    ep = st.selectbox("Project", ["SKIT", "BROCHURE"])
                    ty = st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"])
                    d = st.date_input("Date")
                    st_time = st.time_input("Start")
                    v = st.text_input("Venue")
                    if st.form_submit_button("Add Event"):
                        log_system_event(f"Created event: {ty}", c_name)
                        st.session_state.data["events"].append({
                            "project": ep, "type": ty, "date": d, "start_time": st_time, "venue": v, "status": "Active"
                        })
                        save_data()
                        st.success("Event added!")
                        st.rerun()

                st.divider()
                st.subheader("📝 Existing Events")
                for i, ev in enumerate(st.session_state.data.get("events", [])):
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        c1.write(f"**{ev['type']}** ({ev['project']})")
                        c1.caption(f"📅 {ev['date']} | 📍 {ev.get('venue', 'N/A')} | 🕒 {ev['start_time']}")
                        if c2.button("🗑️ Delete", key=f"del_ev_{i}"):
                            log_system_event(f"{c_name} deleted event '{ev['type']}' on {ev['date']}", c_name)
                            st.session_state.data["events"].pop(i)
                            save_data()
                            st.rerun()
                        with st.expander("✏️ Edit Details"):
                            with st.form(f"edit_ev_{i}"):
                                new_type = st.selectbox("Type", ["Discussion", "Rehearsal", "Work Session", "Production Day"], index=["Discussion", "Rehearsal", "Work Session", "Production Day"].index(ev['type']))
                                new_venue = st.text_input("Venue", value=ev.get("venue", ""))
                                new_note = st.text_input("Cancel Note/Status Reason", value=ev.get("note", ""))
                                new_stat = st.selectbox("Status", ["Active", "Cancelled"], index=0 if ev.get("status") == "Active" else 1)
                                if st.form_submit_button("Save Changes"):
                                    log_system_event(f"Edited event: {ev['type']} → {new_type}", c_name)
                                    st.session_state.data["events"][i]["type"] = new_type
                                    st.session_state.data["events"][i]["venue"] = new_venue
                                    st.session_state.data["events"][i]["note"] = new_note
                                    st.session_state.data["events"][i]["status"] = new_stat
                                    save_data()
                                    st.rerun()

            with at3:
                st.subheader("🔐 Account Credentials (Legacy)")
                st.info("These are default role passwords. User accounts are managed in '👤 User Manager' tab.")
                for role, pw in USER_PASSWORDS.items():
                    st.code(f"{role}: {pw}", language="text")

                st.divider()
                st.subheader("🗑️ Wipe Legacy Accounts")
                for i, a in enumerate(st.session_state.data.get("accounts", [])):
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        c1.write(f"**{a['name']}** ({a.get('role', 'N/A')})")
                        c1.caption(f"Created: {a.get('created_at', 'N/A')}")
                        if c2.button("Wipe", key=f"w_{i}"):
                            st.session_state.data["accounts"].pop(i)
                            save_data()
                            st.rerun()

            with at4:
                st.subheader("⚖️ Manual Time Correction")
                with st.form("adj"):
                    c1, c2 = st.columns(2)
                    ap = c1.selectbox("Project", ["SKIT", "BROCHURE"])
                    an = c2.selectbox("Student", [mx.get('name', 'Unknown') for mx in st.session_state.data.get("members", []) if mx.get('project') == ap] or ["None"])
                    am, ar = st.number_input("Minutes", step=5), st.text_input("Reason")
                    if st.form_submit_button("🔨 Apply Adjustment") and an != "None":
                        ukey = f"{an}_{ap}"
                        st.session_state.data["contributions"][ukey] = st.session_state.data["contributions"].get(ukey, 0) + am
                        st.session_state.data["logs"].append({
                            "log_id": f"adm_{datetime.now(SG_TZ).strftime('%H%M%S')}",
                            "user": an, "date": str(date.today()), "minutes": am,
                            "task": f"ADMIN ADJ: {ar}", "project": ap
                        })
                        save_data()
                        st.success(f"Adjusted {an}!")
                        st.rerun()

            with at5:
                st.subheader("🚨 Danger Zone")
                st.warning("This will permanently wipe all hour contributions and the activity log history.")
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
                    for entry in reversed(logs[-50:]):
                        log_type = "🟢 LOGIN" if "LOGIN" in entry.get("action", "") else "🔴 LOGOUT" if "LOGOUT" in entry.get("action", "") else "⚙️ SYSTEM"
                        st.caption(f"{entry.get('time', 'N/A')} | {log_type} | {entry.get('user', 'Unknown')}")
                        st.text(entry.get('action', ''))
                        st.divider()

            with at7:
                st.title("👤 User Account Manager")
                st.info("Manage user sign-ups and accounts. Toggle sign-ups ON/OFF below.")

                signup_enabled = st.session_state.data.get("signup_enabled", False)
                new_signup_state = st.toggle(
                    "🔓 Allow Public Sign-Ups",
                    value=signup_enabled,
                    help="When OFF, users can only sign in with existing accounts. When ON, anyone can create a new account."
                )

                if new_signup_state != signup_enabled:
                    st.session_state.data["signup_enabled"] = new_signup_state
                    log_system_event(f"SIGNUP SETTING: {'ENABLED' if new_signup_state else 'DISABLED'} by Chairman", c_name)
                    save_data()
                    st.success(f"Sign-ups {'enabled' if new_signup_state else 'disabled'}!")
                    st.rerun()

                st.divider()

                st.subheader("📋 Registered User Accounts")
                accounts = st.session_state.data.get("accounts", [])

                if not accounts:
                    st.info("No user accounts created yet.")
                else:
                    col_search, col_filter = st.columns([3, 1])
                    with col_search:
                        search_term = st.text_input("🔍 Search users", key="user_search")
                    with col_filter:
                        filter_role = st.selectbox("Filter by Role", ["All"] + ROLE_TYPES, key="user_filter")

                    filtered_accounts = accounts
                    if search_term:
                        filtered_accounts = [a for a in filtered_accounts if search_term.lower() in a["name"].lower()]
                    if filter_role != "All":
                        filtered_accounts = [a for a in filtered_accounts if any(r.get("role_type") == filter_role for r in a.get("roles", []))]

                    for i, acc in enumerate(filtered_accounts):
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([3, 2, 1])

                            with c1:
                                st.markdown(f"**{acc['name']}**")
                                # Show assigned roles as badges
                                roles_display = " | ".join([r.get("role_type", "N/A") for r in acc.get("roles", [])]) if acc.get("roles") else "⚠️ No roles assigned"
                                st.caption(f"Roles: {roles_display} | Status: {acc.get('status', 'active')}")

                            with c2:
                                pw_hash = acc.get("password_hash", "N/A")
                                if pw_hash and pw_hash != "N/A" and isinstance(pw_hash, str):
                                    st.code(f"🔐 Hash: {pw_hash[:16]}...", language="text")
                                else:
                                    st.caption("⚠️ Legacy account (no password hash)")

                            with c3:
                                if st.button("🔄 Reset PW", key=f"reset_pw_{i}"):
                                    new_pw = st.text_input(f"New password for {acc['name']}", type="password", key=f"new_pw_{i}")
                                    if st.button("Confirm Reset", key=f"confirm_reset_{i}"):
                                        if new_pw and len(new_pw) >= 6:
                                            for a in st.session_state.data["accounts"]:
                                                if a["name"] == acc["name"] and a["email"] == acc["email"]:
                                                    a["password_hash"] = hash_password(new_pw)
                                                    a["reset_by"] = c_name
                                                    a["reset_at"] = datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S")
                                            log_system_event(f"PASSWORD RESET: {acc['name']} by {c_name}", c_name)
                                            save_data()
                                            st.success("Password reset!")
                                            st.rerun()
                                        else:
                                            st.error("Password must be 6+ characters")

                                if st.button("🗑️ Delete", key=f"del_acc_{i}", type="secondary"):
                                    st.session_state.data["accounts"] = [a for a in st.session_state.data["accounts"]
                                                                      if not (a["name"] == acc["name"] and a["email"] == acc["email"])]
                                    log_system_event(f"ACCOUNT DELETED: {acc['name']} by {c_name}", c_name)
                                    save_data()
                                    st.rerun()

                st.divider()

                st.subheader("➕ Create Account Manually")
                with st.expander("Create account for someone else"):
                    with st.form("manual_create"):
                        mc_name = st.text_input("User Name").strip().title()
                        mc_email = st.text_input("User Email").strip().lower()
                        mc_pw = st.text_input("Set Password", type="password", key="mc_pw")
                        mc_confirm = st.text_input("Confirm Password", type="password", key="mc_confirm")

                        if st.form_submit_button("Create Account"):
                            if not mc_name or not mc_pw or not mc_email:
                                st.error("Name, email, and password required")
                            elif mc_pw != mc_confirm:
                                st.error("Passwords don't match")
                            elif len(mc_pw) < 6:
                                st.error("Password must be 6+ characters")
                            else:
                                exists = next((a for a in st.session_state.data.get("accounts", [])
                                             if a["email"].lower() == mc_email.lower()), None)
                                if exists:
                                    st.error("Account with this email already exists")
                                else:
                                    new_acc = {
                                        "name": mc_name, "email": mc_email,
                                        "password_hash": hash_password(mc_pw),
                                        "roles": [],  # ← Empty until Chairman assigns
                                        "status": "active",
                                        "created_at": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                                        "created_by": c_name
                                    }
                                    st.session_state.data.setdefault("accounts", []).append(new_acc)
                                    log_system_event(f"MANUAL CREATE: {mc_name} ({mc_email}) by {c_name}", c_name)
                                    save_data()
                                    st.success(f"✅ Account created for {mc_name}! Assign roles in '🎭 Role Assignment' tab.")
                                    st.rerun()

            # ============================================================================
            # --- NEW TAB 8: ROLE ASSIGNMENT (CHAIRMAN ONLY) ---
            # ============================================================================
            with at8:
                st.title("🎭 Role Assignment Manager")
                st.info(f"Assign up to {MAX_ROLES_PER_USER} roles per user. Roles determine project access and permissions.")
                
                # Select user to manage
                all_users = st.session_state.data.get("accounts", [])
                if not all_users:
                    st.warning("No user accounts found. Create accounts first in '👤 User Manager' tab.")
                else:
                    user_options = [f"{u['name']} ({u['email']})" for u in all_users]
                    selected_user_display = st.selectbox("👤 Select User to Manage Roles", user_options)
                    selected_user = next((u for u in all_users if f"{u['name']} ({u['email']})" == selected_user_display), None)
                    
                    if selected_user:
                        current_roles = selected_user.get("roles", [])
                        
                        # Display current roles
                        st.subheader("📋 Current Roles")
                        if not current_roles:
                            st.caption("No roles assigned yet.")
                        else:
                            for idx, role in enumerate(current_roles):
                                with st.container(border=True):
                                    col1, col2 = st.columns([4, 1])
                                    proj = role.get("project", "CLASS")
                                    role_type = role.get("role_type", "N/A")
                                    sub_role = role.get("sub_role", "N/A")
                                    is_rep = role.get("is_rep", False)
                                    
                                    badge_class = "representative" if is_rep else ""
                                    col1.markdown(f"""
                                    <span class="role-badge {badge_class}">{role_type} • {sub_role} ({proj})</span>
                                    """, unsafe_allow_html=True)
                                    
                                    if col2.button("🗑️ Remove", key=f"rem_role_{selected_user['email']}_{idx}"):
                                        current_roles.pop(idx)
                                        selected_user["roles"] = current_roles
                                        log_system_event(f"ROLE REMOVED: {role_type} from {selected_user['name']}", c_name)
                                        save_data()
                                        st.rerun()
                        
                        st.divider()
                        
                        # Add new role form
                        st.subheader("➕ Assign New Role")
                        
                        # Check role limit
                        remaining_slots = MAX_ROLES_PER_USER - len(current_roles)
                        if remaining_slots <= 0:
                            st.warning(f"⚠️ User already has {MAX_ROLES_PER_USER} roles (maximum reached). Remove a role first to add a new one.")
                        else:
                            st.caption(f"Slots remaining: {remaining_slots}/{MAX_ROLES_PER_USER}")
                            
                            with st.form("assign_role_form"):
                                col1, col2, col3 = st.columns(3)
                                
                                with col1:
                                    new_proj = st.selectbox("Project", PROJECT_OPTIONS, key="new_proj")
                                
                                with col2:
                                    # Filter role types based on project
                                    if new_proj == "CLASS":
                                        role_options = ["Teacher", "VIA Committee", "VIA members"]
                                    elif new_proj == "SKIT":
                                        role_options = ["Skit Representative", "VIA members"]
                                    else:  # BROCHURE
                                        role_options = ["Brochure Representative", "VIA members"]
                                    
                                    new_role_type = st.selectbox("Role Type", role_options, key="new_role")
                                
                                with col3:
                                    is_rep = st.checkbox("Representative?", value="Representative" in new_role_type, key="new_is_rep")
                                    sub_options = SUB_ROLES.get(new_proj, SUB_ROLES["CLASS"])
                                    new_sub_role = st.selectbox("Sub-Role", sub_options, key="new_sub")
                                
                                if st.form_submit_button("✅ Assign Role"):
                                    # Validate uniqueness (prevent duplicate role+project combos)
                                    duplicate = any(
                                        r.get("project") == new_proj and r.get("role_type") == new_role_type
                                        for r in current_roles
                                    )
                                    if duplicate:
                                        st.error(f"⚠️ User already has '{new_role_type}' role for {new_proj} project.")
                                    else:
                                        new_role = {
                                            "role_type": new_role_type,
                                            "project": new_proj,
                                            "is_rep": is_rep,
                                            "sub_role": new_sub_role,
                                            "assigned_at": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                                            "assigned_by": c_name
                                        }
                                        current_roles.append(new_role)
                                        selected_user["roles"] = current_roles
                                        
                                        # Also add to members list if not exists
                                        existing_member = next((m for m in st.session_state.data.get("members", [])
                                                              if m.get("name") == selected_user["name"] and m.get("project") == new_proj), None)
                                        if not existing_member:
                                            st.session_state.data["members"].append({
                                                "name": selected_user["name"],
                                                "project": new_proj if new_proj != "CLASS" else None,
                                                "role_type": new_role_type if new_proj != "CLASS" else "CLASS",
                                                "is_rep": is_rep,
                                                "sub_role": new_sub_role
                                            })
                                        
                                        log_system_event(f"ROLE ASSIGNED: {new_role_type} ({new_proj}) to {selected_user['name']}", c_name)
                                        save_data()
                                        st.success(f"✅ Role assigned to {selected_user['name']}!")
                                        st.rerun()
                        
                        # Quick actions
                        st.divider()
                        col_q1, col_q2 = st.columns(2)
                        
                        with col_q1:
                            if st.button("🔄 Reset All Roles", type="secondary"):
                                if st.checkbox("Confirm reset all roles for this user?", key="confirm_reset_roles"):
                                    selected_user["roles"] = []
                                    log_system_event(f"ROLES RESET: All roles removed from {selected_user['name']}", c_name)
                                    save_data()
                                    st.success("Roles reset!")
                                    st.rerun()
                        
                        with col_q2:
                            if st.button("📋 Copy Role Template", type="secondary"):
                                st.code(f"""
# Template for {selected_user['name']}
{{
    "role_type": "ROLE_NAME",
    "project": "PROJECT_NAME",
    "is_rep": True/False,
    "sub_role": "SPECIFIC_ROLE"
}}
                                """, language="json")

# ============================================================================
# --- FOOTER ---
# ============================================================================
st.markdown("---")
st.markdown(f"""
<div style="text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 1rem;">
    VIA Class Portal 2026 • Singapore Time: {datetime.now(SG_TZ).strftime('%Y-%m-%d %H:%M:%S')} • 
    <a href="#" style="color: var(--primary); text-decoration: none;">Help</a> • 
    <a href="#" style="color: var(--primary); text-decoration: none;">Privacy</a>
</div>
""", unsafe_allow_html=True)
