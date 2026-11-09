import sqlite3
import os
import hashlib
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Any
import supabase_db

def get_app_data_dir() -> str:
    """Returns persistent application data directory for WorkLogix across all runs."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        app_dir = os.path.join(local_app_data, "WorkLogix")
    else:
        app_dir = os.path.join(os.path.expanduser("~"), ".worklogix")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

DB_FILE = os.path.join(get_app_data_dir(), "tracker_data.db")

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hashed, salt

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database tables and schema migrations."""
    conn = get_connection()
    cursor = conn.cursor()

    # Admin users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # Check if default admin exists, if not create 'admin' / 'admin123'
    cursor.execute("SELECT id FROM admin_users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed, salt = hash_password("admin123")
        cursor.execute("""
        INSERT INTO admin_users (username, password_hash, salt, created_at)
        VALUES ('admin', ?, ?, ?)
        """, (hashed, salt, datetime.now().isoformat()))

    # Employees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        employee_code TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL,
        shift_start TEXT DEFAULT '09:30',
        shift_end TEXT DEFAULT '18:00',
        is_auto_start INTEGER DEFAULT 1,
        idle_threshold INTEGER DEFAULT 300,
        pin_hash TEXT,
        pin_salt TEXT
    )
    """)

    # Migrate employees table if columns don't exist
    cursor.execute("PRAGMA table_info(employees)")
    cols = [row["name"] for row in cursor.fetchall()]
    if "shift_start" not in cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN shift_start TEXT DEFAULT '09:30'")
    if "shift_end" not in cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN shift_end TEXT DEFAULT '18:00'")
    if "is_auto_start" not in cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN is_auto_start INTEGER DEFAULT 1")
    if "idle_threshold" not in cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN idle_threshold INTEGER DEFAULT 300")
    if "pin_hash" not in cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN pin_hash TEXT")
    if "pin_salt" not in cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN pin_salt TEXT")

    # Set default PIN '1234' for existing employees without a PIN
    cursor.execute("SELECT id FROM employees WHERE pin_hash IS NULL")
    null_rows = cursor.fetchall()
    for r in null_rows:
        h, s = hash_password("1234")
        cursor.execute("UPDATE employees SET pin_hash = ?, pin_salt = ? WHERE id = ?", (h, s, r["id"]))

    # Sessions table (One per workday / shift)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        login_time TEXT NOT NULL,
        logout_time TEXT,
        total_active_sec INTEGER DEFAULT 0,
        total_inactive_sec INTEGER DEFAULT 0,
        total_lunch_sec INTEGER DEFAULT 0,
        status TEXT NOT NULL, -- 'OPEN', 'COMPLETED'
        FOREIGN KEY (employee_id) REFERENCES employees(id)
    )
    """)

    # Activity interval logs (Active blocks, Inactive blocks, Lunch blocks)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        event_type TEXT NOT NULL, -- 'ACTIVE', 'INACTIVE', 'LUNCH'
        start_time TEXT NOT NULL,
        end_time TEXT,
        duration_sec INTEGER DEFAULT 0,
        note TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    """)

    # Foreground app usage statistics
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        app_name TEXT NOT NULL,
        duration_sec INTEGER DEFAULT 0,
        UNIQUE(session_id, app_name),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    """)

    # Website domain usage statistics (e.g., youtube.com, github.com)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS website_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        domain TEXT NOT NULL,
        duration_sec INTEGER DEFAULT 0,
        UNIQUE(session_id, domain),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    """)

    # Global default shift configuration
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shift_config (
        id INTEGER PRIMARY KEY,
        shift_name TEXT NOT NULL DEFAULT 'Standard Office Shift',
        start_time TEXT NOT NULL DEFAULT '09:30',
        end_time TEXT NOT NULL DEFAULT '18:00',
        is_auto_start INTEGER NOT NULL DEFAULT 1,
        idle_threshold INTEGER NOT NULL DEFAULT 300
    )
    """)

    # Ensure default shift exists
    cursor.execute("SELECT id FROM shift_config WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO shift_config (id, shift_name, start_time, end_time, is_auto_start, idle_threshold)
        VALUES (1, 'Standard Office Shift', '09:30', '18:00', 1, 300)
        """)

    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

# ==============================================================================
# EMPLOYEE AUTHENTICATION & PERSISTENT SESSION
# ==============================================================================

def verify_employee_credentials(code: str, pin: str) -> Optional[Dict[str, Any]]:
    """Verifies employee credentials by code and PIN. Default PIN: '1234'."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.verify_employee_credentials(code, pin)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, employee_code, pin_hash, pin_salt, shift_start, shift_end, is_auto_start, idle_threshold
    FROM employees
    WHERE LOWER(employee_code) = LOWER(?)
    """, (code.strip(),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    if not row["pin_hash"] or not row["pin_salt"]:
        set_employee_pin(row["id"], pin or "1234")
        return dict(row)

    computed_hash, _ = hash_password(pin.strip(), row["pin_salt"])
    if computed_hash == row["pin_hash"]:
        return dict(row)
    return None

def set_employee_pin(employee_id: int, new_pin: str) -> bool:
    """Sets/updates employee PIN."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.set_employee_pin(employee_id, new_pin)
    hashed, salt = hash_password(new_pin.strip())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET pin_hash = ?, pin_salt = ? WHERE id = ?", (hashed, salt, employee_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_authenticated_employee() -> Optional[Dict[str, Any]]:
    """Retrieves locally persisted employee from settings table, auto-selecting default if not set."""
    emp_id_str = get_setting("auth_employee_id", "")
    if not emp_id_str or not emp_id_str.isdigit():
        all_emps = get_all_employees()
        if all_emps:
            first_emp = all_emps[0]
            set_authenticated_employee(first_emp["id"])
            return first_emp
        return None
    emp_id = int(emp_id_str)
    if supabase_db.is_supabase_enabled():
        try:
            client = supabase_db.get_supabase_client()
            res = client.table("employees").select("id, name, employee_code, shift_start, shift_end, is_auto_start, idle_threshold").eq("id", emp_id).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            print("[Supabase Error] get_authenticated_employee:", e)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, employee_code, shift_start, shift_end, is_auto_start, idle_threshold
    FROM employees WHERE id = ?
    """, (emp_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def set_authenticated_employee(employee_id: int):
    """Persists authenticated employee so they do not have to sign in every day."""
    set_setting("auth_employee_id", str(employee_id))

def clear_authenticated_employee():
    """Clears local authentication (switch employee)."""
    set_setting("auth_employee_id", "")

def verify_admin_credentials(username: str, password: str) -> bool:
    """Verifies admin username and password against the database."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.verify_admin_credentials(username, password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt FROM admin_users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False
    
    expected_hash, salt = row["password_hash"], row["salt"]
    computed_hash, _ = hash_password(password, salt)
    return computed_hash == expected_hash

def update_admin_password(username: str, new_password: str) -> bool:
    """Updates password for an admin user."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.update_admin_password(username, new_password)
    conn = get_connection()
    cursor = conn.cursor()
    hashed, salt = hash_password(new_password)
    cursor.execute("""
    UPDATE admin_users SET password_hash = ?, salt = ? WHERE username = ?
    """, (hashed, salt, username))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def record_app_usage(session_id: int, app_name: str, seconds: int = 1):
    """Increments duration for a given application during an active session."""
    if not app_name or not session_id:
        return
    if supabase_db.is_supabase_enabled():
        return supabase_db.record_app_usage(session_id, app_name, seconds)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO app_usage (session_id, app_name, duration_sec)
    VALUES (?, ?, ?)
    ON CONFLICT(session_id, app_name)
    DO UPDATE SET duration_sec = duration_sec + ?
    """, (session_id, app_name, seconds, seconds))
    conn.commit()
    conn.close()

