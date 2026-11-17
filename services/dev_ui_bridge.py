import os
import sys
import json
import random
import webbrowser
import subprocess
import shutil
import threading
import time
import atexit
import hashlib
import importlib.util
import webview
from utils import get_app_dir, get_user_data_dir, open_instructions_html, safe_delete_module_dir
from services.notifications_engine import get_notifications_engine
from module_loader import discover_modules

# ─── SESSION EXTRACTION CACHE ────────────────────────────────────
_SESSION_EXTRACTION_CACHE = {}
_SESSION_CACHE_DIR = os.path.join(get_user_data_dir(), "cache", f"session_bank_ext_{os.getpid()}")
try:
    os.makedirs(_SESSION_CACHE_DIR, exist_ok=True)
except Exception:
    pass

def _cleanup_session_cache():
    global _SESSION_EXTRACTION_CACHE
    _SESSION_EXTRACTION_CACHE.clear()
    if os.path.exists(_SESSION_CACHE_DIR):
        try:
            shutil.rmtree(_SESSION_CACHE_DIR, ignore_errors=True)
        except Exception:
            pass

atexit.register(_cleanup_session_cache)

# ─── UNIVERSAL NAMESPACE PACKAGE INITIALIZATION ─────────────────
def _init_module_namespaces():
    app_d = get_app_dir()
    base_dir = os.path.dirname(app_d)
    user_modules_dir = os.path.join(get_user_data_dir(), "modules")
    
    import types
    try:
        import services
    except ImportError:
        services = types.ModuleType("services")
        services.__path__ = []
        sys.modules["services"] = services

    candidate_roots = [base_dir, user_modules_dir]
    for root in candidate_roots:
        if os.path.isdir(root):
            for entry in os.listdir(root):
                entry_p = os.path.join(root, entry)
                if os.path.isdir(entry_p) and (
                    entry.startswith("module_")
                    or entry.startswith("mod_")
                    or entry.startswith("vtx-")
                    or entry.startswith("vtx_")
                    or os.path.exists(os.path.join(entry_p, "manifest.json"))
                ):
                    s_p = os.path.join(entry_p, "services")
                    if os.path.isdir(s_p) and s_p not in services.__path__:
                        services.__path__.append(s_p)
                    v_p = os.path.join(entry_p, "_vendor")
                    if os.path.isdir(v_p) and v_p not in sys.path:
                        sys.path.insert(0, v_p)
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(v_p)
                            except Exception:
                                pass

_init_module_namespaces()

_DEV_WINDOW = None
_LOG_PROC = None
_PROXY_PORT = 48123

def set_proxy_port(port: int):
    global _PROXY_PORT
    _PROXY_PORT = int(port)

def get_proxy_port() -> int:
    return _PROXY_PORT

