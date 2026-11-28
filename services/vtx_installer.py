"""
vtx_installer.py - Module Packaging, Installation & Cloud Auto-Updater Helper.
Handles installation of .vtx / .zip archives, folder copy, and GitHub Releases cloud catalog updates.
"""
import os
import sys
import shutil
import json
import zipfile
import tempfile
from utils import safe_delete_module_dir

try:
    from version import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "1.0.0"



def install_vtx_archive(archive_path: str, modules_dir: str) -> tuple[bool, str, str]:
    """
    Extracts a .vtx or .zip archive file into modules/<module_id>/.
    Validates manifest.json presence before extracting.
    Returns (success, module_id, message).
    """
    if not os.path.exists(archive_path):
        return False, "", f"File not found: {archive_path}"

    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()

            # Check if manifest.json is at root or inside a single top-level folder
            manifest_in_root = "manifest.json" in file_list
            manifest_path = None

            if manifest_in_root:
                manifest_path = "manifest.json"
            else:
                for f in file_list:
                    if f.endswith("manifest.json") and f.count("/") == 1:
                        manifest_path = f
                        break

            if not manifest_path:
                return False, "", "Invalid .vtx package: 'manifest.json' not found inside archive."

            # Read and parse manifest.json
            with zip_ref.open(manifest_path) as mf:
                manifest_data = json.loads(mf.read().decode('utf-8'))

            mod_id = manifest_data.get("id")
            mod_name = manifest_data.get("name", mod_id)
            mod_version = manifest_data.get("version", "1.0.0")

            if not mod_id:
                return False, "", "Invalid manifest.json: missing 'id' field."

            # Target installation directory
            target_dir = os.path.join(modules_dir, f"module_{mod_id}")
            if os.path.exists(target_dir):
                safe_delete_module_dir(target_dir)

            os.makedirs(target_dir, exist_ok=True)


            # Extract files
            top_folder_prefix = manifest_path.rsplit("manifest.json", 1)[0]
            for member in zip_ref.infolist():
                if member.is_dir():
                    continue
                rel_path = member.filename
                if top_folder_prefix and rel_path.startswith(top_folder_prefix):
                    rel_path = rel_path[len(top_folder_prefix):]
                
                if not rel_path:
                    continue

                dest_file_path = os.path.abspath(os.path.join(target_dir, rel_path))
                # Security: Prevent Zip-Slip directory traversal attacks
                target_dir_abs = os.path.abspath(target_dir)
                if os.path.commonpath([target_dir_abs, dest_file_path]) != target_dir_abs:
                    print(f"[Security Warning] Skipped suspicious zip entry with path traversal: {member.filename}")
                    continue
                os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)

                with zip_ref.open(member) as source, open(dest_file_path, "wb") as target:
                    shutil.copyfileobj(source, target)

            # Dynamically register newly installed module namespaces & vendor path
            try:
                import importlib
                importlib.invalidate_caches()

                # Purge any stale in-memory cached imports for this module
                to_purge = [k for k in sys.modules if k.startswith(f"module_{mod_id}") or k == mod_id or k.startswith(f"{mod_id}.")]
                for k in to_purge:
                    sys.modules.pop(k, None)

                from services.dev_ui_bridge import _init_module_namespaces
                _init_module_namespaces()
            except Exception:
                pass

            return True, mod_id, f"Successfully installed '{mod_name}' v{mod_version}!"

    except Exception as e:
        return False, "", f"Failed to install package: {e}"


# ─── GITHUB RELEASES & RAW CDN CLOUD STORE UTILITIES ─────────────
import requests
from utils import get_app_dir

GITHUB_USER = "vishwasupponi"
RAW_GITHUB_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}"
GITHUB_RELEASE_BASE = f"https://github.com/{GITHUB_USER}"
OFFICIAL_REGISTRY_URL = f"{RAW_GITHUB_BASE}/vertex-shell/main/modules.json"

DEFAULT_OFFICIAL_MODULES = [
    {
        "id": "bank_statement_converter",
        "name": "Bank Statement Converter",
        "repo": "vtx-bank-statement-converter",
        "bundle": "bank_statement_converter_v1.0.0.vtx"
    },
    {
        "id": "excel_consolidator",
        "name": "Excel Consolidator",
        "repo": "vtx-excel-consolidator",
        "bundle": "excel_consolidator_v1.0.0.vtx"
    },
    {
        "id": "gst_portal_downloader",
        "name": "GSTR Downloader",
        "repo": "vtx-gstr-downloader",
        "bundle": "gst_portal_downloader_v1.0.0.vtx"
    },
    {
        "id": "gst_processor",
        "name": "GST Processor & Consolidator",
        "repo": "vtx-gst-processor",
        "bundle": "gst_processor_v1.0.0.vtx"
    },
    {
        "id": "ocr_engine",
        "name": "OCR Local Neural Engine",
        "repo": "vtx-ocr-engine",
        "bundle": "ocr_local_neural_engine_v1.0.0.vtx"
    }
]


