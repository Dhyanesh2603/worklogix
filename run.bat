@echo off
cd /d "%~dp0"
echo Starting Office Activity & Session Tracker...
python main.py
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)
