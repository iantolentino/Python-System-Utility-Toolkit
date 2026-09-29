"""Report installed applications and the configurations this toolkit manages.

Read-only: nothing here changes the workstation. The report tells an operator what
is already present before setup starts, so Install Software can skip those
applications instead of reinstalling them.
"""
from __future__ import annotations

import os
import subprocess
import winreg

from pathlib import Path

HOSTS_PATH = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"

UNINSTALL_KEYS = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
)

APPLICATION_PATTERNS = {
    "OBS Studio": ("OBS Studio",),
    "AnyDesk": ("AnyDesk",),
    "TeamLogger": ("TeamLogger",),
    "Zoom": ("Zoom Workplace", "Zoom"),
    "Microsoft Teams": ("Microsoft Teams", "Teams Machine-Wide Installer", "MSTeams"),
    "WinRAR": ("WinRAR",),
    "Microsoft Office": ("Microsoft 365", "Microsoft Office", "Office 16"),
    "RustDesk": ("RustDesk",),
    "Front": ("Front App", "Front"),
    "Windows App": ("Windows App", "Microsoft Remote Desktop"),
}

# Display names that contain a pattern but are a different product.
APPLICATION_EXCLUSIONS = {
    "Microsoft Teams": ("add-in", "addin", "meeting"),
    "Front": ("frontpage", "frontier"),
}

# Modern Teams and Windows App ship as MSIX packages, which have no uninstall
# entry, so their package folder is checked as well.
APPLICATION_PACKAGE_GLOBS = {
    "Microsoft Teams": "MSTeams_*",
    "Windows App": "MicrosoftCorporationII.WindowsApp_*",
}

NORMAL_SETUP_NAMES = ("OBS Studio", "AnyDesk", "TeamLogger", "Zoom",
                      "Microsoft Teams", "WinRAR", "Microsoft Office", "RustDesk")
CNG_SETUP_NAMES = ("Front", "Windows App")

BROWSER_POLICIES = {
    "Chrome": r"SOFTWARE\Policies\Google\Chrome",
    "Edge": r"SOFTWARE\Policies\Microsoft\Edge",
    "Brave": r"SOFTWARE\Policies\BraveSoftware\Brave",
    "Opera": r"SOFTWARE\Policies\Opera Software\Opera",
}


def _registry_value(key, name):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def installed_programs() -> dict[str, str]:
    """Map installed DisplayName -> DisplayVersion from the uninstall keys."""
    programs: dict[str, str] = {}
    for hive, path in UNINSTALL_KEYS:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    subkey = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(hive, f"{path}\\{subkey}") as entry:
                        display = _registry_value(entry, "DisplayName")
                        if not isinstance(display, str) or not display.strip():
                            continue
                        version = _registry_value(entry, "DisplayVersion")
                        programs[display.strip()] = str(version) if version else ""
                except OSError:
                    continue
    return programs


def match_application(name: str, programs: dict[str, str]) -> tuple[str | None, str | None]:
    """Prefer an exact DisplayName match, then a substring match.

    Display names listed in APPLICATION_EXCLUSIONS are skipped so a component such
    as the Teams meeting add-in is never mistaken for the application itself.
    """
    patterns = APPLICATION_PATTERNS.get(name, (name,))
    exclusions = APPLICATION_EXCLUSIONS.get(name, ())
    lowered = {display.lower(): display for display in programs}

    def acceptable(display: str) -> bool:
        low = display.lower()
        return not any(bad in low for bad in exclusions)

    for pattern in patterns:
        exact = lowered.get(pattern.lower())
        if exact and acceptable(exact):
            return exact, programs[exact]
    for pattern in patterns:
        needle = pattern.lower()
        for display in programs:
            if needle in display.lower() and acceptable(display):
                return display, programs[display]
    return None, None


