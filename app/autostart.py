"""Start Sahm when the user logs in.
Windows: HKCU\\...\\Run registry value (same one the installer writes).
macOS:   ~/Library/LaunchAgents/com.sahm.downloadmanager.plist"""
import os
import sys
import plistlib

LABEL = "com.sahm.downloadmanager"
WIN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--minimized"]
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), "--minimized"]


def _plist_path():
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", LABEL + ".plist")


def supported():
    return sys.platform in ("win32", "darwin")


def is_enabled():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_KEY) as k:
                winreg.QueryValueEx(k, "Sahm")
                return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return os.path.exists(_plist_path())
    return False


def set_enabled(on):
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_KEY) as k:
            if on:
                cmd = " ".join(f'"{a}"' if " " in a else a for a in _command())
                winreg.SetValueEx(k, "Sahm", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, "Sahm")
                except OSError:
                    pass
    elif sys.platform == "darwin":
        path = _plist_path()
        if on:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                plistlib.dump({"Label": LABEL, "ProgramArguments": _command(),
                               "RunAtLoad": True, "ProcessType": "Interactive"}, f)
        else:
            try:
                os.remove(path)
            except OSError:
                pass
