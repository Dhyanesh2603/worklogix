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

BROWSER_FRIENDLY_NAMES = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "brave.exe": "Brave Browser",
    "firefox.exe": "Mozilla Firefox",
    "opera.exe": "Opera",
    "opera_gx.exe": "Opera GX",
    "vivaldi.exe": "Vivaldi",
    "arc.exe": "Arc Browser",
    "safari.exe": "Apple Safari",
    "iexplore.exe": "Internet Explorer"
}

BROWSER_PROCESSES = set(BROWSER_FRIENDLY_NAMES.keys())

APPLICATION_CATALOG = {
    # Browsers
    "chrome.exe": ("Google Chrome", "Web Browser"),
    "msedge.exe": ("Microsoft Edge", "Web Browser"),
    "brave.exe": ("Brave Browser", "Web Browser"),
    "firefox.exe": ("Mozilla Firefox", "Web Browser"),
    "opera.exe": ("Opera", "Web Browser"),
    "opera_gx.exe": ("Opera GX", "Web Browser"),
    "vivaldi.exe": ("Vivaldi", "Web Browser"),
    "arc.exe": ("Arc Browser", "Web Browser"),
    # Development
    "code.exe": ("Visual Studio Code", "Development"),
    "devenv.exe": ("Visual Studio", "Development"),
    "pycharm64.exe": ("PyCharm", "Development"),
    "idea64.exe": ("IntelliJ IDEA", "Development"),
    "windowsterminal.exe": ("Windows Terminal", "Development"),
    "powershell.exe": ("PowerShell", "Development"),
    "cmd.exe": ("Command Prompt", "Development"),
    "git-bash.exe": ("Git Bash", "Development"),
    "dbeaver.exe": ("DBeaver", "Database"),
    "postman.exe": ("Postman", "Development"),
    # Productivity & Office
    "excel.exe": ("Microsoft Excel", "Office"),
    "winword.exe": ("Microsoft Word", "Office"),
    "powerpnt.exe": ("Microsoft PowerPoint", "Office"),
    "onenote.exe": ("Microsoft OneNote", "Office"),
    "outlook.exe": ("Microsoft Outlook", "Office"),
    "notion.exe": ("Notion", "Productivity"),
    "slack.exe": ("Slack", "Communication"),
    "teams.exe": ("Microsoft Teams", "Communication"),
    "zoom.exe": ("Zoom", "Communication"),
    "discord.exe": ("Discord", "Communication"),
    "figma.exe": ("Figma", "Design"),
    "canva.exe": ("Canva", "Design"),
    "explorer.exe": ("Windows File Explorer", "System"),
    "officetracker.exe": ("Office Work Tracker", "Productivity"),
    "antigravity.exe": ("Antigravity IDE", "Development"),
}

def get_browser_friendly_name(proc_name: str) -> Optional[str]:
    """Returns clean human-readable browser name, or None if not a recognized browser."""
    return BROWSER_FRIENDLY_NAMES.get(proc_name.lower())

def get_app_display_info(proc_name: str) -> Dict[str, str]:
    """Returns friendly application name and category."""
    lower = proc_name.lower()
    if lower in APPLICATION_CATALOG:
        friendly, cat = APPLICATION_CATALOG[lower]
        return {"app": proc_name, "friendly_name": friendly, "category": cat}
    import os
    base = os.path.splitext(proc_name)[0]
    return {"app": proc_name, "friendly_name": base.capitalize(), "category": "General Application"}

