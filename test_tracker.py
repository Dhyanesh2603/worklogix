import os
import sys
from datetime import datetime, timedelta
import database
from tracker_core import TrackerEngine, TrackerState
import exporter

def run_tests():
    print("--- 1. Testing Database Initialization ---")
    database.init_db()
    emp_id = database.get_or_create_employee("Test Employee", "TEST-001")
    print(f"Created/Retrieved Employee ID: {emp_id}")
    assert emp_id > 0, "Failed to get employee ID"

    print("--- 2. Testing Tracker Engine & State Transitions ---")
    engine = TrackerEngine(idle_threshold_seconds=10) # 10s threshold for testing

    state_log = []
    interval_log = []

    engine.on_state_change = lambda s: state_log.append(s.value)
    engine.on_interval_logged = lambda inv: interval_log.append(inv)

    # Start day
    engine.start_day(emp_id)
    assert engine.state == TrackerState.ACTIVE
    assert len(state_log) == 1 and state_log[0] == "Active"
    print("Clock in: OK")

    # Simulate 5 seconds active
    for _ in range(5):
        engine.tick()

    # Simulate Lunch Break
    engine.start_lunch()
    assert engine.state == TrackerState.LUNCH
    print("Lunch start: OK")

    for _ in range(3):
        engine.tick()

    # Resume Work
    engine.resume_from_lunch()
    assert engine.state == TrackerState.ACTIVE
    print("Lunch resume: OK")

    # End Day
    engine.end_day()
    assert engine.state == TrackerState.LOGGED_OUT
    print("Clock out: OK")

    print(f"Intervals logged: {len(interval_log)}")
    for inv in interval_log:
        print(f"  -> [{inv['event_type']}] {inv['start_time']} to {inv['end_time']} ({inv['duration_sec']}s)")

    print("--- 3. Testing Excel Export ---")
    test_excel = os.path.join(os.path.dirname(__file__), "test_report.xlsx")
    exporter.export_to_excel(test_excel)
    assert os.path.exists(test_excel), "Excel file was not created"
    print(f"Excel export verified successfully: {test_excel} ({os.path.getsize(test_excel)} bytes)")

    print("\nALL SYSTEM TESTS PASSED SUCCESSFULLY! [PASS]")

if __name__ == "__main__":
    run_tests()
