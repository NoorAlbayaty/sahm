"""Tiny local HTTP server so the browser extension can hand downloads to the app.

Security model
- listens on 127.0.0.1 only
- Host header must be 127.0.0.1/localhost:PORT  -> blocks DNS-rebinding attacks from web pages
- Origin, when present, must be a browser extension -> blocks web pages
- requests must be JSON + carry X-Sahm-Client (forces a CORS preflight, which is never approved)
- everything received is validated; file names are reduced to a safe bare name
"""
import os
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from settings import APP_NAME, APP_VERSION, SERVER_PORT
from engine import safe_filename

incoming = queue.Queue(maxsize=50)
ALLOWED_HOSTS = {f"127.0.0.1:{SERVER_PORT}", f"localhost:{SERVER_PORT}"}
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://", "extension://")
MAX_URL = 8192


def _ok_url(u):
    return isinstance(u, str) and len(u) <= MAX_URL and u.startswith(("http://", "https://"))


def _clean_header(v, limit=16384):
    """Header values must not contain line breaks (header injection)."""
    v = str(v)[:limit]
    return v.replace("\r", "").replace("\n", "")


def _clean_cookie(c):
    if not isinstance(c, dict):
        return None
    out = {}
    for k in ("domain", "path", "name", "value"):
        out[k] = _clean_header(c.get(k, ""), 8192).replace("\t", " ")
    if not out["domain"] or not out["name"]:
        return None
    out["hostOnly"] = bool(c.get("hostOnly"))
    out["secure"] = bool(c.get("secure"))
    try:
        out["expirationDate"] = float(c.get("expirationDate") or 0)
    except (TypeError, ValueError):
        out["expirationDate"] = 0
    return out


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _trusted(self):
        if self.headers.get("Host", "").lower() not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin and not origin.startswith(ALLOWED_ORIGIN_PREFIXES):
            return False
        return True

    def do_GET(self):
        if not self._trusted():
            return self._send(403, {"error": "forbidden"})
        if self.path == "/ping":
            self._send(200, {"app": APP_NAME, "version": APP_VERSION})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if (self.path not in ("/add", "/video") or not self._trusted()
                or self.headers.get("X-Sahm-Client") != "extension"
                or not self.headers.get("Content-Type", "").startswith("application/json")):
            return self._send(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > 2_000_000:
                return self._send(413, {"error": "too large"})
            data = json.loads(self.rfile.read(n))
            if not isinstance(data, dict):
                raise ValueError("bad body")
            url = data.get("url", "")
            if not _ok_url(url):
                return self._send(400, {"error": "bad url"})
            if self.path == "/video":
                media = [m for m in (data.get("media") or []) if _ok_url(m)][:30]
                cookies = [c for c in map(_clean_cookie, (data.get("cookieList") or [])[:300]) if c]
                item = {"type": "video", "url": url, "title": str(data.get("title", ""))[:300],
                        "media": media, "cookies": cookies}
            else:
                headers = {}
                if _ok_url(data.get("referrer", "")):
                    headers["Referer"] = _clean_header(data["referrer"], MAX_URL)
                if data.get("cookies"):
                    headers["Cookie"] = _clean_header(data["cookies"])
                if data.get("userAgent"):
                    headers["User-Agent"] = _clean_header(data["userAgent"], 512)
                raw_name = str(data.get("filename") or "")
                name = safe_filename(os.path.basename(raw_name.replace("\\", "/"))) if raw_name else ""
                item = {"type": "file", "url": url, "filename": name, "headers": headers}
            incoming.put_nowait(item)
            self._send(200, {"ok": True})
        except queue.Full:
            self._send(429, {"error": "busy"})
        except Exception:  # noqa
            self._send(400, {"error": "bad request"})


def start_server(port=SERVER_PORT):
    """Returns the server, or None if the port is busy."""
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    except OSError:
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
