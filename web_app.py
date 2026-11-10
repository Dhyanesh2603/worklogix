import os
import sys
import secrets
import threading
import time
import hmac
import hashlib
from datetime import datetime, date
from fastapi import FastAPI, Request, Response, Header, Cookie, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Set, List

# Ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database
import exporter
from tracker_core import TrackerEngine, TrackerState, get_idle_seconds, get_active_app_info, attach_to_interactive_desktop

app = FastAPI(title="Office Work Session & Activity Tracker")

# Initialize database
database.init_db()

# In-memory admin session storage
ACTIVE_ADMIN_TOKENS: Set[str] = set()

# System-wide background tracker engine running in Python
global_engine = TrackerEngine(idle_threshold_seconds=300)
engine_lock = threading.RLock()
latest_stats = {
    "state": "Logged Out",
    "idle_seconds": 0,
    "total_active": 0,
    "total_inactive": 0,
    "total_lunch": 0,
    "total_overtime": 0,
    "total_span": 0,
    "active_app": "Offline",
    "window_title": "Offline",
    "active_domain": None,
    "employee_name": "Not Clocked In",
    "employee_code": "---",
    "login_time": "--:--"
}

def on_engine_tick(stats):
    global latest_stats
    latest_stats.update(stats)

global_engine.on_tick = on_engine_tick

# Background daemon thread: monitors hardware, employee's assigned shift, websites, idle
def background_tracking_loop():
    attach_to_interactive_desktop()
    while True:
        try:
            with engine_lock:
                auth_emp = database.get_authenticated_employee()
                if auth_emp:
                    emp_id = auth_emp["id"]
                    # Automatically starts/stops on that employee's assigned shift
                    global_engine.check_shift_window(emp_id)

                    if global_engine.state != TrackerState.LOGGED_OUT:
                        global_engine.tick()
        except Exception as e:
            print("Background tracking loop error:", e)
        time.sleep(1)

bg_thread = threading.Thread(target=background_tracking_loop, daemon=True)
bg_thread.start()

# --- Pydantic Request Models ---
class EmployeeAuthRequest(BaseModel):
    code: str
    pin: str

class ClockInRequest(BaseModel):
    employee_id: int

class EmployeeShiftUpdateRequest(BaseModel):
    employee_id: int
    start_time: str
    end_time: str
    is_auto_start: bool
    idle_threshold: int = 300
    new_pin: Optional[str] = None

class BulkShiftUpdateRequest(BaseModel):
    shift_start: str
    shift_end: str

class AddEmployeeRequest(BaseModel):
    name: str
    code: str
    pin: str = "1234"
    shift_start: str = "09:30"
    shift_end: str = "18:00"
    is_auto_start: bool = True
    idle_threshold: int = 300

class AdminLoginRequest(BaseModel):
    username: str
    password: str

ADMIN_SECRET = "super_secret_admin_office_tracker_key_2026"

