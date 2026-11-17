"""
services/update_checker.py - Vertex Application Auto-Update & Release Checker.
Monitors GitHub releases for 'vishwasupponi/vertex-shell' to detect new Stable and Beta releases.
Provides non-blocking queries, in-memory & UserData caching, and semantic version comparison.
"""
import os
import re
import json
import time
import urllib.request
import urllib.error
from utils import get_user_data_dir

CURRENT_VERSION = "1.0.0"
GITHUB_RELEASES_API = "https://api.github.com/repos/vishwasupponi/vertex-shell/releases"
FALLBACK_VERSION_URL = "https://raw.githubusercontent.com/vishwasupponi/vertex-shell/main/version.json"
CACHE_TTL_SECONDS = 900  # 15 minutes

_MEM_CACHE = {
    "timestamp": 0.0,
    "data": None
}


def parse_semver(ver_str: str) -> tuple[tuple[int, ...], bool, str]:
    """
    Parses a version string into:
    (major_minor_patch_tuple, is_prerelease, prerelease_tag)
    Examples:
      'v1.0.0'      -> ((1, 0, 0), False, '')
      '1.0.1-beta'  -> ((1, 0, 1), True, 'beta')
      'v1.2.0-rc.1' -> ((1, 2, 0), True, 'rc.1')
    """
    if not ver_str:
        return ((0, 0, 0), False, "")

    clean = ver_str.strip().lstrip("vV")
    is_prerelease = False
    prerelease_tag = ""

    # Check for pre-release separator
    if "-" in clean:
        parts = clean.split("-", 1)
        base = parts[0]
        prerelease_tag = parts[1].lower()
        is_prerelease = True
    else:
        base = clean

    nums = []
    for token in re.findall(r"\d+", base):
        try:
            nums.append(int(token))
        except ValueError:
            nums.append(0)

    while len(nums) < 3:
        nums.append(0)

    # If tag contains beta, rc, alpha, preview, mark as prerelease
    if any(k in clean.lower() for k in ["beta", "rc", "alpha", "preview"]):
        is_prerelease = True

    return (tuple(nums[:3]), is_prerelease, prerelease_tag)


def is_version_newer(candidate_ver: str, current_ver: str = CURRENT_VERSION) -> bool:
    """
    Returns True if candidate_ver is strictly newer than current_ver.
    Handles semantic comparisons between stable and prereleases.
    """
    c_nums, c_pre, _ = parse_semver(candidate_ver)
    cur_nums, cur_pre, _ = parse_semver(current_ver)

    if c_nums > cur_nums:
        return True
    elif c_nums == cur_nums:
        # If numeric versions are identical, a final release is newer than a prerelease
        if cur_pre and not c_pre:
            return True
        return False
    return False


def _get_cache_file_path() -> str:
    return os.path.join(get_user_data_dir(), "app_update_cache.json")


def _read_disk_cache() -> dict | None:
    path = _get_cache_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cached_time = data.get("cached_at", 0)
                if (time.time() - cached_time) < CACHE_TTL_SECONDS:
                    return data.get("result")
        except Exception:
            pass
    return None


def _write_disk_cache(result: dict):
    path = _get_cache_file_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "cached_at": time.time(),
                "result": result
            }, f, indent=2)
    except Exception:
        pass


def check_for_updates(force: bool = False) -> dict:
    """
    Checks GitHub for newer releases of Vertex Shell Application.
    Returns structured update descriptor:
      {
        "current_version": "1.0.0",
        "has_update": bool,
        "channel": "stable" | "beta" | None,
        "latest_version": str,
        "release_title": str,
        "release_notes": str,
        "download_url": str,
        "release_url": str,
        "published_at": str
      }
    """
    global _MEM_CACHE

    now = time.time()
    if not force:
        if _MEM_CACHE["data"] and (now - _MEM_CACHE["timestamp"]) < CACHE_TTL_SECONDS:
            return _MEM_CACHE["data"]

        disk = _read_disk_cache()
        if disk:
            _MEM_CACHE["timestamp"] = now
            _MEM_CACHE["data"] = disk
            return disk

    default_res = {
        "current_version": CURRENT_VERSION,
        "has_update": False,
        "channel": None,
        "latest_version": CURRENT_VERSION,
        "release_title": "",
        "release_notes": "",
        "download_url": "",
        "release_url": "https://github.com/vishwasupponi/vertex-shell/releases",
        "published_at": ""
    }

    releases = []

    # Primary check: GitHub Releases REST API
    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_API,
            headers={
                "User-Agent": f"Vertex-Application/{CURRENT_VERSION}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                releases = json.loads(resp.read().decode("utf-8"))
    except Exception:
        releases = []

    # Fallback check: version.json on main branch
    if not releases:
        try:
            req = urllib.request.Request(
                FALLBACK_VERSION_URL,
                headers={"User-Agent": f"Vertex-Application/{CURRENT_VERSION}"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    fallback_data = json.loads(resp.read().decode("utf-8"))
                    cand_ver = fallback_data.get("latest_version") or fallback_data.get("version", "")
                    if cand_ver and is_version_newer(cand_ver, CURRENT_VERSION):
                        is_beta = bool(fallback_data.get("is_beta", False)) or ("beta" in cand_ver.lower())
                        default_res.update({
                            "has_update": True,
                            "channel": "beta" if is_beta else "stable",
                            "latest_version": cand_ver,
                            "release_title": fallback_data.get("title", f"Vertex Application v{cand_ver}"),
                            "release_notes": fallback_data.get("notes", "New update available."),
                            "download_url": fallback_data.get("download_url", ""),
                            "release_url": fallback_data.get("release_url", default_res["release_url"]),
                            "published_at": fallback_data.get("published_at", "")
                        })
                        _write_disk_cache(default_res)
                        _MEM_CACHE = {"timestamp": now, "data": default_res}
                        return default_res
        except Exception:
            pass

    if not releases or not isinstance(releases, list):
        # Offline or no releases found
        return default_res

    # Find the newest release that is newer than CURRENT_VERSION
    best_candidate = None
    for rel in releases:
        tag = rel.get("tag_name", "").strip()
        if not tag:
            continue
        if is_version_newer(tag, CURRENT_VERSION):
            if best_candidate is None or is_version_newer(tag, best_candidate.get("tag_name", "")):
                best_candidate = rel

    if best_candidate:
        tag = best_candidate.get("tag_name", "").strip().lstrip("vV")
        is_prerelease = best_candidate.get("prerelease", False) or ("beta" in tag.lower()) or ("rc" in tag.lower())
        channel = "beta" if is_prerelease else "stable"

        # Locate .zip download asset
        download_url = ""
        assets = best_candidate.get("assets", [])
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".zip") and ("vertex" in name):
                download_url = asset.get("browser_download_url", "")
                break
        if not download_url and assets:
            download_url = assets[0].get("browser_download_url", "")

        default_res.update({
            "has_update": True,
            "channel": channel,
            "latest_version": tag,
            "release_title": best_candidate.get("name") or f"Vertex Application v{tag}",
            "release_notes": best_candidate.get("body", "").strip(),
            "download_url": download_url or best_candidate.get("html_url", ""),
            "release_url": best_candidate.get("html_url", default_res["release_url"]),
            "published_at": best_candidate.get("published_at", "")
        })

    _write_disk_cache(default_res)
    _MEM_CACHE = {"timestamp": now, "data": default_res}
    return default_res