def get_session_app_usage(session_id: int) -> List[Dict[str, Any]]:
    """Returns top applications used during a session."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_session_app_usage(session_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT app_name, duration_sec
    FROM app_usage
    WHERE session_id = ?
    ORDER BY duration_sec DESC
    LIMIT 10
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def record_website_usage(session_id: int, domain: str, seconds: int = 1):
    """Increments duration for a given website domain during an active session."""
    if not domain or not session_id:
        return
    if supabase_db.is_supabase_enabled():
        return supabase_db.record_website_usage(session_id, domain, seconds)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO website_usage (session_id, domain, duration_sec)
    VALUES (?, ?, ?)
    ON CONFLICT(session_id, domain)
    DO UPDATE SET duration_sec = duration_sec + ?
    """, (session_id, domain.lower().strip(), seconds, seconds))
    conn.commit()
    conn.close()

def get_session_website_usage(session_id: int) -> List[Dict[str, Any]]:
    """Returns top websites visited during a session with time spent."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_session_website_usage(session_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT domain, duration_sec
    FROM website_usage
    WHERE session_id = ?
    ORDER BY duration_sec DESC
    LIMIT 15
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ==============================================================================
# INDIVIDUAL EMPLOYEE SHIFT & THRESHOLD CONFIGURATION
# ==============================================================================

def get_shift_config() -> Dict[str, Any]:
    """Retrieves current global default shift timings."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, shift_name, start_time, end_time, is_auto_start, COALESCE(idle_threshold, 300) as idle_threshold FROM shift_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"id": 1, "shift_name": "Standard Office Shift", "start_time": "09:30", "end_time": "18:00", "is_auto_start": 1, "idle_threshold": 300}

