import os
import sys
import platform

import http.server
import requests
import threading
import re
import datetime
import atexit
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)

from utils import get_icon_path, get_user_data_dir, is_compiled, get_app_dir

_is_compiled = is_compiled()
root_app_dir = get_app_dir()

# Enforce strict client environment isolation ONLY when running as standalone/compiled release with bundled Lib/
if _is_compiled or os.path.isdir(os.path.join(root_app_dir, "Lib")) or os.path.isdir(os.path.join(app_dir, "Lib")):
    sys.path = [p for p in sys.path if "AppData" not in p and "Programs\\Python" not in p]

# Route Microsoft Edge WebView2 browser profile cache strictly into UserData/cache/webview
_webview_cache_dir = os.path.join(get_user_data_dir(), "cache", "webview")
try:
    os.makedirs(_webview_cache_dir, exist_ok=True)
    os.environ["WEBVIEW2_USER_DATA_FOLDER"] = _webview_cache_dir
except Exception as e:
    print(f"[Init Notice] WebView2 cache folder init: {e}")

# Set Chromium flags
os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = '--disable-web-security --allow-running-insecure-content'

# ----------------- LIVE REAL-TIME LOGGING REDIRECTION -----------------
user_data_dir = get_user_data_dir()
os.makedirs(user_data_dir, exist_ok=True)
log_path = os.path.join(user_data_dir, "app_debug.log")

# Archive previous session log to app_debug_previous.log so app_debug.log contains ONLY the current session
try:
    if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
        prev_log = os.path.join(user_data_dir, "app_debug_previous.log")
        if os.path.exists(prev_log):
            try:
                os.remove(prev_log)
            except Exception:
                pass
        os.rename(log_path, prev_log)
except Exception as e:
    print(f"[Logging Notice] Session archive error: {e}")

class LineBufferedTee(object):
    def __init__(self, file_handle, original_stream):
        self.file = file_handle
        self.stream = original_stream

    def write(self, data):
        if self.file:
            try:
                self.file.write(data)
                self.file.flush()
            except Exception:
                pass
        if self.stream is not None:
            try:
                self.stream.write(data)
                self.stream.flush()
            except Exception:
                pass

    def flush(self):
        if self.file:
            try:
                self.file.flush()
            except Exception:
                pass
        if self.stream is not None:
            try:
                self.stream.flush()
            except Exception:
                pass

_SHUTDOWN_LOGGED = False
def log_app_shutdown():
    global _SHUTDOWN_LOGGED
    if _SHUTDOWN_LOGGED:
        return
    _SHUTDOWN_LOGGED = True
    close_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[Vertex Shutdown] Session closed on {close_time_str}")
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

atexit.register(log_app_shutdown)

try:
    _log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = LineBufferedTee(_log_handle, sys.stdout)
    sys.stderr = LineBufferedTee(_log_handle, sys.stderr)
    boot_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[Vertex Boot] Session started on {boot_time_str} at {platform.node()} (PID: {os.getpid()})")
    print(f"[Vertex Boot] Writing live logs to: {log_path}")
except Exception as e:
    print(f"[Logging Init Error] {e}")

import webview
from services.dev_ui_bridge import DevVertexAPI, set_dev_window, set_proxy_port

# ----------------- ULTRA-FAST POOLED KEEP-ALIVE PROXY -----------------
PROXY_PORT = 48123
_CACHED_COOKIE = None
_FORWARDER_URL = "https://vishwasupponi.blogspot.com/"
_TARGET_DOMAIN = "https://vishwasupponi.xo.je"

_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://vishwasupponi.blogspot.com/"
})

def resolve_target_domain():
    global _TARGET_DOMAIN, _HTTP_SESSION
    try:
        from urllib.parse import urlparse
        r = _HTTP_SESSION.get(_FORWARDER_URL, timeout=8)
        if r.status_code == 200:
            m = re.search(r'window\.location\.replace\(["\'](https?://[^"\']+)["\']\)', r.text)
            if not m:
                m = re.search(r'window\.location(?:\.href)?\s*=\s*["\'](https?://[^"\']+)["\']', r.text)
            if m:
                dest = m.group(1).strip()
                p = urlparse(dest)
                if p.scheme and p.netloc:
                    _TARGET_DOMAIN = f"{p.scheme}://{p.netloc}"
                    _HTTP_SESSION.headers["Referer"] = f"{_TARGET_DOMAIN}/"
    except Exception:
        pass