def create_admin_token(username: str) -> str:
    ts = str(int(time.time()))
    sig = hmac.new(ADMIN_SECRET.encode(), f"{username}:{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{username}:{ts}:{sig}"

def verify_token_validity(token: str) -> bool:
    if not token:
        return False
    if token in ACTIVE_ADMIN_TOKENS:
        return True
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        user, ts_str, sig = parts
        ts = int(ts_str)
        # Valid for 30 days
        if time.time() - ts > 30 * 86400:
            return False
        expected_sig = hmac.new(ADMIN_SECRET.encode(), f"{user}:{ts_str}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            ACTIVE_ADMIN_TOKENS.add(token)
            return True
    except Exception:
        pass
    return False

def verify_admin_token(
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    admin_token: Optional[str] = Cookie(None)
):
    token = x_admin_token or admin_token
    if token and verify_token_validity(token):
        return token
    # Permanent Auto-Auth for Localhost & Admin Launcher
    client_host = getattr(getattr(request, "client", None), "host", "")
    if client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        auto_tok = create_admin_token("admin")
        ACTIVE_ADMIN_TOKENS.add(auto_tok)
        return auto_tok
    raise HTTPException(status_code=401, detail="Administrator authorization required.")

@app.post("/api/admin/auto-auth")
async def api_admin_auto_auth(response: Response):
    """Generates a persistent 100-year administrator token for seamless permanent login."""
    token = create_admin_token("admin")
    ACTIVE_ADMIN_TOKENS.add(token)
    response.set_cookie(key="admin_token", value=token, max_age=3153600000, httponly=False, samesite="lax")
    return {"status": "ok", "token": token}

# Shared CSS Styles
COMMON_STYLES = """
:root, [data-theme="light"] {
    color-scheme: light;
    --bg-page: #F8FAFC;
    --bg-surface: #FFFFFF;
    --bg-subtle: #F1F5F9;
    --bg-input: #FFFFFF;
    --border-subtle: #E2E8F0;
    --border-strong: #CBD5E1;
    
    --text-main: #0F172A;
    --text-secondary: #475569;
    --text-muted: #94A3B8;

    --btn-primary-bg: #0F172A;
    --btn-primary-text: #FFFFFF;
    --btn-primary-hover: #1E293B;

    --status-active-bg: #ECFDF5;
    --status-active-text: #065F46;
    --status-active-border: #A7F3D0;
    --status-active-dot: #059669;

    --status-inactive-bg: #FFFBEB;
    --status-inactive-text: #92400E;
    --status-inactive-border: #FDE68A;
    --status-inactive-dot: #D97706;

    --status-lunch-bg: #F1F5F9;
    --status-lunch-text: #334155;
    --status-lunch-border: #CBD5E1;
    --status-lunch-dot: #64748B;

    --status-offline-bg: #F1F5F9;
    --status-offline-text: #64748B;
    --status-offline-border: #E2E8F0;
    --status-offline-dot: #94A3B8;

    --card-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.05), 0 1px 2px -1px rgba(15, 23, 42, 0.05);
    --card-shadow-lg: 0 10px 15px -3px rgba(15, 23, 42, 0.06), 0 4px 6px -4px rgba(15, 23, 42, 0.04);
}

[data-theme="dark"] {
    color-scheme: dark;
    --bg-page: #0B0F17;
    --bg-surface: #111827;
    --bg-subtle: #1F2937;
    --bg-input: #1F2937;
    --border-subtle: #1F2937;
    --border-strong: #374151;

    --text-main: #F9FAFB;
    --text-secondary: #9CA3AF;
    --text-muted: #6B7280;

    --btn-primary-bg: #F9FAFB;
    --btn-primary-text: #0B0F17;
    --btn-primary-hover: #E5E7EB;

    --status-active-bg: rgba(6, 95, 70, 0.25);
    --status-active-text: #34D399;
    --status-active-border: rgba(16, 185, 129, 0.35);
    --status-active-dot: #10B981;

    --status-inactive-bg: rgba(146, 64, 14, 0.25);
    --status-inactive-text: #FBBF24;
    --status-inactive-border: rgba(245, 158, 11, 0.35);
    --status-inactive-dot: #F59E0B;

    --status-lunch-bg: rgba(71, 85, 105, 0.25);
    --status-lunch-text: #CBD5E1;
    --status-lunch-border: rgba(148, 163, 184, 0.35);
    --status-lunch-dot: #94A3B8;

    --status-offline-bg: rgba(51, 65, 85, 0.25);
    --status-offline-text: #94A3B8;
    --status-offline-border: rgba(71, 85, 105, 0.35);
    --status-offline-dot: #64748B;

    --card-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.3);
    --card-shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background-color: var(--bg-page);
    color: var(--text-main);
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    min-height: 100vh;
    padding: 28px 24px;
    transition: background-color 0.2s ease, color 0.2s ease;
}
.container { max-width: 1180px; margin: 0 auto; }

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--border-subtle);
    flex-wrap: wrap;
    gap: 16px;
}
.brand-group { display: flex; align-items: center; gap: 12px; }
.brand-icon {
    width: 38px;
    height: 38px;
    border-radius: 8px;
    background-color: var(--btn-primary-bg);
    color: var(--btn-primary-text);
    display: flex;
    align-items: center;
    justify-content: center;
}
.brand-title { font-size: 19px; font-weight: 700; color: var(--text-main); letter-spacing: -0.02em; }
.brand-sub { font-size: 13px; color: var(--text-muted); margin-top: 2px; }

.theme-toggle-btn {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.15s;
}
.theme-toggle-btn:hover { color: var(--text-main); border-color: var(--border-strong); }

.card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 22px;
    margin-bottom: 20px;
    box-shadow: var(--card-shadow);
}
input, select {
    background-color: var(--bg-input);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    font-family: inherit;
    color: var(--text-main);
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
}
input:focus, select:focus {
    border-color: var(--border-strong);
    box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.05);
}

.btn {
    font-family: inherit;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid transparent;
    text-decoration: none;
}
.btn-primary { background-color: var(--btn-primary-bg); color: var(--btn-primary-text); }
.btn-primary:hover:not(:disabled) { background-color: var(--btn-primary-hover); }
.btn-secondary { background-color: var(--bg-surface); border-color: var(--border-strong); color: var(--text-main); }
.btn-secondary:hover:not(:disabled) { background-color: var(--bg-subtle); }
.btn-danger { background-color: var(--bg-surface); border-color: #FECACA; color: #DC2626; }
.btn-danger:hover:not(:disabled) { background-color: #FEF2F2; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }

.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; }
.status-active { background-color: var(--status-active-bg); color: var(--status-active-text); border: 1px solid var(--status-active-border); }
.status-active .status-dot { background-color: var(--status-active-dot); }
.status-inactive { background-color: var(--status-inactive-bg); color: var(--status-inactive-text); border: 1px solid var(--status-inactive-border); }
.status-inactive .status-dot { background-color: var(--status-inactive-dot); }
.status-lunch { background-color: var(--status-lunch-bg); color: var(--status-lunch-text); border: 1px solid var(--status-lunch-border); }
.status-lunch .status-dot { background-color: var(--status-lunch-dot); }
.status-offline { background-color: var(--status-offline-bg); color: var(--status-offline-text); border: 1px solid var(--status-offline-border); }
.status-offline .status-dot { background-color: var(--status-offline-dot); }

table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
th {
    background-color: var(--bg-subtle);
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    text-align: left;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-subtle);
}
th:first-child { border-top-left-radius: 8px; }
th:last-child { border-top-right-radius: 8px; }
td { padding: 12px 14px; border-bottom: 1px solid var(--border-subtle); color: var(--text-main); }
tr:last-child td { border-bottom: none; }
tr:hover td { background-color: var(--bg-subtle); }
.num-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; }

.tab-nav {
    display: flex;
    gap: 6px;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 20px;
    overflow-x: auto;
}
.tab-btn {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
}
.tab-btn:hover { color: var(--text-main); }
.tab-btn.active {
    color: var(--text-main);
    border-bottom-color: var(--btn-primary-bg);
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px;
    margin-bottom: 22px;
}
.kpi-card {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 18px;
    box-shadow: var(--card-shadow);
}
.kpi-title { font-size: 11px; font-weight: 700; color: var(--text-muted); letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 8px; }
.kpi-val { font-size: 24px; font-weight: 700; color: var(--text-main); font-family: 'JetBrains Mono', monospace; }
"""

# ==============================================================================
# 1. PURE EMPLOYEE DASHBOARD (Route: /) - PERMANENT LOGIN, NO ADMIN CLUTTER
# ==============================================================================
EMPLOYEE_HTML_PAGE = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <title>Employee Work Session Tracker</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script>
        const savedTheme = localStorage.getItem("app_theme") || "light";
        document.documentElement.setAttribute("data-theme", savedTheme);
    </script>
    <style>
        {COMMON_STYLES}
        .auth-card {{
            max-width: 400px;
            margin: 60px auto;
            text-align: center;
            padding: 36px 32px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand-group">
                <div class="brand-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                </div>
                <div>
                    <h1 class="brand-title">Employee Work Session Tracker</h1>
                    <p class="brand-sub" id="headerDate">Loading date...</p>
                </div>
            </div>

            <div style="display: flex; align-items: center; gap: 12px;">
                <button id="btnHeaderSwitch" class="btn btn-secondary" onclick="switchEmployeeAccount()" style="display: none; padding: 6px 12px; font-size: 13px; align-items: center; gap: 6px;" title="Switch Employee Account">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="8.5" cy="7" r="4"></circle>
                        <polyline points="17 11 19 13 23 9"></polyline>
                    </svg>
                    <span>Switch Account</span>
                </button>
                <button class="theme-toggle-btn" onclick="toggleTheme()" title="Toggle Theme">
                    <svg id="themeIconSun" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="5"></circle>
                        <line x1="12" y1="1" x2="12" y2="3"></line>
                        <line x1="12" y1="21" x2="12" y2="23"></line>
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                        <line x1="1" y1="12" x2="3" y2="12"></line>
                        <line x1="21" y1="12" x2="23" y2="12"></line>
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                    </svg>
                    <svg id="themeIconMoon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display: none;">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                    </svg>
                </button>
                <div id="liveStatusBadge" class="status-badge status-offline">
                    <span class="status-dot"></span>
                    <span id="liveStatusText">Offline</span>
                </div>
            </div>
        </header>

        <!-- VIEW A: FIRST-TIME WORKSTATION AUTHENTICATION -->
        <div id="empAuthView" class="card auth-card" style="display: none;">
            <div style="width: 48px; height: 48px; border-radius: 12px; background: var(--bg-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px auto;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
            </div>
            <h2 style="font-size: 18px; font-weight: 700; margin-bottom: 6px;">Workstation Sign In</h2>
            <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 18px;">
                Select your employee profile from the list below, or enter your code &amp; PIN to sign in.
            </p>
            <div id="authErrorMsg" style="background: #FEF2F2; border: 1px solid #FECACA; color: #991B1B; padding: 10px; border-radius: 6px; font-size: 12px; margin-bottom: 14px; display: none;">
                Invalid Employee Code or PIN.
            </div>
            <div style="text-align: left; margin-bottom: 14px;">
                <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">Select Employee Account</label>
                <select id="authRosterSelect" onchange="onSelectRosterEmp(this)" style="width: 100%;">
                    <option value="">-- Choose from roster (or enter code below) --</option>
                </select>
            </div>
            <div style="text-align: left; margin-bottom: 14px;">
                <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">Employee Code</label>
                <input type="text" id="authCodeInput" placeholder="e.g. EMP-101" style="width: 100%;">
            </div>
            <div style="text-align: left; margin-bottom: 18px;">
                <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">PIN</label>
                <input type="password" id="authPinInput" placeholder="Default: 1234" style="width: 100%;" onkeydown="if(event.key==='Enter') executeEmployeeAuth()">
            </div>
            <button class="btn btn-primary" style="width: 100%; justify-content: center;" onclick="executeEmployeeAuth()">
                Activate & Stay Signed In
            </button>
            <p style="margin-top: 14px; font-size: 11px; color: var(--text-muted);">Default PIN for new workstations: <code>1234</code></p>
        </div>

        <!-- VIEW B: PERMANENT EMPLOYEE DASHBOARD (NO NAME/CODE INPUTS) -->
        <div id="empMainDashboard" style="display: none;">
            <!-- Authenticated Profile Card -->
            <div class="card" style="padding: 16px 22px; border-left: 4px solid var(--status-active-dot);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <h2 id="dispEmpName" style="font-size: 18px; font-weight: 700;">Employee Name</h2>
                            <code id="dispEmpCode" style="background: var(--bg-subtle); padding: 2px 8px; border-radius: 4px; font-size: 13px; font-weight: 600;">---</code>
                        </div>
                        <p id="dispEmpShift" style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">
                            Assigned Shift: 09:30 to 18:00 (Auto-Monitor Active)
                        </p>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="color: var(--status-active-dot); font-weight: 600; font-size: 13px;">● Workstation Assigned</span>
                        <button class="btn btn-secondary" onclick="switchEmployeeAccount()" style="padding: 4px 10px; font-size: 12px;">Switch Account</button>
                    </div>
                </div>
            </div>

            <!-- 4 Metric Cards -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-title">Clocked In At</div>
                    <div class="kpi-val" id="metricLoginTime" style="font-size: 20px;">--:--</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Active Work Time</div>
                    <div class="kpi-val" id="metricActiveTime" style="color: var(--status-active-dot);">00h 00m 00s</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Inactivity / Away</div>
                    <div class="kpi-val" id="metricInactiveTime" style="color: var(--status-inactive-dot);">00h 00m 00s</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Lunch Break</div>
                    <div class="kpi-val" id="metricLunchTime" style="color: var(--text-secondary);">00h 00m 00s</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Overtime</div>
                    <div class="kpi-val" id="metricOvertime" style="color: #8B5CF6;">00h 00m 00s</div>
                </div>
            </div>

            <!-- Action Controls -->
            <div class="card" style="padding: 16px 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                    <div style="display: flex; gap: 12px;">
                        <button id="btnClockIn" class="btn btn-primary" onclick="clockIn()">Start Shift / Clock In</button>
                        <button id="btnLunch" class="btn btn-secondary" onclick="toggleLunch()" disabled>Take Lunch Break</button>
                        <button id="btnClockOut" class="btn btn-danger" onclick="clockOut()" disabled>End Shift / Clock Out</button>
                    </div>
                    <div id="idleLiveNotice" style="font-size: 12px; color: var(--text-muted);">
                        System Idle: 0s
                    </div>
                </div>
            </div>

            <!-- Activity Intervals Timeline Table -->
            <div class="card">
                <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 14px;">Today's Activity Intervals</h3>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Event</th>
                            <th>Start Time</th>
                            <th>End Time</th>
                            <th>Duration</th>
                        </tr>
                    </thead>
                    <tbody id="intervalTableBody">
                        <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No intervals recorded yet.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('headerDate').innerText = new Date().toLocaleDateString('en-US', {{
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        }});

        function updateThemeIcons(theme) {{
            const sun = document.getElementById('themeIconSun');
            const moon = document.getElementById('themeIconMoon');
            if (theme === 'dark') {{
                sun.style.display = 'none';
                moon.style.display = 'block';
            }} else {{
                sun.style.display = 'block';
                moon.style.display = 'none';
            }}
        }}
        updateThemeIcons(document.documentElement.getAttribute('data-theme') || 'light');

        function toggleTheme() {{
            const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('app_theme', next);
            updateThemeIcons(next);
        }}

        function formatDuration(sec) {{
            let h = Math.floor(sec / 3600);
            let m = Math.floor((sec % 3600) / 60);
            let s = sec % 60;
            return `${{String(h).padStart(2,'0')}}h ${{String(m).padStart(2,'0')}}m ${{String(s).padStart(2,'0')}}s`;
        }}

                let currentEmployee = null;
        let latestData = null;

        async function loadEmployeeRoster() {{
            try {{
                const res = await fetch('/api/employee/roster');
                if (res.ok) {{
                    const emps = await res.json();
                    const sel = document.getElementById('authRosterSelect');
                    if (sel) {{
                        sel.innerHTML = '<option value="">-- Choose from roster (or enter code below) --</option>';
                        emps.forEach(e => {{
                            const opt = document.createElement('option');
                            opt.value = e.employee_code;
                            opt.innerText = `${{e.name}} (${{e.employee_code}})`;
                            sel.appendChild(opt);
                        }});
                    }}
                }}
            }} catch (err) {{}}
        }}

        function onSelectRosterEmp(sel) {{
            if (sel && sel.value) {{
                document.getElementById('authCodeInput').value = sel.value;
                document.getElementById('authPinInput').focus();
            }}
        }}

        async function initEmployeeSession() {{
            if (localStorage.getItem("portal_account_switched") === "true") {{
                showAuthView();
                loadEmployeeRoster();
                return;
            }}

            let storedEmpId = localStorage.getItem("persistent_emp_id");
            let url = storedEmpId ? `/api/employee/me?employee_id=${{storedEmpId}}` : '/api/employee/me';
            try {{
                const res = await fetch(url);
                if (res.ok) {{
                    currentEmployee = await res.json();
                    if (currentEmployee && currentEmployee.id) {{
                        localStorage.setItem("persistent_emp_id", currentEmployee.id);
                        showMainDashboard();
                        return;
                    }}
                }}
            }} catch (e) {{}}

            showAuthView();
            loadEmployeeRoster();
        }}

        function showAuthView() {{
            document.getElementById('empAuthView').style.display = 'block';
            document.getElementById('empMainDashboard').style.display = 'none';
            const btnH = document.getElementById('btnHeaderSwitch');
            if (btnH) btnH.style.display = 'none';
        }}

        function showMainDashboard() {{
            document.getElementById('empAuthView').style.display = 'none';
            document.getElementById('empMainDashboard').style.display = 'block';
            const btnH = document.getElementById('btnHeaderSwitch');
            if (btnH) btnH.style.display = 'inline-flex';

            document.getElementById('dispEmpName').innerText = currentEmployee.name;
            document.getElementById('dispEmpCode').innerText = currentEmployee.employee_code;
            const autoText = currentEmployee.is_auto_start ? 'Auto-Monitor Active' : 'Manual Start';
            document.getElementById('dispEmpShift').innerText = `Assigned Shift: ${{currentEmployee.shift_start}} to ${{currentEmployee.shift_end}} (${{autoText}})`;

            pollLiveStatus();
        }}

        async function executeEmployeeAuth() {{
            const code = document.getElementById('authCodeInput').value.trim();
            const pin = document.getElementById('authPinInput').value.trim() || '1234';
            const errDiv = document.getElementById('authErrorMsg');

            try {{
                const res = await fetch('/api/employee/auth', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ code, pin }})
                }});

                if (res.ok) {{
                    const data = await res.json();
                    currentEmployee = data.employee;
                    localStorage.removeItem("portal_account_switched");
                    localStorage.setItem("persistent_emp_id", currentEmployee.id);
                    errDiv.style.display = 'none';
                    showMainDashboard();
                }} else {{
                    errDiv.style.display = 'block';
                }}
            }} catch (e) {{
                errDiv.style.display = 'block';
            }}
        }}

        async function switchEmployeeAccount() {{
            const empName = currentEmployee ? currentEmployee.name : "Employee";
            if (!confirm(`Switch Workstation Account?\n\nCurrently signed in as ${{empName}}.\nDo you want to switch or link this portal to a different employee account?`)) {{
                return;
            }}
            try {{
                await fetch('/api/employee/logout', {{ method: 'POST' }});
            }} catch (e) {{}}
            localStorage.removeItem("persistent_emp_id");
            localStorage.setItem("portal_account_switched", "true");
            currentEmployee = null;
            document.getElementById('authCodeInput').value = '';
            document.getElementById('authPinInput').value = '';
            showAuthView();
            loadEmployeeRoster();
        }}
        async function pollLiveStatus() {{
            if (!currentEmployee) return;
            try {{
                const res = await fetch('/api/live-status');
                if (!res.ok) return;
                const data = await res.json();
                latestData = data;

                const badge = document.getElementById('liveStatusBadge');
                const badgeText = document.getElementById('liveStatusText');
                const btnClockIn = document.getElementById('btnClockIn');
                const btnLunch = document.getElementById('btnLunch');
                const btnClockOut = document.getElementById('btnClockOut');

                if (data.state === "Active") {{
                    badge.className = "status-badge status-active";
                    badgeText.innerText = "Active Working";
                    btnClockIn.disabled = true;
                    btnLunch.disabled = false;
                    btnClockOut.disabled = false;
                    btnLunch.innerText = "Take Lunch Break";
                }} else if (data.state === "Inactive") {{
                    badge.className = "status-badge status-inactive";
                    badgeText.innerText = "Away / Inactive";
                    btnClockIn.disabled = true;
                    btnLunch.disabled = false;
                    btnClockOut.disabled = false;
                    btnLunch.innerText = "Take Lunch Break";
                }} else if (data.state === "Lunch Break") {{
                    badge.className = "status-badge status-lunch";
                    badgeText.innerText = "On Lunch Break";
                    btnClockIn.disabled = true;
                    btnLunch.disabled = false;
                    btnClockOut.disabled = false;
                    btnLunch.innerText = "Resume Work";
                }} else {{
                    badge.className = "status-badge status-offline";
                    badgeText.innerText = "Offline";
                    btnClockIn.disabled = false;
                    btnLunch.disabled = true;
                    btnClockOut.disabled = true;
                    btnLunch.innerText = "Take Lunch Break";
                }}

                document.getElementById('metricLoginTime').innerText = data.login_time || "--:--";
                document.getElementById('metricActiveTime').innerText = formatDuration(data.total_active || 0);
                document.getElementById('metricInactiveTime').innerText = formatDuration(data.total_inactive || 0);
                document.getElementById('metricLunchTime').innerText = formatDuration(data.total_lunch || 0);
                document.getElementById('metricOvertime').innerText = formatDuration(data.total_overtime || 0);

                if (data.state !== "Logged Out") {{
                    document.getElementById('idleLiveNotice').innerText = `System Idle: ${{data.idle_seconds}}s`;
                }} else {{
                    document.getElementById('idleLiveNotice').innerText = "System Idle: 0s";
                }}

                renderIntervals(data.intervals || []);
            }} catch (err) {{}}
        }}

        function renderIntervals(intervals) {{
            const tbody = document.getElementById('intervalTableBody');
            if (!intervals || intervals.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No intervals recorded yet.</td></tr>';
                return;
            }}
            tbody.innerHTML = intervals.map((inv, idx) => {{
                let badgeClass = inv.event_type === "ACTIVE" ? "status-active" : (inv.event_type === "INACTIVE" ? "status-inactive" : "status-lunch");
                return `<tr>
                    <td class="num-cell">${{idx + 1}}</td>
                    <td><span class="status-badge ${{badgeClass}}"><span class="status-dot"></span>${{inv.event_type}}</span></td>
                    <td class="num-cell">${{inv.start_time}}</td>
                    <td class="num-cell">${{inv.end_time || 'In Progress'}}</td>
                    <td class="num-cell" style="font-weight: 600;">${{formatDuration(inv.duration_sec)}}</td>
                </tr>`;
            }}).join('');
        }}

        async function clockIn() {{
            if (!currentEmployee) return;
            await fetch('/api/clock-in', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ employee_id: currentEmployee.id }})
            }});
            alert("Shift Started!\n\nWork tracking and idle detection are now active for " + currentEmployee.name + ".");
            pollLiveStatus();
        }}

        async function toggleLunch() {{
            const isLunch = latestData && latestData.state === "Lunch Break";
            if (!isLunch) {{
                if (!confirm("Start lunch break now?\n\nInactivity tracking will be paused while you are on lunch.")) return;
            }}
            const res = await fetch('/api/lunch', {{ method: 'POST' }});
            if (res.ok) {{
                const d = await res.json();
                if (d.state === "Lunch Break") {{
                    alert("Lunch Break Started!\n\nEnjoy your meal! Click 'Resume Work' when you return.");
                }} else {{
                    alert("Work Resumed!\n\nWelcome back! Active tracking has resumed.");
                }}
            }}
            pollLiveStatus();
        }}

        async function clockOut() {{
            if (!confirm("Are you sure you want to end your shift for today?\n\nThis will record your final daily hours.")) return;
            const res = await fetch('/api/clock-out', {{ method: 'POST' }});
            if (res.ok) {{
                alert("Shift Ended!\n\nClock-out logged successfully. Have a great evening!");
            }}
            pollLiveStatus();
        }}

        setInterval(pollLiveStatus, 1000);
        initEmployeeSession();
    </script>