def extract_website_domain(proc_name: str, window_title: str) -> Optional[str]:
    """
    Extracts website domain or clean site name from active browser window.
    Returns None if the application is not a recognized web browser.
    """
    if proc_name.lower() not in BROWSER_PROCESSES:
        return None

    if not window_title or window_title.strip() == "":
        return "web-browsing"

    # 1. Clean browser suffix from title
    cleaned = re.sub(
        r'(\s+-\s+(Google Chrome|Microsoft Edge|Brave|Opera GX|Opera|Vivaldi|Arc)|\s+—\s+Mozilla Firefox)$',
        '', window_title, flags=re.IGNORECASE
    ).strip()

    title_lower = cleaned.lower()

    # Browser internal/new tab pages
    if title_lower in ["new tab", "untitled", "speed dial", "start page"]:
        return "new-tab"
    if title_lower.startswith("settings") or "chrome://settings" in title_lower or "edge://settings" in title_lower:
        return "browser-settings"
    if title_lower.startswith("downloads") or "chrome://downloads" in title_lower:
        return "browser-downloads"
    if title_lower.startswith("extensions") or "chrome://extensions" in title_lower:
        return "browser-extensions"

    # 2. Known popular web tools & services by keyword in title (priority over email addresses / titles)
    known_services = [
        # Google Services & Email
        (r'\bgmail\b', 'mail.google.com'),
        (r'\bgoogle docs\b', 'docs.google.com'),
        (r'\bgoogle sheets\b', 'sheets.google.com'),
        (r'\bgoogle slides\b', 'slides.google.com'),
        (r'\bgoogle drive\b', 'drive.google.com'),
        (r'\bgoogle meet\b|\bmeet\s*[-:]', 'meet.google.com'),
        (r'\bgoogle calendar\b', 'calendar.google.com'),
        (r'\bgoogle search\b|\bgoogle\b', 'google.com'),

        # AI & Chatbots
        (r'\bchatgpt\b', 'chatgpt.com'),
        (r'\bclaude\b', 'claude.ai'),
        (r'\bgemini\b', 'gemini.google.com'),
        (r'\bcopilot\b', 'copilot.microsoft.com'),
        (r'\bperplexity\b', 'perplexity.ai'),
        (r'\bdeepseek\b', 'deepseek.com'),
        (r'\bpoe\b', 'poe.com'),

        # Developer & Technical
        (r'\bgithub\b', 'github.com'),
        (r'\bgitlab\b', 'gitlab.com'),
        (r'\bbitbucket\b', 'bitbucket.org'),
        (r'\bstack overflow\b|\bstackoverflow\b', 'stackoverflow.com'),
        (r'\bleetcode\b', 'leetcode.com'),
        (r'\bhackerrank\b', 'hackerrank.com'),
        (r'\bgeeksforgeeks\b', 'geeksforgeeks.org'),
        (r'\bw3schools\b', 'w3schools.com'),
        (r'\bmdn\b|developer\.mozilla', 'developer.mozilla.org'),
        (r'\bhugging\s*face\b', 'huggingface.co'),
        (r'\bfigma\b', 'figma.com'),
        (r'\bcanva\b', 'canva.com'),
        (r'\bnotion\b', 'notion.so'),
        (r'\btrello\b', 'trello.com'),
        (r'\bjira\b|\batlassian\b', 'atlassian.net'),
        (r'\basana\b', 'asana.com'),
        (r'\blinear\b', 'linear.app'),
        (r'\bclickup\b', 'clickup.com'),
        (r'\bsupabase\b', 'supabase.com'),
        (r'\bvercel\b', 'vercel.com'),
        (r'\bfirebase\b', 'firebase.google.com'),
        (r'\baws\b|amazon web services', 'aws.amazon.com'),
        (r'\bazure\b', 'portal.azure.com'),

        # Communication & Social
        (r'\bwhatsapp\b', 'web.whatsapp.com'),
        (r'\btelegram\b', 'web.telegram.org'),
        (r'\bdiscord\b', 'discord.com'),
        (r'\bslack\b', 'slack.com'),
        (r'\bteams\b|microsoft teams', 'teams.microsoft.com'),
        (r'\boutlook\b|office 365|microsoft 365', 'outlook.office.com'),
        (r'\bzoom\b', 'zoom.us'),
        (r'\blinkedin\b', 'linkedin.com'),
        (r'\byoutube\b', 'youtube.com'),
        (r'\breddit\b', 'reddit.com'),
        (r'\bfacebook\b', 'facebook.com'),
        (r'\binstagram\b', 'instagram.com'),
        (r'\btwitter\b|\b\s*/\s*x\b', 'x.com'),

        # Knowledge, Media & Shopping
        (r'\bwikipedia\b', 'wikipedia.org'),
        (r'\bmedium\b', 'medium.com'),
        (r'\bnetflix\b', 'netflix.com'),
        (r'\bspotify\b', 'spotify.com'),
        (r'\bamazon\b', 'amazon.com'),
        (r'\bflipkart\b', 'flipkart.com'),
    ]

    for pattern, dom in known_services:
        if re.search(pattern, title_lower):
            return dom

    # 3. Check for explicit domain in title (excluding email addresses like user@domain.com)
    domain_match = re.search(r'(?<!@)\b([a-z0-9-]+\.(?:com|org|net|io|co|in|ai|app|dev|edu|gov|so|me|xyz|tech|tv|info))\b', cleaned, re.IGNORECASE)
    if domain_match:
        return domain_match.group(1).lower()

    # 4. Fallback: Parse trailing or leading site name (e.g. "Page Title - SiteName" or "Page Title | SiteName")
    parts = re.split(r'\s+[-–|•:]\s+', cleaned)
    if len(parts) > 1:
        for candidate in [parts[-1].strip(), parts[0].strip()]:
            c_low = candidate.lower()
            if 2 <= len(c_low) <= 25 and not any(char in c_low for char in ['/', '\\', 'http', '@', '.']):
                clean_candidate = re.sub(r'[^a-z0-9-]', '', c_low)
                if len(clean_candidate) >= 3:
                    return f"{clean_candidate}.com"

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
        self.session_start_datetime: Optional[datetime] = None
        self.is_session_started_in_shift: bool = False
        self.manual_clock_out_date: Optional[date] = None
        self.shift_completed_date: Optional[date] = None

        # Cumulative totals for current session (in seconds)
        self.total_active_sec = 0
        self.total_inactive_sec = 0
        self.total_lunch_sec = 0
        self.total_overtime_sec = 0

        # Calculate scheduled shift duration in seconds
        try:
            cfg = database.get_employee_shift(employee_id)
            if cfg and "shift_start" in cfg and "shift_end" in cfg:
                s_parts = [int(p) for p in cfg["shift_start"].split(":")]
                e_parts = [int(p) for p in cfg["shift_end"].split(":")]
                s_min = s_parts[0] * 60 + s_parts[1]
                e_min = e_parts[0] * 60 + e_parts[1]
                if e_min < s_min:
                    self.scheduled_shift_sec = ((24 * 60 - s_min) + e_min) * 60
                else:
                    self.scheduled_shift_sec = (e_min - s_min) * 60
            else:
                self.scheduled_shift_sec = 8 * 3600
        except Exception:
            self.scheduled_shift_sec = 8 * 3600
        self.total_overtime_sec = 0
        self.scheduled_shift_sec = 0

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

    def start_day(self, employee_id: int, is_auto: bool = False):
        """Clock In: Starts a new day session."""
        if self.state != TrackerState.LOGGED_OUT:
            return

        self.employee_id = employee_id
        self.session_id = database.create_session(employee_id)
        
        now = datetime.now()
        self.session_start_datetime = now
        if not is_auto:
            self.manual_clock_out_date = None

        # Detect whether this session started within the scheduled shift
        try:
            cfg = database.get_employee_shift(employee_id)
            if cfg and "shift_start" in cfg and "shift_end" in cfg:
                s_parts = [int(p) for p in cfg["shift_start"].split(":")]
                e_parts = [int(p) for p in cfg["shift_end"].split(":")]
                s_time = dtime(s_parts[0], s_parts[1])
                e_time = dtime(e_parts[0], e_parts[1])
                now_t = now.time()
                if s_time > e_time:
                    self.is_session_started_in_shift = (now_t >= s_time or now_t < e_time)
                else:
                    self.is_session_started_in_shift = (s_time <= now_t < e_time)
            else:
                self.is_session_started_in_shift = False
        except Exception:
            self.is_session_started_in_shift = False

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

    def end_day(self, manual: bool = False):
        """Clock Out: Ends the current workday."""
        if self.state == TrackerState.LOGGED_OUT:
            return

        today = datetime.now().date()
        self.manual_clock_out_date = today
        self.shift_completed_date = today

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
        self.session_start_datetime = None
        self.is_session_started_in_shift = False
        self.total_active_sec = 0
        self.total_inactive_sec = 0
        self.total_lunch_sec = 0
        self.total_overtime_sec = 0
        self.scheduled_shift_sec = 0
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

        # Prolonged inactivity exit: if idle for >= 20 minutes (1200 seconds) while in active or inactive state,
        # automatically clock out and finalize the work session.
        if idle_sec >= 1200:
            if self.state in [TrackerState.ACTIVE, TrackerState.INACTIVE]:
                self.end_day(manual=False)
                return

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

        # Calculate overtime if active time exceeds scheduled shift hours
        if self.scheduled_shift_sec > 0 and self.total_active_sec > self.scheduled_shift_sec:
            self.total_overtime_sec = int(self.total_active_sec - self.scheduled_shift_sec)
        else:
            self.total_overtime_sec = 0

        # Emit tick stats to UI
        if self.on_tick:
            self.on_tick({
                "state": self.state.value,
                "idle_seconds": int(idle_sec),
                "total_active": int(self.total_active_sec),
                "total_inactive": int(self.total_inactive_sec),
                "total_lunch": int(self.total_lunch_sec),
                "total_overtime": int(self.total_overtime_sec),
                "total_span": int(self.total_active_sec + self.total_inactive_sec + self.total_lunch_sec),
                "active_app": self.current_app_name,
                "active_browser": get_browser_friendly_name(self.current_app_name),
                "window_title": self.current_window_title,
                "active_domain": self.current_website_domain
            })

    def check_shift_window(self, emp_id: int):
        """Checks individual employee's admin shift schedule and automatically activates work session once per day."""
        try:
            cfg = database.get_employee_shift(emp_id)
            if not cfg or not cfg.get("is_auto_start"):
                return

            now = datetime.now()
            now_time = now.time()
            today_date = now.date()

            # Rule 1: Once-per-day enforcement.
            # If the session was already completed or clocked out today, auto-start stays DISABLED for the rest of today.
            if self.shift_completed_date == today_date or self.manual_clock_out_date == today_date:
                return

            # Check database persistence: if employee already completed a session today, disable auto-start
            today_str = today_date.strftime("%Y-%m-%d")
            if hasattr(database, 'has_completed_session_today') and database.has_completed_session_today(emp_id, today_str):
                self.shift_completed_date = today_date
                self.manual_clock_out_date = today_date
                return

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

            if in_shift and self.state == TrackerState.LOGGED_OUT:
                # Rule 2: Physical presence check - NEVER auto-start if the laptop is currently idle!
                # Auto-start should ONLY trigger when the employee actually moves their mouse or types.
                idle_sec = get_idle_seconds()
                if idle_sec > 5.0:
                    # Laptop is currently unattended. Wait until employee physically touches it.
                    return

                # All conditions met: Auto-start session once for today!
                self.start_day(emp_id, is_auto=True)
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
