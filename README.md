# WorkLogix

Enterprise Workstation Activity Monitoring and Timesheet Management System

WorkLogix is an automated, real-time desktop monitoring and shift tracking platform designed for organizations requiring accurate visibility into employee workstation utilization. The platform combines a low-overhead native Windows desktop tracking client, centralized cloud data synchronization via Supabase PostgreSQL, and a multi-tab administrative analytics dashboard.

---

## System Architecture

The WorkLogix platform comprises three primary subsystems:

1. **Native Desktop Monitoring Client (`main.py`, `tracker_core.py`)**  
   A PySide6 (Qt) desktop application running on employee workstations. It monitors user presence, records application focus and active browser domains, and operates silently from the Windows System Tray with minimal CPU and memory overhead.

2. **Centralized Administration and Timesheet Portal (`web_app.py`, `admin_launcher.py`)**  
   A high-performance FastAPI web service providing real-time oversight of active personnel, automated attendance rosters, customizable timesheet filters, and multi-sheet Excel report exports. It can be hosted on a central server or run locally via a dedicated desktop executable.

3. **Unified Data Persistence Layer (`database.py`, `supabase_db.py`)**  
   A dual-engine persistence architecture that connects natively to Supabase Cloud PostgreSQL with transparent failover to a local SQLite database when disconnected from the network.

---

## Core Capabilities

### Automated Shift Scheduling and Session Management
- **Individualized Shift Schedules**: Supports distinct work shifts per employee (e.g., 09:30 to 18:00) with configurable idle thresholds.
- **Hands-Free Shift Transitions**: Automatically initiates session tracking when an assigned shift window commences and records clock-out events when the shift concludes.
- **After-Hours and Overtime Protection**: Manual sessions initiated outside regular schedule boundaries are protected from premature termination until explicitly concluded by the user.
- **Persistent Departure Recognition**: Remembers manual early clock-outs to prevent unexpected auto-restarts within the same calendar day.

### Hardware Idle and Activity Detection
- **Native Windows API Integration**: Uses low-level `GetLastInputInfo` hooks against the interactive desktop window station (`WinSta0\Default`) to capture physical mouse and keyboard inactivity without polling overhead.
- **Context-Aware Focus Tracking**: Identifies the foreground application window and extracts active web domains from major Chromium and Gecko browsers (Google Chrome, Microsoft Edge, Brave, Mozilla Firefox, Opera, and Vivaldi) without requiring third-party browser extensions.
- **State Partitioning**: Categorizes total shift time into distinct buckets: Active Working Time, Idle/Away Time, and Meal/Lunch Breaks.

### Administrative Analytics and Compliance Portal
- **Consolidated Shift Roster**: Real-time overview of current employee status, active application focus, shift start timestamps, and elapsed durations.
- **Granular Timesheet Filtering**: Query records by employee identity, predefined date windows (Today, This Week, This Month), or arbitrary date ranges.
- **Activity Profile Inspection**: Deep-dive analytics detailing top application usage, visited domain distributions, and daily timeline intervals per staff member.
- **Automated Excel Export**: Generates standardized, formatted multi-sheet workbooks (`.xlsx`) containing aggregate attendance metrics and comprehensive audit logs.
- **Employee Directory Management**: Add, update, or deactivate employee profiles, configure authentication PINs, and adjust individual shift parameters.

### Enterprise Security and Reliability
- **Stateless Administrative Sessions**: Employs cryptographically signed HMAC tokens (`SHA-256`) with configurable expiration, ensuring session stability across web service restarts.
- **Credential Protection**: Admin passwords and employee PINs are salted and hashed using PBKDF2-HMAC-SHA256 with 100,000 iterations.
- **Resilient Maximization State**: Desktop client preserves window geometry and maximized layout states across background system tray transitions.

---

## Technical Specifications

