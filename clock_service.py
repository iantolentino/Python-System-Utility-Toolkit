"""Check UTC clock accuracy independently of the workstation's timezone."""
from email.utils import parsedate_to_datetime
import time
import subprocess
import uuid
import urllib.error
import urllib.request


def check_online_clock(log):
    errors = []
    for url in ("https://www.microsoft.com", "https://github.com"):
        try:
            request = urllib.request.Request(url + "/?toolkit_clock=" + uuid.uuid4().hex, method="HEAD", headers={
                "User-Agent": "Python-System-Utility-Toolkit", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=15) as response:
                server_date = response.headers.get("Date")
            if not server_date:
                raise ValueError("The server did not provide a Date header.")
            difference = abs(time.time() - parsedate_to_datetime(server_date).timestamp())
            if difference > 300:
                raise RuntimeError(f"Windows clock differs from the online clock by {int(difference)} seconds. Open Settings > Time & language > Date & time, correct the date/time, and retry.")
            log(f"Clock accuracy verified over HTTPS (difference: {int(difference)}s).")
            return
        except RuntimeError:
            raise
        except (OSError, urllib.error.URLError, ValueError) as exc:
            errors.append(str(exc))
    raise RuntimeError("Cannot verify the Windows clock over HTTPS. Check the date/time and internet connection, then use Check / Sync Time and Retry Last Task. " + "; ".join(errors))


def check_system_time(log):
    # Import lazily so the installation service can use this module as preflight.
    from setup_service import require_admin, run_process
    require_admin()
    log("Checking Windows date/time; timezone selection is a separate setting.")
    synchronized = False
    try:
        result = run_process(["sc.exe", "start", "w32time"], log, success_codes=(0, 1056, 1058), timeout=30)
        if result.returncode == 1058:
            log("Windows Time is disabled. Enabling the service for clock synchronization...")
            run_process(["sc.exe", "config", "w32time", "start=", "demand"], log, timeout=30)
            run_process(["sc.exe", "start", "w32time"], log, success_codes=(0, 1056), timeout=30)
        for attempt in range(1, 4):
            log(f"Synchronizing Windows time (attempt {attempt}/3)...")
            try:
                run_process(["w32tm", "/resync", "/rediscover"], log, timeout=45)
                synchronized = True
                break
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                log(f"Time synchronization attempt {attempt}/3 unavailable: {exc}")
                if attempt < 3:
                    time.sleep(2)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        log(f"Windows Time synchronization unavailable: {exc}")
    try:
        check_online_clock(log)
    except RuntimeError as exc:
        # An inaccurate clock must never be accepted even after a sync command.
        if "differs from the online clock" in str(exc) or not synchronized:
            raise
        log("Online date check unavailable; Windows Time synchronization succeeded.")
    log("SUCCESS: Windows clock check completed. Continue with workstation setup.")