def update_shift_config(start_time: str, end_time: str, is_auto_start: bool = True, idle_threshold: int = 300) -> bool:
    """Updates global default shift timings."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE shift_config
    SET start_time = ?, end_time = ?, is_auto_start = ?, idle_threshold = ?
    WHERE id = 1
    """, (start_time, end_time, 1 if is_auto_start else 0, idle_threshold))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_employee_shift(employee_id: int) -> Dict[str, Any]:
    """Retrieves specific shift timing & idle threshold for an employee, with fallback to global default."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_employee_shift(employee_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT shift_start, shift_end, is_auto_start, COALESCE(idle_threshold, 300) as idle_threshold FROM employees WHERE id = ?", (employee_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row["shift_start"] and row["shift_end"]:
        return {
            "shift_start": row["shift_start"],
            "shift_end": row["shift_end"],
            "is_auto_start": bool(row["is_auto_start"]) if row["is_auto_start"] is not None else True,
            "idle_threshold": row["idle_threshold"] or 300
        }

    global_cfg = get_shift_config()
    return {
        "shift_start": global_cfg.get("start_time", "09:30"),
        "shift_end": global_cfg.get("end_time", "18:00"),
        "is_auto_start": bool(global_cfg.get("is_auto_start", 1)),
        "idle_threshold": global_cfg.get("idle_threshold", 300)
    }

def update_employee_shift(
    employee_id: int,
    start_time: str,
    end_time: str,
    is_auto_start: bool = True,
    idle_threshold: int = 300,
    new_pin: Optional[str] = None
) -> bool:
    """Configures individual shift hours, threshold, and optional PIN for a specific employee."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.update_employee_shift(employee_id, start_time, end_time, is_auto_start, idle_threshold, new_pin)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE employees
    SET shift_start = ?, shift_end = ?, is_auto_start = ?, idle_threshold = ?
    WHERE id = ?
    """, (start_time, end_time, 1 if is_auto_start else 0, idle_threshold, employee_id))
    updated = cursor.rowcount > 0

    if new_pin and new_pin.strip():
        h, s = hash_password(new_pin.strip())
        cursor.execute("UPDATE employees SET pin_hash = ?, pin_salt = ? WHERE id = ?", (h, s, employee_id))

    conn.commit()
    conn.close()
    return updated

def get_all_employees() -> List[Dict[str, Any]]:
    """Retrieves all employees with their individual shift configuration and stats."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_all_employees()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT e.id, e.name, e.employee_code, e.created_at,
           COALESCE(e.shift_start, '09:30') as shift_start,
           COALESCE(e.shift_end, '18:00') as shift_end,
           COALESCE(e.is_auto_start, 1) as is_auto_start,
           COALESCE(e.idle_threshold, 300) as idle_threshold,
           COUNT(s.id) as total_sessions,
           MAX(s.date) as last_active_date,
           COALESCE(SUM(s.total_active_sec), 0) as total_active_sec
    FROM employees e
    LEFT JOIN sessions s ON e.id = s.employee_id
    GROUP BY e.id
    ORDER BY e.name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_employee(
    name: str,
    code: str,
    pin: str = "1234",
    shift_start: str = "09:30",
    shift_end: str = "18:00",
    is_auto_start: bool = True,
    idle_threshold: int = 300
) -> int:
    """Creates a new employee with customized shift timings and login PIN."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.add_employee(name, code, pin, shift_start, shift_end, is_auto_start, idle_threshold)
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    h, s = hash_password(pin.strip() if pin else "1234")
    cursor.execute("""
    INSERT INTO employees (name, employee_code, created_at, shift_start, shift_end, is_auto_start, idle_threshold, pin_hash, pin_salt)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, code.strip(), now, shift_start, shift_end, 1 if is_auto_start else 0, idle_threshold, h, s))
    emp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return emp_id

