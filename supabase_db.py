import os
import hashlib
import secrets
import calendar
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client

import sys

if getattr(sys, 'frozen', False):
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

env_path = os.path.join(base_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

exe_env = os.path.join(os.path.dirname(sys.executable), ".env")
if os.path.exists(exe_env):
    load_dotenv(exe_env)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client: Optional[Client] = None

def get_supabase_client() -> Client:
    global _client, SUPABASE_URL, SUPABASE_KEY
    if not SUPABASE_URL:
        SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    if not SUPABASE_KEY:
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured in environment or .env file.")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client

def is_supabase_enabled() -> bool:
    use_sb = os.getenv("USE_SUPABASE", "true").lower()
    return bool(SUPABASE_URL and SUPABASE_KEY and use_sb in ("true", "1", "yes"))

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hashed, salt

# ==============================================================================
# ADMIN AUTHENTICATION
# ==============================================================================

def verify_admin_credentials(username: str, password: str) -> bool:
    try:
        client = get_supabase_client()
        res = client.table("admin_users").select("password_hash, salt").eq("username", username).execute()
        if not res.data:
            return False
        row = res.data[0]
        expected_hash, salt = row["password_hash"], row["salt"]
        computed_hash, _ = hash_password(password, salt)
        return computed_hash == expected_hash
    except Exception as e:
        print("[Supabase Error] verify_admin_credentials:", e)
        return False

def update_admin_password(username: str, new_password: str) -> bool:
    try:
        client = get_supabase_client()
        hashed, salt = hash_password(new_password)
        res = client.table("admin_users").update({
            "password_hash": hashed,
            "salt": salt
        }).eq("username", username).execute()
        return bool(res.data)
    except Exception as e:
        print("[Supabase Error] update_admin_password:", e)
        return False

# ==============================================================================
# EMPLOYEE AUTHENTICATION & PIN
# ==============================================================================

def verify_employee_credentials(code: str, pin: str) -> Optional[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        res = client.table("employees").select("*").ilike("employee_code", code.strip()).execute()
        if not res.data:
            return None
        emp = res.data[0]
        if not emp.get("pin_hash") or not emp.get("pin_salt"):
            set_employee_pin(emp["id"], pin or "1234")
            return emp

        computed_hash, _ = hash_password(pin.strip(), emp["pin_salt"])
        if computed_hash == emp["pin_hash"]:
            return emp
        return None
    except Exception as e:
        print("[Supabase Error] verify_employee_credentials:", e)
        return None

def set_employee_pin(employee_id: int, new_pin: str) -> bool:
    try:
        client = get_supabase_client()
        hashed, salt = hash_password(new_pin.strip())
        res = client.table("employees").update({
            "pin_hash": hashed,
            "pin_salt": salt
        }).eq("id", employee_id).execute()
        return bool(res.data)
    except Exception as e:
        print("[Supabase Error] set_employee_pin:", e)
        return False

# ==============================================================================
# EMPLOYEE ROSTER & SHIFT MANAGEMENT
# ==============================================================================

def get_all_employees() -> List[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        res = client.table("employees").select("*").order("name").execute()
        employees = res.data or []
        
        # Enrich with total sessions and active seconds
        sess_res = client.table("sessions").select("employee_id, total_active_sec, date").execute()
        sessions = sess_res.data or []
        
        counts: Dict[int, int] = {}
        active_secs: Dict[int, int] = {}
        last_dates: Dict[int, str] = {}
        
        for s in sessions:
            eid = s["employee_id"]
            counts[eid] = counts.get(eid, 0) + 1
            active_secs[eid] = active_secs.get(eid, 0) + (s.get("total_active_sec") or 0)
            cur_date = s.get("date") or ""
            if eid not in last_dates or cur_date > last_dates[eid]:
                last_dates[eid] = cur_date

        for emp in employees:
            eid = emp["id"]
            emp["total_sessions"] = counts.get(eid, 0)
            emp["total_active_sec"] = active_secs.get(eid, 0)
            emp["last_active_date"] = last_dates.get(eid, None)
            emp["shift_start"] = emp.get("shift_start") or "09:30"
            emp["shift_end"] = emp.get("shift_end") or "18:00"
            emp["is_auto_start"] = emp.get("is_auto_start", True)
            emp["idle_threshold"] = emp.get("idle_threshold") or 300

        return employees
    except Exception as e:
        print("[Supabase Error] get_all_employees:", e)
        return []

def add_employee(
    name: str,
    code: str,
    pin: str = "1234",
    shift_start: str = "09:30",
    shift_end: str = "18:00",
    is_auto_start: bool = True,
    idle_threshold: int = 300
) -> int:
    try:
        client = get_supabase_client()
        h, s = hash_password(pin.strip() if pin else "1234")
        payload = {
            "name": name.strip(),
            "employee_code": code.strip(),
            "pin_hash": h,
            "pin_salt": s,
            "shift_start": shift_start,
            "shift_end": shift_end,
            "is_auto_start": is_auto_start,
            "idle_threshold": idle_threshold,
            "created_at": datetime.now().isoformat()
        }
        res = client.table("employees").insert(payload).execute()
        if res.data:
            return res.data[0]["id"]
        raise RuntimeError("No employee record returned from Supabase insert.")
    except Exception as e:
        print("[Supabase Error] add_employee:", e)
        raise

def delete_employee(employee_id: int) -> bool:
    try:
        client = get_supabase_client()
        # Cascading deletes will remove sessions, logs, app/website usage
        res = client.table("employees").delete().eq("id", employee_id).execute()
        return bool(res.data)
    except Exception as e:
        print("[Supabase Error] delete_employee:", e)
        return False

def get_employee_shift(employee_id: int) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
        res = client.table("employees").select("shift_start, shift_end, is_auto_start, idle_threshold").eq("id", employee_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print("[Supabase Error] get_employee_shift:", e)
    return {
        "shift_start": "09:30",
        "shift_end": "18:00",
        "is_auto_start": True,
        "idle_threshold": 300
    }

def update_employee_shift(
    employee_id: int,
    start_time: str,
    end_time: str,
    is_auto_start: bool = True,
    idle_threshold: int = 300,
    new_pin: Optional[str] = None
) -> bool:
    try:
        client = get_supabase_client()
        payload = {
            "shift_start": start_time,
            "shift_end": end_time,
            "is_auto_start": is_auto_start,
            "idle_threshold": idle_threshold
        }
        if new_pin and new_pin.strip():
            h, s = hash_password(new_pin.strip())
            payload["pin_hash"] = h
            payload["pin_salt"] = s
            
        res = client.table("employees").update(payload).eq("id", employee_id).execute()
        return bool(res.data)
    except Exception as e:
        print("[Supabase Error] update_employee_shift:", e)
        return False

# ==============================================================================
# SESSIONS & WORK TRACKING
# ==============================================================================

def start_session(employee_id: int) -> int:
    try:
        client = get_supabase_client()
        today = datetime.now().strftime("%Y-%m-%d")
        now_time = datetime.now().strftime("%H:%M:%S")

        # Close any open sessions for this employee
        client.table("sessions").update({
            "status": "COMPLETED",
            "logout_time": now_time
        }).eq("employee_id", employee_id).eq("status", "OPEN").execute()

        payload = {
            "employee_id": employee_id,
            "date": today,
            "login_time": now_time,
            "status": "OPEN",
            "total_active_sec": 0,
            "total_inactive_sec": 0,
            "total_lunch_sec": 0
        }
        res = client.table("sessions").insert(payload).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        print("[Supabase Error] start_session:", e)
    return 0

create_session = start_session

def close_session(session_id: int, active_sec: int, inactive_sec: int, lunch_sec: int):
    try:
        client = get_supabase_client()
        now_time = datetime.now().strftime("%H:%M:%S")
        client.table("sessions").update({
            "logout_time": now_time,
            "status": "COMPLETED",
            "total_active_sec": active_sec,
            "total_inactive_sec": inactive_sec,
            "total_lunch_sec": lunch_sec
        }).eq("id", session_id).execute()
    except Exception as e:
        print("[Supabase Error] close_session:", e)

def log_activity_interval(session_id: int, event_type: str, start_time: str, end_time: Optional[str], duration_sec: int, note: Optional[str] = None) -> int:
    try:
        client = get_supabase_client()
        payload = {
            "session_id": session_id,
            "event_type": event_type,
            "start_time": start_time,
            "end_time": end_time,
            "duration_sec": duration_sec,
            "note": note
        }
        res = client.table("activity_logs").insert(payload).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        print("[Supabase Error] log_activity_interval:", e)
    return 0

save_interval = log_activity_interval

def get_session_intervals(session_id: int) -> List[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        res = client.table("activity_logs").select("*").eq("session_id", session_id).order("id").execute()
        return res.data or []
    except Exception as e:
        print("[Supabase Error] get_session_intervals:", e)
        return []

def record_app_usage(session_id: int, app_name: str, seconds: int = 1):
    if not app_name or not session_id:
        return
    try:
        client = get_supabase_client()
        res = client.table("app_usage").select("id, duration_sec").eq("session_id", session_id).eq("app_name", app_name).execute()
        if res.data:
            row_id = res.data[0]["id"]
            new_dur = (res.data[0].get("duration_sec") or 0) + seconds
            client.table("app_usage").update({"duration_sec": new_dur}).eq("id", row_id).execute()
        else:
            client.table("app_usage").insert({
                "session_id": session_id,
                "app_name": app_name,
                "duration_sec": seconds
            }).execute()
    except Exception as e:
        print("[Supabase Error] record_app_usage:", e)

def get_session_app_usage(session_id: int) -> List[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        res = client.table("app_usage").select("app_name, duration_sec").eq("session_id", session_id).order("duration_sec", desc=True).limit(10).execute()
        return res.data or []
    except Exception as e:
        print("[Supabase Error] get_session_app_usage:", e)
        return []

def record_website_usage(session_id: int, domain: str, seconds: int = 1):
    if not domain or not session_id:
        return
    try:
        client = get_supabase_client()
        clean_domain = domain.lower().strip()
        res = client.table("website_usage").select("id, duration_sec").eq("session_id", session_id).eq("domain", clean_domain).execute()
        if res.data:
            row_id = res.data[0]["id"]
            new_dur = (res.data[0].get("duration_sec") or 0) + seconds
            client.table("website_usage").update({"duration_sec": new_dur}).eq("id", row_id).execute()
        else:
            client.table("website_usage").insert({
                "session_id": session_id,
                "domain": clean_domain,
                "duration_sec": seconds
            }).execute()
    except Exception as e:
        print("[Supabase Error] record_website_usage:", e)

def get_session_website_usage(session_id: int) -> List[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        res = client.table("website_usage").select("domain, duration_sec").eq("session_id", session_id).order("duration_sec", desc=True).limit(15).execute()
        return res.data or []
    except Exception as e:
        print("[Supabase Error] get_session_website_usage:", e)
        return []

# ==============================================================================
# ANALYTICS & REPORTS
# ==============================================================================

def get_filtered_sessions(
    employee_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        # Query sessions with employee join
        query = client.table("sessions").select("*, employees(name, employee_code, shift_start, shift_end)")
        
        if employee_id:
            query = query.eq("employee_id", employee_id)
        if start_date:
            query = query.gte("date", start_date)
        if end_date:
            query = query.lte("date", end_date)
        if status and status != "ALL":
            query = query.eq("status", status)
            
        res = query.order("date", desc=True).order("login_time", desc=True).execute()
        sessions = res.data or []
        
        result = []
        for s in sessions:
            emp = s.get("employees") or {}
            result.append({
                "id": s["id"],
                "employee_id": s["employee_id"],
                "employee_name": emp.get("name", "Unknown"),
                "employee_code": emp.get("employee_code", "---"),
                "shift_start": emp.get("shift_start", "09:30"),
                "shift_end": emp.get("shift_end", "18:00"),
                "date": s["date"],
                "login_time": s["login_time"],
                "logout_time": s.get("logout_time"),
                "total_active_sec": s.get("total_active_sec", 0),
                "total_inactive_sec": s.get("total_inactive_sec", 0),
                "total_lunch_sec": s.get("total_lunch_sec", 0),
                "status": s["status"]
            })
        return result
    except Exception as e:
        print("[Supabase Error] get_filtered_sessions:", e)
        return []

def get_employee_profile(employee_id: int) -> Optional[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        emp_res = client.table("employees").select("*").eq("id", employee_id).execute()
        if not emp_res.data:
            return None
        emp = emp_res.data[0]
        
        # Query employee's sessions
        sess_res = client.table("sessions").select("*").eq("employee_id", employee_id).order("date", desc=True).execute()
        sessions = sess_res.data or []
        
        total_days = len({s["date"] for s in sessions})
        total_active = sum(s.get("total_active_sec") or 0 for s in sessions)
        total_inactive = sum(s.get("total_inactive_sec") or 0 for s in sessions)
        total_work = total_active + total_inactive
        
        avg_active = int(total_active / total_days) if total_days > 0 else 0
        inactivity_pct = round((total_inactive / total_work * 100), 1) if total_work > 0 else 0.0
        
        session_ids = [s["id"] for s in sessions]
        top_websites: List[Dict[str, Any]] = []
        top_apps: List[Dict[str, Any]] = []
        
        if session_ids:
            # Query websites
            web_res = client.table("website_usage").select("domain, duration_sec").in_("session_id", session_ids).execute()
            web_map: Dict[str, int] = {}
            for w in (web_res.data or []):
                web_map[w["domain"]] = web_map.get(w["domain"], 0) + w.get("duration_sec", 0)
            sorted_webs = sorted(web_map.items(), key=lambda x: x[1], reverse=True)[:10]
            top_websites = [{"domain": d, "duration_sec": s} for d, s in sorted_webs]

            # Query apps
            app_res = client.table("app_usage").select("app_name, duration_sec").in_("session_id", session_ids).execute()
            app_map: Dict[str, int] = {}
            for a in (app_res.data or []):
                app_map[a["app_name"]] = app_map.get(a["app_name"], 0) + a.get("duration_sec", 0)
            sorted_apps = sorted(app_map.items(), key=lambda x: x[1], reverse=True)[:10]
            top_apps = [{"app_name": an, "duration_sec": s} for an, s in sorted_apps]

        return {
            "employee": emp,
            "kpis": {
                "total_days": total_days,
                "total_active_sec": total_active,
                "total_inactive_sec": total_inactive,
                "avg_active_sec": avg_active,
                "inactivity_pct": inactivity_pct
            },
            "top_websites": top_websites,
            "top_apps": top_apps,
            "recent_sessions": sessions[:15]
        }
    except Exception as e:
        print("[Supabase Error] get_employee_profile:", e)
        return None

def get_daily_report(date_str: str) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
        emps = client.table("employees").select("*").order("name").execute().data or []
        sess = client.table("sessions").select("*").eq("date", date_str).execute().data or []
        
        sess_map = {s["employee_id"]: s for s in sess}
        
        # Get website and app usage for today's sessions
        sess_ids = [s["id"] for s in sess]
        top_webs = {}
        top_apps = {}
        if sess_ids:
            try:
                w_res = client.table("website_usage").select("session_id, domain, duration_sec").in_("session_id", sess_ids).execute().data or []
                for w in sorted(w_res, key=lambda x: x.get("duration_sec", 0), reverse=True):
                    sid = w["session_id"]
                    if sid not in top_webs:
                        top_webs[sid] = w["domain"]
            except Exception:
                pass
            try:
                a_res = client.table("app_usage").select("session_id, app_name, duration_sec").in_("session_id", sess_ids).execute().data or []
                for a in sorted(a_res, key=lambda x: x.get("duration_sec", 0), reverse=True):
                    sid = a["session_id"]
                    if sid not in top_apps:
                        top_apps[sid] = a["app_name"]
            except Exception:
                pass

        records = []
        total_active_all = 0
        total_inactive_all = 0
        total_lunch_all = 0
        present_count = 0
        
        for e in emps:
            eid = e["id"]
            s = sess_map.get(eid)
            if s:
                present_count += 1
                sid = s["id"]
                act = s.get("total_active_sec") or 0
                inact = s.get("total_inactive_sec") or 0
                lunch = s.get("total_lunch_sec") or 0
                total_active_all += act
                total_inactive_all += inact
                total_lunch_all += lunch
                records.append({
                    "id": sid,
                    "session_id": sid,
                    "employee_id": eid,
                    "name": e["name"],
                    "employee_name": e["name"],
                    "employee_code": e["employee_code"],
                    "shift_start": e.get("shift_start", "09:30"),
                    "shift_end": e.get("shift_end", "18:00"),
                    "is_present": True,
                    "login_time": s.get("login_time", "--:--"),
                    "logout_time": s.get("logout_time") or "In Progress",
                    "total_active_sec": act,
                    "total_inactive_sec": inact,
                    "total_lunch_sec": lunch,
                    "top_website": top_webs.get(sid, "None"),
                    "top_app": top_apps.get(sid, "None"),
                    "status": s.get("status", "OPEN")
                })

        total_work = total_active_all + total_inactive_all
        inact_pct = round((total_inactive_all / total_work * 100), 1) if total_work > 0 else 0.0

        return {
            "date": date_str,
            "total_employees": len(emps),
            "total_employees_present": present_count,
            "present_count": present_count,
            "absent_count": len(emps) - present_count,
            "total_active_sec": total_active_all,
            "total_inactive_sec": total_inactive_all,
            "total_lunch_sec": total_lunch_all,
            "inactivity_pct": inact_pct,
            "records": records,
            "roster": records
        }
    except Exception as e:
        print("[Supabase Error] get_daily_report:", e)
        return {"date": date_str, "total_employees": 0, "total_employees_present": 0, "present_count": 0, "absent_count": 0, "total_active_sec": 0, "total_inactive_sec": 0, "total_lunch_sec": 0, "inactivity_pct": 0.0, "records": [], "roster": []}

def get_monthly_report(year: int, month: int) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year:04d}-{month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
        
        emps = client.table("employees").select("*").order("name").execute().data or []
        sess = client.table("sessions").select("*").gte("date", start_date).lte("date", end_date).execute().data or []
        
        emp_sessions: Dict[int, List[Dict[str, Any]]] = {}
        for s in sess:
            eid = s["employee_id"]
            emp_sessions.setdefault(eid, []).append(s)
            
        records = []
        company_active_sec = 0
        company_inactive_sec = 0
        company_lunch_sec = 0
        company_total_sessions = 0

        for e in emps:
            eid = e["id"]
            s_list = emp_sessions.get(eid, [])
            days_worked = len({s["date"] for s in s_list})
            total_active = sum(s.get("total_active_sec") or 0 for s in s_list)
            total_inactive = sum(s.get("total_inactive_sec") or 0 for s in s_list)
            total_lunch = sum(s.get("total_lunch_sec") or 0 for s in s_list)
            avg_daily = int(total_active / days_worked) if days_worked > 0 else 0
            
            company_active_sec += total_active
            company_inactive_sec += total_inactive
            company_lunch_sec += total_lunch
            company_total_sessions += days_worked

            tot_work = total_active + total_inactive
            inact_pct = round((total_inactive / tot_work * 100), 1) if tot_work > 0 else 0.0
            
            records.append({
                "employee_id": eid,
                "name": e["name"],
                "employee_code": e["employee_code"],
                "shift_start": e.get("shift_start", "09:30"),
                "shift_end": e.get("shift_end", "18:00"),
                "days_worked": days_worked,
                "total_active_sec": total_active,
                "total_inactive_sec": total_inactive,
                "total_lunch_sec": total_lunch,
                "avg_daily_active_sec": avg_daily,
                "avg_active_sec_per_day": avg_daily,
                "inactivity_pct": inact_pct,
                "top_website": "None"
            })

        company_work = company_active_sec + company_inactive_sec
        company_inactivity_pct = round((company_inactive_sec / company_work * 100), 1) if company_work > 0 else 0.0

        overall = {
            "total_employees": len(emps),
            "active_employees": len([r for r in records if r["days_worked"] > 0]),
            "total_sessions": company_total_sessions,
            "total_active_sec": company_active_sec,
            "total_inactive_sec": company_inactive_sec,
            "total_lunch_sec": company_lunch_sec,
            "company_inactivity_pct": company_inactivity_pct
        }

        return {
            "year": year,
            "month": month,
            "month_str": f"{year:04d}-{month:02d}",
            "period": f"{year:04d}-{month:02d}",
            "overall": overall,
            "employees": records,
            "records": records
        }
    except Exception as e:
        print("[Supabase Error] get_monthly_report:", e)
        return {
            "year": year, "month": month, "month_str": f"{year:04d}-{month:02d}", "period": f"{year:04d}-{month:02d}",
            "overall": {"total_employees": 0, "active_employees": 0, "total_sessions": 0, "total_active_sec": 0, "total_inactive_sec": 0, "total_lunch_sec": 0, "company_inactivity_pct": 0.0},
            "employees": [], "records": []
        }

def get_monthly_website_usage(year: int, month: int) -> List[Dict[str, Any]]:
    try:
        client = get_supabase_client()
        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year:04d}-{month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
        
        sess_res = client.table("sessions").select("id, employee_id, employees(name)").gte("date", start_date).lte("date", end_date).execute()
        sessions = sess_res.data or []
        if not sessions:
            return []
            
        session_ids = [s["id"] for s in sessions]
        emp_map = {s["id"]: ((s.get("employees") or {}).get("name") or "Employee") for s in sessions}
        
        web_res = client.table("website_usage").select("session_id, domain, duration_sec").in_("session_id", session_ids).execute()
        websites = web_res.data or []
        
        agg: Dict[tuple[str, str], int] = {}
        for w in websites:
            emp_name = emp_map.get(w["session_id"], "Employee")
            domain = w["domain"]
            key = (emp_name, domain)
            agg[key] = agg.get(key, 0) + (w.get("duration_sec") or 0)
            
        result = [
            {"emp_name": k[0], "domain": k[1], "duration_sec": v}
            for k, v in agg.items()
        ]
        result.sort(key=lambda x: x["duration_sec"], reverse=True)
        return result
    except Exception as e:
        print("[Supabase Error] get_monthly_website_usage:", e)
        return []

def clear_all_sessions() -> bool:
    try:
        client = get_supabase_client()
        # Deleting all rows from sessions cascades to logs, app_usage, website_usage
        client.table("activity_logs").delete().neq("id", 0).execute()
        client.table("app_usage").delete().neq("id", 0).execute()
        client.table("website_usage").delete().neq("id", 0).execute()
        client.table("sessions").delete().neq("id", 0).execute()
        return True
    except Exception as e:
        print("[Supabase Error] clear_all_sessions:", e)
        return False

def clear_all_mock_data():
    try:
        client = get_supabase_client()
        client.table("activity_logs").delete().neq("id", 0).execute()
        client.table("app_usage").delete().neq("id", 0).execute()
        client.table("website_usage").delete().neq("id", 0).execute()
        client.table("sessions").delete().neq("id", 0).execute()
        client.table("employees").delete().neq("id", 0).execute()
    except Exception as e:
        print("[Supabase Error] clear_all_mock_data:", e)


def get_all_website_usage(limit: int = 250) -> List[Dict[str, Any]]:
    """Retrieves all website visits across all workstations with employee and browser details."""
    try:
        import tracker_core
        client = get_supabase_client()
        web_res = client.table("website_usage").select("id, session_id, domain, duration_sec").order("id", desc=True).limit(limit).execute()
        rows = web_res.data or []
        if not rows:
            return []

        session_ids = list({r["session_id"] for r in rows if r.get("session_id")})
        sess_res = client.table("sessions").select("id, employee_id, date, employees(name, employee_code)").in_("id", session_ids).execute()
        sess_map = {}
        for s in (sess_res.data or []):
            emp = s.get("employees") or {}
            sess_map[s["id"]] = {
                "date": s.get("date", ""),
                "emp_name": emp.get("name", "Employee"),
                "employee_code": emp.get("employee_code", "---")
            }

        # Query browsers used in these sessions to associate with website visits
        browser_processes = list(tracker_core.BROWSER_PROCESSES)
        app_res = client.table("app_usage").select("session_id, app_name, duration_sec").in_("session_id", session_ids).in_("app_name", browser_processes).execute()
        sess_browser_map = {}
        for a in (app_res.data or []):
            sid = a["session_id"]
            friendly = tracker_core.get_browser_friendly_name(a["app_name"]) or "Web Browser"
            # Keep browser with highest duration
            if sid not in sess_browser_map or a.get("duration_sec", 0) > sess_browser_map[sid][1]:
                sess_browser_map[sid] = (friendly, a.get("duration_sec", 0))

        result = []
        for r in rows:
            sid = r.get("session_id")
            s_info = sess_map.get(sid, {})
            b_info = sess_browser_map.get(sid, ("Google Chrome", 0))
            result.append({
                "id": r["id"],
                "session_id": sid,
                "emp_name": s_info.get("emp_name", "Employee"),
                "employee_code": s_info.get("employee_code", "---"),
                "date": s_info.get("date", ""),
                "domain": r.get("domain", "web-browsing"),
                "browser": b_info[0],
                "duration_sec": r.get("duration_sec", 0)
            })
        return result
    except Exception as e:
        print("[Supabase Error] get_all_website_usage:", e)
        return []

def get_all_browser_usage(limit: int = 250) -> List[Dict[str, Any]]:
    """Retrieves dedicated browser usage logs across all workstations."""
    try:
        import tracker_core
        client = get_supabase_client()
        browser_processes = list(tracker_core.BROWSER_PROCESSES)
        app_res = client.table("app_usage").select("id, session_id, app_name, duration_sec").in_("app_name", browser_processes).order("duration_sec", desc=True).limit(limit).execute()
        rows = app_res.data or []
        if not rows:
            return []

        session_ids = list({r["session_id"] for r in rows if r.get("session_id")})
        sess_res = client.table("sessions").select("id, employee_id, date, employees(name, employee_code)").in_("id", session_ids).execute()
        sess_map = {}
        for s in (sess_res.data or []):
            emp = s.get("employees") or {}
            sess_map[s["id"]] = {
                "date": s.get("date", ""),
                "emp_name": emp.get("name", "Employee"),
                "employee_code": emp.get("employee_code", "---")
            }

        result = []
        for r in rows:
            sid = r.get("session_id")
            s_info = sess_map.get(sid, {})
            friendly = tracker_core.get_browser_friendly_name(r["app_name"]) or "Web Browser"
            result.append({
                "id": r["id"],
                "session_id": sid,
                "emp_name": s_info.get("emp_name", "Employee"),
                "employee_code": s_info.get("employee_code", "---"),
                "date": s_info.get("date", ""),
                "browser_name": friendly,
                "process_name": r["app_name"],
                "duration_sec": r.get("duration_sec", 0)
            })
        return result
    except Exception as e:
        print("[Supabase Error] get_all_browser_usage:", e)
        return []

def get_all_apps_usage(limit: int = 250) -> List[Dict[str, Any]]:
    """Retrieves all application usage logs across workstations with categorization."""
    try:
        import tracker_core
        client = get_supabase_client()
        app_res = client.table("app_usage").select("id, session_id, app_name, duration_sec").order("duration_sec", desc=True).limit(limit).execute()
        rows = app_res.data or []
        if not rows:
            return []

        session_ids = list({r["session_id"] for r in rows if r.get("session_id")})
        sess_res = client.table("sessions").select("id, employee_id, date, employees(name, employee_code)").in_("id", session_ids).execute()
        sess_map = {}
        for s in (sess_res.data or []):
            emp = s.get("employees") or {}
            sess_map[s["id"]] = {
                "date": s.get("date", ""),
                "emp_name": emp.get("name", "Employee"),
                "employee_code": emp.get("employee_code", "---")
            }

        result = []
        for r in rows:
            sid = r.get("session_id")
            s_info = sess_map.get(sid, {})
            disp = tracker_core.get_app_display_info(r["app_name"])
            result.append({
                "id": r["id"],
                "session_id": sid,
                "emp_name": s_info.get("emp_name", "Employee"),
                "employee_code": s_info.get("employee_code", "---"),
                "date": s_info.get("date", ""),
                "app_name": r["app_name"],
                "friendly_name": disp["friendly_name"],
                "category": disp["category"],
                "duration_sec": r.get("duration_sec", 0)
            })
        return result
    except Exception as e:
        print("[Supabase Error] get_all_apps_usage:", e)
        return []

def get_browser_website_analytics() -> Dict[str, Any]:
    """Generates comprehensive analytics for browsers and websites across all workstations."""
    websites = get_all_website_usage(200)
    browsers = get_all_browser_usage(200)
    apps = get_all_apps_usage(200)

    # Compute total browsing seconds
    total_browsing_sec = sum(b.get("duration_sec", 0) for b in browsers)

    # Browser share breakdown
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

    # Website totals
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


def update_all_employee_shifts(start_time: str, end_time: str) -> bool:
    """Updates shift start and end times for all employees across the company."""
    try:
        client = get_supabase_client()
        res = client.table("employees").update({
            "shift_start": start_time,
            "shift_end": end_time
        }).neq("id", 0).execute()
        return bool(res.data)
    except Exception as e:
        print("[Supabase Error] update_all_employee_shifts:", e)
        return False
