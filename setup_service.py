"""Workstation setup operations; callbacks report progress without touching Tk."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from installer_store import _download, load_catalog, prepare_installers
from clock_service import check_system_time

SYDNEY_TIMEZONE = "AUS Eastern Standard Time"
FRONT_URL = "https://dl.frontapp.com/win32/FrontSetupMachine.msi"
TEAMS_URL = "https://go.microsoft.com/fwlink/?linkid=2243204&clcid=0x409"
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Python-System-Utility-Toolkit" / "installers"


def require_admin():
    if os.name != "nt" or not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Run install_and_run.bat and accept its Windows administrator prompt before setting up this workstation.")


def run_process(command, log, success_codes=(0,), timeout=1800):
    """Wait for the actual installer and preserve diagnostics in the output log."""
    for attempt in range(1, 4):
        result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                                timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 1618 or attempt == 3:
            break
        log(f"Windows Installer is busy. Retry {attempt + 1}/3 in 10s...")
        time.sleep(10)
    for output in (result.stdout, result.stderr):
        if output and output.strip():
            log(output.strip())
    if result.returncode not in success_codes:
        raise RuntimeError(f"{Path(command[0]).name} failed (exit code {result.returncode}).")
    if result.returncode in (1641, 3010):
        log("Restart required to finish installation; restart when convenient.")
    return result


def set_sydney_timezone(log):
    require_admin()
    log("Setting timezone to Sydney (daylight saving enabled)...")
    run_process(["tzutil", "/s", SYDNEY_TIMEZONE], log, timeout=30)
    result = run_process(["tzutil", "/g"], log, timeout=30)
    if result.stdout.strip() != SYDNEY_TIMEZONE:
        raise RuntimeError("Windows did not retain the Sydney timezone setting.")
    log("SUCCESS: Sydney timezone applied and verified.")


def installer_command(entry):
    path = entry["local_path"]
    if entry["name"] == "AnyDesk":
        return [path, "--install", os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "AnyDesk"),
                "--silent", "--create-shortcuts", "--start-with-win"]
    arguments = (entry.get("silent_args") or "").split()
    if path.lower().endswith(".msi"):
        return ["msiexec.exe", "/i", path, *arguments, "/norestart"]
    return [path, *arguments]


def install_normal(log):
    require_admin()
    check_system_time(log)
    catalog = load_catalog(RESOURCE_DIR / "installers.json")
    log("Preparing Normal Setup packages from installers-v1...")
    entries = prepare_installers(catalog, CACHE_DIR, log)
    failures = []
    for index, entry in enumerate(entries, 1):
        name = entry["name"]
        log(f"Installing {index}/{len(entries)}: {name}...")
        if name == "Microsoft Office":
            log("Microsoft Office uses an interactive installer. Complete its setup window to continue.")
        try:
            if name == "Microsoft Teams":
                log("Using Microsoft's current Teams bootstrapper to provision supported Teams.")
                teams_path = CACHE_DIR / "teamsbootstrapper.exe"
                download_signed(TEAMS_URL, teams_path, log)
                run_process([str(teams_path), "-p"], log)
            else:
                run_process(installer_command(entry), log, success_codes=(0, 1641, 3010))
            log(f"SUCCESS: {name} installer completed.")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures.append(name)
            log(f"ERROR: {name}: {exc}")
    if failures:
        raise RuntimeError("Normal Setup incomplete. Failed: " + ", ".join(failures))
    log("SUCCESS: All Normal Setup installers completed.")


def download_signed(url, path, log):
    path.parent.mkdir(parents=True, exist_ok=True)
    _download(url, path, log)
    escaped_path = str(path).replace("'", "''")
    log(f"Verifying installer signature: {path.name}...")
    run_process(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 f"$signature = Get-AuthenticodeSignature -LiteralPath '{escaped_path}'; "
                 "if ($signature.Status -ne 'Valid') { Write-Error 'Installer signature is not valid'; exit 1 }"], log, timeout=60)


def install_front(log):
    require_admin()
    path = CACHE_DIR / "FrontSetupMachine.msi"
    log("Downloading Front from its official desktop installer source...")
    download_signed(FRONT_URL, path, log)
    log("Installing Front for all users...")
    run_process(["msiexec.exe", "/i", str(path), "/qn", "/norestart"], log, success_codes=(0, 1641, 3010))
    log("SUCCESS: Front installer completed.")


def install_windows_app(log):
    winget = shutil.which("winget")
    if not winget:
        raise RuntimeError("WinGet is unavailable. Install or update App Installer from Microsoft Store, then retry.")
    log("Installing Microsoft Windows App for the current Windows user...")
    log("WinGet will download and verify Windows App and its dependencies.")
    command = [winget, "install", "--id", "Microsoft.WindowsApp", "--exact", "--source", "winget",
               "--scope", "user", "--silent", "--disable-interactivity", "--accept-package-agreements",
               "--accept-source-agreements"]
    source_missing = (0x8A15000F, -1978335217)
    for attempt in range(1, 4):
        log(f"Windows App installation - attempt {attempt}/3...")
        result = run_process(command, log, success_codes=(0, 0x8A15002B, -1978335189, *source_missing))
        if result.returncode not in source_missing:
            break
        if attempt == 3:
            raise RuntimeError("WinGet source data is still missing after repair and 3 attempts. "
                               "Update Microsoft App Installer, check network/policies, then use Retry Last Task.")
        if attempt == 1:
            log("WinGet source data is missing. Repairing the community source...")
            for args in (("source", "reset", "--name", "winget", "--force", "--disable-interactivity"),
                         ("source", "update", "--name", "winget", "--disable-interactivity")):
                try:
                    run_process([winget, *args], log, timeout=120)
                except RuntimeError as exc:
                    log(f"WARNING: Source repair: {exc}. Retrying installation anyway.")
        time.sleep(3)
    log("SUCCESS: Microsoft Windows App installed or already current.")


def install_cng(log, apps=("Front", "Windows App")):
    check_system_time(log)
    set_sydney_timezone(log)
    failures = []
    for name, install in (("Front", install_front), ("Windows App", install_windows_app)):
        if name not in apps:
            continue
        try:
            install(log)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures.append(name)
            log(f"ERROR: {name}: {exc}")
    if failures:
        raise RuntimeError("CNG Setup incomplete. Failed: " + ", ".join(failures))
    log("SUCCESS: CNG Setup completed.")
