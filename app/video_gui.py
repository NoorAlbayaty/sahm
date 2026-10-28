"""Video quality picker (like IDM's "Download this video") and the one-time tool installer."""
import os
import threading
import urllib.parse

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QLineEdit, QFileDialog)

import tools
import video
from settings import data_dir
from i18n import tr, human_size

VIDEO_SITES = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "instagram.com", "tiktok.com",
               "x.com", "twitter.com", "vimeo.com", "dailymotion.com", "twitch.tv", "reddit.com",
               "soundcloud.com", "aparat.com", "bilibili.com", "rumble.com", "streamable.com")
DIRECT_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4a", ".mp3", ".flv", ".avi")


def is_video_page(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in VIDEO_SITES)


def cookie_file_for(url, cookies):
    if not cookies:
        return None
    import re
    import uuid
    host = re.sub(r"[^a-z0-9.-]", "_", (urllib.parse.urlparse(url).hostname or "site").lower())[:60]
    d = os.path.join(data_dir(), "cookies")
    os.makedirs(d, exist_ok=True)
    return tools.write_cookie_file(cookies, os.path.join(d, f"{host}-{uuid.uuid4().hex[:8]}.txt"))


# ------------------------------------------------------------------ quality picker
class VideoDialog(QDialog):
    def __init__(self, parent, settings, url, title="", media=None, cookies=None, limiter=None):
        super().__init__(parent)
        self.setWindowTitle(tr("video_title"))
        self.setMinimumSize(560, 420)
        self.page_url = url
        self.media = media or []
        self.cookie_file = cookie_file_for(url, cookies)
        self.result = None
        self._probe_result = None
        self._prep = None          # setup progress (only if the bundled tools are missing)
        self._stop = threading.Event()
        self.limiter = limiter

        v = QVBoxLayout(self)
        self.title_lbl = QLabel(f"<b>{title or url}</b>")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.title_lbl)
        self.info = QLabel(tr("video_searching"))
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._accept(True))
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("save_to")))
        self.folder = QLineEdit(settings["download_dir"])
        b = QPushButton(tr("browse"))
        b.clicked.connect(lambda: self.folder.setText(
            QFileDialog.getExistingDirectory(self, tr("save_to"), self.folder.text()) or self.folder.text()))
        row.addWidget(self.folder, 1)
        row.addWidget(b)
        v.addLayout(row)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton(tr("cancel"))
        self.later = QPushButton(tr("later"))
        self.now = QPushButton(tr("start_now"))
        self.now.setDefault(True)
        for w in (self.later, self.now):
            w.setEnabled(False)
        cancel.clicked.connect(self.reject)
        self.later.clicked.connect(lambda: self._accept(False))
        self.now.clicked.connect(lambda: self._accept(True))
        for w in (cancel, self.later, self.now):
            btns.addWidget(w)
        v.addLayout(btns)

        threading.Thread(target=self._probe, daemon=True).start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check)
        self.timer.start(200)

    def _probe(self):
        if tools.missing():
            self._prep = 0.0
            ok = tools.auto_install(self.limiter, lambda f: setattr(self, "_prep", f), self._stop)
            if not ok and (self._stop.is_set() or not tools.find("yt-dlp")):
                if not self._stop.is_set():
                    self._probe_result = ([], "", tr("video_tools_failed"), self.page_url)
                return
            self._prep = None
        options, title, err, used_url = [], "", "", self.page_url
        candidates = [self.page_url] + [m for m in self.media if ".m3u8" in m or ".mpd" in m]
        for u in candidates:
            try:
                info = video.probe(u, self.cookie_file)
                if info.get("_type") == "playlist" and info.get("entries"):
                    info = info["entries"][0]
                options = [dict(o, kind="video") for o in video.quality_options(info)]
                title, used_url = info.get("title") or "", u
                break
            except Exception as e:  # noqa
                err = err or str(e)
        # direct media files the page loaded (mp4/webm…) -> normal multi-connection engine
        for m in self.media:
            path = urllib.parse.urlparse(m).path.lower()
            if path.endswith(DIRECT_EXT):
                options.append({"label": f"{tr('direct_file')} – {os.path.basename(path)}", "format": "",
                                "size": None, "kind": "file", "url": m, "mp3": False})
        self._probe_result = (options, title, err, used_url)

    def _check(self):
        if self._probe_result is None:
            if self._prep is not None:
                self.info.setText(f"{tr('video_preparing')} {self._prep * 100:.0f}%")
            else:
                self.info.setText(tr("video_searching"))
            return
        self.timer.stop()
        options, title, err, used_url = self._probe_result
        self.used_url = used_url
        if title:
            self.title_lbl.setText(f"<b>{title}</b>")
        self.video_title = title
        if not options:
            msg = err or tr("video_none")
            if "Sign in" in msg or "bot" in msg:
                msg += "\n\n" + tr("video_signin")
            self.info.setText(f"<span style='color:#d93025'>{msg}</span>")
            return
        self.info.setText(tr("video_pick"))
        for o in options:
            it = QListWidgetItem(f"{o['label']}" + (f"    ·    ~{human_size(o['size'])}" if o.get("size") else ""))
            it.setData(Qt.ItemDataRole.UserRole, o)
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.later.setEnabled(True)
        self.now.setEnabled(True)

    def reject(self):
        self._stop.set()
        if self.cookie_file:          # cancelled: don't leave cookies on disk
            try:
                os.remove(self.cookie_file)
            except OSError:
                pass
        super().reject()

    def _accept(self, now):
        it = self.list.currentItem()
        if not it:
            return
        self.result = {"option": it.data(Qt.ItemDataRole.UserRole), "folder": self.folder.text(),
                       "start_now": now, "url": self.used_url, "title": self.video_title,
                       "cookie_file": self.cookie_file}
        self.accept()
