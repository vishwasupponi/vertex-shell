"""
module_loader.py - Discovers and loads Vertex Addon Modules from UserData/modules/ and cloud_packages/.
Scans persistent UserData/modules/ directory and cloud_packages/ for .vtx archives,
reads manifest.json, and dynamically imports entrypoint classes (.py and .pyd C binaries).
Enforces Rule #7: Interactive UI modules use 'mod_' prefix; background service engines (like ocr_engine) do not.
"""
import os
import sys
import json
import shutil
import importlib
import importlib.util
import ctypes

def _get_long_path(p):
    try:
        buf = ctypes.create_unicode_buffer(1024)
        res = ctypes.windll.kernel32.GetLongPathNameW(str(p), buf, 1024)
        return buf.value if res > 0 else str(p)
    except Exception:
        return str(p)

_ACTIVE_DLL_COOKIES = []
_REGISTERED_DLL_DIRS = set()

_orig_add_dll_directory = getattr(os, "add_dll_directory", None)
if _orig_add_dll_directory:
    def _safe_add_dll_directory(path):
        try:
            long_p = _get_long_path(path)
            if long_p not in _REGISTERED_DLL_DIRS and os.path.isdir(long_p):
                cookie = _orig_add_dll_directory(long_p)
                if cookie is not None:
                    _ACTIVE_DLL_COOKIES.append(cookie)
                    _REGISTERED_DLL_DIRS.add(long_p)
                return cookie
        except Exception:
            pass
    os.add_dll_directory = _safe_add_dll_directory

from utils import get_app_dir, get_user_data_dir, cleanup_pending_deleted_modules

def get_installed_modules_dir():
    """Returns the persistent UserData/modules folder path."""
    modules_dir = os.path.join(get_user_data_dir(), "modules")
    os.makedirs(modules_dir, exist_ok=True)
    return modules_dir


def init_global_vendor_and_stdlib_paths():
    """
    Ensures that:
    1. Main/Lib and Main/DLLs are in sys.path and DLL search paths.
    2. All _vendor folders in UserData/modules/ are registered on sys.path and targeted DLL search paths.
    """
    app_dir = _get_long_path(get_app_dir())
    dlls_dir = _get_long_path(os.path.join(app_dir, "DLLs"))
    lib_dir = _get_long_path(os.path.join(app_dir, "Lib"))

    for p in [app_dir, lib_dir, dlls_dir]:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    
    if os.path.isdir(dlls_dir):
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(dlls_dir)
            except Exception:
                pass
    
    # Register targeted _vendor folders across all installed modules
    try:
        modules_dir = _get_long_path(get_installed_modules_dir())
        if os.path.isdir(modules_dir):
            for mod_folder in os.listdir(modules_dir):
                mod_path = _get_long_path(os.path.join(modules_dir, mod_folder))
                if os.path.isdir(mod_path):
                    v_dir = _get_long_path(os.path.join(mod_path, "_vendor"))
                    if os.path.isdir(v_dir):
                        if v_dir not in sys.path:
                            sys.path.append(v_dir)
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(v_dir)
                            except Exception:
                                pass
                        
                        torch_lib = _get_long_path(os.path.join(v_dir, "torch", "lib"))
                        if os.path.isdir(torch_lib):
                            if hasattr(os, "add_dll_directory"):
                                try:
                                    os.add_dll_directory(torch_lib)
                                except Exception:
                                    pass
                            dll_p = os.path.join(torch_lib, 'libiomp5md.dll')
                            if os.path.exists(dll_p):
                                try:
                                    ctypes.CDLL(dll_p)
                                except Exception:
                                    pass
    except Exception as e:
        print(f"[ModuleLoader] Vendor registration error: {e}")


# Global stdlib path initialization
init_global_vendor_and_stdlib_paths()