def resolve_auth_cookie():
    global _CACHED_COOKIE
    resolve_target_domain()
    if "xo.je" not in _TARGET_DOMAIN and "epizy" not in _TARGET_DOMAIN:
        return None
    try:
        r = _HTTP_SESSION.get(f"{_TARGET_DOMAIN}/", timeout=10)
        challenge_html = r.text
        nums = re.findall(r'toNumbers\("([0-9a-fA-F]+)"\)', challenge_html)
        if len(nums) >= 3:
            a = bytes.fromhex(nums[0])
            b = bytes.fromhex(nums[1])
            c = bytes.fromhex(nums[2])
            cipher = Cipher(algorithms.AES(a), modes.CBC(b))
            dec = cipher.decryptor()
            _CACHED_COOKIE = (dec.update(c) + dec.finalize()).hex()
            _HTTP_SESSION.headers["Cookie"] = f"__test={_CACHED_COOKIE}"
            _HTTP_SESSION.get(f"{_TARGET_DOMAIN}/?i=1", timeout=10)
            return _CACHED_COOKIE
    except Exception:
        pass
    return _CACHED_COOKIE


class UltraFastProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _CACHED_COOKIE, _TARGET_DOMAIN
        if not _CACHED_COOKIE and ("xo.je" in _TARGET_DOMAIN or "epizy" in _TARGET_DOMAIN):
            resolve_auth_cookie()

        target_path = self.path if self.path else '/'
        target_url = f"{_TARGET_DOMAIN}{target_path}"

        try:
            resp = _HTTP_SESSION.get(target_url, timeout=12)
            data = resp.content
            content_type = resp.headers.get("Content-Type", "application/octet-stream")

            if b"/aes.js" in data and len(data) < 2000 and ("xo.je" in _TARGET_DOMAIN or "epizy" in _TARGET_DOMAIN):
                resolve_auth_cookie()
                retry_url = target_url if "?i=1" in target_url else (target_url + ("&i=1" if "?" in target_url else "?i=1"))
                resp = _HTTP_SESSION.get(retry_url, timeout=12)
                data = resp.content
                content_type = resp.headers.get("Content-Type", content_type)

            if "text/html" in content_type:
                html = data.decode("utf-8", errors="ignore")
                html = html.replace(f"{_TARGET_DOMAIN}/", f"http://127.0.0.1:{PROXY_PORT}/")
                html = html.replace(_TARGET_DOMAIN, f"http://127.0.0.1:{PROXY_PORT}")
                data = html.encode("utf-8")

            self.send_response(resp.status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            try:
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Proxy Error: {e}".encode())
            except Exception:
                pass

    def log_message(self, format, *args):
        pass


def start_proxy_server():
    global PROXY_PORT
    threading.Thread(target=resolve_auth_cookie, daemon=True).start()
    try:
        server = http.server.ThreadingHTTPServer(('127.0.0.1', PROXY_PORT), UltraFastProxyHandler)
    except OSError as e:
        print(f"[Vertex Boot] Default proxy port {PROXY_PORT} occupied ({e}). Binding to dynamic ephemeral port...")
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), UltraFastProxyHandler)
        PROXY_PORT = server.server_port
    set_proxy_port(PROXY_PORT)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print("[Vertex Boot] Live Streaming Proxy initialized")


def run_app():
    start_proxy_server()
    ui_index = os.path.join(app_dir, "web_ui", "index.html")
    icon_path = get_icon_path()
    profile_dir = os.path.join(get_user_data_dir(), "webview_profile")
    os.makedirs(profile_dir, exist_ok=True)

    api = DevVertexAPI()
    window = webview.create_window(
        title="Vertex",
        url=ui_index,
        js_api=api,
        width=1280,
        height=820,
        min_size=(960, 620),
        background_color="#0B0B0B",
        on_top=False
    )
    set_dev_window(window)

    def on_loaded():
        # Enforce window is NOT TopMost
        try:
            if hasattr(window, "native") and window.native:
                window.native.TopMost = False
        except Exception as e:
            print(f"[Window Setup Notice] TopMost error: {e}")

        # Hide console in standalone compiled mode
        if _is_compiled:
            try:
                import ctypes
                con_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if con_hwnd:
                    ctypes.windll.user32.ShowWindow(con_hwnd, 0)
                ctypes.windll.kernel32.FreeConsole()
            except Exception as e:
                print(f"[Console Notice] FreeConsole error: {e}")

        # Apply WinForms icon (title bar)
        if icon_path and os.path.exists(icon_path):
            try:
                import clr
                clr.AddReference("System.Drawing")
                from System.Drawing import Icon
                if hasattr(window, "native") and window.native:
                    window.native.Icon = Icon(icon_path)
            except Exception as e:
                print(f"[Window Setup Notice] WinForms Icon error: {e}")

    webview.start(
        on_loaded,
        gui="edgechromium",
        private_mode=False,
        storage_path=profile_dir,
        debug=False,
        icon=icon_path
    )
    log_app_shutdown()


if __name__ == "__main__":
    try:
        import ctypes
        COINIT_APARTMENTTHREADED = 0x2
        ctypes.windll.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    except Exception as e:
        print(f"[OLE Init Notice] CoInitializeEx error: {e}")
    run_app()


