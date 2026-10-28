import os
import sys
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from settings import Settings, SERVER_PORT
from manager import Manager
import i18n
import server


def hand_off_to_running_instance(url):
    """If Sahm is already running, send it the URL (e.g. `Sahm.exe <url>`) and exit."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{SERVER_PORT}/add", data=json.dumps({"url": url}).encode(),
            headers={"Content-Type": "application/json", "X-Sahm-Client": "extension"})
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def install_error_handler():
    """Log unexpected errors and show them instead of letting the app close."""
    import traceback
    from settings import data_dir
    log = os.path.join(data_dir(), "error.log")

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Sahm – error", f"{value}\n\nDetails saved to:\n{log}")
        except Exception:
            pass
    sys.excepthook = hook


def main():
    install_error_handler()
    cli_url = next((a for a in sys.argv[1:] if a.startswith(("http://", "https://"))), None)
    srv = server.start_server()
    if srv is None and cli_url and hand_off_to_running_instance(cli_url):
        return 0

    settings = Settings()
    i18n.set_language(settings["language"])

    app = QApplication(sys.argv)
    app.setApplicationName("Sahm")
    app.setQuitOnLastWindowClosed(False)
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 10))      # macOS keeps its own system font
    if i18n.is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    from gui import MainWindow
    manager = Manager(settings)
    win = MainWindow(manager, settings, server_ok=srv is not None)
    app.aboutToQuit.connect(manager.shutdown)          # Cmd+Q / logout: save the list first
    if sys.platform == "darwin":                       # clicking the Dock icon brings the window back
        app.applicationStateChanged.connect(
            lambda st: win.show_normal() if st == Qt.ApplicationState.ApplicationActive and win.isHidden()
            and not win._quitting else None)
    if "--minimized" not in sys.argv:
        win.show()
    if cli_url:
        server.incoming.put({"type": "file", "url": cli_url, "filename": "", "headers": {}})
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
