import ctypes
import time
import re
from datetime import datetime, timedelta, date, time as dtime
from enum import Enum
from typing import Optional, Callable, Dict, Any
import win32gui
import win32process
import win32service
import win32con
import psutil
import database

def attach_to_interactive_desktop():
    """Ensures the calling thread is attached to the user's interactive Windows desktop ('Default')."""
    try:
        hdesk = win32service.OpenDesktop("Default", 0, False, win32con.GENERIC_ALL)
        if hdesk:
            ctypes.windll.user32.SetThreadDesktop(int(hdesk))
    except Exception:
        pass

BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe", "vivaldi.exe"
}

def extract_website_domain(proc_name: str, window_title: str) -> Optional[str]:
    """Extracts website domain or clean site name from active browser window."""
    if proc_name.lower() not in BROWSER_PROCESSES:
        return None

    # 1. Check window title for clean domain match (e.g., github.com, youtube.com)
    cleaned = re.sub(
        r'(\s+-\s+(Google Chrome|Microsoft Edge|Brave|Opera|Vivaldi)|\s+—\s+Mozilla Firefox)$',
        '', window_title, flags=re.IGNORECASE
    )

    domain_match = re.search(r'\b([a-z0-9-]+\.(?:com|org|net|io|co|in|ai|app|dev|edu|gov|so))\b', cleaned, re.IGNORECASE)
    if domain_match:
        return domain_match.group(1).lower()

    # 2. Known popular web tools & services by keyword in title
    title_lower = cleaned.lower()
    known_services = {
        "youtube": "youtube.com",
        "gmail": "mail.google.com",
        "google docs": "docs.google.com",
        "google sheets": "sheets.google.com",
        "google drive": "drive.google.com",
        "github": "github.com",
        "figma": "figma.com",
        "notion": "notion.so",
        "slack": "slack.com",
        "linkedin": "linkedin.com",
        "stackoverflow": "stackoverflow.com",
        "trello": "trello.com",
        "jira": "atlassian.net",
        "chatgpt": "chatgpt.com",
        "canva": "canva.com",
        "zoom": "zoom.us",
        "reddit": "reddit.com",
        "twitter": "x.com",
        "facebook": "facebook.com",
        "instagram": "instagram.com"
    }
    for kw, dom in known_services.items():
        if kw in title_lower:
            return dom

    # 3. Fallback: Parse trailing or leading site name (e.g., "Page Title - SiteName")
    parts = re.split(r'\s+[-–|•:]\s+', cleaned)
    if len(parts) > 1:
        candidate = (parts[-1].strip() or parts[0].strip()).lower()
        if len(candidate) < 25 and not any(char in candidate for char in ['/', '\\', 'http']):
            return f"{candidate}.com"

    return "web-browsing"

class TrackerState(Enum):
    LOGGED_OUT = "Logged Out"
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    LUNCH = "Lunch Break"

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('dwTime', ctypes.c_uint)
    ]

def get_idle_seconds() -> float:
    """Returns number of seconds since the last system-wide keyboard or mouse input."""
    attach_to_interactive_desktop()
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        current_tick = ctypes.windll.kernel32.GetTickCount()
        # Handle 32-bit unsigned wrap-around
        idle_ms = (current_tick - lii.dwTime) & 0xFFFFFFFF
        return idle_ms / 1000.0
    return 0.0

def get_active_app_info() -> Dict[str, str]:
    """Detects the foreground active window and application name in Windows."""
    attach_to_interactive_desktop()
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return {"app": "Desktop/Idle", "title": "Windows Desktop"}
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return {"app": proc.name(), "title": title or proc.name()}
    except Exception:
        return {"app": "System", "title": "Unknown"}

