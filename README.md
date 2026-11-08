# WorkLogix ⏱️

> **Automated Workstation Activity & Shift Tracking System**  
> Modern, real-time desktop monitoring agent with centralized Cloud Supabase PostgreSQL sync and an advanced multi-tab Admin Timesheet Portal.

---

## 🎯 Key Capabilities

1. **Individual Employee Shift Schedules**:
   - Each employee can be assigned personalized shift windows (e.g. `09:30 - 18:00`).
   - **Hands-Free Shift Auto-Start/Stop**: Starts tracking automatically when the employee's shift begins, and clocks out when the shift ends.
   - **Overtime & Manual Session Protection**: Unscheduled after-hours work or manual sessions remain active until explicitly clocked out.
   - **Early Clock-Out Memory**: Respects early manual departure without repeatedly forcing the employee back into work on the same day.

2. **Native Windows Desktop Tracker (PySide6 / Qt)**:
   - Quiet background monitoring minimized to the Windows System Tray.
   - Zero-overhead native hardware idle detection (`GetLastInputInfo` on `WinSta0\Default`).
   - Fullscreen/maximized geometry state memory across tray minimize/restore cycles.
   - High-contrast Light and Dark mode interfaces.
   - Windows Startup integration via `python autostart.py enable`.

3. **Active Application & Website Domain Tracking**:
   - Non-invasive detection of foreground applications and active browser domains (Google Chrome, Microsoft Edge, Brave, Mozilla Firefox, Opera, Vivaldi) without requiring browser extensions.
   - Accurately tallies active working time, idle time, and lunch breaks.

4. **Multi-Tab Admin Analytics Portal**:
   - **Timesheets & Audit Filter**: Filter by individual employee, date range presets (*Today*, *This Week*, *This Month*), or custom dates.
   - **Employee Deep-Dive Profile**: Top applications, top websites visited, average daily active time, and chronological shift logs.
   - **Daily Attendance Dashboard**: Roster breakdown of present/absent employees, login/logout timestamps, and active work ratios.
   - **Monthly Timesheets**: Company-wide aggregation with one-click multi-sheet Excel export (`.xlsx`).
   - **Employee & Shift Management**: Add, update, or remove employees and configure individual shift hours, PINs, and idle thresholds.
   - **Persistent HMAC Session Security**: Survives server reloads without random session expirations.

5. **Cloud Database (Supabase PostgreSQL) + Local SQLite**:
   - Dual-engine data layer: Seamlessly syncs to Supabase Cloud PostgreSQL with transparent local SQLite fallback.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11 / 3.12 / 3.13)
- Windows 10 or 11 (for desktop hardware tracking features)

### 2. Installation
```powershell
# Clone the repository
git clone https://github.com/Dhyanesh2603/worklogix.git
cd worklogix

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in your Supabase credentials:
```powershell
Copy-Item .env.example .env
```
```ini
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-service-role-or-anon-key
USE_SUPABASE=true
```

---

## 💻 Running the Application

### Option A: Desktop Employee Tracker
```powershell
python main.py
```
- Minimize the application to keep it running silently in the Windows System Tray.
- To set the desktop tracker to start automatically when Windows boots:
  ```powershell
  python autostart.py enable
  ```

### Option B: Web & Admin Management Portal
```powershell
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```
- **Employee Web View**: [http://localhost:8000/](http://localhost:8000/)
- **Admin Management Portal**: [http://localhost:8000/admin](http://localhost:8000/admin)  
  *(Default Credentials — Username: `admin` | Password: `admin123`)*

---

## 📦 Building Standalone Executable (.exe)

To bundle the desktop tracker into a standalone `.exe`:
```powershell
python -m PyInstaller --noconfirm OfficeTracker.spec
```
The compiled single-file binary will be placed inside `dist/OfficeTracker.exe`.

---

## 📁 Repository Structure

```
worklogix/
├── main.py              # PySide6 desktop application GUI & system tray manager
├── web_app.py           # FastAPI server & multi-tab admin dashboard portal
├── tracker_core.py      # Win32 hardware idle detection & shift scheduler engine
├── database.py          # Unified data access routing layer
├── supabase_db.py       # Cloud Supabase PostgREST database driver
├── exporter.py          # Excel (.xlsx) timesheet & attendance report generator
├── autostart.py         # Windows Registry integration for automatic boot startup
├── test_suite.py        # Automated test verification suite
├── test_tracker.py      # Core engine unit tests
├── requirements.txt     # Python project dependencies
├── .env.example         # Environment variables template
└── README.md            # Project documentation
```

---

## 🛡️ License

This project is licensed under the MIT License.
