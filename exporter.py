import os
import csv
from datetime import datetime
from typing import Optional, List, Dict, Any
import database

def format_duration(seconds: int) -> str:
    """Helper to convert seconds into HH:MM:SS or 'Xh Ym Zs'."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def export_to_excel(
    output_file: str,
    employee_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None
) -> str:
    """Exports filtered sessions and their detailed intervals to an Excel spreadsheet."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()

    # --- Sheet 1: Attendance Summary ---
    ws_summary = wb.active
    ws_summary.title = "Attendance Summary"

    headers_summary = [
        "Session ID", "Employee Name", "Emp Code", "Assigned Shift", "Date",
        "Login Time", "Logout Time", "Active Work Time",
        "Inactive Time", "Lunch Break", "Total Shift Span", "Status"
    ]
    ws_summary.append(headers_summary)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid") # Executive Slate
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color="E2E8F0"),
        right=Side(style='thin', color="E2E8F0"),
        top=Side(style='thin', color="E2E8F0"),
        bottom=Side(style='thin', color="E2E8F0")
    )

    for col_num in range(1, len(headers_summary) + 1):
        cell = ws_summary.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    sessions = database.get_filtered_sessions(employee_id, start_date, end_date, status)
    session_ids = [s["id"] for s in sessions]

    for row_idx, s in enumerate(sessions, start=2):
        total_span = (s["total_active_sec"] or 0) + (s["total_inactive_sec"] or 0) + (s["total_lunch_sec"] or 0)
        shift_text = f"{s.get('shift_start', '09:30')} - {s.get('shift_end', '18:00')}"
        row_data = [
            s["id"],
            s["employee_name"],
            s["employee_code"],
            shift_text,
            s["date"],
            s["login_time"],
            s["logout_time"] or "In Progress",
            format_duration(s["total_active_sec"] or 0),
            format_duration(s["total_inactive_sec"] or 0),
            format_duration(s["total_lunch_sec"] or 0),
            format_duration(total_span),
            s["status"]
        ]
        ws_summary.append(row_data)

        # Style data cells
        for col_num in range(1, len(row_data) + 1):
            cell = ws_summary.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border
            if col_num == 12: # Status column
                if s["status"] == "COMPLETED":
                    cell.font = Font(color="059669", bold=True) # Emerald
                else:
                    cell.font = Font(color="D97706", bold=True) # Amber

    # Auto-adjust column widths
    for col in ws_summary.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws_summary.column_dimensions[col_letter].width = max(max_len + 4, 13)

    # --- Sheet 2: Detailed Activity Intervals ---
    ws_details = wb.create_sheet(title="Activity Logs (Intervals)")
    headers_details = [
        "Log ID", "Session ID", "Event Type", "Start Time", "End Time", "Duration", "Duration (Sec)", "Notes"
    ]
    ws_details.append(headers_details)

    for col_num in range(1, len(headers_details) + 1):
        cell = ws_details.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    conn = database.get_connection()
    cursor = conn.cursor()

    if session_ids:
        placeholders = ','.join(['?'] * len(session_ids))
        cursor.execute(f"""
            SELECT a.id, a.session_id, a.event_type, a.start_time, a.end_time, a.duration_sec, a.note
            FROM activity_logs a
            WHERE a.session_id IN ({placeholders})
            ORDER BY a.session_id DESC, a.id ASC
        """, session_ids)
    else:
        cursor.execute("""
            SELECT a.id, a.session_id, a.event_type, a.start_time, a.end_time, a.duration_sec, a.note
            FROM activity_logs a
            ORDER BY a.session_id DESC, a.id ASC
            LIMIT 500
        """)
    logs = cursor.fetchall()

    fill_active = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid") # Emerald Tint
    fill_inactive = PatternFill(start_color="FFFBEB", end_color="FFFBEB", fill_type="solid") # Amber Tint
    fill_lunch = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Slate Tint

    for row_idx, log in enumerate(logs, start=2):
        event = log["event_type"]
        row_data = [
            log["id"],
            log["session_id"],
            event,
            log["start_time"],
            log["end_time"] or "In Progress",
            format_duration(log["duration_sec"] or 0),
            log["duration_sec"],
            log["note"] or ""
        ]
        ws_details.append(row_data)

        for col_num in range(1, len(row_data) + 1):
            cell = ws_details.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border
            if col_num == 3: # Event Type column
                if event == "ACTIVE":
                    cell.fill = fill_active
                    cell.font = Font(color="059669", bold=True)
                elif event == "INACTIVE":
                    cell.fill = fill_inactive
                    cell.font = Font(color="D97706", bold=True)
                elif event == "LUNCH":
                    cell.fill = fill_lunch
                    cell.font = Font(color="475569", bold=True)

    for col in ws_details.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws_details.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # --- Sheet 3: Website Domain Usage ---
    ws_web = wb.create_sheet(title="Websites Visited")
    headers_web = [
        "Record ID", "Session ID", "Employee Name", "Date", "Website / Domain", "Time Spent", "Seconds"
    ]
    ws_web.append(headers_web)

    for col_num in range(1, len(headers_web) + 1):
        cell = ws_web.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    if session_ids:
        placeholders = ','.join(['?'] * len(session_ids))
        cursor.execute(f"""
            SELECT w.id, w.session_id, e.name as emp_name, s.date, w.domain, w.duration_sec
            FROM website_usage w
            JOIN sessions s ON w.session_id = s.id
            JOIN employees e ON s.employee_id = e.id
            WHERE w.session_id IN ({placeholders})
            ORDER BY w.session_id DESC, w.duration_sec DESC
        """, session_ids)
    else:
        cursor.execute("""
            SELECT w.id, w.session_id, e.name as emp_name, s.date, w.domain, w.duration_sec
            FROM website_usage w
            JOIN sessions s ON w.session_id = s.id
            JOIN employees e ON s.employee_id = e.id
            ORDER BY w.session_id DESC, w.duration_sec DESC
            LIMIT 500
        """)
    web_logs = cursor.fetchall()
    conn.close()

    for row_idx, w in enumerate(web_logs, start=2):
        row_data = [
            w["id"],
            w["session_id"],
            w["emp_name"],
            w["date"],
            w["domain"],
            format_duration(w["duration_sec"] or 0),
            w["duration_sec"]
        ]
        ws_web.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws_web.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border

    for col in ws_web.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws_web.column_dimensions[col_letter].width = max(max_len + 4, 14)

    wb.save(output_file)
    return output_file