</body>
</html>
"""

# ==============================================================================
# 2. UPGRADED MANAGEMENT & ANALYTICS PORTAL (Route: /admin)
# ==============================================================================
ADMIN_HTML_PAGE = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <title>Office Management & Analytics Portal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script>
        const savedTheme = localStorage.getItem("app_theme") || "light";
        document.documentElement.setAttribute("data-theme", savedTheme);
    </script>
    <style>
        {COMMON_STYLES}
        .auth-card {{
            max-width: 400px;
            margin: 60px auto;
            text-align: center;
            padding: 36px 32px;
        }}
        .auth-icon-wrap {{
            width: 48px;
            height: 48px;
            border-radius: 12px;
            background-color: var(--bg-subtle);
            border: 1px solid var(--border-subtle);
            color: var(--text-main);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px auto;
        }}
        .auth-title {{ font-size: 18px; font-weight: 700; color: var(--text-main); margin-bottom: 6px; }}
        .auth-desc {{ font-size: 13px; color: var(--text-muted); margin-bottom: 24px; line-height: 1.5; }}
        .auth-field {{ text-align: left; margin-bottom: 16px; }}
        .auth-field label {{ display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }}
        .auth-field input {{ width: 100%; }}
        .auth-error {{
            background-color: #FEF2F2;
            border: 1px solid #FECACA;
            color: #991B1B;
            padding: 10px;
            border-radius: 6px;
            font-size: 12px;
            margin-bottom: 16px;
            display: none;
        }}
        .filter-bar {{
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
            padding-bottom: 16px;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border-subtle);
        }}
        .filter-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; }}
        .quick-date-btn {{
            background: var(--bg-subtle);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s;
        }}
        .quick-date-btn:hover, .quick-date-btn.active {{
            background: var(--btn-primary-bg);
            color: var(--btn-primary-text);
            border-color: var(--btn-primary-bg);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand-group">
                <div class="brand-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                    </svg>
                </div>
                <div>
                    <h1 class="brand-title">Office Management & Analytics Portal</h1>
                    <p class="brand-sub" id="adminHeaderDate">Administrator Dashboard</p>
                </div>
            </div>

            <div style="display: flex; align-items: center; gap: 10px;">
                <button class="theme-toggle-btn" onclick="toggleTheme()" title="Toggle Theme">
                    <svg id="themeIconSun" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="5"></circle>
                        <line x1="12" y1="1" x2="12" y2="3"></line>
                        <line x1="12" y1="21" x2="12" y2="23"></line>
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                        <line x1="1" y1="12" x2="3" y2="12"></line>
                        <line x1="21" y1="12" x2="23" y2="12"></line>
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                    </svg>
                    <svg id="themeIconMoon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display: none;">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                    </svg>
                </button>
                <button id="adminAddEmpBtn" class="btn btn-primary btn-sm" style="display: none; align-items: center; gap: 6px;" onclick="openAddEmployeeModal()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Add Employee
                </button>
                <!-- Permanent Admin Session Active (No Logout) -->
            </div>
        </header>

        <!-- VIEW A: ADMIN LOGIN FORM -->
        <div id="adminLoginForm" class="card auth-card">
            <div class="auth-icon-wrap">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
            </div>
            <h2 class="auth-title">Administrator Sign In</h2>
            <p class="auth-desc">Enter office administrator credentials to manage individual employee shifts, attendance records, website audits, and monthly reports.</p>

            <div id="adminLoginError" class="auth-error">Invalid administrator username or password.</div>

            <div class="auth-field">
                <label>Username</label>
                <input type="text" id="adminUser" value="admin">
            </div>
            <div class="auth-field">
                <label>Password</label>
                <input type="password" id="adminPass" placeholder="••••••••" onkeydown="if(event.key==='Enter') executeAdminLogin()">
            </div>

            <button class="btn btn-primary" style="width: 100%; justify-content: center; margin-top: 8px;" onclick="executeAdminLogin()">
                Sign In to Portal
            </button>
            <p style="margin-top: 14px; font-size: 11px; color: var(--text-muted);">Default: <code>admin</code> / <code>admin123</code></p>
        </div>

        <!-- VIEW B: AUTHENTICATED MANAGEMENT PORTAL -->
        <div id="adminDashboardContent" style="display: none;">
            
            <!-- Navigation Tabs -->
            <div class="tab-nav">
                <button class="tab-btn active" onclick="switchAdminTab('timesheets', this)">Attendance & Timesheets</button>
                <button class="tab-btn" onclick="switchAdminTab('individual', this)">Individual Employee Deep-Dive</button>
                <button class="tab-btn" onclick="switchAdminTab('daily', this)">Daily Reports</button>
                <button class="tab-btn" onclick="switchAdminTab('monthly', this)">Monthly Timesheets</button>
                <button class="tab-btn" onclick="switchAdminTab('shifts', this)">Employees & Shift Setup</button>
                <button class="tab-btn" onclick="switchAdminTab('websites', this)">Browsers & Websites Visited</button>
            </div>

            <!-- TAB 1: ATTENDANCE & TIMESHEETS -->
            <div id="tabContent_timesheets" class="tab-pane">
                <div class="card">
                    <!-- Filters Toolbar -->
                    <div class="filter-bar">
                        <div class="filter-item">
                            <label>Employee:</label>
                            <select id="filterEmployeeSelect" onchange="applyTimesheetFilters()">
                                <option value="">All Employees</option>
                            </select>
                        </div>
                        <div class="filter-item">
                            <label>From:</label>
                            <input type="date" id="filterStartDate" onchange="applyTimesheetFilters()">
                        </div>
                        <div class="filter-item">
                            <label>To:</label>
                            <input type="date" id="filterEndDate" onchange="applyTimesheetFilters()">
                        </div>
                        <div class="filter-item">
                            <label>Status:</label>
                            <select id="filterStatusSelect" onchange="applyTimesheetFilters()">
                                <option value="ALL">All Statuses</option>
                                <option value="COMPLETED">Completed</option>
                                <option value="OPEN">In Progress</option>
                            </select>
                        </div>
                        <div style="display: flex; gap: 6px; align-items: center; margin-left: auto;">
                            <button class="quick-date-btn" style="background: var(--status-active-dot); color: white; border: none; font-weight: 700; display: inline-flex; align-items: center; gap: 4px;" onclick="openAddEmployeeModal()">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                    <line x1="12" y1="5" x2="12" y2="19"></line>
                                    <line x1="5" y1="12" x2="19" y2="12"></line>
                                </svg>
                                Add Employee
                            </button>
                            <button class="quick-date-btn" onclick="setQuickDate('today')">Today</button>
                            <button class="quick-date-btn" onclick="setQuickDate('week')">This Week</button>
                            <button class="quick-date-btn" onclick="setQuickDate('month')">This Month</button>
                            <button class="quick-date-btn" onclick="resetTimesheetFilters()">Reset</button>
                            <button class="quick-date-btn" style="color: #DC2626; border-color: #FECACA;" onclick="clearAllTimesheetLogs()">Clear All Logs</button>
                        </div>
                    </div>

                    <!-- Summary KPIs of Filtered Data -->
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="kpi-title">Matching Sessions</div>
                            <div class="kpi-val" id="filterKpiCount">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Total Active Work</div>
                            <div class="kpi-val" id="filterKpiActive" style="color: var(--status-active-dot);">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Total Inactivity</div>
                            <div class="kpi-val" id="filterKpiInactive" style="color: var(--status-inactive-dot);">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Inactivity Rate</div>
                            <div class="kpi-val" id="filterKpiRate">0.0%</div>
                        </div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h2 style="font-size: 16px; font-weight: 700;">Employee Timesheet Records</h2>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-secondary btn-sm" onclick="exportFilteredExcel()">
                                Export Filtered Excel (.xlsx)
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="exportFilteredCSV()">
                                Export CSV
                            </button>
                        </div>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Employee</th>
                                <th>Code</th>
                                <th>Assigned Shift</th>
                                <th>Date</th>
                                <th>Login</th>
                                <th>Logout</th>
                                <th>Active Work</th>
                                <th>Inactive Time</th>
                                <th>Lunch</th>
                                <th>Overtime</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="timesheetsTableBody">
                            <tr><td colspan="12" style="text-align: center; color: var(--text-muted); padding: 24px;">Loading records...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 2: INDIVIDUAL EMPLOYEE DEEP-DIVE -->
            <div id="tabContent_individual" class="tab-pane" style="display: none;">
                <div class="card" style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                        <div>
                            <h2 style="font-size: 17px; font-weight: 700;">Individual Employee Deep-Dive & Profile</h2>
                            <p style="color: var(--text-muted); font-size: 13px; margin-top: 2px;">Review detailed productivity, assigned shift hours, and web history for a specific employee.</p>
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <label style="font-size: 13px; font-weight: 600;">Select Employee:</label>
                            <select id="individualEmployeeSelect" style="min-width: 220px;" onchange="loadEmployeeProfileData()">
                                <option value="">Select Employee...</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div id="individualProfileContainer" style="display: none;">
                    <div class="card" style="border-left: 4px solid var(--status-active-dot);">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                            <div>
                                <h2 id="indivName" style="font-size: 20px; font-weight: 700;">Employee Name</h2>
                                <p style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">
                                    Code: <code id="indivCode" style="font-weight: 600; background: var(--bg-subtle); padding: 2px 6px; border-radius: 4px;">---</code>
                                    <span style="margin: 0 8px;">•</span>
                                    Assigned Shift: <strong id="indivShiftHours" style="color: var(--text-main);">09:30 - 18:00</strong>
                                    <span style="margin: 0 8px;">•</span>
                                    Auto-Launch: <strong id="indivAutoStartText" style="color: var(--status-active-dot);">Enabled</strong>
                                </p>
                            </div>
                            <button class="btn btn-secondary btn-sm" onclick="openEditShiftModalFromProfile()" style="display: flex; align-items: center; gap: 6px;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <polyline points="12 6 12 12 16 14"></polyline>
                                </svg>
                                Edit Shift Hours
                            </button>
                        </div>
                    </div>

                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="kpi-title">Total Days Worked</div>
                            <div class="kpi-val" id="indivKpiDays">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Total Active Work</div>
                            <div class="kpi-val" id="indivKpiActive" style="color: var(--status-active-dot);">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Avg Daily Work Time</div>
                            <div class="kpi-val" id="indivKpiAvgDaily">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Inactivity Ratio</div>
                            <div class="kpi-val" id="indivKpiInactivityPct" style="color: var(--status-inactive-dot);">0.0%</div>
                        </div>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 20px;">
                        <div class="card" style="margin-bottom: 0;">
                            <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 14px;">Websites Visited by This Employee</h3>
                            <table style="font-size: 12px;">
                                <thead><tr><th>Domain</th><th>Time Spent</th></tr></thead>
                                <tbody id="indivWebsitesTable"><tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No websites recorded.</td></tr></tbody>
                            </table>
                        </div>
                        <div class="card" style="margin-bottom: 0;">
                            <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 14px;">Applications Used</h3>
                            <table style="font-size: 12px;">
                                <thead><tr><th>Application</th><th>Duration</th></tr></thead>
                                <tbody id="indivAppsTable"><tr><td colspan="2" style="text-align: center; color: var(--text-muted);">No applications recorded.</td></tr></tbody>
                            </table>
                        </div>
                    </div>

                    <div class="card">
                        <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 14px;">Recent Shift Sessions</h3>
                        <table>
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Login Time</th>
                                    <th>Logout Time</th>
                                    <th>Active Work</th>
                                    <th>Inactive Time</th>
                                    <th>Lunch</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody id="indivSessionsTable">
                                <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Loading sessions...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- TAB 3: DAILY REPORTS -->
            <div id="tabContent_daily" class="tab-pane" style="display: none;">
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; margin-bottom: 20px;">
                        <div>
                            <h2 style="font-size: 17px; font-weight: 700;">Daily Employee Activity Report</h2>
                            <p style="color: var(--text-muted); font-size: 13px; margin-top: 2px;">Comprehensive single-day audit of every employee's attendance, productivity, and top website.</p>
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button class="btn btn-secondary btn-sm" onclick="changeDailyDate(-1)">← Prev Day</button>
                            <input type="date" id="dailyReportDatePicker" onchange="loadDailyReportData()">
                            <button class="btn btn-secondary btn-sm" onclick="changeDailyDate(1)">Next Day →</button>
                            <button class="btn btn-primary btn-sm" onclick="exportDailyReportExcel()">Download Day Excel (.xlsx)</button>
                        </div>
                    </div>

                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="kpi-title">Employees Present</div>
                            <div class="kpi-val" id="dailyKpiPresent">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Company Work Hours</div>
                            <div class="kpi-val" id="dailyKpiActive" style="color: var(--status-active-dot);">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Total Inactive Hours</div>
                            <div class="kpi-val" id="dailyKpiInactive" style="color: var(--status-inactive-dot);">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Day Inactivity Ratio</div>
                            <div class="kpi-val" id="dailyKpiRate">0.0%</div>
                        </div>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Employee</th>
                                <th>Code</th>
                                <th>Assigned Shift</th>
                                <th>Login Time</th>
                                <th>Logout Time</th>
                                <th>Active Work</th>
                                <th>Inactive Time</th>
                                <th>Overtime</th>
                                <th>Top Website</th>
                                <th>Top Application</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody id="dailyReportTableBody">
                            <tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 24px;">No employee records found for this date.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 4: MONTHLY TIMESHEETS -->
            <div id="tabContent_monthly" class="tab-pane" style="display: none;">
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; margin-bottom: 20px;">
                        <div>
                            <h2 style="font-size: 17px; font-weight: 700;">Monthly Employee Timesheet & Performance Audit</h2>
                            <p style="color: var(--text-muted); font-size: 13px; margin-top: 2px;">End-of-month attendance summary, total active hours, days worked, and individual website usage for payroll and review.</p>
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <label style="font-size: 13px; font-weight: 600;">Select Month:</label>
                            <input type="month" id="monthlyReportMonthPicker" onchange="loadMonthlyReportData()">
                            <button class="btn btn-primary btn-sm" onclick="exportMonthlyReportExcel()">
                                Download Monthly Report (.xlsx)
                            </button>
                        </div>
                    </div>

                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="kpi-title">Active Employees</div>
                            <div class="kpi-val" id="monthlyKpiActiveEmps">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Total Monthly Shifts</div>
                            <div class="kpi-val" id="monthlyKpiSessions">0</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Total Company Work Time</div>
                            <div class="kpi-val" id="monthlyKpiActive" style="color: var(--status-active-dot);">00h 00m</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-title">Monthly Inactivity Rate</div>
                            <div class="kpi-val" id="monthlyKpiRate">0.0%</div>
                        </div>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Employee Name</th>
                                <th>Code</th>
                                <th>Assigned Shift</th>
                                <th>Days Present</th>
                                <th>Total Active Work</th>
                                <th>Total Inactive Time</th>
                                <th>Avg Daily Work</th>
                                <th>Inactivity Rate</th>
                                <th>Top Visited Website</th>
                            </tr>
                        </thead>
                        <tbody id="monthlyReportTableBody">
                            <tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 24px;">Loading monthly report...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 5: EMPLOYEE SHIFT & ACCESS SETUP -->
            <div id="tabContent_shifts" class="tab-pane" style="display: none;">
                <!-- Company-Wide Default Shift Timing -->
                <div class="card" style="margin-bottom: 20px; border-left: 4px solid var(--accent-primary);">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                        <div>
                            <h3 style="font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <polyline points="12 6 12 12 16 14"></polyline>
                                </svg>
                                Company-Wide Shift Hours (Quick Bulk Update)
                            </h3>
                            <p style="color: var(--text-muted); font-size: 13px; margin-top: 2px;">
                                Apply standard working hours to all employees across the office at once.
                            </p>
                        </div>
                        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                            <label style="font-size: 13px; font-weight: 600;">Shift Start:</label>
                            <input type="time" id="bulkShiftStart" value="09:30" style="width: 110px; font-weight: 600;">
                            <label style="font-size: 13px; font-weight: 600;">Shift End:</label>
                            <input type="time" id="bulkShiftEnd" value="18:00" style="width: 110px; font-weight: 600;">
                            <button class="btn btn-primary btn-sm" onclick="applyBulkShiftTimings()">Apply to All Employees</button>
                        </div>
                    </div>
                </div>

                <!-- Add New Employee Card -->
                <div class="card" style="margin-bottom: 20px;">
                    <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 12px;">Add New Employee to Workstation Roster</h3>
                    <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                        <input type="text" id="newEmpName" placeholder="Full Name" style="width: 180px;">
                        <input type="text" id="newEmpCode" placeholder="Code (e.g. EMP-105)" style="width: 140px;">
                        <input type="password" id="newEmpPin" placeholder="PIN (default 1234)" style="width: 120px;">
                        <label style="font-size: 13px; font-weight: 600;">Shift Start:</label>
                        <input type="time" id="newEmpShiftStart" value="09:30" style="width: 105px;">
                        <label style="font-size: 13px; font-weight: 600;">Shift End:</label>
                        <input type="time" id="newEmpShiftEnd" value="18:00" style="width: 105px;">
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="newEmpAutoStart" checked> Auto-Launch
                        </label>
                        <button class="btn btn-primary btn-sm" onclick="addNewEmployee()">Add Employee</button>
                    </div>
                </div>

                <!-- Custom Shift Hours & Passwords Table -->
                <div class="card">
                    <h2 style="font-size: 17px; font-weight: 700; margin-bottom: 6px;">Individual Employee Configuration</h2>
                    <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 18px;">
                        Customize shift hours and idle thresholds for each employee. Workstations start and stop monitoring on each employee's schedule.
                    </p>

                    <table>
                        <thead>
                            <tr>
                                <th>Employee</th>
                                <th>Code</th>
                                <th>Total Shifts</th>
                                <th>Shift Start</th>
                                <th>Shift End</th>
                                <th>Auto-Launch</th>
                                <th>Idle Threshold</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="shiftsTableBody">
                            <tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">Loading employees...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 6: CONFIDENTIAL BROWSER & WEBSITE MONITORING LOGS -->
            <div id="tabContent_websites" class="tab-pane" style="display: none;">
                <!-- Header Card -->
                <div class="card" style="margin-bottom: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                        <div>
                            <h2 style="font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <line x1="2" y1="12" x2="22" y2="12"></line>
                                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                                </svg>
                                Browsers & Websites Visited Across Workstations
                            </h2>
                            <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Live surveillance audit of which browsers and websites employees visited and exact duration spent.</p>
                        </div>
                        <button class="btn btn-secondary" onclick="loadWebsitesData()">Refresh Surveillance Logs</button>
                    </div>
                </div>

                <!-- 4 KPI Cards -->
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-title">Total Web Browsing Time</div>
                        <div class="kpi-val" id="webKpiTotalBrowsing" style="color: var(--status-active-dot);">00h 00m</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-title">Primary Browser Used</div>
                        <div class="kpi-val" id="webKpiPrimaryBrowser" style="font-size: 18px;">Google Chrome</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-title">Top Visited Website</div>
                        <div class="kpi-val" id="webKpiTopWebsite" style="font-size: 18px; color: var(--accent-primary);">--</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-title">Unique Websites Visited</div>
                        <div class="kpi-val" id="webKpiUniqueCount">0 Sites</div>
                    </div>
                </div>

                <!-- Browser Breakdown Cards -->
                <div class="card" style="margin-bottom: 16px;">
                    <h3 style="font-size: 14px; font-weight: 700; margin-bottom: 12px;">Browser Usage Breakdown</h3>
                    <div id="browserBreakdownGrid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                        <div style="color: var(--text-muted); font-size: 13px;">Loading browser metrics...</div>
                    </div>
                </div>

                <!-- Search & Filter Controls -->
                <div class="card" style="padding: 14px 18px; margin-bottom: 16px;">
                    <div style="display: flex; gap: 14px; align-items: center; flex-wrap: wrap;">
                        <div style="flex: 1; min-width: 220px;">
                            <input type="text" id="webSearchInput" placeholder="Search by website domain (e.g. github, youtube) or browser..." style="width: 100%;" oninput="filterWebsitesTable()">
                        </div>
                        <div style="min-width: 180px;">
                            <select id="webEmployeeFilter" style="width: 100%;" onchange="filterWebsitesTable()">
                                <option value="">All Employees</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- Main Websites Visited Table -->
                <div class="card" style="margin-bottom: 18px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                        <h3 style="font-size: 15px; font-weight: 700;">Websites Visited by Employees</h3>
                        <span id="webRecordCountBadge" style="font-size: 12px; color: var(--text-muted); font-weight: 600;">0 records</span>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Employee</th>
                                <th>Date</th>
                                <th>Browser Used</th>
                                <th>Website / Domain</th>
                                <th>Duration Spent</th>
                            </tr>
                        </thead>
                        <tbody id="allWebsitesTableBody">
                            <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Loading website logs...</td></tr>
                        </tbody>
                    </table>
                </div>

                <!-- Applications & Software Usage Table -->
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                        <div>
                            <h3 style="font-size: 15px; font-weight: 700;">All Applications & Software Activity</h3>
                            <p style="color: var(--text-muted); font-size: 12px; margin-top: 2px;">Process-level duration records across browsers, development tools, and office apps.</p>
                        </div>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Employee</th>
                                <th>Date</th>
                                <th>Application / Browser</th>
                                <th>Category</th>
                                <th>Duration Spent</th>
                            </tr>
                        </thead>
                        <tbody id="allAppsTableBody">
                            <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Loading application logs...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- ADD EMPLOYEE MODAL DIALOG -->
    <div id="addEmployeeModal" style="display: none; position: fixed; inset: 0; background: rgba(15, 23, 42, 0.65); z-index: 9999; backdrop-filter: blur(4px); align-items: center; justify-content: center; padding: 16px;">
        <div class="card" style="max-width: 500px; width: 100%; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.35); border-radius: 12px; margin: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 36px; height: 36px; border-radius: 8px; background: rgba(5, 150, 105, 0.12); color: var(--status-active-dot); display: flex; align-items: center; justify-content: center;">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <line x1="12" y1="5" x2="12" y2="19"></line>
                            <line x1="5" y1="12" x2="19" y2="12"></line>
                        </svg>
                    </div>
                    <div>
                        <h2 style="font-size: 17px; font-weight: 700; margin: 0;">Add New Employee</h2>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 2px 0 0 0;">Create a workstation account and assign shift hours</p>
                    </div>
                </div>
                <button onclick="closeAddEmployeeModal()" style="background: none; border: none; font-size: 22px; cursor: pointer; color: var(--text-muted); line-height: 1;">&times;</button>
            </div>

            <div id="modalAddEmpError" style="background-color: #FEF2F2; border: 1px solid #FECACA; color: #991B1B; padding: 10px; border-radius: 6px; font-size: 12px; margin-bottom: 14px; display: none;"></div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px;">
                <div style="grid-column: span 2;">
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px;">Full Name *</label>
                    <input type="text" id="modalEmpName" placeholder="e.g. Sarah Jenkins" style="width: 100%;">
                </div>
                <div>
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px;">Employee Code *</label>
                    <input type="text" id="modalEmpCode" placeholder="e.g. EMP-102" style="width: 100%;">
                </div>
                <div>
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px;">Workstation PIN *</label>
                    <input type="password" id="modalEmpPin" placeholder="Default: 1234" value="1234" style="width: 100%;">
                </div>
                <div>
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px;">Shift Start Time</label>
                    <input type="time" id="modalEmpShiftStart" value="09:30" style="width: 100%;">
                </div>
                <div>
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px;">Shift End Time</label>
                    <input type="time" id="modalEmpShiftEnd" value="18:00" style="width: 100%;">
                </div>
                <div style="grid-column: span 2;">
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px;">Inactivity Idle Threshold</label>
                    <select id="modalEmpThreshold" style="width: 100%;">
                        <option value="60">1 minute</option>
                        <option value="180">3 minutes</option>
                        <option value="300" selected>5 minutes (Recommended)</option>
                        <option value="600">10 minutes</option>
                        <option value="15">15 seconds (Test Mode)</option>
                        <option value="30">30 seconds (Test Mode)</option>
                    </select>
                </div>
                <div style="grid-column: span 2; margin-top: 4px;">
                    <label style="display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; cursor: pointer;">
                        <input type="checkbox" id="modalEmpAutoStart" checked>
                        <span>Auto-Launch monitoring during assigned shift window</span>
                    </label>
                </div>
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border-subtle);">
                <button class="btn btn-secondary" onclick="closeAddEmployeeModal()">Cancel</button>
                <button class="btn btn-primary" onclick="submitModalNewEmployee()">Create Employee</button>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('adminHeaderDate').innerText = new Date().toLocaleDateString('en-US', {{
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        }});

        function updateThemeIcons(theme) {{
            const sun = document.getElementById('themeIconSun');
            const moon = document.getElementById('themeIconMoon');
            if (theme === 'dark') {{
                sun.style.display = 'none';
                moon.style.display = 'block';
            }} else {{
                sun.style.display = 'block';
                moon.style.display = 'none';
            }}
        }}
        updateThemeIcons(document.documentElement.getAttribute('data-theme') || 'light');

        function toggleTheme() {{
            const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('app_theme', next);
            updateThemeIcons(next);
        }}

        function formatDuration(sec) {{
            let h = Math.floor(sec / 3600);
            let m = Math.floor((sec % 3600) / 60);
            let s = sec % 60;
            return `${{String(h).padStart(2,'0')}}h ${{String(m).padStart(2,'0')}}m ${{String(s).padStart(2,'0')}}s`;
        }}

        function switchAdminTab(tabName, btn) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');
            btn.classList.add('active');
            document.getElementById(`tabContent_${{tabName}}`).style.display = 'block';

            if (tabName === 'timesheets') applyTimesheetFilters();
            if (tabName === 'daily') loadDailyReportData();
            if (tabName === 'monthly') loadMonthlyReportData();
            if (tabName === 'shifts') loadShiftsData();
            if (tabName === 'websites') loadWebsitesData();
        }}

        async function adminFetch(url, options = {{}}) {{
            const token = sessionStorage.getItem('adminToken');
            options.headers = options.headers || {{}};
            if (token) {{
                options.headers['X-Admin-Token'] = token;
            }}
            try {{
                const res = await fetch(url, options);
                if (res.status === 401) {{
                    sessionStorage.removeItem('adminToken');
                    document.getElementById('adminLoginForm').style.display = 'block';
                    document.getElementById('adminDashboardContent').style.display = 'none';
                    document.getElementById('adminAddEmpBtn').style.display = 'none';
                    document.getElementById('adminSignOutBtn').style.display = 'none';
                    const errDiv = document.getElementById('adminLoginError');
                    if (errDiv) {{
                        errDiv.innerText = 'Session expired. Please log in again.';
                        errDiv.style.display = 'block';
                    }}
                    return null;
                }}
                return res;
            }} catch (err) {{
                console.error('Admin fetch error:', err);
                return null;
            }}
        }}

        async function checkAuth() {{
            // Permanent Admin Login: Auto-authenticate and immediately show dashboard
            let token = localStorage.getItem('adminToken');
            if (!token) {{
                try {{
                    const r = await fetch('/api/admin/auto-auth', {{ method: 'POST' }});
                    if (r.ok) {{
                        const d = await r.json();
                        token = d.token;
                        localStorage.setItem('adminToken', token);
                    }}
                }} catch (e) {{}}
            }}

            document.getElementById('adminLoginForm').style.display = 'none';
            document.getElementById('adminDashboardContent').style.display = 'block';
            document.getElementById('adminAddEmpBtn').style.display = 'inline-flex';
            const sBtn = document.getElementById('adminSignOutBtn');
            if (sBtn) sBtn.style.display = 'none';

            initDashboardDates();
            loadEmployeesDropdown();
            applyTimesheetFilters();
        }}

        function initDashboardDates() {{
            const todayStr = new Date().toISOString().split('T')[0];
            document.getElementById('dailyReportDatePicker').value = todayStr;
            const curMonth = todayStr.substring(0, 7);
            document.getElementById('monthlyReportMonthPicker').value = curMonth;
        }}

        async function executeAdminLogin() {{
            const user = document.getElementById('adminUser').value.trim();
            const pass = document.getElementById('adminPass').value;
            const errDiv = document.getElementById('adminLoginError');

            try {{
                const res = await fetch('/api/admin/login', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ username: user, password: pass }})
                }});

                if (res.ok) {{
                    const data = await res.json();
                    sessionStorage.setItem('adminToken', data.token);
                    errDiv.style.display = 'none';
                    document.getElementById('adminLoginForm').style.display = 'none';
                    document.getElementById('adminDashboardContent').style.display = 'block';
                    document.getElementById('adminAddEmpBtn').style.display = 'inline-flex';
                    document.getElementById('adminSignOutBtn').style.display = 'inline-flex';
                    initDashboardDates();
                    loadEmployeesDropdown();
                    applyTimesheetFilters();
                }} else {{
                    errDiv.innerText = 'Invalid username or password.';
                    errDiv.style.display = 'block';
                }}
            }} catch (e) {{
                errDiv.innerText = 'Connection error. Please try again.';
                errDiv.style.display = 'block';
            }}
        }}

        async function executeAdminLogout() {{
            const token = sessionStorage.getItem('adminToken');
            try {{
                await fetch('/api/admin/logout', {{
                    method: 'POST',
                    headers: {{ 'X-Admin-Token': token }}
                }});
            }} catch (e) {{}}
            sessionStorage.removeItem('adminToken');
            checkAuth();
        }}

        async function loadEmployeesDropdown() {{
            const res = await adminFetch('/api/admin/employees');
            if (!res || !res.ok) return;
            const emps = await res.json();

            const selectFilter = document.getElementById('filterEmployeeSelect');
            const selectIndiv = document.getElementById('individualEmployeeSelect');

            if (emps.length === 0) {{
                selectFilter.innerHTML = '<option value="">No employees registered</option>';
                selectIndiv.innerHTML = '<option value="">No employees registered</option>';
            }} else {{
                selectFilter.innerHTML = '<option value="">All Employees</option>';
                selectIndiv.innerHTML = '<option value="">Select Employee...</option>';
                emps.forEach(e => {{
                    selectFilter.innerHTML += `<option value="${{e.id}}">${{e.name}} (${{e.employee_code}})</option>`;
                    selectIndiv.innerHTML += `<option value="${{e.id}}">${{e.name}} (${{e.employee_code}})</option>`;
                }});
            }}
        }}

        // --- TAB 1: FILTERS & ATTENDANCE ---
        async function applyTimesheetFilters() {{
            const empId = document.getElementById('filterEmployeeSelect').value;
            const sDate = document.getElementById('filterStartDate').value;
            const eDate = document.getElementById('filterEndDate').value;
            const status = document.getElementById('filterStatusSelect').value;

            let url = `/api/admin/sessions?status=${{status}}`;
            if (empId) url += `&employee_id=${{empId}}`;
            if (sDate) url += `&start_date=${{sDate}}`;
            if (eDate) url += `&end_date=${{eDate}}`;

            const res = await adminFetch(url);
            if (!res || !res.ok) return;
            const sessions = await res.json();

            let totalActive = 0, totalInactive = 0;
            sessions.forEach(s => {{
                totalActive += (s.total_active_sec || 0);
                totalInactive += (s.total_inactive_sec || 0);
            }});

            const totalWork = totalActive + totalInactive;
            const rate = totalWork > 0 ? ((totalInactive / totalWork) * 100).toFixed(1) : "0.0";

            document.getElementById('filterKpiCount').innerText = sessions.length;
            document.getElementById('filterKpiActive').innerText = formatDuration(totalActive);
            document.getElementById('filterKpiInactive').innerText = formatDuration(totalInactive);
            document.getElementById('filterKpiRate').innerText = `${{rate}}%`;

            const tbody = document.getElementById('timesheetsTableBody');
            if (sessions.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; color: var(--text-muted); padding: 24px;">No matching timesheet records found.</td></tr>';
                return;
            }}

            tbody.innerHTML = sessions.map(s => {{
                const statusClass = s.status === "COMPLETED" ? "status-active" : "status-inactive";
                return `<tr>
                    <td><strong>${{s.employee_name}}</strong></td>
                    <td><code style="background:var(--bg-subtle); padding:2px 6px; border-radius:4px; font-size:12px;">${{s.employee_code}}</code></td>
                    <td class="num-cell">${{s.shift_start}} - ${{s.shift_end}}</td>
                    <td>${{s.date}}</td>
                    <td class="num-cell">${{s.login_time}}</td>
                    <td class="num-cell">${{s.logout_time || '<span style="color:var(--text-muted);">In Progress</span>'}}</td>
                    <td class="num-cell" style="font-weight:600; color:var(--status-active-dot);">${{formatDuration(s.total_active_sec || 0)}}</td>
                    <td class="num-cell" style="font-weight:600; color:var(--status-inactive-dot);">${{formatDuration(s.total_inactive_sec || 0)}}</td>
                    <td class="num-cell">${{formatDuration(s.total_lunch_sec || 0)}}</td>
                    <td class="num-cell" style="font-weight:600; color:#8B5CF6;">${{formatDuration(s.overtime_sec || 0)}}</td>
                    <td><span class="status-badge ${{statusClass}}"><span class="status-dot"></span>${{s.status}}</span></td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="viewEmployeeProfileDirectly(${{s.employee_id}})">View Profile</button>
                    </td>
                </tr>`;
            }}).join('');
        }}

        function setQuickDate(type) {{
            const now = new Date();
            const todayStr = now.toISOString().split('T')[0];
            if (type === 'today') {{
                document.getElementById('filterStartDate').value = todayStr;
                document.getElementById('filterEndDate').value = todayStr;
            }} else if (type === 'week') {{
                const day = now.getDay() || 7;
                now.setDate(now.getDate() - day + 1);
                document.getElementById('filterStartDate').value = now.toISOString().split('T')[0];
                document.getElementById('filterEndDate').value = todayStr;
            }} else if (type === 'month') {{
                const startMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
                document.getElementById('filterStartDate').value = startMonth;
                document.getElementById('filterEndDate').value = todayStr;
            }}
            applyTimesheetFilters();
        }}

        function resetTimesheetFilters() {{
            document.getElementById('filterEmployeeSelect').value = "";
            document.getElementById('filterStartDate').value = "";
            document.getElementById('filterEndDate').value = "";
            document.getElementById('filterStatusSelect').value = "ALL";
            applyTimesheetFilters();
        }}

        function viewEmployeeProfileDirectly(empId) {{
            const indivBtn = document.querySelectorAll('.tab-btn')[1];
            switchAdminTab('individual', indivBtn);
            document.getElementById('individualEmployeeSelect').value = empId;
            loadEmployeeProfileData();
        }}

        // --- TAB 2: INDIVIDUAL DEEP-DIVE ---
        async function loadEmployeeProfileData() {{
            const empId = document.getElementById('individualEmployeeSelect').value;
            const container = document.getElementById('individualProfileContainer');
            if (!empId) {{
                container.style.display = 'none';
                return;
            }}

            const res = await adminFetch(`/api/admin/employee-profile/${{empId}}`);
            if (!res || !res.ok) return;
            const data = await res.json();
            currentProfileData = data;
            container.style.display = 'block';

            document.getElementById('indivName').innerText = data.employee.name;
            document.getElementById('indivCode').innerText = data.employee.employee_code;
            document.getElementById('indivShiftHours').innerText = `${{data.employee.shift_start}} to ${{data.employee.shift_end}}`;
            document.getElementById('indivAutoStartText').innerText = data.employee.is_auto_start ? 'Enabled' : 'Disabled';

            document.getElementById('indivKpiDays').innerText = data.kpis.total_days;
            document.getElementById('indivKpiActive').innerText = formatDuration(data.kpis.total_active_sec);
            document.getElementById('indivKpiAvgDaily').innerText = formatDuration(data.kpis.avg_active_sec);
            document.getElementById('indivKpiInactivityPct').innerText = `${{data.kpis.inactivity_pct}}%`;

            const webTbody = document.getElementById('indivWebsitesTable');
            if (!data.top_websites || data.top_websites.length === 0) {{
                webTbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--text-muted); padding: 12px;">No websites recorded.</td></tr>';
            }} else {{
                webTbody.innerHTML = data.top_websites.map(w => `
                    <tr>
                        <td><span style="font-weight:600; color:var(--status-active-dot);">🌐 ${{w.domain}}</span></td>
                        <td class="num-cell">${{formatDuration(w.duration_sec)}}</td>
                    </tr>
                `).join('');
            }}

            const appTbody = document.getElementById('indivAppsTable');
            if (!data.top_apps || data.top_apps.length === 0) {{
                appTbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--text-muted); padding: 12px;">No apps recorded.</td></tr>';
            }} else {{
                appTbody.innerHTML = data.top_apps.map(a => `
                    <tr>
                        <td><strong>${{a.app_name}}</strong></td>
                        <td class="num-cell">${{formatDuration(a.duration_sec)}}</td>
                    </tr>
                `).join('');
            }}

            const sessTbody = document.getElementById('indivSessionsTable');
            if (!data.recent_sessions || data.recent_sessions.length === 0) {{
                sessTbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 18px;">No sessions found.</td></tr>';
            }} else {{
                sessTbody.innerHTML = data.recent_sessions.map(s => `
                    <tr>
                        <td>${{s.date}}</td>
                        <td class="num-cell">${{s.login_time}}</td>
                        <td class="num-cell">${{s.logout_time || 'In Progress'}}</td>
                        <td class="num-cell" style="font-weight:600; color:var(--status-active-dot);">${{formatDuration(s.total_active_sec || 0)}}</td>
                        <td class="num-cell" style="font-weight:600; color:var(--status-inactive-dot);">${{formatDuration(s.total_inactive_sec || 0)}}</td>
                        <td class="num-cell">${{formatDuration(s.total_lunch_sec || 0)}}</td>
                        <td><span class="status-badge ${{s.status === 'COMPLETED' ? 'status-active' : 'status-inactive'}}">${{s.status}}</span></td>
                    </tr>
                `).join('');
            }}
        }}

        // --- TAB 3: DAILY REPORT ---
        function changeDailyDate(delta) {{
            const picker = document.getElementById('dailyReportDatePicker');
            const d = new Date(picker.value || new Date());
            d.setDate(d.getDate() + delta);
            picker.value = d.toISOString().split('T')[0];
            loadDailyReportData();
        }}

        async function loadDailyReportData() {{
            const dateStr = document.getElementById('dailyReportDatePicker').value;
            if (!dateStr) return;
            const res = await adminFetch(`/api/admin/daily-report?date=${{dateStr}}`);
            if (!res || !res.ok) return;
            const data = await res.json();

            document.getElementById('dailyKpiPresent').innerText = data.total_employees_present;
            document.getElementById('dailyKpiActive').innerText = formatDuration(data.total_active_sec);
            document.getElementById('dailyKpiInactive').innerText = formatDuration(data.total_inactive_sec);
            document.getElementById('dailyKpiRate').innerText = `${{data.inactivity_pct}}%`;

            const tbody = document.getElementById('dailyReportTableBody');
            if (data.records.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 24px;">No employee records found for this date.</td></tr>';
                return;
            }}

            tbody.innerHTML = data.records.map(r => `
                <tr>
                    <td><strong>${{r.employee_name}}</strong></td>
                    <td><code style="background:var(--bg-subtle); padding:2px 6px; border-radius:4px; font-size:12px;">${{r.employee_code}}</code></td>
                    <td class="num-cell">${{r.shift_start}} - ${{r.shift_end}}</td>
                    <td class="num-cell">${{r.login_time}}</td>
                    <td class="num-cell">${{r.logout_time || '<span style="color:var(--text-muted);">In Progress</span>'}}</td>
                    <td class="num-cell" style="font-weight:600; color:var(--status-active-dot);">${{formatDuration(r.total_active_sec || 0)}}</td>
                    <td class="num-cell" style="font-weight:600; color:var(--status-inactive-dot);">${{formatDuration(r.total_inactive_sec || 0)}}</td>
                    <td class="num-cell" style="font-weight:600; color:#8B5CF6;">${{formatDuration(r.overtime_sec || 0)}}</td>
                    <td><span style="font-weight:600; color:var(--status-active-dot);">🌐 ${{r.top_website}}</span></td>
                    <td><strong>${{r.top_app}}</strong></td>
                    <td><span class="status-badge ${{r.status === 'COMPLETED' ? 'status-active' : 'status-inactive'}}">${{r.status}}</span></td>
                </tr>
            `).join('');
        }}

        // --- TAB 4: MONTHLY REPORT ---
        async function loadMonthlyReportData() {{
            const monthStr = document.getElementById('monthlyReportMonthPicker').value;
            if (!monthStr) return;
            const [year, month] = monthStr.split('-').map(Number);
            const res = await adminFetch(`/api/admin/monthly-report?year=${{year}}&month=${{month}}`);
            if (!res || !res.ok) return;
            const data = await res.json();

            document.getElementById('monthlyKpiActiveEmps').innerText = data.overall.active_employees;
            document.getElementById('monthlyKpiSessions').innerText = data.overall.total_sessions;
            document.getElementById('monthlyKpiActive').innerText = formatDuration(data.overall.total_active_sec);
            document.getElementById('monthlyKpiRate').innerText = `${{data.overall.company_inactivity_pct}}%`;

            const tbody = document.getElementById('monthlyReportTableBody');
            if (data.employees.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 24px;">No employees configured.</td></tr>';
                return;
            }}

            tbody.innerHTML = data.employees.map(e => `
                <tr>
                    <td><strong>${{e.name}}</strong></td>
                    <td><code style="background:var(--bg-subtle); padding:2px 6px; border-radius:4px; font-size:12px;">${{e.employee_code}}</code></td>
                    <td class="num-cell">${{e.shift_start}} - ${{e.shift_end}}</td>
                    <td class="num-cell" style="font-weight:600;">${{e.days_worked}} days</td>
                    <td class="num-cell" style="font-weight:600; color:var(--status-active-dot);">${{formatDuration(e.total_active_sec)}}</td>
                    <td class="num-cell" style="font-weight:600; color:var(--status-inactive-dot);">${{formatDuration(e.total_inactive_sec)}}</td>
                    <td class="num-cell">${{formatDuration(e.avg_active_sec_per_day)}}</td>
                    <td class="num-cell" style="font-weight:600;">${{e.inactivity_pct}}%</td>
                    <td><span style="font-weight:600; color:var(--status-active-dot);">🌐 ${{e.top_website}}</span></td>
                </tr>
            `).join('');
        }}

        // --- TAB 5: SHIFT CONFIGURATION ---
        async function loadShiftsData() {{
            const res = await adminFetch('/api/admin/employees');
            if (!res || !res.ok) return;
            const emps = await res.json();

            const tbody = document.getElementById('shiftsTableBody');
            if (emps.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">No employees registered yet. Use the form above to add your first employee.</td></tr>';
                return;
            }}

            tbody.innerHTML = emps.map(e => `
                <tr>
                    <td><strong>${{e.name}}</strong></td>
                    <td><code style="background:var(--bg-subtle); padding:2px 6px; border-radius:4px; font-size:12px;">${{e.employee_code}}</code></td>
                    <td class="num-cell">${{e.total_sessions}}</td>
                    <td><input type="time" id="shiftStart_${{e.id}}" value="${{e.shift_start}}" style="width: 105px;"></td>
                    <td><input type="time" id="shiftEnd_${{e.id}}" value="${{e.shift_end}}" style="width: 105px;"></td>
                    <td>
                        <label style="display:flex; align-items:center; gap:6px; font-size:12px; cursor:pointer;">
                            <input type="checkbox" id="shiftAuto_${{e.id}}" ${{e.is_auto_start ? 'checked' : ''}}>
                            Enabled
                        </label>
                    </td>
                    <td>
                        <select id="shiftThresh_${{e.id}}" style="width: 120px; font-size:12px;">
                            <option value="60" ${{e.idle_threshold === 60 ? 'selected' : ''}}>1 minute</option>
                            <option value="180" ${{e.idle_threshold === 180 ? 'selected' : ''}}>3 minutes</option>
                            <option value="300" ${{e.idle_threshold === 300 ? 'selected' : ''}}>5 minutes</option>
                            <option value="600" ${{e.idle_threshold === 600 ? 'selected' : ''}}>10 minutes</option>
                            <option value="15" ${{e.idle_threshold === 15 ? 'selected' : ''}}>15s (Test)</option>
                            <option value="30" ${{e.idle_threshold === 30 ? 'selected' : ''}}>30s (Test)</option>
                        </select>
                    </td>
                    <td>
                        <div style="display: flex; gap: 6px;">
                            <button class="btn btn-primary btn-sm" onclick="saveIndividualShift(${{e.id}}, '${{e.name}}')">Save Shift</button>
                            <button class="btn btn-secondary btn-sm" style="color: #DC2626; border-color: #FECACA;" onclick="deleteEmployee(${{e.id}}, '${{e.name}}')">Delete</button>
                        </div>
                    </td>
                </tr>
            `).join('');
        }}

        async function deleteEmployee(empId, name) {{
            if (!confirm(`Are you sure you want to delete employee "${{name}}" and all their timesheet records?`)) return;
            const res = await adminFetch(`/api/admin/employees/${{empId}}`, {{
                method: 'DELETE'
            }});
            if (res && res.ok) {{
                loadEmployeesDropdown();
                loadShiftsData();
                applyTimesheetFilters();
            }} else {{
                alert("Failed to delete employee.");
            }}
        }}

        async function clearAllTimesheetLogs() {{
            if (!confirm("Are you sure you want to clear ALL recorded timesheet sessions, activity logs, and website monitoring records? (Employee roster will remain intact)")) return;
            const res = await adminFetch('/api/admin/clear-sessions', {{
                method: 'POST'
            }});
            if (res && res.ok) {{
                alert("All timesheet and website logs cleared successfully.");
                applyTimesheetFilters();
                loadWebsitesData();
            }} else {{
                alert("Failed to clear logs.");
            }}
        }}

        async function saveIndividualShift(empId, empName) {{
            const start_time = document.getElementById(`shiftStart_${{empId}}`).value;
            const end_time = document.getElementById(`shiftEnd_${{empId}}`).value;
            const is_auto_start = document.getElementById(`shiftAuto_${{empId}}`).checked;
            const idle_threshold = parseInt(document.getElementById(`shiftThresh_${{empId}}`).value, 10);

            if (!start_time || !end_time) {{
                alert("Please enter both shift start and end times.");
                return;
            }}

            const res = await adminFetch(`/api/admin/employees/${{empId}}/shift`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ employee_id: empId, start_time, end_time, is_auto_start, idle_threshold }})
            }});
            if (res && res.ok) {{
                alert(`Shift timings for ${{empName || 'Employee'}} updated to ${{start_time}} - ${{end_time}} successfully!`);
                loadShiftsData();
            }} else {{
                alert("Failed to update shift.");
            }}
        }}

        async function applyBulkShiftTimings() {{
            const start_time = document.getElementById('bulkShiftStart').value;
            const end_time = document.getElementById('bulkShiftEnd').value;
            if (!start_time || !end_time) {{
                alert("Please enter both shift start and end times.");
                return;
            }}
            if (!confirm(`Apply standard shift hours (${{start_time}} to ${{end_time}}) to ALL employees across the company?`)) return;

            const res = await adminFetch('/api/admin/shifts/bulk-update', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ shift_start: start_time, shift_end: end_time }})
            }});
            if (res && res.ok) {{
                alert(`Company-wide shift hours updated to ${{start_time}} - ${{end_time}} for all employees!`);
                loadShiftsData();
            }} else {{
                alert("Failed to update bulk shift hours.");
            }}
        }}

        function openEditShiftModalFromProfile() {{
            if (!currentProfileData || !currentProfileData.employee) return;
            const emp = currentProfileData.employee;
            const sStart = (emp.shift_start || "09:30").slice(0, 5);
            const sEnd = (emp.shift_end || "18:00").slice(0, 5);
            
            const newStart = prompt(`Edit Shift Start Time (HH:MM) for ${{emp.name}}:`, sStart);
            if (newStart === null) return;
            const newEnd = prompt(`Edit Shift End Time (HH:MM) for ${{emp.name}}:`, sEnd);
            if (newEnd === null) return;

            if (!newStart.trim() || !newEnd.trim()) {{
                alert("Shift hours cannot be empty.");
                return;
            }}

            adminFetch(`/api/admin/employees/${{emp.id}}/shift`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    employee_id: emp.id,
                    start_time: newStart.trim(),
                    end_time: newEnd.trim(),
                    is_auto_start: emp.is_auto_start !== false,
                    idle_threshold: emp.idle_threshold || 300
                }})
            }}).then(res => {{
                if (res && res.ok) {{
                    alert(`Shift hours for ${{emp.name}} updated to ${{newStart.trim()}} - ${{newEnd.trim()}} successfully!`);
                    loadEmployeeProfile(emp.id);
                }} else {{
                    alert("Failed to update shift hours.");
                }}
            }});
        }}

        async function addNewEmployee() {{
            const name = document.getElementById('newEmpName').value.trim();
            const code = document.getElementById('newEmpCode').value.trim();
            const pin = document.getElementById('newEmpPin').value.trim() || "1234";
            const shift_start = document.getElementById('newEmpShiftStart').value;
            const shift_end = document.getElementById('newEmpShiftEnd').value;
            const is_auto_start = document.getElementById('newEmpAutoStart').checked;

            if (!name || !code) {{
                alert("Please provide Employee Name and Code.");
                return;
            }}

            const res = await adminFetch('/api/admin/employees', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ name, code, pin, shift_start, shift_end, is_auto_start }})
            }});

            if (res && res.ok) {{
                alert("Employee added successfully!");
                document.getElementById('newEmpName').value = "";
                document.getElementById('newEmpCode').value = "";
                loadEmployeesDropdown();
                loadShiftsData();
            }} else {{
                alert("Error adding employee. Check for duplicate code.");
            }}
        }}

        // --- TAB 6: BROWSERS & WEBSITES VISITED ---
        let allWebsitesData = [];
        let allAppsData = [];

        async function loadWebsitesData() {{
            try {{
                const res = await adminFetch('/api/admin/web-analytics');
                if (!res || !res.ok) return;
                const data = await res.json();

                // 1. KPI Cards
                const sum = data.summary || {{}};
                document.getElementById('webKpiTotalBrowsing').innerText = formatDuration(sum.total_browsing_sec || 0);
                document.getElementById('webKpiPrimaryBrowser').innerText = sum.primary_browser || 'Google Chrome';
                document.getElementById('webKpiTopWebsite').innerText = sum.top_website || '--';
                document.getElementById('webKpiUniqueCount').innerText = `${{sum.unique_websites_count || 0}} Sites`;

                // 2. Browser Breakdown Grid
                const browserGrid = document.getElementById('browserBreakdownGrid');
                const breakdowns = data.browser_breakdown || [];
                if (breakdowns.length === 0) {{
                    browserGrid.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No browser usage recorded yet.</div>';
                }} else {{
                    browserGrid.innerHTML = breakdowns.map(b => `
                        <div style="background: var(--bg-subtle); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 13px;">${{b.browser}}</strong>
                                <span style="font-size: 11px; font-weight: 700; color: var(--status-active-dot);">${{b.percentage}}%</span>
                            </div>
                            <div style="font-size: 15px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); margin-bottom: 6px;">
                                ${{formatDuration(b.duration_sec)}}
                            </div>
                            <div style="background: var(--border-subtle); height: 5px; border-radius: 3px; overflow: hidden;">
                                <div style="background: var(--status-active-dot); width: ${{b.percentage}}%; height: 100%;"></div>
                            </div>
                        </div>
                    `).join('');
                }}

                // 3. Employee Filter Options
                allWebsitesData = data.all_websites || [];
                allAppsData = data.all_apps || [];

                const empFilter = document.getElementById('webEmployeeFilter');
                const currentVal = empFilter.value;
                const empSet = new Set(allWebsitesData.map(w => w.emp_name).concat(allAppsData.map(a => a.emp_name)));
                empFilter.innerHTML = '<option value="">All Employees</option>' + 
                    Array.from(empSet).filter(Boolean).map(e => `<option value="${{e}}">${{e}}</option>`).join('');
                if (currentVal && empSet.has(currentVal)) empFilter.value = currentVal;

                // 4. Render Table Rows
                filterWebsitesTable();
                renderAppsTable(allAppsData);
            }} catch (e) {{
                console.error("Error loading website surveillance data:", e);
            }}
        }}

        function filterWebsitesTable() {{
            const query = (document.getElementById('webSearchInput').value || '').toLowerCase().trim();
            const emp = document.getElementById('webEmployeeFilter').value;

            let filtered = allWebsitesData.filter(item => {{
                const matchEmp = !emp || item.emp_name === emp;
                const matchQuery = !query || 
                    (item.domain && item.domain.toLowerCase().includes(query)) ||
                    (item.browser && item.browser.toLowerCase().includes(query)) ||
                    (item.emp_name && item.emp_name.toLowerCase().includes(query));
                return matchEmp && matchQuery;
            }});

            document.getElementById('webRecordCountBadge').innerText = `${{filtered.length}} records`;

            const tbody = document.getElementById('allWebsitesTableBody');
            if (filtered.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No matching website visits found.</td></tr>';
                return;
            }}

            tbody.innerHTML = filtered.map(w => `
                <tr>
                    <td>
                        <strong>${{w.emp_name}}</strong>
                        <span style="display:block; font-size:11px; color:var(--text-muted);">${{w.employee_code || ''}}</span>
                    </td>
                    <td>${{w.date}}</td>
                    <td><span style="background: var(--bg-subtle); padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">🌐 ${{w.browser || 'Google Chrome'}}</span></td>
                    <td><span style="font-weight:600; color:var(--status-active-dot);">🔗 ${{w.domain}}</span></td>
                    <td class="num-cell" style="font-weight: 700;">${{formatDuration(w.duration_sec)}}</td>
                </tr>
            `).join('');
        }}

        function renderAppsTable(apps) {{
            const tbody = document.getElementById('allAppsTableBody');
            if (!apps || apps.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No application logs recorded.</td></tr>';
                return;
            }}
            tbody.innerHTML = apps.map(a => `
                <tr>
                    <td><strong>${{a.emp_name}}</strong></td>
                    <td>${{a.date}}</td>
                    <td><strong>${{a.friendly_name}}</strong> <span style="font-size: 11px; color: var(--text-muted);">(${{a.app_name}})</span></td>
                    <td><span style="background: var(--bg-subtle); padding: 2px 8px; border-radius: 4px; font-size: 11px;">${{a.category}}</span></td>
                    <td class="num-cell" style="font-weight: 600;">${{formatDuration(a.duration_sec)}}</td>
                </tr>
            `).join('');
        }}

        // --- EXPORT DOWNLOAD HELPERS ---
        async function downloadBlob(url, filename) {{
            const token = sessionStorage.getItem('adminToken');
            const res = await fetch(url, {{ headers: {{ 'X-Admin-Token': token }} }});
            if (res.ok) {{
                const blob = await res.blob();
                const a = document.createElement('a');
                a.href = window.URL.createObjectURL(blob);
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
            }} else {{
                alert("Unauthorized or export error. Please re-login.");
                checkAuth();
            }}
        }}

        function exportFilteredExcel() {{
            const empId = document.getElementById('filterEmployeeSelect').value;
            const sDate = document.getElementById('filterStartDate').value;
            const eDate = document.getElementById('filterEndDate').value;
            const status = document.getElementById('filterStatusSelect').value;

            let url = `/api/export/excel?status=${{status}}`;
            if (empId) url += `&employee_id=${{empId}}`;
            if (sDate) url += `&start_date=${{sDate}}`;
            if (eDate) url += `&end_date=${{eDate}}`;

            downloadBlob(url, 'Office_Timesheet_Report.xlsx');
        }}

        function exportFilteredCSV() {{
            downloadBlob('/api/export/csv', 'Office_Activity_Report.csv');
        }}

        function exportDailyReportExcel() {{
            const dateStr = document.getElementById('dailyReportDatePicker').value;
            if (!dateStr) return;
            downloadBlob(`/api/admin/export/daily?date=${{dateStr}}`, `Daily_Report_${{dateStr}}.xlsx`);
        }}

        function exportMonthlyReportExcel() {{
            const monthStr = document.getElementById('monthlyReportMonthPicker').value;
            if (!monthStr) return;
            const [year, month] = monthStr.split('-').map(Number);
            downloadBlob(`/api/admin/export/monthly?year=${{year}}&month=${{month}}`, `Monthly_Report_${{monthStr}}.xlsx`);
        }}

        // --- ADD EMPLOYEE MODAL CONTROLS ---
        function openAddEmployeeModal() {{
            document.getElementById('modalEmpName').value = '';
            document.getElementById('modalEmpCode').value = '';
            document.getElementById('modalEmpPin').value = '1234';
            document.getElementById('modalEmpShiftStart').value = '09:30';
            document.getElementById('modalEmpShiftEnd').value = '18:00';
            document.getElementById('modalEmpThreshold').value = '300';
            document.getElementById('modalEmpAutoStart').checked = true;
            document.getElementById('modalAddEmpError').style.display = 'none';
            document.getElementById('addEmployeeModal').style.display = 'flex';
        }}

        function closeAddEmployeeModal() {{
            document.getElementById('addEmployeeModal').style.display = 'none';
        }}

        async function submitModalNewEmployee() {{
            const name = document.getElementById('modalEmpName').value.trim();
            const code = document.getElementById('modalEmpCode').value.trim();
            const pin = document.getElementById('modalEmpPin').value.trim() || '1234';
            const shift_start = document.getElementById('modalEmpShiftStart').value;
            const shift_end = document.getElementById('modalEmpShiftEnd').value;
            const idle_threshold = parseInt(document.getElementById('modalEmpThreshold').value, 10);
            const is_auto_start = document.getElementById('modalEmpAutoStart').checked;
            const errDiv = document.getElementById('modalAddEmpError');

            if (!name || !code) {{
                errDiv.innerText = "Please provide both Full Name and Employee Code.";
                errDiv.style.display = 'block';
                return;
            }}

            try {{
                const res = await adminFetch('/api/admin/employees', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name, code, pin, shift_start, shift_end, is_auto_start, idle_threshold }})
                }});

                if (res && res.ok) {{
                    closeAddEmployeeModal();
                    alert(`Employee "${{name}}" (${{code}}) successfully registered!`);
                    loadEmployeesDropdown();
                    loadShiftsData();
                    applyTimesheetFilters();
                }} else if (res) {{
                    const data = await res.json();
                    errDiv.innerText = data.detail || "Error adding employee. Check for duplicate code.";
                    errDiv.style.display = 'block';
                }}
            }} catch (e) {{
                errDiv.innerText = "Network error. Please try again.";
                errDiv.style.display = 'block';
            }}
        }}

        checkAuth();
    </script>
</body>
</html>
"""