def delete_employee(employee_id: int) -> bool:
    """Permanently deletes an employee and all associated sessions, logs, and website records."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.delete_employee(employee_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sessions WHERE employee_id = ?", (employee_id,))
    session_ids = [r["id"] for r in cursor.fetchall()]
    for sid in session_ids:
        cursor.execute("DELETE FROM activity_logs WHERE session_id = ?", (sid,))
        cursor.execute("DELETE FROM app_usage WHERE session_id = ?", (sid,))
        cursor.execute("DELETE FROM website_usage WHERE session_id = ?", (sid,))
    cursor.execute("DELETE FROM sessions WHERE employee_id = ?", (employee_id,))
    cursor.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    deleted = cursor.rowcount > 0
    
    cursor.execute("SELECT value FROM settings WHERE key = 'auth_employee_id'")
    r = cursor.fetchone()
    if r and r["value"] == str(employee_id):
        cursor.execute("DELETE FROM settings WHERE key = 'auth_employee_id'")
        
    conn.commit()
    conn.close()
    return deleted

def clear_all_sessions() -> bool:
    """Purges all sessions, activity logs, app usage, and website records while keeping employees."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.clear_all_sessions()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM activity_logs")
    cursor.execute("DELETE FROM app_usage")
    cursor.execute("DELETE FROM website_usage")
    cursor.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()
    return True

def clear_all_mock_data():
    """Wipes all mock employees, sessions, and activity logs for a completely fresh clean database."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.clear_all_mock_data()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM activity_logs")
    cursor.execute("DELETE FROM app_usage")
    cursor.execute("DELETE FROM website_usage")
    cursor.execute("DELETE FROM sessions")
    cursor.execute("DELETE FROM employees")
    cursor.execute("DELETE FROM settings WHERE key = 'auth_employee_id'")
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_or_create_employee(name: str, code: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM employees WHERE employee_code = ?", (code,))
    row = cursor.fetchone()
    if row:
        emp_id = row["id"]
        cursor.execute("UPDATE employees SET name = ? WHERE id = ?", (name, emp_id))
        conn.commit()
    else:
        now = datetime.now().isoformat()
        global_cfg = get_shift_config()
        h, s = hash_password("1234")
        cursor.execute("""
        INSERT INTO employees (name, employee_code, created_at, shift_start, shift_end, is_auto_start, idle_threshold, pin_hash, pin_salt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, code, now, global_cfg.get("start_time", "09:30"), global_cfg.get("end_time", "18:00"), global_cfg.get("is_auto_start", 1), 300, h, s))
        conn.commit()
        emp_id = cursor.lastrowid
    conn.close()
    return emp_id

