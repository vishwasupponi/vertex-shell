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
            except BrokenPipeError:
                self.stream = None
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
            except BrokenPipeError:
                self.stream = None
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


def _show_win_message(title, message, flags=0x10):
    """Shows a native Windows message box when running on win32."""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(0, str(message), str(title), flags)
    except Exception:
        return 0


def _is_webview2_installed():
    """Checks Windows registry for Microsoft Edge WebView2 Runtime (>= 86.0.622.0)."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        is_x86 = platform.machine().lower() in ("x86", "i386")
        guids = [
            "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",  # Evergreen Runtime
            "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",  # Beta
            "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",  # Dev
            "{65C35B14-6C1D-4122-AC46-7148CC9D6497}",  # Canary
        ]
        for guid in guids:
            for root_key, root_name in ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
                subpath = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"
                if not is_x86 and root_name == "HKLM":
                    subpath = rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"
                try:
                    with winreg.OpenKey(root_key, subpath) as key:
                        ver, _ = winreg.QueryValueEx(key, "pv")
                        parts = [int(p) for p in str(ver).split(".")[:4] if p.isdigit()]
                        if parts and tuple(parts) >= (86, 0, 622, 0):
                            return True
                except OSError:
                    pass
    except Exception as e:
        print(f"[Vertex Boot] Registry check notice: {e}")
    return False


def ensure_windows_prerequisites():
    """Verifies .NET Framework 4.6.2+ and Edge WebView2 Runtime on Windows, offering guided install if missing."""
    if sys.platform != "win32":
        return True

    # 1. Verify .NET Framework 4.6.2+ (Release >= 394802)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as net_key:
            release_val, _ = winreg.QueryValueEx(net_key, "Release")
        if int(release_val) < 394802:
            msg = (
                "Vertex requires Microsoft .NET Framework 4.6.2 or later.\n\n"
                "Please update Windows or install .NET Framework 4.8 and re-open Vertex."
            )
            print(f"[Vertex Boot Error] {msg}")
            _show_win_message("Vertex - Missing Prerequisite", msg, 0x10 | 0x40000)
            return False
    except OSError:
        pass

    # 2. Verify Microsoft Edge WebView2 Runtime
    if _is_webview2_installed():
        return True

    print("[Vertex Boot] Microsoft Edge WebView2 Runtime not detected.")
    setup_candidates = [
        os.path.join(app_dir, "MicrosoftEdgeWebView2Setup.exe"),
        os.path.join(root_app_dir, "MicrosoftEdgeWebView2Setup.exe"),
        os.path.join(root_app_dir, "Main", "MicrosoftEdgeWebView2Setup.exe"),
    ]
    setup_exe = next((p for p in setup_candidates if os.path.isfile(p)), None)

    if setup_exe:
        choice = _show_win_message(
            "Vertex - WebView2 Runtime Required",
            "Vertex requires the Microsoft Edge WebView2 Runtime to display its interface.\n\n"
            "Would you like to run the included Microsoft installer now?",
            0x04 | 0x30 | 0x40000,  # MB_YESNO | MB_ICONWARNING | MB_TOPMOST
        )
        if choice == 6:  # IDYES
            import subprocess
            print(f"[Vertex Boot] Launching WebView2 installer: {setup_exe}")
            try:
                subprocess.run([setup_exe], check=False)
            except Exception as e:
                print(f"[Vertex Boot Error] Failed to run WebView2 installer: {e}")
            if _is_webview2_installed():
                print("[Vertex Boot] Microsoft Edge WebView2 Runtime installed successfully.")
                return True
            _show_win_message(
                "Vertex - Installation Incomplete",
                "Microsoft Edge WebView2 Runtime was not detected after setup.\n\n"
                "Please ensure you have internet access and finish the WebView2 installation, then relaunch Vertex.",
                0x10 | 0x40000,
            )
        return False

    choice = _show_win_message(
        "Vertex - WebView2 Runtime Required",
        "Vertex requires the Microsoft Edge WebView2 Runtime to display its interface.\n\n"
        "Would you like to open Microsoft's official WebView2 download page now?",
        0x04 | 0x30 | 0x40000,
    )
    if choice == 6:
        import webbrowser
        webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")
    return False

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
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        req_headers = self.headers.get("Access-Control-Request-Headers", "*")
        self.send_header("Access-Control-Allow-Headers", req_headers)
        self.end_headers()

    def do_GET(self):
        self._forward_request("GET")

    def do_POST(self):
        self._forward_request("POST")

    def _forward_request(self, method):
        global _CACHED_COOKIE, _TARGET_DOMAIN
        if not _CACHED_COOKIE and ("xo.je" in _TARGET_DOMAIN or "epizy" in _TARGET_DOMAIN):
            resolve_auth_cookie()

        target_path = self.path if self.path else '/'
        target_url = f"{_TARGET_DOMAIN}{target_path}"

        body = None
        if method in ("POST", "PUT", "PATCH"):
            try:
                content_len = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                content_len = 0
            body = self.rfile.read(content_len) if content_len > 0 else b""

        fwd_headers = {
            "Origin": _TARGET_DOMAIN,
            "Referer": f"{_TARGET_DOMAIN}/",
        }
        for hdr in ("Content-Type", "Accept", "X-Requested-With"):
            val = self.headers.get(hdr)
            if val:
                fwd_headers[hdr] = val

        try:
            resp = _HTTP_SESSION.request(method, target_url, data=body, headers=fwd_headers, timeout=15)
            data = resp.content
            content_type = resp.headers.get("Content-Type", "application/octet-stream")

            if b"/aes.js" in data and len(data) < 2000 and ("xo.je" in _TARGET_DOMAIN or "epizy" in _TARGET_DOMAIN):
                resolve_auth_cookie()
                retry_url = target_url if "?i=1" in target_url else (target_url + ("&i=1" if "?" in target_url else "?i=1"))
                resp = _HTTP_SESSION.request(method, retry_url, data=body, headers=fwd_headers, timeout=15)
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
            self.send_header("Cache-Control", "public, max-age=3600" if method == "GET" else "no-store")
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
    if not ensure_windows_prerequisites():
        return
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
        # Wait until the Vertex window is actually shown on screen before signaling launcher
        try:
            window.events.shown.wait(15)
        except Exception:
            pass
        print("[Vertex Ready]", flush=True)
        if os.environ.get("VERTEX_SPLASH_LAUNCHER") == "1":
            for s in (sys.stdout, sys.stderr):
                if hasattr(s, "stream"):
                    s.stream = None

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
    try:
        run_app()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        if sys.platform == "win32" and os.environ.get("VERTEX_SPLASH_LAUNCHER") != "1":
            has_console = False
            try:
                import ctypes
                has_console = bool(ctypes.windll.kernel32.GetConsoleWindow())
            except Exception:
                pass
            if not has_console:
                _show_win_message(
                    "Vertex - Startup Error",
                    f"Vertex failed to start:\n\n{exc}\n\nSee UserData\\app_debug.log for details.",
                    0x10 | 0x40000,
                )
        sys.exit(1)