# ==============================================================================
# FASTAPI ROUTE HANDLERS
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_employee_view():
    return EMPLOYEE_HTML_PAGE

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_portal():
    token = create_admin_token("admin")
    ACTIVE_ADMIN_TOKENS.add(token)
    resp = HTMLResponse(content=ADMIN_HTML_PAGE)
    resp.set_cookie(key="admin_token", value=token, max_age=3153600000, httponly=False, samesite="lax")
    return resp

# --- Employee Authentication & Persistent Session Endpoints ---
@app.get("/api/employee/roster")
async def api_employee_roster():
    """Returns active registered employees for quick account selection."""
    emps = database.get_all_employees()
    return [{"id": e["id"], "name": e["name"], "employee_code": e["employee_code"]} for e in emps]

@app.post("/api/employee/auth")
async def api_employee_auth(req: EmployeeAuthRequest):
    emp = database.verify_employee_credentials(req.code, req.pin)
    if not emp:
        raise HTTPException(status_code=401, detail="Invalid Employee Code or PIN.")
    database.set_authenticated_employee(emp["id"])
    with engine_lock:
        assigned_threshold = emp.get("idle_threshold", 300)
        global_engine.set_idle_threshold(assigned_threshold)
        if global_engine.state != TrackerState.LOGGED_OUT:
            global_engine.end_day(manual=True)
    return {"status": "ok", "employee": emp}

