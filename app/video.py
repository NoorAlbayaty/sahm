"""Video downloads (YouTube and 1000+ sites) by driving yt-dlp as a subprocess.
VideoTask has the same interface as engine.DownloadTask so the list/queue treat both alike."""
import os
import json
import time
import uuid
import threading
import subprocess

import tools
from engine import Status

PROGRESS = ("download:SAHM|%(progress.status)s|%(progress.downloaded_bytes)s|"
            "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|"
            "%(progress.eta)s|%(progress.filename)s")


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ format probing
def probe(url, cookie_file=None, timeout=90):
    """Return yt-dlp's info dict for a page (raises RuntimeError with yt-dlp's message)."""
    exe = tools.find("yt-dlp")
    if not exe:
        raise RuntimeError("yt-dlp is not installed")
    args = [exe, "-J", "--no-playlist", "--no-warnings"]
    if cookie_file:
        args += ["--cookies", cookie_file]
    args += ["--", url]          # "--": a URL can never be read as a yt-dlp option
    r = tools.run(args, timeout=timeout)
    if r.returncode != 0 or not r.stdout.strip():
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        msg = next((l for l in reversed(err) if "ERROR" in l), err[-1] if err else "unknown error")
        raise RuntimeError(msg.replace("ERROR: ", ""))
    return json.loads(r.stdout.decode("utf-8", "replace"))


