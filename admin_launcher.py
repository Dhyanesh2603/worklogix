import sys
import os
try:
    import certifi
    ca_bundle = certifi.where()
    if getattr(sys, 'frozen', False):
        base_meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        for cand in [
            os.path.join(base_meipass, 'certifi', 'cacert.pem'),
            os.path.join(base_meipass, 'cacert.pem'),
            os.path.join(os.path.dirname(sys.executable), 'cacert.pem')
        ]:
            if os.path.exists(cand):
                ca_bundle = cand
                break
    os.environ['SSL_CERT_FILE'] = ca_bundle
    os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle
except Exception:
    pass
import time
import socket
import threading
import webbrowser
import traceback
import urllib.request
from datetime import datetime
from typing import Optional

# Setup directories and logging
if getattr(sys, 'frozen', False):
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.append(base_dir)

# Ensure persistent debug log in ~/.worklogix/admin_portal.log
try:
    log_dir = os.path.join(os.path.expanduser("~"), ".worklogix")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "admin_portal.log")
    log_file = open(log_path, "a", encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file
except Exception:
    pass

print(f"\n--- WorkLogix Admin Portal Session: {datetime.now()} ---")
print(f"Base Directory: {base_dir}")
print(f"Executable: {sys.executable}")

# Load environment variables
from dotenv import load_dotenv
env_file = os.path.join(base_dir, ".env")
if os.path.exists(env_file):
    print(f"Loading environment from: {env_file}")
    load_dotenv(env_file)

exe_env = os.path.join(os.path.dirname(sys.executable), ".env")
if os.path.exists(exe_env):
    print(f"Loading environment from: {exe_env}")
    load_dotenv(exe_env)

# PySide6 GUI imports
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSystemTrayIcon, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor, QFont, QPen

import uvicorn
from web_app import app

def create_admin_icon() -> QIcon:
    """Generates an administrative badge icon in memory."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Base shape - Deep Charcoal Navy
    brush = QBrush(QColor("#0F172A"))
    painter.setBrush(brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

    # Dial / Shield accent - Sky Blue
    accent_pen = QPen(QColor("#38BDF8"), 3)
    painter.setPen(accent_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(14, 14, 36, 36)

    # Center graph bar / clock accent
    line_pen = QPen(QColor("#F8FAFC"), 3)
    painter.setPen(line_pen)
    painter.drawLine(32, 32, 32, 22)
    painter.drawLine(32, 32, 42, 32)
    painter.end()
    return QIcon(pixmap)

def check_admin_endpoint(url: str) -> bool:
    """Verifies that the /admin HTTP endpoint responds with 200 OK."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WorkLogixAdminLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def find_available_port(preferred_port: int = 8000) -> int:
    """Checks if preferred port can be bound; if not, selects an available port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', preferred_port))
            return preferred_port
    except Exception as e:
        print(f"Port {preferred_port} bind check: {e}")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.error: Optional[str] = None
        self.is_running = False

        # Explicit uvicorn configuration with h11 and asyncio to avoid missing optional packages
        self.config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            loop="asyncio",
            http="h11",
            ws="none",
            lifespan="off",
            log_level="info",
            access_log=False
        )
        self.server = uvicorn.Server(self.config)

    def run(self):
        try:
            print(f"Starting uvicorn server on http://{self.host}:{self.port}...")
            self.is_running = True
            self.server.run()
            self.is_running = False
            print("Uvicorn server exited normally.")
        except Exception as e:
            self.is_running = False
            self.error = str(e)
            print(f"Fatal uvicorn server error: {e}")
            traceback.print_exc()

    def stop(self):
        self.server.should_exit = True

class AdminLauncherWindow(QMainWindow):
    def __init__(self, host: str, port: int, server_thread: Optional[ServerThread] = None):
        super().__init__()
        self.host = host
        self.port = port
        self.server_thread = server_thread
        self.admin_url = f"http://{host}:{port}/admin"
        self.browser_opened = False
        self.startup_retries = 0

        self.setWindowTitle("WorkLogix Admin Portal")
        self.setFixedSize(520, 390)
        self.setWindowIcon(create_admin_icon())

        self.init_ui()
        self.setup_tray()

        # Polling timer to verify server readiness before opening browser
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.check_server_startup)
        self.poll_timer.start(300)

    def init_ui(self):
        central = QWidget()
        central.setStyleSheet("""
            QWidget {
                background-color: #F8FAFC;
                color: #0F172A;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        # Header Section
        lbl_title = QLabel("WorkLogix Admin Portal")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        lbl_sub = QLabel("Centralized Timesheets, Shifts & Attendance Service")
        lbl_sub.setStyleSheet("font-size: 13px; color: #64748B;")
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_sub)

        # Status Card Frame
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        # Status Pill Row
        row_status = QHBoxLayout()
        self.lbl_badge = QLabel("  STARTING  ")
        self.lbl_badge.setStyleSheet("""
            background-color: #FEF3C7;
            color: #92400E;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 12px;
            border: 1px solid #FDE68A;
        """)
        self.lbl_url = QLabel(self.admin_url)
        self.lbl_url.setStyleSheet("font-size: 13px; font-weight: 600; color: #0F172A; font-family: 'Consolas', monospace;")
        row_status.addWidget(self.lbl_badge)
        row_status.addWidget(self.lbl_url)
        row_status.addStretch()
        card_layout.addLayout(row_status)

        self.lbl_desc = QLabel("Initializing admin management service...")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("font-size: 12px; color: #64748B; line-height: 1.4;")
        card_layout.addWidget(self.lbl_desc)

        layout.addWidget(card)

        # Primary Open Browser Action
        self.btn_open = QPushButton("Open Admin Dashboard in Browser")
        self.btn_open.setFixedHeight(42)
        self.btn_open.setEnabled(False)
        self.btn_open.setStyleSheet("""
            QPushButton {
                background-color: #0F172A;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 600;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1E293B;
            }
            QPushButton:disabled {
                background-color: #E2E8F0;
                color: #94A3B8;
            }
        """)
        self.btn_open.clicked.connect(self.open_browser)
        layout.addWidget(self.btn_open)

        # Secondary Actions
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_copy = QPushButton("Copy URL")
        self.btn_copy.setFixedHeight(36)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
            }
        """)
        self.btn_copy.clicked.connect(self.copy_url)
        btn_layout.addWidget(self.btn_copy)

        self.btn_minimize = QPushButton("Minimize to Tray")
        self.btn_minimize.setFixedHeight(36)
        self.btn_minimize.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
            }
        """)
        self.btn_minimize.clicked.connect(self.hide)
        btn_layout.addWidget(self.btn_minimize)

        self.btn_stop = QPushButton("Stop & Exit")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #FECACA;
                color: #DC2626;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #FEF2F2;
                border-color: #F87171;
            }
        """)
        self.btn_stop.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_stop)

        layout.addLayout(btn_layout)

    def check_server_startup(self):
        """Polls local endpoint until server responds, then opens browser."""
        self.startup_retries += 1
        is_ready = check_admin_endpoint(self.admin_url)

        if is_ready:
            self.poll_timer.stop()
            self.lbl_badge.setText("  ONLINE  ")
            self.lbl_badge.setStyleSheet("""
                background-color: #ECFDF5;
                color: #065F46;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 12px;
                border: 1px solid #A7F3D0;
            """)
            self.lbl_desc.setText("The management service is active. Use your browser to administer employee profiles, review shift logs, and export monthly payroll spreadsheets.")
            self.btn_open.setEnabled(True)

            if not self.browser_opened:
                self.browser_opened = True
                self.open_browser()
        elif self.server_thread and self.server_thread.error:
            self.poll_timer.stop()
            self.lbl_badge.setText("  ERROR  ")
            self.lbl_badge.setStyleSheet("""
                background-color: #FEF2F2;
                color: #991B1B;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 12px;
                border: 1px solid #FECACA;
            """)
            self.lbl_desc.setText(f"Server error: {self.server_thread.error}")
        elif self.startup_retries > 30: # 9 seconds timeout
            self.poll_timer.stop()
            self.lbl_badge.setText("  UNREACHABLE  ")
            self.lbl_desc.setText("Server took too long to respond. Check log file for details.")

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(create_admin_icon())
        self.tray.setToolTip("WorkLogix Admin Portal")

        menu = QMenu()
        act_open = menu.addAction("Open Admin Dashboard")
        act_open.triggered.connect(self.open_browser)

        act_show = menu.addAction("Show Status Window")
        act_show.triggered.connect(self.show_window)

        menu.addSeparator()

        act_exit = menu.addAction("Shut Down Admin Service")
        act_exit.triggered.connect(self.close)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def open_browser(self):
        webbrowser.open(self.admin_url)

    def copy_url(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.admin_url)
        self.btn_copy.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.btn_copy.setText("Copy URL"))

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Stopping the Admin Portal will shut down the management server.\n\nDo you want to proceed and exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.tray.hide()
            if self.server_thread:
                self.server_thread.stop()
            event.accept()
        else:
            event.ignore()

def main():
    app_qt = QApplication(sys.argv)
    
    host = "127.0.0.1"
    
    # 1. Check if WorkLogix admin is already running on port 8000
    if check_admin_endpoint("http://127.0.0.1:8000/admin"):
        print("Admin portal is already active on port 8000. Opening browser...")
        webbrowser.open("http://127.0.0.1:8000/admin")
        window = AdminLauncherWindow(host=host, port=8000, server_thread=None)
        window.show()
        sys.exit(app_qt.exec())

    # 2. Find available port
    port = find_available_port(8000)

    # 3. Start uvicorn server in background thread
    server_thread = ServerThread(host=host, port=port)
    server_thread.start()

    window = AdminLauncherWindow(host=host, port=port, server_thread=server_thread)
    window.show()

    exit_code = app_qt.exec()
    server_thread.stop()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