def package_installed(name: str) -> bool:
    """True when an MSIX package folder for the application exists."""
    pattern = APPLICATION_PACKAGE_GLOBS.get(name)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not pattern or not local_app_data:
        return False
    try:
        return next((Path(local_app_data) / "Packages").glob(pattern), None) is not None
    except OSError:
        return False


def application_report(names=NORMAL_SETUP_NAMES, programs: dict[str, str] | None = None) -> list[dict]:
    programs = installed_programs() if programs is None else programs
    report = []
    for name in names:
        display, version = match_application(name, programs)
        if display is None and package_installed(name):
            display, version = f"MSIX package ({APPLICATION_PACKAGE_GLOBS[name]})", ""
        report.append({"name": name, "installed": display is not None,
                       "display": display, "version": version})
    return report


def log_application_report(log, names=NORMAL_SETUP_NAMES, programs: dict[str, str] | None = None) -> list[dict]:
    report = application_report(names, programs)
    detected = sum(1 for entry in report if entry["installed"])
    log(f"Installed applications detected: {detected} of {len(report)}.")
    for entry in report:
        if entry["installed"]:
            version = f" {entry['version']}" if entry["version"] else ""
            log(f"  [installed] {entry['name']}{version}  ({entry['display']})")
        else:
            log(f"  [missing]   {entry['name']}")
    return report


def _command_text(command) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=20,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def timezone_state() -> str:
    return _command_text(["tzutil", "/g"]) or "Unknown"


def power_plan_state() -> str:
    output = _command_text(["powercfg", "/getactivescheme"])
    if not output:
        return "Unknown"
    return output.split("(", 1)[-1].rstrip(")") if "(" in output else output


def usb_storage_state() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\USBSTOR") as key:
            start = _registry_value(key, "Start")
    except OSError:
        return "Unknown"
    return "Disabled (USBSTOR Start=4)" if start == 4 else f"Enabled (USBSTOR Start={start})"


def hotspot_state() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Policies\Microsoft\Windows\Network Connections") as key:
            value = _registry_value(key, "NC_ShowSharedAccessUI")
    except OSError:
        return "Not hidden (policy absent)"
    return "Hidden (policy applied)" if value == 0 else f"Not hidden (NC_ShowSharedAccessUI={value})"


def hosts_state() -> str:
    try:
        lines = HOSTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "Unknown"
    entries = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
    return f"{len(entries)} blocked entries" if entries else "No blocked entries"


def browser_policy_state() -> str:
    applied = []
    for name, path in BROWSER_POLICIES.items():
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path + r"\ExtensionInstallBlocklist") as key:
                if _registry_value(key, "1"):
                    applied.append(name)
        except OSError:
            continue
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Mozilla\Firefox") as key:
            if _registry_value(key, "ExtensionSettings"):
                applied.append("Firefox")
    except OSError:
        pass
    return "Extensions blocked for " + ", ".join(applied) if applied else "No extension policy applied"


def outlook_limit_state() -> str:
    for version in ("16.0", "15.0"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                f"Software\\Microsoft\\Office\\{version}\\Outlook\\PST") as key:
                value = _registry_value(key, "MaxLargeFileSize")
        except OSError:
            continue
        if value:
            return f"{int(value) // 1024} GB limit set (Outlook {version})"
    return "Default limit"


def configuration_report() -> list[tuple[str, str]]:
    return [
        ("Timezone", timezone_state()),
        ("Power plan", power_plan_state()),
        ("USB storage", usb_storage_state()),
        ("Mobile hotspot sharing", hotspot_state()),
        ("Blocked sites (hosts file)", hosts_state()),
        ("Browser extensions", browser_policy_state()),
        ("Outlook large file limit", outlook_limit_state()),
    ]


def log_system_state(log, names=NORMAL_SETUP_NAMES) -> None:
    """Log the installed-application and configuration report as one job."""
    log("Scanning installed applications and applied configurations...")
    log_application_report(log, names)
    log("Applied configurations:")
    for setting, state in configuration_report():
        log(f"  {setting}: {state}")
    log("SUCCESS: System state scan completed.")