def export_monthly_report_to_excel(year: int, month: int, output_file: str) -> str:
    """Exports a dedicated monthly management report with employee timesheets and website stats."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color="E2E8F0"),
        right=Side(style='thin', color="E2E8F0"),
        top=Side(style='thin', color="E2E8F0"),
        bottom=Side(style='thin', color="E2E8F0")
    )

    monthly_data = database.get_monthly_report(year, month)

    # --- Sheet 1: Monthly Attendance Summary ---
    ws1 = wb.active
    ws1.title = "Monthly Summary"

    headers1 = [
        "Employee Name", "Emp Code", "Assigned Shift", "Days Worked",
        "Total Active Work", "Total Inactive Time", "Total Lunch Break",
        "Avg Daily Active", "Inactivity Rate (%)", "Top Visited Website"
    ]
    ws1.append(headers1)

    for col_num in range(1, len(headers1) + 1):
        cell = ws1.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    for row_idx, emp in enumerate(monthly_data["employees"], start=2):
        row_data = [
            emp["name"],
            emp["employee_code"],
            f"{emp['shift_start']} - {emp['shift_end']}",
            emp["days_worked"],
            format_duration(emp["total_active_sec"]),
            format_duration(emp["total_inactive_sec"]),
            format_duration(emp["total_lunch_sec"]),
            format_duration(emp["avg_active_sec_per_day"]),
            f"{emp['inactivity_pct']}%",
            emp["top_website"]
        ]
        ws1.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws1.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border
            if col_num == 5:
                cell.font = Font(color="059669", bold=True)
            elif col_num == 6:
                cell.font = Font(color="D97706", bold=True)

    for col in ws1.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws1.column_dimensions[col_letter].width = max(max_len + 4, 14)

    # --- Sheet 2: Daily Records in this Month ---
    ws2 = wb.create_sheet(title="Daily Timesheet Logs")
    headers2 = [
        "Date", "Employee Name", "Emp Code", "Login Time", "Logout Time",
        "Active Work Time", "Inactive Time", "Lunch Break", "Status"
    ]
    ws2.append(headers2)

    for col_num in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    month_str = f"{year:04d}-{month:02d}"
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.date, e.name as emp_name, e.employee_code, s.login_time, s.logout_time,
               s.total_active_sec, s.total_inactive_sec, s.total_lunch_sec, s.status
        FROM sessions s
        JOIN employees e ON s.employee_id = e.id
        WHERE s.date LIKE ?
        ORDER BY s.date ASC, e.name ASC
    """, (f"{month_str}%",))
    daily_records = cursor.fetchall()
    conn.close()

    for row_idx, r in enumerate(daily_records, start=2):
        row_data = [
            r["date"],
            r["emp_name"],
            r["employee_code"],
            r["login_time"],
            r["logout_time"] or "In Progress",
            format_duration(r["total_active_sec"] or 0),
            format_duration(r["total_inactive_sec"] or 0),
            format_duration(r["total_lunch_sec"] or 0),
            r["status"]
        ]
        ws2.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws2.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border

    for col in ws2.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws2.column_dimensions[col_letter].width = max(max_len + 4, 14)

    # --- Sheet 3: Monthly Website Logs ---
    ws3 = wb.create_sheet(title="Monthly Websites Visited")
    headers3 = [
        "Employee Name", "Emp Code", "Website / Domain", "Total Time Spent", "Seconds"
    ]
    ws3.append(headers3)

    for col_num in range(1, len(headers3) + 1):
        cell = ws3.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    web_usage = database.get_monthly_website_usage(year, month)
    for row_idx, w in enumerate(web_usage, start=2):
        row_data = [
            w["emp_name"],
            w["employee_code"],
            w["domain"],
            format_duration(w["duration_sec"]),
            w["duration_sec"]
        ]
        ws3.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws3.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border

    for col in ws3.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws3.column_dimensions[col_letter].width = max(max_len + 4, 14)

    wb.save(output_file)
    return output_file