def create_session(employee_id: int) -> int:
    """Starts a new shift session."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.create_session(employee_id)
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    cursor.execute("""
    INSERT INTO sessions (employee_id, date, login_time, status)
    VALUES (?, ?, ?, 'OPEN')
    """, (employee_id, date_str, time_str))
    
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def close_session(session_id: int, total_active: int, total_inactive: int, total_lunch: int):
    """Marks session completed with final totals."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.close_session(session_id, total_active, total_inactive, total_lunch)
    conn = get_connection()
    cursor = conn.cursor()
    logout_time = datetime.now().strftime("%H:%M:%S")

    cursor.execute("""
    UPDATE sessions
    SET logout_time = ?,
        total_active_sec = ?,
        total_inactive_sec = ?,
        total_lunch_sec = ?,
        status = 'COMPLETED'
    WHERE id = ?
    """, (logout_time, total_active, total_inactive, total_lunch, session_id))
    
    conn.commit()
    conn.close()

def save_interval(session_id: int, event_type: str, start_time: str, end_time: str, duration_sec: int, note: str = "") -> int:
    """Saves a completed interval (active, inactive, lunch)."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.save_interval(session_id, event_type, start_time, end_time, duration_sec, note)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO activity_logs (session_id, event_type, start_time, end_time, duration_sec, note)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, event_type, start_time, end_time, duration_sec, note))
    interval_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return interval_id

def get_session_intervals(session_id: int) -> List[Dict[str, Any]]:
    """Returns all intervals recorded for a given session."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_session_intervals(session_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, event_type, start_time, end_time, duration_sec, note
    FROM activity_logs
    WHERE session_id = ?
    ORDER BY id ASC
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_sessions_summary() -> List[Dict[str, Any]]:
    return get_filtered_sessions()

