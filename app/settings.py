import os
import sys
import json

APP_NAME = "Sahm"
APP_VERSION = "1.1.1"
SERVER_PORT = 9614


def data_dir():
    """Windows: %APPDATA%\\Sahm   macOS: ~/Library/Application Support/Sahm   other: ~/.config/Sahm"""
    if os.environ.get("APPDATA"):
        base = os.environ["APPDATA"]
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def default_download_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads", APP_NAME)


DEFAULTS = {
    "download_dir": default_download_dir(),
    "connections": 8,
    "max_concurrent": 3,
    "speed_limit_kb": 0,          # 0 = unlimited
    "language": "en",             # "en" | "ar"
    "browser_show_dialog": True,  # show Add dialog for downloads caught by the extension
    "notify_on_complete": True,
    "close_to_tray": True,
    "start_at_login": False,
    "sched_enabled": False,
    "sched_start": "02:00",
    "sched_stop": "",             # "" = don't stop automatically
    "sched_shutdown": False,      # placeholder for future: shut down when queue done
}


class Settings(dict):
    def __init__(self, path=None):
        super().__init__(DEFAULTS)
        self.path = path or os.path.join(data_dir(), "settings.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(self), f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