def export_daily_report_to_excel(date_str: str, output_file: str) -> str:
    """Exports a single day's attendance and website summary for all employees."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color="E2E8F0"),
        right=Side(style='thin', color="E2E8F0"),
        top=Side(style='thin', color="E2E8F0"),
        bottom=Side(style='thin', color="E2E8F0")
    )

    ws = wb.active
    ws.title = f"Report {date_str}"

    headers = [
        "Employee Name", "Emp Code", "Assigned Shift", "Login Time", "Logout Time",
        "Active Work Time", "Inactive Time", "Lunch Break", "Top App", "Top Website", "Status"
    ]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    daily_data = database.get_daily_report(date_str)
    for row_idx, r in enumerate(daily_data["records"], start=2):
        row_data = [
            r["employee_name"],
            r["employee_code"],
            f"{r['shift_start']} - {r['shift_end']}",
            r["login_time"],
            r["logout_time"] or "In Progress",
            format_duration(r["total_active_sec"] or 0),
            format_duration(r["total_inactive_sec"] or 0),
            format_duration(r["total_lunch_sec"] or 0),
            r["top_app"],
            r["top_website"],
            r["status"]
        ]
        ws.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_idx, column=col_num)
            cell.alignment = center_align
            cell.border = thin_border

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    wb.save(output_file)
    return output_file

def export_to_csv(output_file: str, session_id: Optional[int] = None) -> str:
    """Exports activity logs to standard CSV."""
    conn = database.get_connection()
    cursor = conn.cursor()
    
    if session_id:
        cursor.execute("""
            SELECT id, session_id, event_type, start_time, end_time, duration_sec, note
            FROM activity_logs
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,))
    else:
        cursor.execute("""
            SELECT a.id, a.session_id, e.name as emp_name, a.event_type, a.start_time, a.end_time, a.duration_sec, a.note
            FROM activity_logs a
            JOIN sessions s ON a.session_id = s.id
            JOIN employees e ON s.employee_id = e.id
            ORDER BY a.session_id DESC, a.id ASC
            LIMIT 1000
        """)
    rows = cursor.fetchall()
    conn.close()

    with open(output_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if session_id:
            writer.writerow(["Log ID", "Session ID", "Event Type", "Start Time", "End Time", "Duration (Sec)", "Duration Formatted", "Note"])
            for r in rows:
                writer.writerow([r["id"], r["session_id"], r["event_type"], r["start_time"], r["end_time"], r["duration_sec"], format_duration(r["duration_sec"]), r["note"]])
        else:
            writer.writerow(["Log ID", "Session ID", "Employee", "Event Type", "Start Time", "End Time", "Duration (Sec)", "Duration Formatted", "Note"])
            for r in rows:
                writer.writerow([r["id"], r["session_id"], r["emp_name"], r["event_type"], r["start_time"], r["end_time"], r["duration_sec"], format_duration(r["duration_sec"]), r["note"]])

    return output_file
