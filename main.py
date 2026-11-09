import sys
import os
from datetime import datetime, date, time as dtime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame, QLineEdit, QDialog, QSystemTrayIcon, QMenu,
    QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap, QPainter, QBrush, QPen, QPalette

# Ensure local imports work reliably
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database
from tracker_core import TrackerEngine, TrackerState

# ==============================================================================
# UNIFIED, COMPREHENSIVE THEME STYLESHEETS (NO INLINE OVERRIDES)
# ==============================================================================

LIGHT_THEME_QSS = """
    QMainWindow, QWidget#centralWidget {
        background-color: #F8FAFC;
        color: #0F172A;
        font-family: 'Plus Jakarta Sans', 'Segoe UI', Arial, sans-serif;
    }
    QFrame#cardFrame, QFrame#employeeCard, QFrame#bannerFrame, QFrame#metricCard {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
    }
    QLabel {
        color: #0F172A;
        font-family: 'Plus Jakarta Sans', 'Segoe UI', Arial, sans-serif;
    }
    QLabel#mutedText {
        color: #64748B;
    }
    QLabel#metricTitle {
        color: #64748B;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    QLineEdit {
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        color: #0F172A;
        padding: 8px 12px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border: 1px solid #0F172A;
    }
    QPushButton#btnPrimary {
        background-color: #0F172A;
        color: #FFFFFF;
        font-weight: 600;
        font-size: 13px;
        border-radius: 8px;
        padding: 9px 20px;
        border: none;
    }
    QPushButton#btnPrimary:hover {
        background-color: #1E293B;
    }
    QPushButton#btnPrimary:disabled {
        background-color: #E2E8F0;
        color: #94A3B8;
    }
    QPushButton#btnSecondary {
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        color: #0F172A;
        font-weight: 600;
        font-size: 13px;
        border-radius: 8px;
        padding: 9px 18px;
    }
    QPushButton#btnSecondary:hover {
        background-color: #F8FAFC;
        border-color: #94A3B8;
    }
    QPushButton#btnSecondary:disabled {
        background-color: #F8FAFC;
        border-color: #E2E8F0;
        color: #94A3B8;
    }
    QPushButton#btnDanger {
        background-color: #FFFFFF;
        border: 1px solid #FECACA;
        color: #DC2626;
        font-weight: 600;
        font-size: 13px;
        border-radius: 8px;
        padding: 9px 18px;
    }
    QPushButton#btnDanger:hover {
        background-color: #FEF2F2;
        border-color: #F87171;
    }
    QPushButton#btnDanger:disabled {
        background-color: #F8FAFC;
        border-color: #E2E8F0;
        color: #94A3B8;
    }
    QPushButton#btnUtility {
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        color: #475569;
        font-size: 12px;
        font-weight: 600;
        border-radius: 6px;
        padding: 6px 14px;
    }
    QPushButton#btnUtility:hover {
        background-color: #F8FAFC;
        color: #0F172A;
    }
    QTableWidget {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        gridline-color: #F1F5F9;
        color: #0F172A;
        font-size: 13px;
    }
    QHeaderView::section {
        background-color: #F8FAFC;
        color: #475569;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.5px;
        padding: 9px;
        border: none;
        border-bottom: 1px solid #E2E8F0;
    }
    QMessageBox, QDialog {
        background-color: #FFFFFF;
        color: #0F172A;
    }
    QMessageBox QLabel, QDialog QLabel {
        color: #0F172A;
        font-size: 13px;
        background-color: transparent;
    }
    QMessageBox QPushButton, QDialog QPushButton {
        background-color: #0F172A;
        color: #FFFFFF;
        font-weight: 600;
        font-size: 13px;
        border-radius: 6px;
        padding: 8px 24px;
        min-width: 80px;
        border: none;
    }
    QMessageBox QPushButton:hover, QDialog QPushButton:hover {
        background-color: #1E293B;
    }
"""