def _apply_numpy_compat_polyfill():
    """Bridges missing legacy NumPy type aliases for openpyxl / pandas compatibility."""
    try:
        import numpy as _np
        for _alias, _target in [
            ('short', getattr(_np, 'int16', None)),
            ('ushort', getattr(_np, 'uint16', None)),
            ('int_', getattr(_np, 'int64', getattr(_np, 'int32', None))),
            ('uint', getattr(_np, 'uint64', getattr(_np, 'uint32', None))),
            ('longlong', getattr(_np, 'int64', None)),
            ('ulonglong', getattr(_np, 'uint64', None)),
            ('half', getattr(_np, 'float16', None)),
            ('single', getattr(_np, 'float32', None)),
            ('double', getattr(_np, 'float64', None)),
            ('longdouble', getattr(_np, 'float64', None)),
            ('intp', getattr(_np, 'int64', getattr(_np, 'int32', None))),
            ('uintp', getattr(_np, 'uint64', getattr(_np, 'uint32', None))),
        ]:
            if _target is not None and not hasattr(_np, _alias):
                setattr(_np, _alias, _target)
    except Exception:
        pass

_apply_numpy_compat_polyfill()



def auto_extract_cloud_packages():
    """
    Checks the application's cloud_packages/ folder for .vtx archives.
    Automatically extracts them into UserData/modules/module_<id>/ if not already installed.
    """
    app_dir = get_app_dir()
    cloud_dirs = [
        os.path.join(app_dir, "cloud_packages"),
        os.path.join(app_dir, "modules"),
        os.path.join(os.path.dirname(app_dir), "cloud_packages"),
        os.path.join(os.path.dirname(app_dir), "modules")
    ]

    from services.vtx_installer import install_vtx_archive
    modules_dir = get_installed_modules_dir()

    for cd in cloud_dirs:
        if os.path.isdir(cd):
            for item in sorted(os.listdir(cd)):
                if item.endswith(".vtx") or item.endswith(".zip"):
                    vtx_path = os.path.join(cd, item)
                    try:
                        install_vtx_archive(vtx_path, modules_dir)
                    except Exception as e:
                        print(f"[ModuleLoader] Auto-extract cloud package '{item}' error: {e}")