def get_filtered_sessions(
    employee_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetches sessions matching flexible filters."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_filtered_sessions(employee_id, start_date, end_date, status)
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT s.id, e.id as employee_id, e.name as employee_name, e.employee_code,
           COALESCE(e.shift_start, '09:30') as shift_start,
           COALESCE(e.shift_end, '18:00') as shift_end,
           s.date, s.login_time, s.logout_time,
           s.total_active_sec, s.total_inactive_sec, s.total_lunch_sec, s.status
    FROM sessions s
    JOIN employees e ON s.employee_id = e.id
    WHERE 1=1
    """
    params = []

    if employee_id:
        query += " AND s.employee_id = ?"
        params.append(employee_id)
    if start_date:
        query += " AND s.date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND s.date <= ?"
        params.append(end_date)
    if status and status.upper() != "ALL":
        query += " AND s.status = ?"
        params.append(status.upper())

    query += " ORDER BY s.id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_employee_profile(employee_id: int) -> Dict[str, Any]:
    """Retrieves full profile, performance KPIs, and recent records for one employee."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_employee_profile(employee_id) or {}
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, name, employee_code, created_at,
           COALESCE(shift_start, '09:30') as shift_start,
           COALESCE(shift_end, '18:00') as shift_end,
           COALESCE(is_auto_start, 1) as is_auto_start,
           COALESCE(idle_threshold, 300) as idle_threshold
    FROM employees
    WHERE id = ?
    """, (employee_id,))
    emp_row = cursor.fetchone()
    if not emp_row:
        conn.close()
        return {}
    emp_data = dict(emp_row)

    cursor.execute("""
    SELECT COUNT(id) as total_days,
           COALESCE(SUM(total_active_sec), 0) as total_active_sec,
           COALESCE(SUM(total_inactive_sec), 0) as total_inactive_sec,
           COALESCE(SUM(total_lunch_sec), 0) as total_lunch_sec
    FROM sessions
    WHERE employee_id = ?
    """, (employee_id,))
    stats_row = cursor.fetchone()
    total_days = stats_row["total_days"]
    total_active = stats_row["total_active_sec"]
    total_inactive = stats_row["total_inactive_sec"]
    total_lunch = stats_row["total_lunch_sec"]

    total_work = total_active + total_inactive
    inactivity_pct = round((total_inactive / total_work * 100), 1) if total_work > 0 else 0.0
    avg_active_sec = int(total_active / total_days) if total_days > 0 else 0

    cursor.execute("""
    SELECT id, date, login_time, logout_time, total_active_sec, total_inactive_sec, total_lunch_sec, status
    FROM sessions
    WHERE employee_id = ?
    ORDER BY id DESC
    LIMIT 20
    """, (employee_id,))
    recent_sessions = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT w.domain, SUM(w.duration_sec) as duration_sec
    FROM website_usage w
    JOIN sessions s ON w.session_id = s.id
    WHERE s.employee_id = ?
    GROUP BY w.domain
    ORDER BY duration_sec DESC
    LIMIT 10
    """, (employee_id,))
    top_websites = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT a.app_name, SUM(a.duration_sec) as duration_sec
    FROM app_usage a
    JOIN sessions s ON a.session_id = s.id
    WHERE s.employee_id = ?
    GROUP BY a.app_name
    ORDER BY duration_sec DESC
    LIMIT 10
    """, (employee_id,))
    top_apps = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "employee": emp_data,
        "kpis": {
            "total_days": total_days,
            "total_active_sec": total_active,
            "total_inactive_sec": total_inactive,
            "total_lunch_sec": total_lunch,
            "inactivity_pct": inactivity_pct,
            "avg_active_sec": avg_active_sec
        },
        "recent_sessions": recent_sessions,
        "top_websites": top_websites,
        "top_apps": top_apps
    }

def get_daily_report(date_str: str) -> Dict[str, Any]:
    """Generates comprehensive daily report for all employees on a specific date."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_daily_report(date_str)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT s.id, e.id as employee_id, e.name as employee_name, e.employee_code,
           COALESCE(e.shift_start, '09:30') as shift_start,
           COALESCE(e.shift_end, '18:00') as shift_end,
           s.login_time, s.logout_time,
           s.total_active_sec, s.total_inactive_sec, s.total_lunch_sec, s.status
    FROM sessions s
    JOIN employees e ON s.employee_id = e.id
    WHERE s.date = ?
    ORDER BY s.id ASC
    """, (date_str,))
    rows = cursor.fetchall()

    employees_data = []
    total_active_day = 0
    total_inactive_day = 0
    total_lunch_day = 0

    for r in rows:
        session_id = r["id"]
        total_active_day += r["total_active_sec"] or 0
        total_inactive_day += r["total_inactive_sec"] or 0
        total_lunch_day += r["total_lunch_sec"] or 0

        cursor.execute("""
        SELECT domain, duration_sec FROM website_usage
        WHERE session_id = ?
        ORDER BY duration_sec DESC LIMIT 1
        """, (session_id,))
        top_web_row = cursor.fetchone()
        top_web = top_web_row["domain"] if top_web_row else "None"

        cursor.execute("""
        SELECT app_name, duration_sec FROM app_usage
        WHERE session_id = ?
        ORDER BY duration_sec DESC LIMIT 1
        """, (session_id,))
        top_app_row = cursor.fetchone()
        top_app = top_app_row["app_name"] if top_app_row else "None"

        item = dict(r)
        item["top_website"] = top_web
        item["top_app"] = top_app
        employees_data.append(item)

    conn.close()

    total_work = total_active_day + total_inactive_day
    inactivity_pct = round((total_inactive_day / total_work * 100), 1) if total_work > 0 else 0.0

    return {
        "date": date_str,
        "total_employees_present": len(employees_data),
        "total_active_sec": total_active_day,
        "total_inactive_sec": total_inactive_day,
        "total_lunch_sec": total_lunch_day,
        "inactivity_pct": inactivity_pct,
        "records": employees_data
    }

def get_monthly_report(year: int, month: int) -> Dict[str, Any]:
    """Generates monthly attendance and performance report for all employees."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_monthly_report(year, month)
    conn = get_connection()
    cursor = conn.cursor()

    month_str = f"{year:04d}-{month:02d}"

    cursor.execute("""
    SELECT e.id, e.name, e.employee_code,
           COALESCE(e.shift_start, '09:30') as shift_start,
           COALESCE(e.shift_end, '18:00') as shift_end
    FROM employees e
    ORDER BY e.name ASC
    """)
    employees = cursor.fetchall()

    summaries = []
    company_active_sec = 0
    company_inactive_sec = 0
    company_lunch_sec = 0
    company_total_sessions = 0

    for emp in employees:
        emp_id = emp["id"]

        cursor.execute("""
        SELECT COUNT(id) as days_worked,
               COALESCE(SUM(total_active_sec), 0) as total_active_sec,
               COALESCE(SUM(total_inactive_sec), 0) as total_inactive_sec,
               COALESCE(SUM(total_lunch_sec), 0) as total_lunch_sec
        FROM sessions
        WHERE employee_id = ? AND date LIKE ?
        """, (emp_id, f"{month_str}%"))
        stat_row = cursor.fetchone()

        days_worked = stat_row["days_worked"]
        active_sec = stat_row["total_active_sec"]
        inactive_sec = stat_row["total_inactive_sec"]
        lunch_sec = stat_row["total_lunch_sec"]

        company_active_sec += active_sec
        company_inactive_sec += inactive_sec
        company_lunch_sec += lunch_sec
        company_total_sessions += days_worked

        work_total = active_sec + inactive_sec
        inactivity_pct = round((inactive_sec / work_total * 100), 1) if work_total > 0 else 0.0
        avg_active_sec = int(active_sec / days_worked) if days_worked > 0 else 0

        cursor.execute("""
        SELECT w.domain, SUM(w.duration_sec) as dur
        FROM website_usage w
        JOIN sessions s ON w.session_id = s.id
        WHERE s.employee_id = ? AND s.date LIKE ?
        GROUP BY w.domain
        ORDER BY dur DESC
        LIMIT 1
        """, (emp_id, f"{month_str}%"))
        top_w_row = cursor.fetchone()
        top_web = top_w_row["domain"] if top_w_row else "None"

        summaries.append({
            "employee_id": emp_id,
            "name": emp["name"],
            "employee_code": emp["employee_code"],
            "shift_start": emp["shift_start"],
            "shift_end": emp["shift_end"],
            "days_worked": days_worked,
            "total_active_sec": active_sec,
            "total_inactive_sec": inactive_sec,
            "total_lunch_sec": lunch_sec,
            "avg_active_sec_per_day": avg_active_sec,
            "inactivity_pct": inactivity_pct,
            "top_website": top_web
        })

    conn.close()

    company_work = company_active_sec + company_inactive_sec
    company_inactivity_pct = round((company_inactive_sec / company_work * 100), 1) if company_work > 0 else 0.0

    return {
        "year": year,
        "month": month,
        "month_str": month_str,
        "overall": {
            "total_employees": len(employees),
            "active_employees": len([s for s in summaries if s["days_worked"] > 0]),
            "total_sessions": company_total_sessions,
            "total_active_sec": company_active_sec,
            "total_inactive_sec": company_inactive_sec,
            "total_lunch_sec": company_lunch_sec,
            "company_inactivity_pct": company_inactivity_pct
        },
        "employees": summaries
    }

