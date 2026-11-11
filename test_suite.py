import sys
import os
import urllib.request
import json

def run_tests():
    # 1. Employee Auth (Code & PIN)
    req = urllib.request.Request(
        'http://127.0.0.1:8000/api/employee/auth',
        data=json.dumps({'code': 'EMP-001', 'pin': '1234'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    res = urllib.request.urlopen(req)
    emp_auth = json.loads(res.read().decode('utf-8'))
    emp = emp_auth["employee"]
    print(f"[PASS] Employee Auth Successful: {emp['name']} ({emp['employee_code']})")

    # 2. Employee Profile & Shift Retrieval
    req = urllib.request.Request(f"http://127.0.0.1:8000/api/employee/me?employee_id={emp['id']}")
    res = urllib.request.urlopen(req)
    me = json.loads(res.read().decode('utf-8'))
    print(f"[PASS] Employee Session Verified: Assigned Shift {me['shift_start']} to {me['shift_end']}")

    # 3. Admin Login
    req = urllib.request.Request(
        'http://127.0.0.1:8000/api/admin/login',
        data=json.dumps({'username': 'admin', 'password': 'siva@1978'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    res = urllib.request.urlopen(req)
    token = json.loads(res.read().decode('utf-8'))['token']
    print("[PASS] Admin Login Successful")

    # 4. Admin View Employees
    req = urllib.request.Request('http://127.0.0.1:8000/api/admin/employees', headers={'X-Admin-Token': token})
    res = urllib.request.urlopen(req)
    emps = json.loads(res.read().decode('utf-8'))
    print(f"[PASS] Admin Employees Roster: {len(emps)} registered")

    # 5. Admin Update Individual Shift & Idle Threshold
    emp_id = emp['id']
    req = urllib.request.Request(
        f'http://127.0.0.1:8000/api/admin/employees/{emp_id}/shift',
        data=json.dumps({
            'employee_id': emp_id,
            'start_time': '09:00',
            'end_time': '18:00',
            'is_auto_start': True,
            'idle_threshold': 300
        }).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'X-Admin-Token': token}
    )
    res = urllib.request.urlopen(req)
    print("[PASS] Admin Updated Individual Shift:", json.loads(res.read().decode('utf-8')))

    # 6. Admin Daily Report
    req_daily = urllib.request.Request('http://127.0.0.1:8000/api/admin/daily-report', headers={'X-Admin-Token': token})
    today_str = json.loads(urllib.request.urlopen(req_daily).read().decode('utf-8'))['date']
    print(f"[PASS] Daily Report Available for: {today_str}")

    # 7. Admin Monthly Report
    req = urllib.request.Request('http://127.0.0.1:8000/api/admin/monthly-report?year=2026&month=11', headers={'X-Admin-Token': token})
    monthly = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
    print(f"[PASS] Monthly Timesheet Audit for {monthly['month_str']}: {len(monthly['employees'])} employees, {monthly['overall']['total_sessions']} total shifts")

    # 8. Monthly Excel Export
    req = urllib.request.Request('http://127.0.0.1:8000/api/admin/export/monthly?year=2026&month=11', headers={'X-Admin-Token': token})
    excel_data = urllib.request.urlopen(req).read()
    print(f"[PASS] Monthly Excel Report Generated: {len(excel_data)} bytes")

    print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
