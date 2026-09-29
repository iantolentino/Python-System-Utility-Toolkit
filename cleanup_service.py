"""Remove the toolkit's own traces while preserving everything it provisioned.

Only files this toolkit creates are removed: the verified installer cache, the
temporary staging folders and helper downloads, and repository folders cloned by
bootstrap.bat. Installed applications, registry policies, the timezone, the power
plan, and the hosts file replaced by Block Sites are never touched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from pathlib import Path

CACHE_FOLDER = "Python-System-Utility-Toolkit"
REPOSITORY_FOLDER = "Python-System-Utility-Toolkit"
CLEANUP_SCRIPT_PREFIX = "toolkit-cleanup-"
TEMP_FILE_NAMES = ("toolkit-prerequisites.ps1", "bootstrap.bat")
TEMP_FOLDER_PATTERNS = ("toolkit-prerequisite-*", "toolkit-winget-*")


def temp_directory() -> Path:
    return Path(tempfile.gettempdir())


def cache_directory() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / CACHE_FOLDER


def temporary_files() -> list[Path]:
    """Helper downloads and staging folders left in the temporary directory."""
    temp = temp_directory()
    targets = [temp / name for name in TEMP_FILE_NAMES]
    for pattern in TEMP_FOLDER_PATTERNS:
        targets.extend(sorted(temp.glob(pattern)))
    return [path for path in targets
            if path.exists() and not path.name.startswith(CLEANUP_SCRIPT_PREFIX)]


def toolkit_files() -> list[Path]:
    """Files that can be removed immediately, while the toolkit is still running."""
    targets = temporary_files()
    cache = cache_directory()
    if cache is not None and cache.exists():
        targets.insert(0, cache)
    return targets


def repository_folders() -> list[Path]:
    """Repository checkouts created by bootstrap.bat under the user profile."""
    profile = os.environ.get("USERPROFILE")
    if not profile:
        return []
    return [path for path in sorted(Path(profile).glob(REPOSITORY_FOLDER + "*"))
            if path.is_dir()]


def running_directory() -> Path:
    return Path(__file__).resolve().parent


def deferred_folders() -> list[Path]:
    """Folders that can only be removed after this process exits.

    A checkout the toolkit is currently running from cannot be deleted in place,
    so it is handed to a detached script. A development checkout outside the user
    profile is deliberately never accepted, which keeps a working copy safe.
    """
    folders = repository_folders()
    profile = os.environ.get("USERPROFILE")
    running = running_directory()
    if not profile or running.parent != Path(profile).resolve():
        return folders
    if not running.name.startswith(REPOSITORY_FOLDER):
        return folders
    if running not in folders:
        folders.append(running)
    return folders


def _size_of(path: Path) -> int:
    try:
        if path.is_dir():
            return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        return path.stat().st_size
    except OSError:
        return 0


def describe(paths: list[Path]) -> tuple[int, int]:
    """Return the number of existing targets and their combined size in bytes."""
    existing = [path for path in paths if path.exists()]
    return len(existing), sum(_size_of(path) for path in existing)


def clean_toolkit_files(log=lambda message: None) -> tuple[int, int]:
    """Delete the cache and temporary traces; return (removed count, bytes freed)."""
    removed = 0
    freed = 0
    for path in toolkit_files():
        size = _size_of(path)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as exc:
            log(f"ERROR: Could not remove {path}: {exc}")
            continue
        removed += 1
        freed += size
        log(f"Removed {path}")
    return removed, freed


def schedule_folder_removal(folders: list[Path], log=lambda message: None, pid: int | None = None) -> Path | None:
    """Write and launch a detached script that removes folders once this process exits."""
    targets = [path for path in folders if path.exists()]
    if not targets:
        return None
    pid = os.getpid() if pid is None else pid
    script = temp_directory() / f"{CLEANUP_SCRIPT_PREFIX}{os.urandom(6).hex()}.ps1"
    quoted = ",\n    ".join("'" + str(path).replace("'", "''") + "'" for path in targets)
    script.write_text(
        "$ErrorActionPreference = 'SilentlyContinue'\n"
        f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Milliseconds 700\n"
        "foreach ($path in @(\n    " + quoted + "\n)) {\n"
        "    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue\n"
        "}\n"
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8",
    )
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", str(script)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    log("Folder removal scheduled after exit: " + ", ".join(str(path) for path in targets))
    return script