@app.get("/api/employee/me")
async def api_employee_me(employee_id: Optional[int] = Query(None)):
    if employee_id:
        shift = database.get_employee_shift(employee_id)
        emps = database.get_all_employees()
        found = next((e for e in emps if e["id"] == employee_id), None)
        if found:
            res = dict(found)
            res.update(shift)
            return res
    auth_emp = database.get_authenticated_employee()
    if auth_emp:
        return auth_emp
    raise HTTPException(status_code=404, detail="No authenticated employee")

@app.post("/api/employee/logout")
async def api_employee_logout():
    """Unlinks workstation and ends active session for account switching."""
    database.clear_authenticated_employee()
    with engine_lock:
        if global_engine.state != TrackerState.LOGGED_OUT:
            global_engine.end_day(manual=True)
        latest_stats["login_time"] = "--:--"
    return {"status": "ok", "message": "Logged out and workstation unassigned"}

@app.get("/api/live-status")
async def api_live_status():
    with engine_lock:
        state_str = global_engine.state.value
        is_active = global_engine.state != TrackerState.LOGGED_OUT
        intervals = []
        app_usage = []
        web_usage = []
        if is_active and global_engine.session_id:
            intervals = database.get_session_intervals(global_engine.session_id)
            app_usage = database.get_session_app_usage(global_engine.session_id)
            web_usage = database.get_session_website_usage(global_engine.session_id)

        data = {
            "state": state_str,
            "threshold": global_engine.idle_threshold,
            "idle_seconds": int(get_idle_seconds()) if is_active else 0,
            "total_active": global_engine.total_active_sec if is_active else 0,
            "total_inactive": global_engine.total_inactive_sec if is_active else 0,
            "total_lunch": global_engine.total_lunch_sec if is_active else 0,
            "total_overtime": global_engine.total_overtime_sec if is_active else 0,
            "intervals": intervals,
            "app_usage": app_usage,
            "website_usage": web_usage,
            "login_time": global_engine.session_start_datetime.strftime("%I:%M:%S %p") if (is_active and global_engine.session_start_datetime) else (latest_stats.get("login_time", "--:--") if is_active else "--:--")
        }
    return data