| Parameter | Specification |
| :--- | :--- |
| Supported Operating Systems | Windows 10, Windows 11, Windows Server 2019/2022 |
| Runtime Environment | Python 3.10 or higher |
| GUI Framework | PySide6 (Qt 6.x) |
| Web Service Framework | FastAPI, Starlette, Uvicorn |
| Primary Database | Supabase (Cloud PostgreSQL 15+) |
| Fallback Database | SQLite 3 |
| Export Formats | Microsoft Excel (.xlsx via openpyxl) |

---

## Installation and Configuration

### Prerequisites
Ensure Python 3.10+ and Git are installed and available on your system path.

### 1. Clone Repository
```powershell
git clone https://github.com/Dhyanesh2603/worklogix.git
cd worklogix
```

### 2. Configure Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Generate a local `.env` configuration file from the provided template:
```powershell
Copy-Item .env.example .env
```
Populate the configuration variables in `.env`:
```ini
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-service-role-or-anon-key
USE_SUPABASE=true
```

---

## Application Execution

### Desktop Workstation Client
Launch the employee monitoring client:
```powershell
python main.py
```
To register the application for automatic launch on Windows boot:
```powershell
python autostart.py enable
```
To remove the automatic startup registration:
```powershell
python autostart.py disable
```

### Administrative Web Portal
Start the FastAPI server via Uvicorn:
```powershell
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```
- Web Portal Interface: `http://localhost:8000/admin`
- Employee Browser Portal: `http://localhost:8000/`
- Default Administrator Credentials:
  - Username: `admin`
  - Password: `admin123`

### Desktop Administrative Launcher
Alternatively, run the dedicated administrative launcher window which automatically manages the server process and launches the system default browser:
```powershell
python admin_launcher.py
```

---

## Standalone Executable Compilation

Standalone executables for both the workstation client and administrative controller can be compiled using PyInstaller.

### 1. Workstation Client Executable
```powershell
python -m PyInstaller --noconfirm OfficeTracker.spec
```
Output: `dist/OfficeTracker.exe`

### 2. Administrative Portal Executable
```powershell
python -m PyInstaller --noconfirm AdminPortal.spec
```
Output: `dist/AdminPortal.exe`

---

## Repository Structure

```
worklogix/
|-- main.py              # Workstation client application and system tray manager
|-- admin_launcher.py    # Desktop launcher for the administrative web portal
|-- web_app.py           # FastAPI administrative service and timesheet dashboard
|-- tracker_core.py      # Win32 hardware idle detection and shift schedule engine
|-- database.py          # Unified persistence abstraction layer
|-- supabase_db.py       # Supabase Cloud PostgreSQL database client
|-- exporter.py          # Excel workbook (.xlsx) timesheet generation engine
|-- autostart.py         # Windows Startup Registry management utility
|-- test_suite.py        # System verification and regression test suite
|-- test_tracker.py      # Core engine unit tests
|-- requirements.txt     # Pinned Python package dependencies
|-- .env.example         # Environment variable configuration template
|-- .gitignore           # Git ignore definitions for builds, secrets, and caches
`-- README.md            # System documentation
```

---

## Database Schema Overview

The Supabase Cloud PostgreSQL schema incorporates the following relational tables:

- **`admin_users`**: Administrative credentials, password hashes, and cryptographic salts.
- **`employees`**: Employee identities, codes, assigned shift start and end windows, authentication PINs, and idle thresholds.
- **`work_sessions`**: Daily clock-in and clock-out sessions with aggregate active, inactive, and meal durations.
- **`activity_intervals`**: Granular tracking intervals recording individual state transitions (Active, Inactive, Lunch) with exact start and end timestamps.
- **`app_activity_logs`**: Foreground application and active browser domain audit logs per employee session.

---

## Security and Privacy Guidelines

- **Zero Keystroke Logging**: The platform tracks user presence via aggregate Windows input timestamps (`GetLastInputInfo`) and does not record keystroke contents, screen captures, or personal credentials.
- **Transport Security**: All cloud database communication is conducted over TLS-encrypted HTTPS connections to Supabase PostgreSQL endpoints.
- **Environment Isolation**: Production secrets and configuration parameters are maintained exclusively in local environment files and are excluded from source control.

---

## License

This software is released under the MIT License. Refer to the LICENSE file for further terms.
