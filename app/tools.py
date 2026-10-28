"""External helper tools for video downloads: yt-dlp, FFmpeg and Deno.
They ship inside the program (Windows: next to Sahm.exe, macOS: inside Sahm.app);
yt-dlp is copied to the user's data folder so it can update itself."""
import os
import sys
import stat
import platform
import time
import shutil
import zipfile
import subprocess
import threading

from settings import data_dir

IS_WIN = sys.platform == "win32"
EXE = ".exe" if IS_WIN else ""
NO_WINDOW = 0x08000000 if IS_WIN else 0     # CREATE_NO_WINDOW: no console popping up

IS_MAC = sys.platform == "darwin"


def platform_key(machine=None):
    """'win', 'mac-arm64' (Apple Silicon), 'mac-x64' (Intel Mac) or 'other'."""
    if IS_WIN:
        return "win"
    if IS_MAC:
        m = (machine or platform.machine()).lower()
        return "mac-arm64" if m in ("arm64", "aarch64") else "mac-x64"
    return "other"


_GH = "https://github.com"
_RIEDL = "https://ffmpeg.martin-riedl.de/redirect/latest/macos/{arch}/release/{prog}.zip"
# tool -> list of (download url, files to take from the zip or None for a plain executable)
TOOL_SOURCES = {
    "win": {
        "yt-dlp": [(f"{_GH}/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", None)],
        "ffmpeg": [(f"{_GH}/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                    ("ffmpeg", "ffprobe"))],
        "deno": [(f"{_GH}/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip", ("deno",))],
    },
    **{key: {
        "yt-dlp": [(f"{_GH}/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos", None)],
        "ffmpeg": [(_RIEDL.format(arch=arch, prog="ffmpeg"), ("ffmpeg",)),
                   (_RIEDL.format(arch=arch, prog="ffprobe"), ("ffprobe",))],
        "deno": [(f"{_GH}/denoland/deno/releases/latest/download/deno-{deno}-apple-darwin.zip", ("deno",))],
    } for key, arch, deno in (("mac-arm64", "arm64", "aarch64"), ("mac-x64", "amd64", "x86_64"))},
}


def make_executable(path):
    if not IS_WIN:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def bundled_dir():
    """Tools shipped inside the program (installed next to Sahm.exe, or vendor_tools/ when run from source)."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "tools")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor_tools", platform_key())


def tools_dir():
    d = os.path.join(data_dir(), "tools")
    os.makedirs(d, exist_ok=True)
    return d


def find(name):
    """Path of a tool: user folder (self-updated yt-dlp), then the bundled copy, then PATH."""
    for d in (tools_dir(), bundled_dir()):
        p = os.path.join(d, name + EXE)
        if os.path.exists(p):
            return p
    return shutil.which(name)


def missing():
    return [n for n in ("yt-dlp", "ffmpeg", "deno") if not find(n)]


def env():
    """Environment for yt-dlp: our tools first on PATH (so it finds ffmpeg + deno), UTF-8 output."""
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([tools_dir(), bundled_dir(), e.get("PATH", "")])
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def run(args, timeout=None):
    return subprocess.run(args, capture_output=True, env=env(), timeout=timeout,
                          creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)


def install_file(downloaded_path, members, dest_dir, plain_name=None):
    """Put one downloaded file in place: a plain executable (renamed to plain_name),
    or the wanted programs extracted from a zip. Works for Windows and macOS builds."""
    os.makedirs(dest_dir, exist_ok=True)
    if members is None:
        dest = os.path.join(dest_dir, plain_name)
        os.replace(downloaded_path, dest)
        make_executable(dest)
        return [dest]
    out = []
    with zipfile.ZipFile(downloaded_path) as z:
        for member in z.namelist():
            base = os.path.basename(member)
            stem = base[:-4] if base.lower().endswith(".exe") else base
            if stem.lower() in members and not member.endswith("/"):
                dest = os.path.join(dest_dir, stem + EXE)
                with z.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                make_executable(dest)
                out.append(dest)
    os.remove(downloaded_path)
    return out


_update_lock = threading.Lock()


def prepare():
    """At startup: copy the bundled yt-dlp to the user folder (Program Files is read-only,
    and yt-dlp must be able to update itself), then update it in the background."""
    src = os.path.join(bundled_dir(), "yt-dlp" + EXE)
    dst = os.path.join(tools_dir(), "yt-dlp" + EXE)
    try:
        if os.path.exists(src) and (not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst)):
            shutil.copy2(src, dst)
            make_executable(dst)
    except OSError:
        pass
    update_ytdlp_in_background()


def auto_install(limiter=None, progress=None, stop=None):
    """Silent fallback when the bundle is missing: fetch the tools with Sahm's own engine.
    progress(fraction) is called while downloading. Returns True when everything is ready."""
    need = missing()
    if not need:
        return True
    sources = TOOL_SOURCES.get(platform_key())
    if not sources:
        return False
    from engine import DownloadTask, Status
    tmp = os.path.join(tools_dir(), "downloading")
    tasks = {}
    for n in need:
        for i, (url, members) in enumerate(sources[n]):
            t = DownloadTask(url, tmp, f"{n}-{i}.download", connections=8)
            t.start(limiter)
            tasks[(n, i)] = (t, members)
    while True:
        if stop is not None and stop.is_set():
            for t, _ in tasks.values():
                t.pause()
            return False
        done = sum(t.downloaded for t, _ in tasks.values())
        total = sum(t.size or 0 for t, _ in tasks.values())
        if progress and total:
            progress(done / total)
        if any(t.status == Status.ERROR for t, _ in tasks.values()):
            return False
        if all(t.status == Status.COMPLETED for t, _ in tasks.values()):
            break
        time.sleep(0.3)
    for (n, _), (t, members) in tasks.items():
        install_file(t.path, members, tools_dir(), n + EXE)
    return not missing()


def update_ytdlp_in_background(force=False):
    """Run `yt-dlp -U` at most once a day (YouTube changes often)."""
    def work():
        with _update_lock:
            exe = find("yt-dlp")
            if not exe or not os.path.abspath(exe).startswith(os.path.abspath(tools_dir())):
                return
            stamp = os.path.join(tools_dir(), "last_update")
            try:
                if not force and time.time() - os.path.getmtime(stamp) < 86400:
                    return
            except OSError:
                pass
            try:
                run([exe, "-U"], timeout=300)
                with open(stamp, "w") as f:
                    f.write(str(time.time()))
            except Exception:
                pass
    threading.Thread(target=work, daemon=True).start()


def kill_tree(proc):
    if proc is None or proc.poll() is not None:
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, creationflags=NO_WINDOW)
    else:
        # yt-dlp runs in its own process group, so this also stops the ffmpeg it started
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def popen_kwargs():
    """Extra Popen options: no console window on Windows, own process group elsewhere."""
    return {"creationflags": NO_WINDOW} if IS_WIN else {"start_new_session": True}


def write_cookie_file(cookies, path):
    """cookies: list of chrome.cookies objects -> Netscape cookies.txt for yt-dlp."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies or []:
        try:
            domain = c["domain"]
            host_only = c.get("hostOnly", False)
            if not host_only and not domain.startswith("."):
                domain = "." + domain
            if any(ch in str(c.get(k, "")) for k in ("domain", "path", "name", "value") for ch in "\t\r\n"):
                continue          # would break the cookies.txt format
            lines.append("\t".join([
                domain, "FALSE" if host_only else "TRUE", c.get("path", "/"),
                "TRUE" if c.get("secure") else "FALSE",
                str(int(c.get("expirationDate", 0) or 0)), c["name"], c.get("value", "")]))
        except (KeyError, TypeError):
            continue
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # owner-only
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