def get_monthly_website_usage(year: int, month: int) -> List[Dict[str, Any]]:
    """Retrieves all website usage aggregated for a given month."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_monthly_website_usage(year, month)
    conn = get_connection()
    cursor = conn.cursor()
    month_str = f"{year:04d}-{month:02d}%"

    cursor.execute("""
    SELECT e.name as emp_name, e.employee_code, w.domain, SUM(w.duration_sec) as duration_sec
    FROM website_usage w
    JOIN sessions s ON w.session_id = s.id
    JOIN employees e ON s.employee_id = e.id
    WHERE s.date LIKE ?
    GROUP BY e.id, w.domain
    ORDER BY duration_sec DESC
    """, (month_str,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_website_usage(limit: int = 250) -> List[Dict[str, Any]]:
    """Retrieves website surveillance logs across all workstations."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_all_website_usage(limit)
    import tracker_core
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.id, w.session_id, e.name as emp_name, e.employee_code, s.date, w.domain, w.duration_sec
        FROM website_usage w
        JOIN sessions s ON w.session_id = s.id
        JOIN employees e ON s.employee_id = e.id
        ORDER BY w.id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        sid = r["session_id"]
        cursor.execute("""
            SELECT app_name, duration_sec FROM app_usage
            WHERE session_id = ?
            ORDER BY duration_sec DESC
        """, (sid,))
        apps = cursor.fetchall()
        browser = "Google Chrome"
        for a in apps:
            friendly = tracker_core.get_browser_friendly_name(a["app_name"])
            if friendly:
                browser = friendly
                break
        r["browser"] = browser

    conn.close()
    return rows