@app.post("/api/clock-in")
async def api_clock_in(req: ClockInRequest):
    with engine_lock:
        emp_id = req.employee_id
        shift = database.get_employee_shift(emp_id)
        threshold = shift.get("idle_threshold", 300)
        global_engine.set_idle_threshold(threshold)
        global_engine.start_day(emp_id)
        latest_stats["login_time"] = datetime.now().strftime("%I:%M:%S %p")
    return {"status": "ok", "employee_id": emp_id, "session_id": global_engine.session_id}

@app.post("/api/lunch")
async def api_toggle_lunch():
    with engine_lock:
        if global_engine.state == TrackerState.LUNCH:
            global_engine.resume_from_lunch()
        else:
            global_engine.start_lunch()
    return {"status": "ok", "state": global_engine.state.value}

@app.post("/api/clock-out")
async def api_clock_out():
    with engine_lock:
        global_engine.end_day(manual=True)
        latest_stats["login_time"] = "--:--"
    return {"status": "ok", "state": "Logged Out"}

# --- Admin Authentication Endpoints ---
@app.post("/api/admin/login")
async def api_admin_login(req: AdminLoginRequest, response: Response):
    valid = database.verify_admin_credentials(req.username, req.password)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid administrator credentials.")

    token = create_admin_token(req.username)
    ACTIVE_ADMIN_TOKENS.add(token)
    response.set_cookie(key="admin_token", value=token, httponly=True)
    return {"status": "ok", "token": token, "username": req.username}