def fetch_live_cloud_catalog():
    """
    Discovers available official modules from GitHub.
    1. Fetches modules.json registry from raw.githubusercontent.com (falls back to local modules.json or DEFAULT_OFFICIAL_MODULES).
    2. Fetches manifest.json for each module in parallel using ThreadPoolExecutor (no 60 req/hr API rate limit).
    3. Dynamically constructs download URLs pointing to GitHub Releases.
    Returns a list of module dictionary descriptors. Gracefully returns [] if offline or repos are 404.
    """
    items = []
    modules_list = None

    # Step 1: Attempt to fetch modules.json from remote raw GitHub
    try:
        r = requests.get(OFFICIAL_REGISTRY_URL, timeout=5, headers={"User-Agent": f"Vertex-Application/{APP_VERSION}"})
        if r.status_code == 200:
            modules_list = r.json()
    except Exception:
        pass

    # Step 1b: Fallback to local modules.json if available
    if not modules_list:
        local_registry = os.path.join(get_app_dir(), "modules.json")
        if os.path.exists(local_registry):
            try:
                with open(local_registry, "r", encoding="utf-8") as f:
                    modules_list = json.load(f)
            except Exception:
                pass

    if not modules_list:
        modules_list = DEFAULT_OFFICIAL_MODULES

    # Step 2: Fetch manifest for each module concurrently
    from concurrent.futures import ThreadPoolExecutor

    def _fetch_module_manifest(mod):
        repo = mod.get("repo", "")
        bundle = mod.get("bundle", f"{mod.get('id', 'module')}.vtx")
        manifest_url = f"{RAW_GITHUB_BASE}/{repo}/main/manifest.json"
        try:
            resp = requests.get(manifest_url, timeout=5, headers={"User-Agent": f"Vertex-Application/{APP_VERSION}"})
            if resp.status_code == 200:
                manifest_data = resp.json()
                version = str(manifest_data.get("version", "1.0.0"))
                mid = str(manifest_data.get("id", mod.get("id", "")))
                cat = manifest_data.get("category", "General Utilities")
                icon = manifest_data.get("icon")
                if not icon:
                    mid_lower = mid.lower()
                    cat_lower = str(cat).lower()
                    if "bank" in mid_lower or "finance" in cat_lower:
                        icon = "🏦"
                    elif "excel" in mid_lower or "spreadsheet" in cat_lower:
                        icon = "📊"
                    elif "gst" in mid_lower or "tax" in cat_lower:
                        icon = "📑"
                    elif "ocr" in mid_lower or "ai" in cat_lower or "neural" in cat_lower:
                        icon = "🧠"
                    else:
                        icon = "📦"

                return {
                    "id": mid,
                    "name": manifest_data.get("name", mod.get("name", repo)),
                    "version": version,
                    "author": manifest_data.get("author", "Vishwas Upponi"),
                    "author_url": manifest_data.get("author_url", "https://vishwasupponi.blogspot.com/links"),
                    "category": cat,
                    "icon": icon,
                    "description": manifest_data.get("description", ""),
                    "is_ui_module": bool(manifest_data.get("ui_page")) or (bool(manifest_data.get("entry_class")) and not mid.startswith("ocr_")),
                    "ui_page": manifest_data.get("ui_page", ""),
                    "vtx_filename": bundle,
                    "download_url": f"{GITHUB_RELEASE_BASE}/{repo}/releases/download/v{version}/{bundle}",
                    "repo": repo
                }
            elif resp.status_code == 404:
                # Repository or manifest not yet published on GitHub
                return None
        except Exception:
            return None
        return None

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(_fetch_module_manifest, modules_list)
            for res in results:
                if res is not None:
                    items.append(res)
    except Exception as e:
        print(f"[CloudStore] Notice while querying module manifests: {e}")

    if not items:
        print("[CloudStore] Notice: Vertex Store modules currently unavailable or offline.")

    return items


def download_module_package(download_url: str, destination_path: str, progress_callback=None, cancel_check=None) -> bool:
    """
    Downloads a module .vtx package from a direct HTTP(S) URL (e.g. GitHub Releases CDN)
    with streaming chunks, progress reporting, and cancellation support.
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': f'Vertex-Application/{APP_VERSION} (Windows NT 10.0; Win64; x64)'
    })

    try:
        with session.get(download_url, stream=True, timeout=45) as res:
            if res.status_code != 200:
                print(f"[CloudStore] Download HTTP error: {res.status_code} for {download_url}")
                return False

            total_size = int(res.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 65536

            with open(destination_path, "wb") as f:
                for chunk in res.iter_content(chunk_size):
                    if cancel_check and cancel_check():
                        f.close()
                        if os.path.exists(destination_path):
                            try: os.remove(destination_path)
                            except Exception: pass
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            progress_callback(percent, downloaded, total_size)

        if os.path.exists(destination_path):
            size = os.path.getsize(destination_path)
            # Ensure it's not an HTML error page
            if size < 5000:
                with open(destination_path, "rb") as f:
                    header = f.read(100)
                    if b"<html" in header.lower() or b"<!doctype" in header.lower():
                        os.remove(destination_path)
                        return False
            return size > 0
    except Exception as e:
        print(f"[CloudStore] Download exception: {e}")
        if os.path.exists(destination_path):
            try: os.remove(destination_path)
            except Exception: pass
        return False
    return False


def install_from_directory(source_dir: str, modules_dir: str) -> tuple[bool, str, str]:
    """
    Copies a module folder into modules/<module_id>/.
    Returns (success, module_id, message).
    """
    manifest_path = os.path.join(source_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return False, "", "Selected folder does not contain a valid 'manifest.json'."

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        mod_id = manifest_data.get("id")
        mod_name = manifest_data.get("name", mod_id)
        mod_version = manifest_data.get("version", "1.0.0")

        if not mod_id:
            return False, "", "Invalid manifest.json: missing 'id' field."

        target_dir = os.path.join(modules_dir, f"module_{mod_id}")
        if os.path.exists(target_dir):
            safe_delete_module_dir(target_dir)

        shutil.copytree(source_dir, target_dir)

        return True, mod_id, f"Successfully installed '{mod_name}' v{mod_version}!"
    except Exception as e:
        return False, "", f"Failed to copy module folder: {e}"