class TrackerEngine:
    def __init__(self, idle_threshold_seconds: int = 300):
        self.idle_threshold = idle_threshold_seconds # Default 5 minutes
        self.state = TrackerState.LOGGED_OUT
        self.session_id: Optional[int] = None
        self.employee_id: Optional[int] = None
        # Cumulative totals for current session (in seconds)
        self.total_active_sec = 0
        self.total_inactive_sec = 0
        self.total_lunch_sec = 0

        # Current foreground app & website info
        self.current_app_name: str = "System"
        self.current_window_title: str = ""
        self.current_website_domain: Optional[str] = None

        # Current interval details
        self.current_interval_type: Optional[str] = None
        self.current_interval_start: Optional[datetime] = None

        # Callbacks for UI updates
        self.on_state_change: Optional[Callable[[TrackerState], None]] = None
        self.on_tick: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_interval_logged: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_idle_threshold(self, seconds: int):
        self.idle_threshold = max(5, seconds)

    def start_day(self, employee_id: int):
        """Clock In: Starts a new day session."""
        if self.state != TrackerState.LOGGED_OUT:
            return

        self.employee_id = employee_id
        self.session_id = database.create_session(employee_id)
        
        now = datetime.now()
        self.total_active_sec = 0
        self.total_inactive_sec = 0
        self.total_lunch_sec = 0

        # Current foreground app & website info
        self.current_app_name: str = "System"
        self.current_window_title: str = ""
        self.current_website_domain: Optional[str] = None

        self.state = TrackerState.ACTIVE
        self.current_interval_type = "ACTIVE"
        self.current_interval_start = now

        if self.on_state_change:
            self.on_state_change(self.state)

    def start_lunch(self):
        """User toggles lunch break."""
        if self.state not in [TrackerState.ACTIVE, TrackerState.INACTIVE]:
            return

        now = datetime.now()
        # Close the running interval (active or inactive)
        self._commit_current_interval(now)

        # Transition to LUNCH
        self.state = TrackerState.LUNCH
        self.current_interval_type = "LUNCH"
        self.current_interval_start = now

        if self.on_state_change:
            self.on_state_change(self.state)

    def resume_from_lunch(self):
        """User returns from lunch."""
        if self.state != TrackerState.LUNCH:
            return

        now = datetime.now()
        # Close the lunch interval
        self._commit_current_interval(now)

        # Transition to ACTIVE
        self.state = TrackerState.ACTIVE
        self.current_interval_type = "ACTIVE"
        self.current_interval_start = now

        if self.on_state_change:
            self.on_state_change(self.state)

    def end_day(self):
        """Clock Out: Ends the current workday."""
        if self.state == TrackerState.LOGGED_OUT:
            return

        now = datetime.now()
        # Commit the active/lunch/inactive interval that was running
        self._commit_current_interval(now)

        # Close session in DB
        if self.session_id:
            database.close_session(
                self.session_id,
                int(self.total_active_sec),
                int(self.total_inactive_sec),
                int(self.total_lunch_sec)
            )

        self.state = TrackerState.LOGGED_OUT
        self.session_id = None
        self.total_active_sec = 0
        self.total_inactive_sec = 0
        self.total_lunch_sec = 0
        self.current_interval_type = None
        self.current_interval_start = None

        if self.on_state_change:
            self.on_state_change(self.state)

    def _commit_current_interval(self, end_time: datetime, note: str = ""):
        """Helper to save the finished interval into DB and fire callback."""
        if not self.session_id or not self.current_interval_start or not self.current_interval_type:
            return

        duration_sec = int((end_time - self.current_interval_start).total_seconds())
        if duration_sec < 0:
            duration_sec = 0

        start_str = self.current_interval_start.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")

        # Save to database
        interval_id = database.save_interval(
            self.session_id,
            self.current_interval_type,
            start_str,
            end_str,
            duration_sec,
            note
        )

        log_data = {
            "id": interval_id,
            "event_type": self.current_interval_type,
            "start_time": start_str,
            "end_time": end_str,
            "duration_sec": duration_sec,
            "note": note
        }

        if self.on_interval_logged:
            self.on_interval_logged(log_data)

    def tick(self):
        """Called once every second by the UI timer loop."""
        if self.state == TrackerState.LOGGED_OUT:
            return

        idle_sec = get_idle_seconds()
        now = datetime.now()

        if self.state == TrackerState.ACTIVE:
            # Detect currently active application & window
            app_info = get_active_app_info()
            self.current_app_name = app_info["app"]
            self.current_window_title = app_info["title"]
            if self.session_id:
                database.record_app_usage(self.session_id, self.current_app_name, 1)

                # Extract and record website domain if browser
                domain = extract_website_domain(self.current_app_name, self.current_window_title)
                self.current_website_domain = domain
                if domain:
                    database.record_website_usage(self.session_id, domain, 1)
            else:
                self.current_website_domain = None

            if idle_sec >= self.idle_threshold:
                # User has been idle for >= threshold!
                # Calculate the exact moment inactivity started
                inactive_start = now - timedelta(seconds=idle_sec)
                if inactive_start < self.current_interval_start:
                    inactive_start = self.current_interval_start

                # 1. Close the active interval up to the exact moment inactivity began
                self._commit_current_interval(inactive_start)

                # 2. Start INACTIVE interval from that exact timestamp
                self.state = TrackerState.INACTIVE
                self.current_interval_type = "INACTIVE"
                self.current_interval_start = inactive_start

                # Recalculate totals
                self._recalculate_totals_from_intervals()

                if self.on_state_change:
                    self.on_state_change(self.state)
            else:
                self.total_active_sec += 1

        elif self.state == TrackerState.INACTIVE:
            if idle_sec < 2.0:
                # User returned and moved mouse/pressed key!
                inactive_end = now

                # 1. Close the inactive interval
                self._commit_current_interval(inactive_end)

                # 2. Resume ACTIVE interval
                self.state = TrackerState.ACTIVE
                self.current_interval_type = "ACTIVE"
                self.current_interval_start = inactive_end

                self._recalculate_totals_from_intervals()

                if self.on_state_change:
                    self.on_state_change(self.state)
            else:
                self.total_inactive_sec += 1

        elif self.state == TrackerState.LUNCH:
            self.total_lunch_sec += 1

        # Emit tick stats to UI
        if self.on_tick:
            self.on_tick({
                "state": self.state.value,
                "idle_seconds": int(idle_sec),
                "total_active": int(self.total_active_sec),
                "total_inactive": int(self.total_inactive_sec),
                "total_lunch": int(self.total_lunch_sec),
                "total_span": int(self.total_active_sec + self.total_inactive_sec + self.total_lunch_sec),
                "active_app": self.current_app_name,
                "window_title": self.current_window_title,
                "active_domain": self.current_website_domain
            })

    def check_shift_window(self, emp_id: int):
        """Checks individual employee's admin shift schedule and automatically activates or ends work session."""
        try:
            cfg = database.get_employee_shift(emp_id)
            if not cfg or not cfg.get("is_auto_start"):
                return

            now = datetime.now()
            now_time = now.time()
            today_date = now.date()

            start_parts = [int(p) for p in cfg["shift_start"].split(":")]
            end_parts = [int(p) for p in cfg["shift_end"].split(":")]

            shift_start = dtime(start_parts[0], start_parts[1])
            shift_end = dtime(end_parts[0], end_parts[1])

            # Determine whether now is within the scheduled shift window
            is_overnight = shift_start > shift_end
            if is_overnight:
                in_shift = (now_time >= shift_start or now_time < shift_end)
            else:
                in_shift = (shift_start <= now_time < shift_end)

            if in_shift:
                # In shift window: Auto-start if logged out and not manually clocked out today
                if self.state == TrackerState.LOGGED_OUT:
                    if self.manual_clock_out_date != today_date:
                        self.start_day(emp_id, is_auto=True)
            else:
                # Outside shift window: Auto-end ONLY IF the current session was started
                # while within shift hours (i.e. shift reached its scheduled conclusion).
                # If the employee started manually outside shift hours (overtime/testing), do NOT auto-end!
                if self.state in [TrackerState.ACTIVE, TrackerState.INACTIVE]:
                    if self.is_session_started_in_shift:
                        self.end_day(manual=False)
        except Exception as e:
            pass

    def _recalculate_totals_from_intervals(self):
        """Accurately re-sums committed intervals to prevent drift."""
        if not self.session_id:
            return
        intervals = database.get_session_intervals(self.session_id)
        active = sum(item["duration_sec"] for item in intervals if item["event_type"] == "ACTIVE")
        inactive = sum(item["duration_sec"] for item in intervals if item["event_type"] == "INACTIVE")
        lunch = sum(item["duration_sec"] for item in intervals if item["event_type"] == "LUNCH")
        
        self.total_active_sec = active
        self.total_inactive_sec = inactive
        self.total_lunch_sec = lunch