DARK_THEME_QSS = """
    QMainWindow, QWidget#centralWidget {
        background-color: #0B0F17;
        color: #F9FAFB;
        font-family: 'Plus Jakarta Sans', 'Segoe UI', Arial, sans-serif;
    }
    QFrame#cardFrame, QFrame#employeeCard, QFrame#bannerFrame, QFrame#metricCard {
        background-color: #111827;
        border: 1px solid #1F2937;
        border-radius: 10px;
    }
    QLabel {
        color: #F9FAFB;
        font-family: 'Plus Jakarta Sans', 'Segoe UI', Arial, sans-serif;
    }
    QLabel#mutedText {
        color: #9CA3AF;
    }
    QLabel#metricTitle {
        color: #9CA3AF;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    QLineEdit {
        background-color: #1F2937;
        border: 1px solid #374151;
        border-radius: 6px;
        color: #F9FAFB;
        padding: 8px 12px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border: 1px solid #E5E7EB;
    }
    QPushButton#btnPrimary {
        background-color: #F9FAFB;
        color: #0B0F17;
        font-weight: 600;
        font-size: 13px;
        border-radius: 8px;
        padding: 9px 20px;
        border: none;
    }
    QPushButton#btnPrimary:hover {
        background-color: #E5E7EB;
    }
    QPushButton#btnPrimary:disabled {
        background-color: #1F2937;
        color: #6B7280;
    }
    QPushButton#btnSecondary {
        background-color: #111827;
        border: 1px solid #374151;
        color: #F9FAFB;
        font-weight: 600;
        font-size: 13px;
        border-radius: 8px;
        padding: 9px 18px;
    }
    QPushButton#btnSecondary:hover {
        background-color: #1F2937;
        border-color: #4B5563;
    }
    QPushButton#btnSecondary:disabled {
        background-color: #111827;
        border-color: #1F2937;
        color: #4B5563;
    }
    QPushButton#btnDanger {
        background-color: #111827;
        border: 1px solid rgba(239, 68, 68, 0.4);
        color: #F87171;
        font-weight: 600;
        font-size: 13px;
        border-radius: 8px;
        padding: 9px 18px;
    }
    QPushButton#btnDanger:hover {
        background-color: rgba(185, 28, 28, 0.2);
        border-color: #EF4444;
    }
    QPushButton#btnDanger:disabled {
        background-color: #111827;
        border-color: #1F2937;
        color: #4B5563;
    }
    QPushButton#btnUtility {
        background-color: #111827;
        border: 1px solid #374151;
        color: #9CA3AF;
        font-size: 12px;
        font-weight: 600;
        border-radius: 6px;
        padding: 6px 14px;
    }
    QPushButton#btnUtility:hover {
        background-color: #1F2937;
        color: #F9FAFB;
    }
    QTableWidget {
        background-color: #111827;
        border: 1px solid #1F2937;
        border-radius: 8px;
        gridline-color: #1F2937;
        color: #F9FAFB;
        font-size: 13px;
    }
    QHeaderView::section {
        background-color: #1F2937;
        color: #9CA3AF;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.5px;
        padding: 9px;
        border: none;
        border-bottom: 1px solid #374151;
    }
    QMessageBox, QDialog {
        background-color: #1E293B;
        color: #F8FAFC;
    }
    QMessageBox QLabel, QDialog QLabel {
        color: #F8FAFC;
        font-size: 13px;
        background-color: transparent;
    }
    QMessageBox QPushButton, QDialog QPushButton {
        background-color: #38BDF8;
        color: #0F172A;
        font-weight: 700;
        font-size: 13px;
        border-radius: 6px;
        padding: 8px 24px;
        min-width: 80px;
        border: none;
    }
    QMessageBox QPushButton:hover, QDialog QPushButton:hover {
        background-color: #7DD3FC;
    }
"""