class ModuleInfo:
    """Holds metadata and loaded class for a single addon module."""
    def __init__(self, module_dir, manifest):
        self.module_dir = module_dir
        self.manifest = manifest
        self.id = manifest.get("id", "unknown")
        self.name = manifest.get("name", "Unknown Module")
        self.version = manifest.get("version", "0.0.0")
        self.author = manifest.get("author", "Unknown")
        self.category = manifest.get("category", "UNCATEGORIZED")
        self.description = manifest.get("description", "")
        self.icon = manifest.get("icon")
        if not self.icon:
            mid_lower = self.id.lower()
            cat_lower = str(self.category).lower()
            if "bank" in mid_lower or "finance" in cat_lower:
                self.icon = "🏦"
            elif "excel" in mid_lower or "spreadsheet" in cat_lower:
                self.icon = "📊"
            elif "gst" in mid_lower or "tax" in cat_lower:
                self.icon = "📑"
            elif "ocr" in mid_lower or "ai" in cat_lower or "neural" in cat_lower:
                self.icon = "🧠"
            else:
                self.icon = "📦"
        self.entrypoint = manifest.get("entrypoint", manifest.get("entry_point", "entrypoint.py"))
        self.entry_class = manifest.get("entry_class", "")
        self.dependencies = manifest.get("dependencies", [])
        self.ui_page = manifest.get("ui_page", manifest.get("ui_entry", ""))
        self.page_key = manifest.get("page_key", self.id)
        
        # Rule #7: Interactive UI modules use 'mod_' prefix or explicit UI entry class
        self.is_ui_module = self.id.startswith("mod_") or (manifest.get("has_ui", True) and bool(self.entry_class) and not self.id.startswith("ocr_") and self.id != "ocr_engine")
        self.enabled = True
        self.loaded_class = None
        self.load_error = None

    def load(self):
        """Dynamically import the module's entry class (supporting .py source and .pyd binaries).

        Note: .py source files are always preferred when both exist. The gui/ and services/
        root packages are saved, evicted, and restored around each load to prevent the main
        app's packages from shadowing the addon's own.
        """
        if self.loaded_class is not None:
            return self.loaded_class

        if not self.entry_class:
            return None

        import traceback as _tb

        # Track modified __path__ lists to clean up in finally
        path_modifications = []
        module_dir_added = False
        vendor_dir_added = False
        vendor_dir = os.path.join(self.module_dir, "_vendor")

        # Invalidate import caches so newly extracted vendor packages are immediately discoverable
        importlib.invalidate_caches()

        # Evict uninitialized or broken numpy / pandas imports from sys.modules
        for _pkg in ['numpy', 'pandas', 'openpyxl']:
            if _pkg in sys.modules:
                mod_obj = sys.modules[_pkg]
                if not hasattr(mod_obj, '__version__') or not hasattr(mod_obj, '__file__'):
                    del sys.modules[_pkg]

        modules_before = set(sys.modules.keys())

        try:
            # --- Step 1: Prepend module_dir and _vendor to sys.path ---
            if self.module_dir in sys.path:
                sys.path.remove(self.module_dir)
            sys.path.insert(0, self.module_dir)
            module_dir_added = True

            # Collect all vendor directories to register (current module + shared engines)
            all_vendors = [vendor_dir]
            mods_parent = os.path.dirname(self.module_dir)
            if os.path.isdir(mods_parent):
                for other_mod in os.listdir(mods_parent):
                    other_v = os.path.join(mods_parent, other_mod, "_vendor")
                    if os.path.isdir(other_v) and other_v not in all_vendors:
                        all_vendors.append(other_v)

            for v_path in all_vendors:
                if os.path.isdir(v_path):
                    if v_path not in sys.path:
                        sys.path.insert(0, v_path)
                    try:
                        long_v = _get_long_path(v_path)
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(long_v)
                            except Exception:
                                pass

                        t_lib = _get_long_path(os.path.join(long_v, "torch", "lib"))
                        if os.path.isdir(t_lib):
                            if hasattr(os, "add_dll_directory"):
                                try:
                                    os.add_dll_directory(t_lib)
                                except Exception:
                                    pass
                            omp = os.path.join(t_lib, "libiomp5md.dll")
                            if os.path.exists(omp):
                                try:
                                    ctypes.CDLL(omp)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # --- Step 2: Extend __path__ of existing 'gui' and 'services' packages ---
            for ns in ("gui", "services"):
                sub_dir = os.path.join(self.module_dir, ns)
                if os.path.isdir(sub_dir) and ns in sys.modules:
                    pkg = sys.modules[ns]
                    if hasattr(pkg, "__path__"):
                        try:
                            if sub_dir not in pkg.__path__:
                                pkg.__path__.insert(0, sub_dir)
                                path_modifications.append((pkg.__path__, sub_dir))
                        except Exception:
                            pass

            # --- Step 3: Resolve and load entrypoint ---
            entry_path = os.path.join(self.module_dir, self.entrypoint)
            if not os.path.exists(entry_path):
                # Fallback 1: check for .pyc compiled bytecode
                pyc_path = entry_path + "c"
                if os.path.exists(pyc_path):
                    entry_path = pyc_path
                else:
                    # Fallback 2: check for native C extension .pyd
                    entry_stem = os.path.splitext(self.entrypoint)[0]
                    pyd_candidates = [
                        os.path.join(self.module_dir, f"{entry_stem}.pyd"),
                        os.path.join(self.module_dir, f"{entry_stem}.cp312-win_amd64.pyd"),
                    ]
                    found_pyd = next((p for p in pyd_candidates if os.path.exists(p)), None)
                    if found_pyd:
                        entry_path = found_pyd
                    else:
                        raise FileNotFoundError(f"Entrypoint file '{self.entrypoint}' (or .pyd binary) not found in {self.module_dir}")

            entry_stem = os.path.splitext(os.path.basename(entry_path))[0]
            if entry_stem.endswith(".cp312-win_amd64"):
                entry_stem = entry_stem.replace(".cp312-win_amd64", "")

            # If entry_path is a .pyd binary, use importlib.machinery or standard spec
            if entry_path.endswith(".pyd"):
                spec = importlib.util.spec_from_file_location(entry_stem, entry_path)
            else:
                spec = importlib.util.spec_from_file_location(entry_stem, entry_path)

            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {entry_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[entry_stem] = module
            spec.loader.exec_module(module)

            cls = getattr(module, self.entry_class, None)
            if cls is None:
                raise AttributeError(f"Class '{self.entry_class}' not found in {entry_path}")

            self.loaded_class = cls
            self.load_error = None
            print(f"[ModuleLoader] Loaded addon class '{self.entry_class}': {self.name} v{self.version}")
            return cls

        except Exception as e:
            self.load_error = str(e)
            print(f"[ModuleLoader] Failed to load addon '{self.name}': {e}")
            _tb.print_exc()
            return None

        finally:
            # Clean up temporary namespace package __path__ modifications
            for path_list, target_dir in path_modifications:
                if target_dir in path_list:
                    path_list.remove(target_dir)

            # If load failed, remove module_dir and _vendor from sys.path
            if self.loaded_class is None:
                if module_dir_added and self.module_dir in sys.path:
                    sys.path.remove(self.module_dir)
                if vendor_dir_added and vendor_dir in sys.path:
                    sys.path.remove(vendor_dir)



def discover_modules(search_dir=None):
    """
    Scans search_dir and UserData/modules for module directories containing manifest.json.
    Auto-extracts local cloud_packages/ .vtx files first.
    Returns a list of ModuleInfo objects sorted by category then name.
    """
    # 0. Clean up any stale .deleted_* folders from previous runs before discovery
    cleanup_pending_deleted_modules(get_installed_modules_dir())
    if search_dir is not None:
        cleanup_pending_deleted_modules(search_dir)

    # 1. Auto-extract local cloud_packages/ if present
    auto_extract_cloud_packages()

    search_dirs = []
    
    app_dir = get_app_dir()
    # Check top-level modules folder alongside UserData/modules
    for candidate in [
        os.path.join(app_dir, "modules"),
        os.path.join(get_user_data_dir(), "modules")
    ]:
        if os.path.isdir(candidate) and candidate not in search_dirs:
            search_dirs.append(candidate)

    # Custom or workspace search directory
    if search_dir is not None and os.path.isdir(search_dir):
        if search_dir not in search_dirs:
            search_dirs.append(search_dir)
    else:
        parent_dir = os.path.dirname(get_app_dir())
        if os.path.isdir(parent_dir):
            search_dirs.append(parent_dir)

    modules = []
    seen_ids = set()

    for s_dir in search_dirs:
        if not os.path.isdir(s_dir):
            continue

        for entry in sorted(os.listdir(s_dir)):
            if ".deleted_" in entry:
                continue

            module_dir = os.path.join(s_dir, entry)
            if not os.path.isdir(module_dir):
                continue

                
            manifest_path = os.path.join(module_dir, "manifest.json")
            if not os.path.exists(manifest_path):
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                
                mod_id = manifest.get("id")
                if mod_id and mod_id in seen_ids:
                    continue

                mod_info = ModuleInfo(module_dir, manifest)
                modules.append(mod_info)
                if mod_id:
                    seen_ids.add(mod_id)
                print(f"[ModuleLoader] Discovered addon: {mod_info.name} v{mod_info.version} in {module_dir}")
                
            except Exception as e:
                print(f"[ModuleLoader] Error reading manifest in '{entry}': {e}")

    # Sort by category first, then by name
    modules.sort(key=lambda m: (m.category, m.name))
    print(f"[ModuleLoader] Total addons discovered: {len(modules)}")
    return modules


def load_module_settings(settings_path):
    """Load module enabled/disabled state from a settings JSON file."""
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_module_settings(settings_path, settings):
    """Save module enabled/disabled state to a settings JSON file."""
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"[ModuleLoader] Failed to save settings: {e}")