def get_all_browser_usage(limit: int = 250) -> List[Dict[str, Any]]:
    """Retrieves dedicated browser usage logs across all workstations."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_all_browser_usage(limit)
    import tracker_core
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.session_id, e.name as emp_name, e.employee_code, s.date, a.app_name as process_name, a.duration_sec
        FROM app_usage a
        JOIN sessions s ON a.session_id = s.id
        JOIN employees e ON s.employee_id = e.id
        ORDER BY a.duration_sec DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    browser_rows = []
    for r in rows:
        friendly = tracker_core.get_browser_friendly_name(r["process_name"])
        if friendly:
            r["browser_name"] = friendly
            browser_rows.append(r)
            if len(browser_rows) >= limit:
                break
    return browser_rows

def get_all_apps_usage(limit: int = 250) -> List[Dict[str, Any]]:
    """Retrieves all application usage logs across workstations."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_all_apps_usage(limit)
    import tracker_core
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.session_id, e.name as emp_name, e.employee_code, s.date, a.app_name, a.duration_sec
        FROM app_usage a
        JOIN sessions s ON a.session_id = s.id
        JOIN employees e ON s.employee_id = e.id
        ORDER BY a.duration_sec DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        disp = tracker_core.get_app_display_info(r["app_name"])
        r["friendly_name"] = disp["friendly_name"]
        r["category"] = disp["category"]
    return rows

def get_browser_website_analytics() -> Dict[str, Any]:
    """Generates comprehensive analytics for browsers and websites across all workstations."""
    if supabase_db.is_supabase_enabled():
        return supabase_db.get_browser_website_analytics()
    websites = get_all_website_usage(200)
    browsers = get_all_browser_usage(200)
    apps = get_all_apps_usage(200)

    total_browsing_sec = sum(b.get("duration_sec", 0) for b in browsers)
    browser_totals: Dict[str, int] = {}
    for b in browsers:
        name = b["browser_name"]
        browser_totals[name] = browser_totals.get(name, 0) + b["duration_sec"]

    browser_breakdown = []
    for b_name, b_sec in sorted(browser_totals.items(), key=lambda x: x[1], reverse=True):
        pct = round((b_sec / total_browsing_sec * 100), 1) if total_browsing_sec > 0 else 0.0
        browser_breakdown.append({
            "browser": b_name,
            "duration_sec": b_sec,
            "percentage": pct
        })

    web_totals: Dict[str, int] = {}
    web_emps: Dict[str, set] = {}
    for w in websites:
        dom = w["domain"]
        web_totals[dom] = web_totals.get(dom, 0) + w["duration_sec"]
        if dom not in web_emps:
            web_emps[dom] = set()
        web_emps[dom].add(w["emp_name"])

    top_websites = []
    for dom, sec in sorted(web_totals.items(), key=lambda x: x[1], reverse=True)[:15]:
        top_websites.append({
            "domain": dom,
            "duration_sec": sec,
            "employees": list(web_emps.get(dom, []))
        })

    primary_browser = browser_breakdown[0]["browser"] if browser_breakdown else "Google Chrome"
    top_site = top_websites[0]["domain"] if top_websites else "None"

    return {
        "summary": {
            "total_browsing_sec": total_browsing_sec,
            "primary_browser": primary_browser,
            "top_website": top_site,
            "unique_websites_count": len(web_totals)
        },
        "browser_breakdown": browser_breakdown,
        "top_websites": top_websites,
        "all_websites": websites,
        "all_browsers": browsers,
        "all_apps": apps
    }