def create_app_icon() -> QIcon:
    """Generates a clean modern application icon in memory using QPainter."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background rounded rect - Deep Charcoal
    brush = QBrush(QColor("#0F172A"))
    painter.setBrush(brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

    # Clock dial circle - Clean White
    dial_pen = QPen(QColor("#FFFFFF"), 3)
    painter.setPen(dial_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(14, 14, 36, 36)

    # Clock hands
    painter.drawLine(32, 32, 32, 22)
    painter.drawLine(32, 32, 40, 32)
    painter.end()
    return QIcon(pixmap)

def format_sec(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}h {m:02d}m {s:02d}s"

class EmployeeAuthDialog(QDialog):
    """First-time Workstation Employee Activation Dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workstation Activation")
        self.setFixedSize(400, 310)
        self.setStyleSheet(LIGHT_THEME_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Employee Workstation Sign In")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)

        desc = QLabel("Enter your Employee Code and PIN to activate this workstation. You will remain logged in automatically.")
        desc.setObjectName("mutedText")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; margin-bottom: 6px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("Employee Code:"))
        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText("e.g. EMP-101")
        layout.addWidget(self.txt_code)

        layout.addWidget(QLabel("PIN:"))
        self.txt_pin = QLineEdit()
        self.txt_pin.setPlaceholderText("Default: 1234")
        self.txt_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_pin)

        self.lbl_error = QLabel("Invalid Employee Code or PIN.")
        self.lbl_error.setStyleSheet("color: #DC2626; font-size: 12px; display: none;")
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        layout.addSpacing(6)

        btn_signin = QPushButton("Activate & Stay Signed In")
        btn_signin.setObjectName("btnPrimary")
        btn_signin.clicked.connect(self.attempt_login)
        layout.addWidget(btn_signin)

        self.authenticated_emp = None

    def attempt_login(self):
        code = self.txt_code.text().strip()
        pin = self.txt_pin.text().strip() or "1234"
        emp = database.verify_employee_credentials(code, pin)
        if emp:
            database.set_authenticated_employee(emp["id"])
            self.authenticated_emp = emp
            self.accept()
        else:
            self.lbl_error.setVisible(True)

class TimeTrackerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Office Work Session Tracker")
        self.setMinimumSize(880, 680)
        self.setWindowIcon(create_app_icon())
        self._was_maximized = False

        self.current_theme = "light"

        # Initialize DB & Core Engine
        database.init_db()

        # Check authenticated employee (permanent login - never asks again)
        self.emp = database.get_authenticated_employee()
        if not self.emp:
            all_emps = database.get_all_employees()
            if all_emps:
                self.emp = all_emps[0]
                database.set_authenticated_employee(self.emp["id"])
            else:
                QMessageBox.warning(
                    None,
                    "Account Setup Required",
                    "No employee accounts found in the database.\n\nPlease open the Admin Portal (http://localhost:8000/admin) to register an employee account first."
                )
                sys.exit(0)

        # Initialize tracking engine with employee's assigned threshold
        assigned_threshold = self.emp.get("idle_threshold", 300) if self.emp else 300
        self.engine = TrackerEngine(idle_threshold_seconds=assigned_threshold)
        self.engine.on_state_change = self.handle_state_change
        self.engine.on_tick = self.handle_tick
        self.engine.on_interval_logged = self.handle_interval_logged

        # Setup GUI & Tray
        self.init_ui()
        self.setup_tray_icon()
        self.apply_theme()

        # Engine tick timer (1 Hz)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer_tick)
        self.timer.start(1000)

    def apply_theme(self):
        """Applies light or dark stylesheet uniformly across entire app."""
        if self.current_theme == "light":
            self.setStyleSheet(LIGHT_THEME_QSS)
            self.btn_theme_toggle.setText("Dark Mode")
            self.metric_active_color = "#059669"
            self.metric_inactive_color = "#D97706"
            self.metric_lunch_color = "#475569"
        else:
            self.setStyleSheet(DARK_THEME_QSS)
            self.btn_theme_toggle.setText("Light Mode")
            self.metric_active_color = "#10B981"
            self.metric_inactive_color = "#F59E0B"
            self.metric_lunch_color = "#94A3B8"

        # Update metric labels with theme-appropriate colors
        self.card_active["val"].setStyleSheet(f"font-size: 24px; font-weight: 700; color: {self.metric_active_color}; font-family: 'JetBrains Mono', monospace;")
        self.card_inactive["val"].setStyleSheet(f"font-size: 24px; font-weight: 700; color: {self.metric_inactive_color}; font-family: 'JetBrains Mono', monospace;")
        self.card_lunch["val"].setStyleSheet(f"font-size: 24px; font-weight: 700; color: {self.metric_lunch_color}; font-family: 'JetBrains Mono', monospace;")

        # Set native window palette background so Windows never paints white space on resize
        bg_col = QColor("#F8FAFC" if self.current_theme == "light" else "#0B0F17")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, bg_col)
        pal.setColor(QPalette.ColorRole.Base, bg_col)
        self.setPalette(pal)

    def toggle_theme(self):
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        self.apply_theme()

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(28, 22, 28, 22)
        main_layout.setSpacing(16)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        lbl_app_title = QLabel("Office Work Session Tracker")
        lbl_app_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.lbl_datetime = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        self.lbl_datetime.setObjectName("mutedText")
        self.lbl_datetime.setStyleSheet("font-size: 13px;")
        header_left.addWidget(lbl_app_title)
        header_left.addWidget(self.lbl_datetime)
        header_layout.addLayout(header_left)

        header_layout.addStretch()

        # Theme Toggle Button
        self.btn_theme_toggle = QPushButton("Dark Mode")
        self.btn_theme_toggle.setObjectName("btnUtility")
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.btn_theme_toggle)

        # Status Badge
        self.status_badge = QLabel("OFFLINE")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setStyleSheet("""
            background-color: #F1F5F9; color: #64748B; font-size: 12px; font-weight: 700;
            padding: 6px 16px; border-radius: 20px; border: 1px solid #CBD5E1;
        """)
        header_layout.addWidget(self.status_badge)
        main_layout.addLayout(header_layout)

        # 2. Authenticated Employee Profile & Shift Card (No name/code inputs)
        profile_frame = QFrame()
        profile_frame.setObjectName("employeeCard")
        profile_layout = QHBoxLayout(profile_frame)
        profile_layout.setContentsMargins(18, 14, 18, 14)

        emp_name = self.emp.get("name", "Employee") if self.emp else "Employee"
        emp_code = self.emp.get("employee_code", "---") if self.emp else "---"
        st = self.emp.get("shift_start", "09:30") if self.emp else "09:30"
        et = self.emp.get("shift_end", "18:00") if self.emp else "18:00"
        auto_text = "Auto-Monitor Active" if self.emp.get("is_auto_start", 1) else "Manual Start"

        emp_info_layout = QVBoxLayout()
        lbl_welcome = QLabel(f"<strong>{emp_name}</strong> &nbsp;•&nbsp; <span style='font-family:monospace;'>{emp_code}</span>")
        lbl_welcome.setStyleSheet("font-size: 15px;")
        lbl_shift = QLabel(f"Assigned Shift: {st} to {et} ({auto_text})")
        lbl_shift.setObjectName("mutedText")
        lbl_shift.setStyleSheet("font-size: 13px; margin-top: 2px;")
        emp_info_layout.addWidget(lbl_welcome)
        emp_info_layout.addWidget(lbl_shift)
        profile_layout.addLayout(emp_info_layout)

        profile_layout.addStretch()

        # Permanent Workstation Login - Employee cannot log out
        badge_active = QLabel("● Workstation Active")
        badge_active.setStyleSheet("color: #059669; font-weight: 600; font-size: 13px;")
        profile_layout.addWidget(badge_active)

        main_layout.addWidget(profile_frame)

        # 3. 4-Metrics Cards Grid (No inline #FFFFFF)
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(14)

        self.card_start = self.create_metric_card("Shift Started", "--:--")
        self.card_active = self.create_metric_card("Active Work Time", "00h 00m 00s")
        self.card_inactive = self.create_metric_card("Inactivity / Away", "00h 00m 00s")
        self.card_lunch = self.create_metric_card("Lunch Break", "00h 00m 00s")

        metrics_layout.addWidget(self.card_start["frame"])
        metrics_layout.addWidget(self.card_active["frame"])
        metrics_layout.addWidget(self.card_inactive["frame"])
        metrics_layout.addWidget(self.card_lunch["frame"])
        main_layout.addLayout(metrics_layout)

        # 4. Action Controls Bar (Start, Lunch, End, Minimize)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)

        self.btn_clock_in = QPushButton("Start Shift / Clock In")
        self.btn_clock_in.setObjectName("btnPrimary")
        self.btn_clock_in.setMinimumHeight(42)
        self.btn_clock_in.clicked.connect(self.action_clock_in)
        controls_layout.addWidget(self.btn_clock_in)

        self.btn_lunch = QPushButton("Take Lunch Break")
        self.btn_lunch.setObjectName("btnSecondary")
        self.btn_lunch.setMinimumHeight(42)
        self.btn_lunch.setEnabled(False)
        self.btn_lunch.clicked.connect(self.action_toggle_lunch)
        controls_layout.addWidget(self.btn_lunch)

        self.btn_clock_out = QPushButton("End Shift / Clock Out")
        self.btn_clock_out.setObjectName("btnDanger")
        self.btn_clock_out.setMinimumHeight(42)
        self.btn_clock_out.setEnabled(False)
        self.btn_clock_out.clicked.connect(self.action_clock_out)
        controls_layout.addWidget(self.btn_clock_out)

        controls_layout.addStretch()

        self.btn_tray = QPushButton("Minimize to Background")
        self.btn_tray.setObjectName("btnSecondary")
        self.btn_tray.setMinimumHeight(42)
        self.btn_tray.clicked.connect(self.action_minimize_to_tray)
        controls_layout.addWidget(self.btn_tray)

        main_layout.addLayout(controls_layout)

        # 5. Today's Activity Interval Timeline
        act_header_layout = QHBoxLayout()
        lbl_act_title = QLabel("Today's Activity Intervals")
        lbl_act_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        act_header_layout.addWidget(lbl_act_title)

        act_header_layout.addStretch()

        self.lbl_active_app = QLabel("")
        self.lbl_active_app.setStyleSheet("font-size: 12px; font-weight: 600; color: #059669; padding-right: 12px;")
        act_header_layout.addWidget(self.lbl_active_app)

        self.lbl_idle_indicator = QLabel("System Idle: 0s")
        self.lbl_idle_indicator.setObjectName("mutedText")
        self.lbl_idle_indicator.setStyleSheet("font-size: 12px;")
        act_header_layout.addWidget(self.lbl_idle_indicator)
        main_layout.addLayout(act_header_layout)

        self.table_logs = QTableWidget(0, 5)
        self.table_logs.setHorizontalHeaderLabels(["#", "Status Event", "Start Time", "End Time", "Duration"])
        self.table_logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_logs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_logs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_logs.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table_logs)

    def create_metric_card(self, title: str, initial_val: str) -> dict:
        """Creates a metric card without hardcoded background colors."""
        frame = QFrame()
        frame.setObjectName("metricCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        lbl_title = QLabel(title.upper())
        lbl_title.setObjectName("metricTitle")
        layout.addWidget(lbl_title)

        lbl_val = QLabel(initial_val)
        lbl_val.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace;")
        layout.addWidget(lbl_val)

        return {"frame": frame, "val": lbl_val}

    def setup_tray_icon(self):
        """Sets up Windows system tray icon and context menu."""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_app_icon())
        self.tray_icon.setToolTip("Office Work Session Tracker")

        tray_menu = QMenu()
        act_show = tray_menu.addAction("Open App Window")
        act_show.triggered.connect(self.show_and_activate)

        tray_menu.addSeparator()

        self.act_tray_lunch = tray_menu.addAction("Take Lunch Break")
        self.act_tray_lunch.triggered.connect(self.action_toggle_lunch)
        self.act_tray_lunch.setEnabled(False)

        tray_menu.addSeparator()

        act_exit = tray_menu.addAction("Exit App")
        act_exit.triggered.connect(self.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_and_activate()

    def action_minimize_to_tray(self):
        self._was_maximized = self.isMaximized()
        self.hide()

    def show_and_activate(self):
        self.show()
        if getattr(self, "_was_maximized", False):
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if not self.isMinimized():
                self._was_maximized = self.isMaximized()
            if self.isMinimized():
                self.hide()
        super().changeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.isMinimized():
            self._was_maximized = self.isMaximized()

    def closeEvent(self, event):
        if self.engine.state != TrackerState.LOGGED_OUT:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Your work session is currently running. Do you want to clock out and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.engine.end_day(manual=True)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def switch_account(self):
        """Allows signing out and switching to a different employee account."""
        database.clear_authenticated_employee()
        if self.engine.state != TrackerState.LOGGED_OUT:
            self.engine.end_day(manual=True)

        dialog = EmployeeAuthDialog(self)
        if dialog.exec() and dialog.authenticated_emp:
            self.emp = dialog.authenticated_emp
            emp_id = self.emp["id"]
            database.set_authenticated_employee(emp_id)
            assigned_threshold = self.emp.get("idle_threshold", 300)
            self.engine.set_idle_threshold(assigned_threshold)
            self.table_logs.setRowCount(0)
            QMessageBox.information(self, "Workstation Activated", f"Workstation is now assigned to: {self.emp['name']}")
            # Recreate UI
            self.init_ui()
            self.apply_theme()
        else:
            # User cancelled or chose not to sign in - exit cleanly
            sys.exit(0)

    def on_timer_tick(self):
        """Runs every 1 second: handles employee's individual shift schedule and engine tick."""
        if not self.emp:
            return
        emp_id = self.emp["id"]

        # Check this employee's individual shift schedule
        self.engine.check_shift_window(emp_id)

        # Tick engine
        if self.engine.state != TrackerState.LOGGED_OUT:
            self.engine.tick()

    def action_clock_in(self):
        if not self.emp:
            return
        emp_id = self.emp["id"]
        assigned_threshold = self.emp.get("idle_threshold", 300)
        self.engine.set_idle_threshold(assigned_threshold)
        self.engine.start_day(emp_id)

        now_str = datetime.now().strftime("%I:%M:%S %p")
        self.btn_clock_in.setEnabled(False)
        self.btn_lunch.setEnabled(True)
        self.btn_clock_out.setEnabled(True)
        self.act_tray_lunch.setEnabled(True)
        self.card_start["val"].setText(now_str)
        self.table_logs.setRowCount(0)

        # Informative Shift Started Popup
        st = self.emp.get("shift_start", "09:30") if self.emp else "09:30"
        et = self.emp.get("shift_end", "18:00") if self.emp else "18:00"
        emp_name = self.emp.get("name", "Employee") if self.emp else "Employee"
        emp_code = self.emp.get("employee_code", "") if self.emp else ""
        QMessageBox.information(
            self,
            "Shift Started",
            f"Work shift clocked in successfully at {now_str}!\n\n"
            f"Employee: {emp_name} ({emp_code})\n"
            f"Assigned Shift: {st} to {et}\n\n"
            "Hardware activity and application focus are now being monitored."
        )

    def action_toggle_lunch(self):
        now_str = datetime.now().strftime("%I:%M:%S %p")
        if self.engine.state == TrackerState.LUNCH:
            # Resuming work from lunch
            self.engine.resume_from_lunch()
            self.btn_lunch.setText("Take Lunch Break")
            self.act_tray_lunch.setText("Take Lunch Break")
            QMessageBox.information(
                self,
                "Work Resumed",
                f"Welcome back! Lunch break ended at {now_str}.\n\n"
                "Active work tracking and inactivity detection have resumed."
            )
        else:
            # Starting lunch break with confirmation
            reply = QMessageBox.question(
                self,
                "Confirm Lunch Break",
                "Would you like to start your lunch break now?\n\n"
                "Inactivity detection will be paused while you are on break.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.engine.start_lunch()
                self.btn_lunch.setText("Resume Work")
                self.act_tray_lunch.setText("Resume Work")
                QMessageBox.information(
                    self,
                    "Lunch Break Started",
                    f"Lunch break started at {now_str}.\n\n"
                    "Enjoy your meal! Click 'Resume Work' when you return to your workstation."
                )

    def action_clock_out(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clock Out",
            "Are you sure you want to end your shift for today?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.engine.end_day(manual=True)
            self.btn_clock_in.setEnabled(True)
            self.btn_lunch.setEnabled(False)
            self.btn_clock_out.setEnabled(False)
            self.btn_lunch.setText("Take Lunch Break")
            self.act_tray_lunch.setEnabled(False)
            self.card_start["val"].setText("--:--")

            now_str = datetime.now().strftime("%I:%M:%S %p")
            total_active = self.card_active['val'].text()
            total_idle = self.card_inactive['val'].text()
            total_lunch = self.card_lunch['val'].text()

            QMessageBox.information(
                self,
                "Shift Ended",
                f"Clock-out logged successfully at {now_str}!\n\n"
                f"• Total Active Work:  {total_active}\n"
                f"• Total Inactivity:   {total_idle}\n"
                f"• Total Lunch Break:  {total_lunch}\n\n"
                "Your daily work session has concluded."
            )

    def handle_state_change(self, new_state: TrackerState):
        """Updates the status badge color & text."""
        if new_state == TrackerState.ACTIVE:
            self.status_badge.setText("ACTIVE WORKING")
            self.status_badge.setStyleSheet("""
                background-color: #ECFDF5; color: #065F46; font-size: 12px; font-weight: 700;
                padding: 6px 16px; border-radius: 20px; border: 1px solid #A7F3D0;
            """)
            self.btn_clock_in.setEnabled(False)
            self.btn_lunch.setEnabled(True)
            self.btn_clock_out.setEnabled(True)
            self.act_tray_lunch.setEnabled(True)
            if self.card_start["val"].text() == "--:--":
                self.card_start["val"].setText(datetime.now().strftime("%I:%M:%S %p"))
                if hasattr(self, 'tray_icon') and self.emp:
                    self.tray_icon.showMessage(
                        "WorkLogix - Shift Started",
                        f"Assigned shift ({self.emp.get('shift_start', '09:30')} - {self.emp.get('shift_end', '18:00')}) is now active.",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000
                    )
        elif new_state == TrackerState.INACTIVE:
            self.status_badge.setText("AWAY / INACTIVE")
            self.status_badge.setStyleSheet("""
                background-color: #FFFBEB; color: #92400E; font-size: 12px; font-weight: 700;
                padding: 6px 16px; border-radius: 20px; border: 1px solid #FDE68A;
            """)
        elif new_state == TrackerState.LUNCH:
            self.status_badge.setText("ON LUNCH BREAK")
            self.status_badge.setStyleSheet("""
                background-color: #F1F5F9; color: #334155; font-size: 12px; font-weight: 700;
                padding: 6px 16px; border-radius: 20px; border: 1px solid #CBD5E1;
            """)
        elif new_state == TrackerState.LOGGED_OUT:
            self.status_badge.setText("OFFLINE")
            self.status_badge.setStyleSheet("""
                background-color: #F1F5F9; color: #64748B; font-size: 12px; font-weight: 700;
                padding: 6px 16px; border-radius: 20px; border: 1px solid #CBD5E1;
            """)
            self.btn_clock_in.setEnabled(True)
            self.btn_lunch.setEnabled(False)
            self.btn_clock_out.setEnabled(False)
            self.act_tray_lunch.setEnabled(False)

    def handle_tick(self, stats: dict):
        """Called every second by the engine."""
        self.card_active["val"].setText(format_sec(stats["total_active"]))
        self.card_inactive["val"].setText(format_sec(stats["total_inactive"]))
        self.card_lunch["val"].setText(format_sec(stats["total_lunch"]))

        idle = stats["idle_seconds"]
        thresh = self.engine.idle_threshold
        active_app = stats.get("active_app", "")
        active_browser = stats.get("active_browser")
        active_domain = stats.get("active_domain")

        if stats["state"] == TrackerState.ACTIVE.value:
            self.lbl_idle_indicator.setText(f"System Idle: {idle}s / {thresh}s")
            if active_domain:
                b_name = active_browser or "Browser"
                self.lbl_active_app.setText(f"Active: {b_name} • {active_domain}")
            elif active_app and active_app not in ["Desktop/Idle", "System", "explorer.exe"]:
                disp = tracker_core.get_app_display_info(active_app)
                self.lbl_active_app.setText(f"Active: {disp['friendly_name']}")
            else:
                self.lbl_active_app.setText("")
        elif stats["state"] == TrackerState.INACTIVE.value:
            self.lbl_idle_indicator.setText(f"Inactivity: {idle}s away")
            self.lbl_active_app.setText("")
        elif stats["state"] == TrackerState.LUNCH.value:
            self.lbl_idle_indicator.setText("Lunch break in progress")
            self.lbl_active_app.setText("")
        else:
            self.lbl_idle_indicator.setText("System Idle: 0s")
            self.lbl_active_app.setText("")

    def handle_interval_logged(self, log: dict):
        """Inserts completed interval row into the table."""
        row_pos = self.table_logs.rowCount()
        self.table_logs.insertRow(row_pos)

        item_id = QTableWidgetItem(str(row_pos + 1))
        item_event = QTableWidgetItem(log["event_type"])
        item_start = QTableWidgetItem(log["start_time"])
        item_end = QTableWidgetItem(log["end_time"])
        item_dur = QTableWidgetItem(format_sec(log["duration_sec"]))

        for item in [item_id, item_event, item_start, item_end, item_dur]:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if log["event_type"] == "ACTIVE":
            item_event.setForeground(QColor("#059669"))
        elif log["event_type"] == "INACTIVE":
            item_event.setForeground(QColor("#D97706"))
        elif log["event_type"] == "LUNCH":
            item_event.setForeground(QColor("#475569"))

        self.table_logs.setItem(row_pos, 0, item_id)
        self.table_logs.setItem(row_pos, 1, item_event)
        self.table_logs.setItem(row_pos, 2, item_start)
        self.table_logs.setItem(row_pos, 3, item_end)
        self.table_logs.setItem(row_pos, 4, item_dur)

        self.table_logs.scrollToBottom()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = TimeTrackerApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