def get_python_exe():
    candidates = [
        os.path.join(get_app_dir(), "Main", "python.exe"),
        os.path.join(os.path.dirname(sys.executable), "Main", "python.exe"),
        os.path.join(os.path.dirname(sys.executable), "python.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p) and "vertex.exe" not in p.lower():
            return p
    return sys.executable

_MODULES_CACHE = []
_MODULES_LOCK = threading.Lock()

_AREA_SELECTOR_RUNNING = False
_AREA_SELECTOR_LOCK = threading.Lock()

_GST_DOWNLOAD_STOP_EVENT = threading.Event()

ALL_PALETTES = [
    "Monochrome Black",
    "Teal & Cyan (Original)",
    "Royal Purple",
    "Emerald Green",
    "Sunset Orange",
    "Sakura Pink",
    "Classic Blue"
]

def _precache_modules():
    global _MODULES_CACHE
    try:
        mods = discover_modules()
        with _MODULES_LOCK:
            _MODULES_CACHE = mods
    except Exception as e:
        print(f"[Module Precache Error] {e}")
        sys.stdout.flush()

threading.Thread(target=_precache_modules, daemon=True).start()

def set_dev_window(window):
    global _DEV_WINDOW
    _DEV_WINDOW = window

class DevVertexAPI:
    def __init__(self):
        self.notif_engine = get_notifications_engine()

    def get_settings(self):
        settings_file = os.path.join(get_user_data_dir(), "app_settings.json")
        saved_palette = "Monochrome Black"
        saved_mode = "dark"
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved_palette = data.get("palette", data.get("theme", "Monochrome Black"))
                    saved_mode = data.get("mode", "dark")
            except Exception:
                pass

        if saved_palette == "Random on Launch":
            active_palette = random.choice(ALL_PALETTES)
            print(f"[Theme Engine] 'Random on Launch' active -> Picked '{active_palette}' for this session")
            sys.stdout.flush()
        else:
            active_palette = saved_palette

        return {
            "saved_palette": saved_palette,
            "active_palette": active_palette,
            "palette": active_palette,
            "mode": saved_mode,
            "version": "1.1.0"
        }

    def save_theme(self, palette_name, mode):
        settings_file = os.path.join(get_user_data_dir(), "app_settings.json")
        try:
            current = {}
            if os.path.exists(settings_file):
                try:
                    with open(settings_file, "r", encoding="utf-8") as f:
                        current = json.load(f)
                except Exception:
                    pass
            current["palette"] = palette_name
            current["theme"] = palette_name
            current["mode"] = mode
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
            print(f"[Theme Engine] Preference saved: '{palette_name}' ({mode} mode)")
            sys.stdout.flush()
            return True
        except Exception as e:
            print(f"[Theme Engine] Save error: {e}")
            sys.stdout.flush()
            return False

    def open_instructions(self, module_id=None):
        target_name = module_id or "main application"
        print(f"[Help] Opening instructions for {target_name} in default browser...")
        sys.stdout.flush()
        open_instructions_html(module_id)
        return True

    def open_browser_url(self, url):
        print(f"[Browser] Opening link in default browser: {url}")
        sys.stdout.flush()
        webbrowser.open(url)
        return True

    def open_external_url(self, url):
        return self.open_browser_url(url)

    def open_log_window(self):
        global _LOG_PROC
        log_path = os.path.join(get_user_data_dir(), "app_debug.log")
        if not os.path.exists(log_path):
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("[Vertex Log Stream Initialized]\n")
            except Exception:
                pass

        if _LOG_PROC is not None:
            try:
                if _LOG_PROC.poll() is None:
                    print("[Logs] Log stream window already active.")
                    sys.stdout.flush()
                    return "ALREADY_OPEN"
            except Exception:
                pass

        try:
            print(f"[Logs] Spawning live PowerShell log viewer for {log_path}...")
            sys.stdout.flush()
            _LOG_PROC = subprocess.Popen(
                [
                    "powershell.exe", "-NoExit", "-Command",
                    f"$host.UI.RawUI.WindowTitle = 'Vertex System Logs'; "
                    f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                    f"Get-Content -Path '{log_path}' -Wait",
                ],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return "OPENED"
        except Exception as e:
            print(f"[Log Window Error] {e}")
            sys.stdout.flush()
            return "ERROR"

    # ─── Thread-Safe Native Windows File Dialogs ────────────────
    def browse_folder_dialog(self, title="Select Destination Folder"):
        global _DEV_WINDOW
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(webview.FileDialog.FOLDER)
                if res:
                    return res[0] if isinstance(res, (list, tuple)) else str(res)
            except Exception as e:
                print(f"[Folder Dialog Error] {e}")
        return ""

    # ─── Notifications Bridge APIs ──────────────────────────────
    def get_notifications(self, category="ALL", search_q=""):
        return self.notif_engine.get_notifications(category_filter=category, search_query=search_q)

    def get_unread_notifications_count(self):
        return self.notif_engine.get_unread_count()

    def mark_all_notifications_read(self):
        print("[Notifications] Marked all notifications as read.")
        sys.stdout.flush()
        self.notif_engine.mark_all_as_read()
        return True

    def mark_notification_read(self, notif_id):
        self.notif_engine.mark_as_read(notif_id)
        return True

    def dismiss_notification(self, notif_id):
        print(f"[Notifications] Dismissed notification ID: {notif_id}")
        sys.stdout.flush()
        self.notif_engine.dismiss_notification(notif_id)
        return True

    def refresh_notifications_feed(self):
        print("[Notifications] Refreshing live feed from remote catalog...")
        sys.stdout.flush()
        return self.notif_engine.fetch_remote_notifications()

    # ─── Module Manager Bridge APIs ─────────────────────────────
    def get_installed_modules(self):
        global _MODULES_CACHE
        with _MODULES_LOCK:
            if not _MODULES_CACHE:
                _MODULES_CACHE = discover_modules()
            modules = list(_MODULES_CACHE)

        settings_file = os.path.join(get_user_data_dir(), "module_settings.json")
        saved_settings = {}
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    saved_settings = json.load(f)
            except Exception:
                pass

        res = []
        for mod in modules:
            enabled = saved_settings.get(mod.id, {}).get("enabled", True)
            res.append({
                "id": mod.id,
                "name": mod.name,
                "version": mod.version,
                "author": mod.author,
                "author_url": getattr(mod, "author_url", "https://vishwasupponi.blogspot.com/links") or "https://vishwasupponi.blogspot.com/links",
                "category": getattr(mod, "category", "General Utilities"),
                "icon": getattr(mod, "icon", "📦"),
                "description": mod.description,
                "enabled": enabled,
                "is_ui_module": getattr(mod, "is_ui_module", True),
                "module_dir": mod.module_dir,
                "load_error": mod.load_error or "",
                "ui_page": getattr(mod, "ui_page", "") or (mod.manifest.get("ui_page") if hasattr(mod, "manifest") and isinstance(mod.manifest, dict) else ""),
                "page_key": getattr(mod, "page_key", mod.id) or mod.id,
                "repo": getattr(mod, "repo", "") or (mod.manifest.get("repo", "") if hasattr(mod, "manifest") and isinstance(mod.manifest, dict) else "")
            })
        return res

    def toggle_module(self, mod_id, new_state):
        settings_file = os.path.join(get_user_data_dir(), "module_settings.json")
        saved_settings = {}
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    saved_settings = json.load(f)
            except Exception:
                pass
        if mod_id not in saved_settings:
            saved_settings[mod_id] = {}
        saved_settings[mod_id]["enabled"] = new_state
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(saved_settings, f, indent=2)
            print(f"[ModuleManager] Module '{mod_id}' toggle set to: {new_state}")
            sys.stdout.flush()
            return True
        except Exception as e:
            print(f"[Toggle Error] {e}")
            sys.stdout.flush()
            return False

    def delete_installed_module(self, mod_id, module_dir=None):
        global _MODULES_CACHE, _DEV_WINDOW
        target_dir = None

        # 1. Resolve module path from cache first
        with _MODULES_LOCK:
            for m in _MODULES_CACHE:
                mid = getattr(m, "id", None) if not isinstance(m, dict) else m.get("id")
                mdir = getattr(m, "module_dir", None) if not isinstance(m, dict) else m.get("module_dir")
                if mid == mod_id and mdir and os.path.isdir(mdir):
                    target_dir = mdir
                    break

        # 2. Check UserData/modules/ for standard directory names
        if not target_dir:
            user_mods = os.path.join(get_user_data_dir(), "modules")
            clean_id = mod_id.removeprefix("module_").removeprefix("mod_").removeprefix("vtx-").removeprefix("vtx_")
            candidates = [
                os.path.join(user_mods, f"module_{mod_id}"),
                os.path.join(user_mods, mod_id),
                os.path.join(user_mods, f"vtx-{mod_id}"),
                os.path.join(user_mods, f"module_{clean_id}"),
                os.path.join(user_mods, f"mod_{clean_id}"),
                os.path.join(user_mods, f"vtx-{clean_id}"),
                os.path.join(user_mods, f"vtx_{clean_id}"),
            ]
            for c in candidates:
                if os.path.isdir(c):
                    target_dir = c
                    break

        # 3. Fallback: normalize module_dir if provided
        if not target_dir and module_dir:
            norm = os.path.normpath(str(module_dir).strip())
            if os.path.isdir(norm):
                target_dir = norm

        if not target_dir or not os.path.isdir(target_dir):
            return {"success": False, "error": f"Module directory for '{mod_id}' not found."}

        try:
            print(f"[ModuleManager] Deleting module directory: {target_dir}")
            sys.stdout.flush()
            success, msg = safe_delete_module_dir(target_dir)

            _init_module_namespaces()
            with _MODULES_LOCK:
                _MODULES_CACHE = discover_modules()

            if _DEV_WINDOW:
                try: _DEV_WINDOW.evaluate_js("window.syncSidebarModules && window.syncSidebarModules();")
                except Exception: pass

            return {"success": success, "error": msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def select_and_install_local_file(self):
        global _MODULES_CACHE, _DEV_WINDOW
        print("[ModuleManager] Opening file selector for local module installation...")
        sys.stdout.flush()
        file_path = None
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(
                    webview.FileDialog.OPEN,
                    file_types=("Vertex Module Package (*.vtx;*.zip)", "All Files (*.*)")
                )
                if res:
                    file_path = res[0] if isinstance(res, (list, tuple)) else str(res)
            except Exception:
                pass

        if not file_path:
            return {"cancelled": True}

        print(f"[ModuleManager] Installing package from '{file_path}'...")
        sys.stdout.flush()
        from services.vtx_installer import install_vtx_archive
        installed_dir = os.path.join(get_user_data_dir(), "modules")
        ins_success, ins_mod_id, ins_msg = install_vtx_archive(file_path, installed_dir)
        _init_module_namespaces()
        with _MODULES_LOCK:
            _MODULES_CACHE = discover_modules()
        if _DEV_WINDOW:
            try: _DEV_WINDOW.evaluate_js("window.syncSidebarModules && window.syncSidebarModules();")
            except Exception: pass
        print(f"[ModuleManager] Installation result: {ins_success} ({ins_msg})")
        sys.stdout.flush()
        return {
            "cancelled": False,
            "success": ins_success,
            "mod_id": ins_mod_id,
            "message": ins_msg,
            "filename": os.path.basename(file_path)
        }

    def fetch_cloud_catalog(self):
        print("[CloudStore] Querying cloud catalog from Vertex Store...")
        sys.stdout.flush()
        from services.vtx_installer import fetch_live_cloud_catalog
        items = fetch_live_cloud_catalog()
        print(f"[CloudStore] Discovered {len(items)} items in catalog.")
        sys.stdout.flush()
        return items

    def fetch_module_readme(self, repo_name: str) -> dict:
        """
        Fetches README.md from GitHub raw content CDN with timeout and caching.
        Returns a dict: {"success": bool, "markdown": str, "repo": str}
        """
        if not repo_name:
            return {"success": False, "markdown": "*No repository specified.*", "repo": ""}

        import urllib.request
        clean_repo = str(repo_name).strip().strip("/")
        if "/" not in clean_repo:
            clean_repo = f"vishwasupponi/{clean_repo}"

        raw_url = f"https://raw.githubusercontent.com/{clean_repo}/main/README.md"
        try:
            req = urllib.request.Request(raw_url, headers={"User-Agent": "Vertex-Application/1.0.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    content = resp.read().decode("utf-8")
                    return {"success": True, "markdown": content, "repo": clean_repo}
        except Exception as e:
            print(f"[CloudStore] Notice: Unable to fetch remote README for {clean_repo}: {e}")

        # Local fallback if offline or during development
        repo_short = clean_repo.split("/")[-1]
        mod_id = repo_short.replace("vtx-", "").replace("-", "_")
        local_candidates = [
            os.path.join(get_user_data_dir(), "modules", f"module_{mod_id}", "README.md"),
            os.path.join(get_user_data_dir(), "modules", mod_id, "README.md"),
            os.path.join(get_app_dir(), "..", repo_short, "README.md"),
            os.path.join(get_app_dir(), repo_short, "README.md")
        ]
        for cand in local_candidates:
            if os.path.exists(cand):
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        return {"success": True, "markdown": f.read(), "repo": clean_repo}
                except Exception:
                    pass

        # Fallback offline template
        short_title = clean_repo.split("/")[-1].replace("vtx-", "").replace("-", " ").title()
        return {
            "success": False,
            "markdown": f"# {short_title}\n\n> Documentation preview is currently unavailable offline.\n\nWhen connected to the internet, live documentation, user guides, screenshots, and release highlights will load directly from the repository.",
            "repo": clean_repo
        }

    def check_application_updates(self, force: bool = False) -> dict:
        """
        Queries GitHub releases to check whether a newer Stable or Beta release is available.
        """
        try:
            from services.update_checker import check_for_updates
            return check_for_updates(force=force)
        except Exception as e:
            print(f"[UpdateChecker] Error checking application updates: {e}")
            return {
                "current_version": "1.0.0",
                "has_update": False,
                "latest_version": "1.0.0",
                "error": str(e)
            }

    def download_and_install_cloud_module(self, item):
        global _MODULES_CACHE, _DEV_WINDOW
        import time
        from services.vtx_installer import download_module_package, fetch_live_cloud_catalog, install_vtx_archive

        def _emit(step_msg, pct, detail=""):
            print(f"[CloudStore] {step_msg} ({pct}%) - {detail}")
            sys.stdout.flush()
            if _DEV_WINDOW:
                try:
                    _DEV_WINDOW.evaluate_js(f"window.onCloudInstallStep && window.onCloudInstallStep({json.dumps(step_msg)}, {pct}, {json.dumps(detail)});")
                except Exception: pass

        item_name = item.get("name", "Module")
        _emit("Step 1/5: Connecting to Vertex Store...", 10, f"Locating '{item_name}' package...")

        cloud_pkg_dir = os.path.join(get_user_data_dir(), "downloads")
        os.makedirs(cloud_pkg_dir, exist_ok=True)
        vtx_filename = item.get("vtx_filename", f"{item.get('id', 'module')}_v{item.get('version', '1.0.0')}.vtx")
        dest_vtx_path = os.path.join(cloud_pkg_dir, vtx_filename)

        download_url = item.get("download_url")
        if not download_url:
            cat = fetch_live_cloud_catalog()
            for c in cat:
                if c.get("id") == item.get("id") or c.get("vtx_filename") == vtx_filename:
                    download_url = c.get("download_url")
                    break

        if not download_url:
            return {"success": False, "error": f"Download URL for '{item_name}' not found in Vertex Store."}

        _emit("Step 2/5: Downloading package...", 15, "Establishing stream...")

        def _dl_cb(percent, downloaded, total):
            dl_mb = downloaded / (1024 * 1024)
            tot_mb = total / (1024 * 1024) if total > 0 else 0
            prog_pct = int(15 + (percent * 0.60))
            msg = f"Step 2/5: Downloading package... {dl_mb:.1f} MB / {tot_mb:.1f} MB ({percent}%)"
            _emit(msg, prog_pct, f"{percent}% downloaded")

        success = download_module_package(download_url, dest_vtx_path, progress_callback=_dl_cb)
        if not success:
            return {"success": False, "error": "Download failed from Vertex Store. Please check your internet connection."}

        _emit("Step 3/5: Verifying package integrity...", 80, "Checking archive checksum...")
        time.sleep(0.2)

        _emit("Step 4/5: Extracting module files & vendor packages...", 88, "Preserving isolated libraries...")
        installed_dir = os.path.join(get_user_data_dir(), "modules")
        ins_success, ins_mod_id, ins_msg = install_vtx_archive(dest_vtx_path, installed_dir)

        # Delete downloaded .vtx after successful installation
        try:
            if os.path.exists(dest_vtx_path):
                os.remove(dest_vtx_path)
                print("[CloudStore] Cleaned up temporary package archive.")
                sys.stdout.flush()
            if os.path.exists(cloud_pkg_dir) and not os.listdir(cloud_pkg_dir):
                os.rmdir(cloud_pkg_dir)
        except Exception as e:
            print(f"[CloudStore] Notice: {e}")

        if not ins_success:
            return {"success": False, "error": ins_msg}

        _emit("Step 5/5: Registering module & configuring runtime...", 96, "Updating sidebar and namespaces...")
        _init_module_namespaces()
        with _MODULES_LOCK:
            _MODULES_CACHE = discover_modules()

        if _DEV_WINDOW:
            try: _DEV_WINDOW.evaluate_js("window.syncSidebarModules && window.syncSidebarModules();")
            except Exception: pass

        _emit("✓ Module installed successfully!", 100, f"'{item_name}' is ready to use.")
        print(f"[CloudStore] Installed cloud module: {ins_success} ({ins_msg})")
        sys.stdout.flush()
        return {"success": True, "message": ins_msg}

    # ─── 1. Bank Statement Converter Engine ─────────────────────
    def pick_bank_files(self):
        global _DEV_WINDOW
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(
                    webview.FileDialog.OPEN,
                    allow_multiple=True,
                    file_types=("Statements (*.pdf;*.txt)", "PDF Files (*.pdf)", "Text Files (*.txt)", "All Files (*.*)")
                )
                return list(res) if res else []
            except Exception as e:
                print(f"[Pick Bank Files Error] {e}")
        return []

    def get_pdf_info(self, file_path, password=""):
        try:
            import fitz
            doc = fitz.open(file_path)
            if doc.is_encrypted and password:
                doc.authenticate(password)
            page_list = []
            for i in range(len(doc)):
                p = doc[i]
                page_list.append({
                    "page_idx": i,
                    "width": round(p.rect.width, 2),
                    "height": round(p.rect.height, 2)
                })
            doc.close()
            return {"success": True, "total_pages": len(page_list), "pages": page_list}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_pdf_page_render(self, file_path, page_idx=0, password="", zoom=1.5):
        try:
            import fitz
            import base64
            doc = fitz.open(file_path)
            if doc.is_encrypted and password:
                doc.authenticate(password)
            idx = int(page_idx)
            if idx < 0 or idx >= len(doc):
                doc.close()
                return {"success": False, "error": "Invalid page index."}
            page = doc[idx]
            z = max(0.5, min(float(zoom), 3.0))
            mat = fitz.Matrix(z, z)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            b64_str = base64.b64encode(img_bytes).decode("ascii")
            pt_w = page.rect.width
            pt_h = page.rect.height
            doc.close()
            return {
                "success": True,
                "image": f"data:image/png;base64,{b64_str}",
                "width": pix.width,
                "height": pix.height,
                "pt_width": pt_w,
                "pt_height": pt_h
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def auto_detect_page_boxes(self, file_path, page_idx=0, password="", ref_box=None):
        try:
            _init_module_namespaces()
            import fitz
            from services import auto_detect
            doc = fitz.open(file_path)
            if doc.is_encrypted and password:
                doc.authenticate(password)
            idx = int(page_idx)
            if ref_box and isinstance(ref_box, dict) and ref_box.get('rect'):
                detected = auto_detect.adapt_template_to_page(doc, ref_box, idx)
                source = "adapted"
            else:
                detected = auto_detect.auto_detect_page_table(doc, idx)
                source = "detected"
            doc.close()
            return {"success": True, "detected": detected, "source": source}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def auto_detect_all_page_boxes(self, file_path, password="", existing_crop_rects=None):
        try:
            _init_module_namespaces()
            import fitz
            from services import auto_detect
            doc = fitz.open(file_path)
            if doc.is_encrypted and password:
                doc.authenticate(password)
            
            total_pages = len(doc)
            existing = existing_crop_rects or {}
            
            user_pages = set()
            for p_str, b_list in existing.items():
                try: p_num = int(p_str)
                except Exception: continue
                if b_list and b_list != 'skip' and isinstance(b_list, list):
                    first_b = b_list[0]
                    if isinstance(first_b, dict) and (first_b.get('user_modified') or first_b.get('origin') == 'user'):
                        user_pages.add(p_num)

            results = {}
            success_count = len(user_pages)

            for p in range(total_pages):
                if p in user_pages:
                    results[p] = existing.get(str(p)) or existing.get(p)
                    continue

                prev_user_pages = [m for m in user_pages if m < p]
                if prev_user_pages:
                    m_latest = max(prev_user_pages)
                    ref_list = existing.get(str(m_latest)) or existing.get(m_latest)
                    if ref_list and isinstance(ref_list, list) and ref_list[0]:
                        ref_box = ref_list[0]
                        adapted = auto_detect.adapt_template_to_page(doc, ref_box, p)
                        results[p] = [adapted]
                        success_count += 1
                        continue

                detected = auto_detect.auto_detect_page_table(doc, p)
                if detected:
                    results[p] = [detected]
                    success_count += 1

            doc.close()
            return {"success": True, "results": results, "success_pages": success_count, "total_pages": total_pages}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def propagate_tuning_forward(self, file_path, from_page, ref_box, existing_crop_rects=None, password=""):
        try:
            _init_module_namespaces()
            import fitz
            from services import auto_detect
            doc = fitz.open(file_path)
            if doc.is_encrypted and password:
                doc.authenticate(password)

            total_pages = len(doc)
            from_p = int(from_page)
            existing = existing_crop_rects or {}
            results = {}

            for p in range(from_p + 1, total_pages):
                curr_p = existing.get(str(p)) or existing.get(p)
                if curr_p == 'skip':
                    continue
                if curr_p and isinstance(curr_p, list) and len(curr_p) > 0:
                    fb = curr_p[0]
                    if isinstance(fb, dict) and (fb.get('user_modified') or fb.get('origin') == 'user'):
                        continue

                adapted = auto_detect.adapt_template_to_page(doc, ref_box, p)
                results[p] = [adapted]

            doc.close()
            return {"success": True, "propagated": results}
        except Exception as e:
            return {"success": False, "error": str(e)}



    def run_bank_extraction(self, file_paths, use_gemini, api_key, use_ocr, auto_organize, default_pwd, apply_all, crop_rects):
        global _DEV_WINDOW
        if not file_paths:
            return {"success": False, "error": "No statement files selected."}

        _init_module_namespaces()
        def normalize_path(p):
            return os.path.normpath(os.path.abspath(p))

        try:
            import fitz
            from services import bank_statement_parser as parser_engine
            from services import bank_statement_config as config

            if use_gemini and api_key:
                config.set_api_key(api_key)

            file_passwords = {}
            for f in file_paths:
                if f.lower().endswith(".pdf"):
                    norm_p = normalize_path(f)
                    try:
                        doc = fitz.open(f)
                        if doc.is_encrypted and default_pwd:
                            if doc.authenticate(default_pwd) > 0:
                                file_passwords[norm_p] = default_pwd
                        doc.close()
                    except Exception:
                        pass

            all_transactions = []
            total_files = len(file_paths)
            print(f"[Bank Statement Converter] Starting extraction for {total_files} statements...")
            sys.stdout.flush()

            any_from_cache = False

            for idx, file in enumerate(file_paths):
                file_name = os.path.basename(file)
                norm_file_path = normalize_path(file)
                raw_file_crop = crop_rects.get(norm_file_path) if crop_rects else None
                file_crop = None
                if raw_file_crop and isinstance(raw_file_crop, dict):
                    file_crop = {}
                    for k, v in raw_file_crop.items():
                        try: p_idx = int(k)
                        except Exception: p_idx = k
                        file_crop[p_idx] = v

                file_pwd = file_passwords.get(norm_file_path, default_pwd)

                # Compute unique session cache key based on file metadata and exact extraction params
                mtime = os.path.getmtime(file) if os.path.exists(file) else 0
                size = os.path.getsize(file) if os.path.exists(file) else 0
                cache_payload = {
                    "file": norm_file_path,
                    "mtime": mtime,
                    "size": size,
                    "crop": file_crop,
                    "use_gemini": use_gemini,
                    "use_ocr": use_ocr,
                    "auto_organize": auto_organize,
                    "pwd": file_pwd or ""
                }
                cache_key = hashlib.sha256(json.dumps(cache_payload, sort_keys=True).encode("utf-8")).hexdigest()

                # 1. Check in-memory session cache & session temp files
                cached_txs = _SESSION_EXTRACTION_CACHE.get(cache_key)
                if cached_txs is None and os.path.exists(_SESSION_CACHE_DIR):
                    disk_cache_file = os.path.join(_SESSION_CACHE_DIR, f"{cache_key}.json")
                    if os.path.exists(disk_cache_file):
                        try:
                            with open(disk_cache_file, "r", encoding="utf-8") as cf:
                                cached_txs = json.load(cf)
                                _SESSION_EXTRACTION_CACHE[cache_key] = cached_txs
                        except Exception:
                            cached_txs = None

                if cached_txs is not None:
                    any_from_cache = True
                    print(f"[Bank Statement Converter] Instant Session Cache Hit for '{file_name}' ({len(cached_txs)} transactions loaded)")
                    sys.stdout.flush()

                    frac = (idx + 1) / max(total_files, 1)
                    pct = int(round(frac * 100))
                    msg = f"Loaded '{file_name}' from session memory ({len(cached_txs)} rows)..."
                    if _DEV_WINDOW:
                        try:
                            _DEV_WINDOW.evaluate_js(f"window.onBankProgress && window.onBankProgress({pct}, {json.dumps(msg)});")
                        except Exception:
                            pass
                    txs = [dict(t) for t in cached_txs]
                else:
                    def on_page_progress(cur_p, tot_p, text=""):
                        frac = (idx + (cur_p + 1) / max(tot_p, 1)) / max(total_files, 1)
                        pct = int(round(frac * 100))
                        msg = f"Parsing '{file_name}': page {cur_p+1}/{tot_p} ({pct}%)..."
                        if _DEV_WINDOW:
                            try:
                                _DEV_WINDOW.evaluate_js(f"window.onBankProgress && window.onBankProgress({pct}, {json.dumps(msg)});")
                            except Exception:
                                pass

                    txs = parser_engine.process_file(
                        file,
                        use_ocr=use_ocr,
                        use_gemini=use_gemini,
                        api_key=api_key,
                        crop_rect=file_crop,
                        auto_organize=auto_organize,
                        password=file_pwd or "",
                        progress_callback=on_page_progress
                    )
                    for t in txs:
                        t["Source"] = file

                    # Save into session memory & session temp disk cache
                    _SESSION_EXTRACTION_CACHE[cache_key] = [dict(t) for t in txs]
                    if os.path.exists(_SESSION_CACHE_DIR):
                        try:
                            disk_cache_file = os.path.join(_SESSION_CACHE_DIR, f"{cache_key}.json")
                            with open(disk_cache_file, "w", encoding="utf-8") as cf:
                                json.dump(txs, cf)
                        except Exception:
                            pass

                    print(f"[Bank Statement Converter] Extracted {len(txs)} transactions from '{file_name}'")
                    sys.stdout.flush()

                all_transactions.extend(txs)

            print(f"[Bank Statement Converter] Extraction complete! Total extracted: {len(all_transactions)} (cached: {any_from_cache})")
            sys.stdout.flush()

            if not all_transactions:
                return {"success": False, "count": 0, "error": "No transactions could be extracted from the selected files."}

            return {
                "success": True,
                "count": len(all_transactions),
                "transactions": all_transactions,
                "cached": any_from_cache
            }
        except Exception as e:
            print(f"[Bank Extraction Error] {e}")
            sys.stdout.flush()
            return {"success": False, "error": str(e)}

    def clear_session_extraction_cache(self):
        _cleanup_session_cache()
        return {"success": True}

    def export_bank_transactions_dialog(self, transactions, consolidate=True, default_filename="Bank_Transactions.xlsx", rename_dict=None):
        global _DEV_WINDOW
        if not transactions:
            return {"success": False, "error": "No transactions to export."}

        save_path = None
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(
                    webview.FileDialog.SAVE,
                    save_filename=default_filename,
                    file_types=("Excel Workbook (*.xlsx)", "All Files (*.*)")
                )
                if res:
                    save_path = res[0] if isinstance(res, (list, tuple)) else str(res)
            except Exception as e:
                print(f"[Export Dialog Error] {e}")
                sys.stdout.flush()

        if not save_path:
            return {"cancelled": True}

        try:
            _init_module_namespaces()
            from services.excel_exporter import export_transactions_to_excel
            export_transactions_to_excel(transactions, save_path, consolidate=consolidate, rename_dict=rename_dict)
            print(f"[Bank Statement Converter] Successfully exported {len(transactions)} transactions to: {save_path}")
            sys.stdout.flush()
            return {"success": True, "path": save_path, "count": len(transactions)}
        except Exception as e:
            print(f"[Export Error] {e}")
            sys.stdout.flush()
            return {"success": False, "error": str(e)}

    # ─── 2. Excel Consolidator Engine ───────────────────────────
    def pick_excel_files(self):
        global _DEV_WINDOW
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(
                    webview.FileDialog.OPEN,
                    allow_multiple=True,
                    file_types=("Excel Files (*.xlsx;*.xls;*.xlsm;*.xlsb;*.csv)", "All Files (*.*)")
                )
                return list(res) if res else []
            except Exception as e:
                print(f"[Pick Excel Files Error] {e}")
        return []

    def get_unique_excel_sheets(self, file_paths):
        if not file_paths:
            return []
        try:
            _init_module_namespaces()
            from services import excel_consolidator
            sheets = excel_consolidator.get_unique_sheets(file_paths)
            print(f"[Excel Consolidator] Discovered {len(sheets)} unique sheets across {len(file_paths)} files: {sheets}")
            sys.stdout.flush()
            return sheets
        except Exception as e:
            print(f"[Excel Consolidator Error] Failed to read sheets: {e}")
            sys.stdout.flush()
            return []

    def pick_save_excel_path(self, default_name="Consolidated_Output.xlsx"):
        global _DEV_WINDOW
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(
                    webview.FileDialog.SAVE,
                    save_filename=default_name,
                    file_types=("Excel Workbook (*.xlsx)", "All Files (*.*)")
                )
                if res:
                    return res[0] if isinstance(res, (list, tuple)) else str(res)
            except Exception as e:
                print(f"[Pick Save Excel Path Error] {e}")
        return ""

    def run_excel_consolidation(self, file_paths, unique_sheets, save_path):
        global _DEV_WINDOW
        if not file_paths or not save_path:
            return {"success": False, "error": "Missing input files or output save path."}
        try:
            _init_module_namespaces()
            from services import excel_consolidator
            if not unique_sheets:
                unique_sheets = excel_consolidator.get_unique_sheets(file_paths)

            print(f"[Excel Consolidator] Consolidating {len(file_paths)} workbooks to '{save_path}'...")
            sys.stdout.flush()

            def on_progress(fraction):
                pct = int(round(fraction * 100))
                if _DEV_WINDOW:
                    try:
                        _DEV_WINDOW.evaluate_js(f"window.onExcelProgress && window.onExcelProgress({pct});")
                    except Exception:
                        pass

            excel_consolidator.consolidate(file_paths, unique_sheets, save_path, progress_callback=on_progress)
            print(f"[Excel Consolidator] Consolidation complete! Output saved to: {save_path}")
            sys.stdout.flush()
            return {"success": True, "path": save_path}
        except Exception as e:
            print(f"[Excel Consolidator Error] Consolidation failed: {e}")
            sys.stdout.flush()
            return {"success": False, "error": str(e)}

    # ─── 3. GST Returns Downloader Engine ───────────────────────
    def start_gst_download(self, username, password, fy, dest_folder, return_types, months):
        global _GST_DOWNLOAD_STOP_EVENT, _DEV_WINDOW
        _GST_DOWNLOAD_STOP_EVENT.clear()

        try:
            _init_module_namespaces()
            import ctypes
            from services import gst_downloader
            
            def _dialog_callback(dtype, title, msg):
                if _GST_DOWNLOAD_STOP_EVENT and _GST_DOWNLOAD_STOP_EVENT.is_set():
                    return
                def _show_msg(icon_flag):
                    try:
                        ctypes.windll.user32.MessageBoxW(0, str(msg), str(title), icon_flag | 0x10000)
                    except Exception:
                        pass

                if dtype == "info_blocking":
                    _show_msg(0x40)
                elif dtype == "info":
                    threading.Thread(target=_show_msg, args=(0x40,), daemon=True).start()
                elif dtype == "error":
                    threading.Thread(target=_show_msg, args=(0x10,), daemon=True).start()

            def _progress_callback(month_idx, total_months, form_name):
                status_msg = f"Processing: Month {month_idx}/{total_months} — {form_name}"
                print(f"[GST Downloader] {status_msg}")
                sys.stdout.flush()
                if _DEV_WINDOW:
                    try:
                        _DEV_WINDOW.evaluate_js(
                            f"window.VERTEX_STATE && window.VERTEX_STATE.gst_downloader && (window.VERTEX_STATE.gst_downloader.statusText = {json.dumps(status_msg)});"
                            f"const el = document.getElementById('gst-dl-status'); if (el) {{ el.style.display = 'block'; el.style.color = 'var(--accent)'; el.innerText = {json.dumps(status_msg)}; }}"
                        )
                    except Exception: pass

            def _async_worker():
                print(f"[GST Downloader] Initializing automated download session for FY {fy}...")
                print(f"   • Months: {months}")
                print(f"   • Return Forms: {return_types}")
                print(f"   • Destination: {dest_folder or 'Default (Chrome Downloads)'}")
                sys.stdout.flush()
                try:
                    def _log_cb(msg):
                        print(f"[GST Downloader] {msg}")
                        sys.stdout.flush()

                    gst_downloader.run_gst_script(
                        USERNAME=username,
                        PASSWORD=password,
                        YEAR=fy,
                        TARGET_MONTHS=months,
                        SELECTED_FORMS=return_types,
                        log_callback=_log_cb,
                        dialog_callback=_dialog_callback,
                        stop_event=_GST_DOWNLOAD_STOP_EVENT,
                        progress_callback=_progress_callback,
                        download_dir=dest_folder or None
                    )
                    print("[GST Downloader] Download session finished successfully.")
                    sys.stdout.flush()
                    if _DEV_WINDOW:
                        _DEV_WINDOW.evaluate_js("window.onGstDownloadFinished && window.onGstDownloadFinished(true);")
                except Exception as ex:
                    print(f"[GST Downloader Error] {ex}")
                    sys.stdout.flush()
                    if _DEV_WINDOW:
                        _DEV_WINDOW.evaluate_js(f"window.onGstDownloadFinished && window.onGstDownloadFinished(false, {json.dumps(str(ex))});")

            t = threading.Thread(target=_async_worker, daemon=True)
            t.start()
            return {"success": True}
        except Exception as e:
            print(f"[GST Downloader Init Error] {e}")
            sys.stdout.flush()
            return {"success": False, "error": str(e)}

    def stop_gst_download(self):
        global _GST_DOWNLOAD_STOP_EVENT
        _GST_DOWNLOAD_STOP_EVENT.set()
        print("[GST Downloader] Cancellation requested by user.")
        sys.stdout.flush()
        return True

    # ─── 4. GST Processor & Consolidator Engine ─────────────────
    def pick_gst_processor_files(self):
        global _DEV_WINDOW
        if _DEV_WINDOW:
            try:
                res = _DEV_WINDOW.create_file_dialog(
                    webview.FileDialog.OPEN,
                    allow_multiple=True,
                    file_types=("GST Return Files (*.pdf;*.xlsx;*.xls;*.zip;*.json)", "All Files (*.*)")
                )
                return list(res) if res else []
            except Exception as e:
                print(f"[Pick GST Processor Files Error] {e}")
        return []

    def open_folder_in_explorer(self, folder_path):
        if folder_path and os.path.exists(folder_path):
            try:
                subprocess.Popen(f'explorer "{os.path.abspath(folder_path)}"')
                return True
            except Exception as e:
                print(f"[Open Explorer Error] {e}")
        return False

    def run_gst_processing(self, source_mode, source_path, selected_files, output_dir, tasks):
        global _DEV_WINDOW
        try:
            _init_module_namespaces()
            from services.organizer import GSTFileOrganizer
            from services.unified_consolidator import MasterReportConsolidator
            from services.gstr2_consolidator import GSTR2Consolidator

            def _log(msg):
                print(f"[GST Processor] {msg}")
                sys.stdout.flush()

            def _proc_worker():
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    do_organize = tasks.get("organize", True)
                    do_1_3b = tasks.get("master_report", True)
                    do_2a = tasks.get("gstr2a", True)
                    do_2b = tasks.get("gstr2b", True)

                    def _update_progress(pct, msg):
                        _log(msg)
                        if _DEV_WINDOW:
                            try:
                                _DEV_WINDOW.evaluate_js(f"window.onGstProcProgress && window.onGstProcProgress({pct}, {json.dumps(msg)});")
                            except Exception: pass

                    _update_progress(10, f"Starting GST Processing ({source_mode})...")

                    g1_files = []
                    g3b_files = []
                    g2a_sources = []
                    g2b_sources = []

                    organizer = GSTFileOrganizer(log_callback=_log)

                    # Step 1: Organize / Scan
                    if do_organize:
                        _update_progress(20, "Organizing return files into GSTR subfolders...")
                        if source_mode == "files":
                            org_res = organizer.organize_specific_files(
                                file_paths=selected_files,
                                destination_folder=output_dir,
                                deep_inspection=True
                            )
                        else:
                            org_res = organizer.organize_files(
                                source_folder=source_path,
                                destination_folder=output_dir,
                                deep_inspection=True
                            )
                        _log(f"Organization completed! Scanned: {org_res.total_files_scanned}")

                        g1_folder = os.path.join(output_dir, "GSTR-1")
                        g3b_folder = os.path.join(output_dir, "GSTR-3B")
                        g2a_folder = os.path.join(output_dir, "GSTR-2A")
                        g2b_folder = os.path.join(output_dir, "GSTR-2B")

                        if os.path.exists(g1_folder):
                            g1_files = [os.path.join(g1_folder, f) for f in sorted(os.listdir(g1_folder)) if f.lower().endswith(".pdf")]
                        if os.path.exists(g3b_folder):
                            g3b_files = [os.path.join(g3b_folder, f) for f in sorted(os.listdir(g3b_folder)) if f.lower().endswith(".pdf")]
                        if os.path.exists(g2a_folder):
                            g2a_sources = [os.path.join(g2a_folder, f) for f in sorted(os.listdir(g2a_folder)) if f.lower().endswith((".zip", ".xlsx", ".xls"))]
                        if os.path.exists(g2b_folder):
                            g2b_sources = [os.path.join(g2b_folder, f) for f in sorted(os.listdir(g2b_folder)) if f.lower().endswith((".xlsx", ".xls"))]
                    else:
                        _update_progress(20, "Scanning return files directly...")
                        if source_mode == "files":
                            items = organizer.preview_files(selected_files, deep_inspection=True)
                        else:
                            items = organizer.preview_source_folder(source_path, deep_inspection=True)

                        for item in items:
                            fl = item.original_path.lower()
                            if item.detected_form == "GSTR-1" and fl.endswith(".pdf"):
                                g1_files.append(item.original_path)
                            elif item.detected_form == "GSTR-3B" and fl.endswith(".pdf"):
                                g3b_files.append(item.original_path)
                            elif item.detected_form == "GSTR-2A" and fl.endswith((".zip", ".xlsx", ".xls")):
                                g2a_sources.append(item.original_path)
                            elif item.detected_form == "GSTR-2B" and fl.endswith((".xlsx", ".xls")):
                                g2b_sources.append(item.original_path)

                    # Step 2: GSTR-1 & GSTR-3B Master Consolidation
                    if do_1_3b:
                        if g1_files or g3b_files:
                            _update_progress(45, "Generating Master GSTR-1 & 3B Consolidated Report...")
                            output_1_3b = os.path.join(output_dir, "Consolidated Report.xlsx")
                            consolidator = MasterReportConsolidator(log_callback=_log)
                            consolidator.generate_consolidated_report(
                                g1_pdf_paths=g1_files,
                                g3b_pdf_paths=g3b_files,
                                output_filepath=output_1_3b
                            )
                            _log(f"Master GSTR-1 & 3B Report created: {output_1_3b}")
                        else:
                            _log("No GSTR-1 or GSTR-3B PDF files found to consolidate.")

                    # Step 3: GSTR-2A Consolidation
                    if do_2a:
                        if g2a_sources:
                            _update_progress(70, "Consolidating GSTR-2A Returns...")
                            output_2a = os.path.join(output_dir, "Consolidated_GSTR_2A.xlsx")
                            g2_cons = GSTR2Consolidator(log_callback=_log)
                            g2_cons.consolidate_gstr2a(g2a_sources, output_2a)
                            _log(f"Consolidated GSTR-2A Workbook created: {output_2a}")
                        else:
                            _log("No GSTR-2A ZIP or Excel files found to consolidate.")

                    # Step 4: GSTR-2B Consolidation
                    if do_2b:
                        if g2b_sources:
                            _update_progress(88, "Consolidating GSTR-2B Returns...")
                            output_2b = os.path.join(output_dir, "Consolidated_GSTR_2B.xlsx")
                            g2_cons = GSTR2Consolidator(log_callback=_log)
                            g2_cons.consolidate_gstr2b(g2b_sources, output_2b)
                            _log(f"Consolidated GSTR-2B Workbook created: {output_2b}")
                        else:
                            _log("No GSTR-2B Excel files found to consolidate.")

                    _update_progress(100, "ALL REQUESTED GST PROCESSING TASKS COMPLETED SUCCESSFULLY!")
                    if _DEV_WINDOW:
                        _DEV_WINDOW.evaluate_js(f"window.onGstProcFinished && window.onGstProcFinished(true, {json.dumps(output_dir)});")
                except Exception as ex:
                    _log(f"Pipeline failed: {ex}")
                    if _DEV_WINDOW:
                        _DEV_WINDOW.evaluate_js(f"window.onGstProcFinished && window.onGstProcFinished(false, {json.dumps(str(ex))});")

            threading.Thread(target=_proc_worker, daemon=True).start()
            return {"success": True}
        except Exception as e:
            print(f"[GST Processor Init Error] {e}")
            sys.stdout.flush()
            return {"success": False, "error": str(e)}

    def get_proxy_port(self):
        return get_proxy_port()

    def get_page_html(self, page_name):
        print(f"[Navigation] Navigating to page: {page_name}")
        sys.stdout.flush()

        # 1. Check if page_name belongs to any discovered or installed module
        global _MODULES_CACHE
        with _MODULES_LOCK:
            if not _MODULES_CACHE:
                _MODULES_CACHE = discover_modules()
            modules_snapshot = list(_MODULES_CACHE)

        target_module = None
        for mod in modules_snapshot:
            mid = getattr(mod, "id", "")
            mpage_key = getattr(mod, "page_key", mid)
            if page_name in (mid, mpage_key):
                target_module = mod
                break
            if page_name == "bank_converter" and mid == "bank_statement_converter":
                target_module = mod
                break
            if page_name == "gst_downloader" and mid == "gst_portal_downloader":
                target_module = mod
                break

        # If matching module is found, look directly inside its own module_dir
        if target_module and hasattr(target_module, "module_dir") and os.path.isdir(target_module.module_dir):
            mod_dir = target_module.module_dir
            mod_manifest = getattr(target_module, "manifest", {}) or {}

            mod_candidates = []
            declared_ui = getattr(target_module, "ui_page", "") or (mod_manifest.get("ui_page") if isinstance(mod_manifest, dict) else "")
            if declared_ui:
                mod_candidates.append(os.path.join(mod_dir, declared_ui))
                mod_candidates.append(os.path.join(mod_dir, "web_ui", declared_ui))
                mod_candidates.append(os.path.join(mod_dir, "web_ui", os.path.basename(declared_ui)))

            mod_candidates.extend([
                os.path.join(mod_dir, "web_ui", f"{page_name}.html"),
                os.path.join(mod_dir, "web_ui", f"{target_module.id}.html"),
                os.path.join(mod_dir, "web_ui", "page.html"),
                os.path.join(mod_dir, "web_ui", "index.html"),
                os.path.join(mod_dir, f"{page_name}.html"),
                os.path.join(mod_dir, "page.html"),
            ])

            for cp in mod_candidates:
                if cp and os.path.isfile(cp):
                    print(f"[Navigation] Loaded module UI directly from: {cp}")
                    sys.stdout.flush()
                    with open(cp, "r", encoding="utf-8") as f:
                        return f.read()

        # 2. Check core application pages (home, settings, notifications, module_manager) and fallbacks
        app_d = get_app_dir()
        candidate_paths = [
            os.path.join(app_d, "Main", "web_ui", "pages", f"{page_name}.html"),
            os.path.join(app_d, "web_ui", "pages", f"{page_name}.html"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web_ui", "pages", f"{page_name}.html"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_ui", "pages", f"{page_name}.html")
        ]
        for page_path in candidate_paths:
            if os.path.isfile(page_path):
                with open(page_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if page_name == "home":
                    content = content.replace("48123", str(get_proxy_port()))
                return content

        return f"<div class='original-card' style='padding:30px;text-align:center;'><h3 style='color:var(--danger)'>Page '{page_name}' not found.</h3></div>"