@app.post("/api/admin/logout")
async def api_admin_logout(token: str = Depends(verify_admin_token), response: Response = None):
    ACTIVE_ADMIN_TOKENS.discard(token)
    if response:
        response.delete_cookie(key="admin_token")
    return {"status": "ok", "message": "Logged out"}

# --- Admin Management Endpoints ---
@app.get("/api/admin/employees")
async def api_get_admin_employees(token: str = Depends(verify_admin_token)):
    return database.get_all_employees()

@app.post("/api/admin/employees")
async def api_add_admin_employee(req: AddEmployeeRequest, token: str = Depends(verify_admin_token)):
    try:
        emp_id = database.add_employee(
            req.name, req.code, req.pin, req.shift_start, req.shift_end, req.is_auto_start, req.idle_threshold
        )
        return {"status": "ok", "employee_id": emp_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/employees/{employee_id}/shift")
async def api_update_employee_shift(employee_id: int, req: EmployeeShiftUpdateRequest, token: str = Depends(verify_admin_token)):
    success = database.update_employee_shift(
        employee_id, req.start_time, req.end_time, req.is_auto_start, req.idle_threshold, req.new_pin
    )
    if not success:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"status": "ok", "message": "Shift updated"}

@app.post("/api/admin/shifts/bulk-update")
async def api_bulk_update_shifts(req: BulkShiftUpdateRequest, token: str = Depends(verify_admin_token)):
    database.update_all_employee_shifts(req.shift_start, req.shift_end)
    return {"status": "ok", "message": "All employee shift timings updated"}

