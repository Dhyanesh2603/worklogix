import os
import sys
import winreg

APP_NAME = "OfficeTracker"
EXE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "OfficeTracker.exe")

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def enable_autostart():
    """Adds the app to Windows HKCU Run key to launch on Windows boot."""
    target_exe = EXE_PATH if os.path.exists(EXE_PATH) else os.path.abspath(__file__)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{target_exe}"')
        winreg.CloseKey(key)
        print(f"[SUCCESS] Auto-start on Windows login enabled for: {target_exe}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to enable auto-start: {e}")
        return False

def disable_autostart():
    """Removes the app from Windows HKCU Run key."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("[SUCCESS] Auto-start on Windows login disabled.")
        return True
    except FileNotFoundError:
        print("[INFO] Auto-start was not registered.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to disable auto-start: {e}")
        return False

def check_status():
    """Checks if auto-start is registered."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        print(f"[STATUS] Auto-start is ENABLED -> {val}")
        return True
    except FileNotFoundError:
        print("[STATUS] Auto-start is currently DISABLED.")
        return False
    except Exception as e:
        print(f"[ERROR] Could not query registry: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "enable":
            enable_autostart()
        elif cmd == "disable":
            disable_autostart()
        elif cmd == "status":
            check_status()
        else:
            print("Usage: python autostart.py [enable|disable|status]")
    else:
        check_status()