def quality_options(info):
    """Turn yt-dlp's format list into simple IDM-like choices.
    Returns list of dicts: label, format, size (bytes or None), audio_only, mp3."""
    fmts = info.get("formats") or []
    if not fmts and info.get("url"):
        fmts = [info]

    def size(f):
        return f.get("filesize") or f.get("filesize_approx")

    def is_video(f):
        return bool(f.get("height")) and f.get("vcodec") != "none"

    audio = [f for f in fmts if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    best_audio = max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    m4a = [f for f in audio if f.get("ext") == "m4a"]
    best_m4a = max(m4a, key=lambda f: f.get("abr") or 0, default=best_audio)

    heights = sorted({f["height"] for f in fmts if is_video(f)}, reverse=True)
    opts = []
    for h in heights:
        cands = [f for f in fmts if f.get("height") == h and is_video(f)]
        # prefer mp4/h264 (plays everywhere), then biggest bitrate
        cands.sort(key=lambda f: (f.get("ext") == "mp4", (f.get("vcodec") or "").startswith("avc"),
                                  f.get("tbr") or 0), reverse=True)
        v = cands[0]
        has_audio = v.get("acodec") != "none"
        est = size(v)
        if not has_audio and best_audio and est and size(best_audio):
            est += size(best_audio)
        fps = v.get("fps")
        label = f"{h}p" + (f"{int(fps)}" if fps and fps > 30 else "")
        opts.append({
            "label": label + " MP4",
            "format": f"bv*[height={h}][ext=mp4]+ba[ext=m4a]/bv*[height={h}]+ba/b[height={h}]/b",
            "size": est, "audio_only": False, "mp3": False,
        })
    if not heights:
        opts.append({"label": "Best quality", "format": "bv*+ba/b", "size": size(fmts[-1]) if fmts else None,
                     "audio_only": False, "mp3": False})
    if best_audio:
        opts.append({"label": "Audio only – M4A", "format": "ba[ext=m4a]/ba", "size": size(best_m4a),
                     "audio_only": True, "mp3": False})
        opts.append({"label": "Audio only – MP3", "format": "ba/b", "size": size(best_audio),
                     "audio_only": True, "mp3": True})
    return opts


# ------------------------------------------------------------------ task
class VideoTask:
    kind = "video"

    def __init__(self, url, folder, fmt="bv*+ba/b", title="", connections=8, mp3=False,
                 cookie_file=None, size_hint=None, task_id=None):
        self.id = task_id or uuid.uuid4().hex[:12]
        self.url = url
        self.folder = folder
        self.fmt = fmt
        self.title = title
        self.filename = title or url
        self.connections = connections
        self.mp3 = mp3
        self.cookie_file = cookie_file
        self.size = size_hint
        self.status = Status.QUEUED
        self.error = ""
        self.stage = ""
        self.added = time.time()
        self.finished = None
        self.speed = 0.0
        self.final_path = ""
        self.probed = True
        self.resumable = True
        self.headers = {}
        # runtime
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self._done_parts = 0           # bytes of finished parts (video, then audio)
        self._cur = 0                  # bytes of the part being downloaded
        self._cur_total = None
        self._cur_file = None
        self._eta = None
        self.limiter = None
        self.on_finish = None

    # ---- persistence
    def to_dict(self):
        return {"kind": "video", "id": self.id, "url": self.url, "folder": self.folder, "fmt": self.fmt,
                "title": self.title, "filename": self.filename, "connections": self.connections,
                "mp3": self.mp3, "cookie_file": self.cookie_file, "size": self.size,
                "status": Status.PAUSED if self.status in Status.ACTIVE else self.status,
                "error": self.error, "added": self.added, "finished": self.finished,
                "source": getattr(self, "source", "manual"),
                "final_path": self.final_path}

    @classmethod
    def from_dict(cls, d):
        t = cls(d["url"], d["folder"], d.get("fmt", "bv*+ba/b"), d.get("title", ""), d.get("connections", 8),
                d.get("mp3", False), d.get("cookie_file"), d.get("size"), d.get("id"))
        t.filename = d.get("filename") or t.filename
        st = d.get("status", Status.PAUSED)
        t.status = Status.PAUSED if st in Status.ACTIVE else st
        t.error = d.get("error", "")
        t.added = d.get("added", t.added)
        t.source = d.get("source", "manual")
        t.finished = d.get("finished")
        t.final_path = d.get("final_path", "")
        return t

    # ---- info (same names as DownloadTask)
    @property
    def path(self):
        return self.final_path or os.path.join(self.folder, self.filename)

    @property
    def part_path(self):
        return os.path.join(self.folder, "__nonexistent__")

    @property
    def downloaded(self):
        return self._done_parts + self._cur

    @property
    def progress(self):
        if self.status == Status.COMPLETED:
            return 1.0
        if self.size:
            return min(0.999, self.downloaded / self.size)
        if self._cur_total:
            return min(0.999, self._cur / self._cur_total)
        return 0.0

    @property
    def eta(self):
        return self._eta

    @property
    def active_connections(self):
        return self.connections if self.status == Status.DOWNLOADING else 0

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def sample_speed(self):
        if self.status not in Status.ACTIVE:
            self.speed = 0.0

    # ---- control
    def start(self, limiter=None):
        if self.is_running() or self.status == Status.COMPLETED:
            return
        self.limiter = limiter or self.limiter
        self._stop.clear()
        self.error = ""
        self.status = Status.CONNECTING
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        self._stop.set()
        tools.kill_tree(self._proc)
        if self.status == Status.QUEUED:
            self.status = Status.PAUSED

    def wait(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    def forget_cookies(self):
        """Login cookies are only needed while downloading – delete them afterwards."""
        if self.cookie_file:
            try:
                os.remove(self.cookie_file)
            except OSError:
                pass
            self.cookie_file = None

    def reset(self):
        self.pause()
        self.wait(5)
        self.final_path = ""
        self.status = Status.QUEUED

    # ---- internals
    def _command(self, result_file):
        exe = tools.find("yt-dlp")
        a = [exe, "--no-playlist", "--newline", "--no-colors", "--no-mtime",
             "-f", self.fmt, "-N", str(self.connections),
             "-o", os.path.join(self.folder, "%(title).150B [%(id)s].%(ext)s"),
             "--progress-template", PROGRESS,
             "--print-to-file", "after_move:filepath", result_file]
        if self.mp3:
            a += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        elif "+" in self.fmt:
            a += ["--merge-output-format", "mp4"]
        if self.limiter and self.limiter.rate > 0:
            a += ["-r", str(self.limiter.rate)]
        if self.cookie_file and os.path.exists(self.cookie_file):
            a += ["--cookies", self.cookie_file]
        a += ["--", self.url]
        return a

    def _run(self):
        os.makedirs(self.folder, exist_ok=True)
        result_file = os.path.join(tools.tools_dir(), f"result-{self.id}.txt")
        try:
            os.remove(result_file)
        except OSError:
            pass
        self._done_parts = self._cur = 0
        self._cur_file = None
        last_err = ""
        try:
            if not tools.find("yt-dlp"):
                raise RuntimeError("yt-dlp is not installed")
            self._proc = subprocess.Popen(
                self._command(result_file), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, env=tools.env(), **tools.popen_kwargs())
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                if line.startswith("SAHM|"):
                    self._on_progress(line)
                elif line.startswith("ERROR"):
                    last_err = line.replace("ERROR: ", "")
                elif line.startswith(("[Merger]", "[ExtractAudio]", "[FixupM3u8]", "[VideoConvertor]")):
                    self.stage = "merging"
                    self.status = Status.DOWNLOADING
                    self.speed = 0
                elif "has already been downloaded" in line:
                    self.status = Status.DOWNLOADING
            code = self._proc.wait()
            if self._stop.is_set():
                self.status = Status.PAUSED
                return
            if code != 0:
                raise RuntimeError(last_err or f"yt-dlp exited with code {code}")
            try:
                with open(result_file, encoding="utf-8") as f:
                    paths = [p.strip() for p in f if p.strip()]
                if paths:
                    self.final_path = paths[-1]
                    self.filename = os.path.basename(self.final_path)
                    self.size = os.path.getsize(self.final_path)
            except OSError:
                pass
            self.status = Status.COMPLETED
            self.finished = time.time()
            self.speed = 0
            self.stage = ""
            self.forget_cookies()
            if self.on_finish:
                self.on_finish(self)
        except Exception as e:  # noqa
            if self._stop.is_set():
                self.status = Status.PAUSED
            else:
                self.status = Status.ERROR
                self.error = str(e)[:300]
        finally:
            self._proc = None
            self.speed = 0 if self.status != Status.DOWNLOADING else self.speed

    def _on_progress(self, line):
        parts = line.split("|", 7)
        if len(parts) < 8:
            return
        _, status, done, total, est, speed, eta, fname = parts
        if fname != self._cur_file:
            if self._cur_file is not None:
                self._done_parts += self._cur_total or self._cur
            self._cur_file = fname
            self._cur = 0
        self._cur = int(_num(done) or 0)
        self._cur_total = _num(total) or _num(est)
        self.speed = _num(speed) or 0.0
        e = _num(eta)
        self._eta = e
        self.status = Status.DOWNLOADING
        self.stage = ""
        if not self.title:
            self.filename = os.path.basename(fname)
        if self.size and self.downloaded > self.size:
            self.size = None