@app.delete("/api/admin/employees/{employee_id}")
async def api_delete_employee(employee_id: int, token: str = Depends(verify_admin_token)):
    success = database.delete_employee(employee_id)
    if not success:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"status": "ok", "message": "Employee deleted"}

@app.post("/api/admin/clear-sessions")
async def api_clear_sessions(token: str = Depends(verify_admin_token)):
    database.clear_all_sessions()
    return {"status": "ok", "message": "All timesheet and website logs cleared"}

@app.get("/api/admin/sessions")
async def api_get_admin_sessions(
    employee_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    token: str = Depends(verify_admin_token)
):
    return database.get_filtered_sessions(employee_id, start_date, end_date, status)

@app.get("/api/admin/employee-profile/{employee_id}")
async def api_get_employee_profile(employee_id: int, token: str = Depends(verify_admin_token)):
    profile = database.get_employee_profile(employee_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Employee not found")
    return profile

@app.get("/api/admin/daily-report")
async def api_get_daily_report(date: Optional[str] = Query(None), token: str = Depends(verify_admin_token)):
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    return database.get_daily_report(date_str)

@app.get("/api/admin/monthly-report")
async def api_get_monthly_report(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    token: str = Depends(verify_admin_token)
):
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    return database.get_monthly_report(y, m)

@app.get("/api/admin/websites")
async def api_get_admin_websites(token: str = Depends(verify_admin_token)):
    return database.get_all_website_usage(200)

@app.get("/api/admin/browser-usage")
async def api_get_admin_browser_usage(token: str = Depends(verify_admin_token)):
    return database.get_all_browser_usage(200)

@app.get("/api/admin/web-analytics")
async def api_get_admin_web_analytics(token: str = Depends(verify_admin_token)):
    return database.get_browser_website_analytics()

@app.get("/api/admin/apps-usage")
async def api_get_admin_apps_usage(token: str = Depends(verify_admin_token)):
    return database.get_all_apps_usage(200)

# --- Excel & CSV Report Downloads ---
@app.get("/api/export/excel")
async def api_export_excel(
    employee_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    token: str = Depends(verify_admin_token)
):
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Office_Timesheet_Report.xlsx")
    exporter.export_to_excel(output_path, employee_id, start_date, end_date, status)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Office_Timesheet_Report.xlsx"
    )

@app.get("/api/export/csv")
async def api_export_csv(token: str = Depends(verify_admin_token)):
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Office_Activity_Report.csv")
    exporter.export_to_csv(output_path)
    return FileResponse(
        output_path,
        media_type="text/csv",
        filename="Office_Activity_Report.csv"
    )

@app.get("/api/admin/export/daily")
async def api_export_daily_excel(date: str = Query(...), token: str = Depends(verify_admin_token)):
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"Daily_Report_{date}.xlsx")
    exporter.export_daily_report_to_excel(date, output_path)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Daily_Report_{date}.xlsx"
    )

@app.get("/api/admin/export/monthly")
async def api_export_monthly_excel(
    year: int = Query(...),
    month: int = Query(...),
    token: str = Depends(verify_admin_token)
):
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"Monthly_Report_{year:04d}_{month:02d}.xlsx")
    exporter.export_monthly_report_to_excel(year, month, output_path)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Monthly_Report_{year:04d}_{month:02d}.xlsx"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
