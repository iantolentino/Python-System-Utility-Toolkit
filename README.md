# Python System Utility Toolkit

A Windows workstation setup application for IT. Run one CMD command to prepare the prerequisites and open the application, then choose **Category 1: Normal Setup** or **Category 2: CNG Setup**.

## Start on a new PC

The command downloads the current bootstrap from this repository's `main` branch.

Open **Command Prompt** (normal or **Run as administrator**) and paste:

```cmd
curl.exe --fail --location --retry 2 -o "%TEMP%\bootstrap.bat" https://raw.githubusercontent.com/iantolentino/Python-System-Utility-Toolkit/main/bootstrap.bat && call "%TEMP%\bootstrap.bat"
```

Normal CMD automatically requests administrator approval. An administrator CMD continues directly. If you are signed in with a standard Windows account, enter authorized administrator credentials at the Windows prompt. Installation and system timezone/policy changes require that approval; cancelling it stops setup. The bootstrap:

1. Checks Windows Time before prerequisite downloads.
2. Finds Git, or tries WinGet three times with community source repair after the first failure. If WinGet is unavailable or still fails, downloads the official Git for Windows installer, verifies its signature (and release SHA256 when supplied), and installs it for all users. Git becomes available in the same CMD session.
3. Clones this repository to `%USERPROFILE%\Python-System-Utility-Toolkit` in the elevated account, or updates an existing checkout with `git pull --ff-only`. HTTPS and SSH origin URLs for this repository are recognized. If that folder contains another repository or ordinary files, setup preserves it and uses `Python-System-Utility-Toolkit-iantolentino` (then numbered alternatives when needed). The selected path is shown in CMD.
4. Finds Python 3.10+ with Tkinter, or installs Python 3.12 for all users using the same WinGet repair/retry flow, followed by a signed installer from python.org if needed. Microsoft Store shortcuts are skipped.
5. Prepares Microsoft App Installer/WinGet for Windows App if absent, using Microsoft's release assets and SHA256 digests. A failure here is shown but allows the GUI to open for Normal Setup and Front.
6. Automatically opens the maximized application. No third-party Python dependencies are required.

An internet connection and a supported Windows 10/11 installation are required. Windows application deployment must be permitted by the workstation's policies. A failed prerequisite stops the launch and leaves its error visible in CMD.

For a local copy, double-click `install_and_run.bat` or run it from normal/admin CMD; it requests elevation when needed. Use this source launcher; the repository's existing `dist/master_gui.exe` predates these changes.

## Setup categories

| Category | Applications | Timezone behavior |
| --- | --- | --- |
| Normal Setup | OBS Studio, AnyDesk, TeamLogger, Zoom, Microsoft Teams, WinRAR, Microsoft Office, RustDesk | No automatic timezone change; the existing Sync Time PH action remains available. |
| CNG Setup | Front desktop from [front.com](https://front.com/), Microsoft Windows App | Selecting CNG applies and verifies Sydney's `AUS Eastern Standard Time`, including daylight saving. |

Choose **Install Normal Apps** to prepare and run the general installers. Files come from this repository's [installers-v1 release](https://github.com/iantolentino/Python-System-Utility-Toolkit/releases/tag/installers-v1); `installers.json` identifies the assets and pins each file's SHA256. The bundle is copied from the supplied source release with identical filenames and checksums. Verified files are cached under `%LOCALAPPDATA%\Python-System-Utility-Toolkit\installers\installers-v1` and reused. Software installation no longer requires a flash drive. The Block Sites action automatically detects a drive containing your `hosts` file when clicked.

Normal Setup uses Microsoft's [current Teams bootstrapper](https://learn.microsoft.com/en-us/microsoftteams/teams-client-bulk-install) for supported Teams installation, rather than executing the release's older Squirrel installer. Microsoft Office uses its supplied interactive bootstrapper; complete its setup window when prompted. Office activation and app sign-in remain separate from installation.

CNG offers **Install CNG Apps** for both applications, plus individual **Front** and **Windows App** buttons. Front uses its [official machine-wide MSI](https://help.front.com/en/articles/2297) with signature verification. Microsoft Windows App uses the official Microsoft package in WinGet, which resolves its dependencies. Front installs for all users; Windows App installs for the Windows user running the toolkit. Run provisioning in the intended Windows user account, particularly when elevation could use another administrator's credentials.

CNG installation verifies Sydney's timezone before installing either app. A timezone failure stops that installation attempt. Selecting a category does not start app installations.

## Window and progress log

The window starts maximized and is resizable. Setup actions and the output log use the full window width. Scroll the action area with its scrollbar or mouse wheel to reach all utilities; the output log stays visible. **Retry Last Task** is above the log. Press **F11** or use **Full Screen** to toggle borderless fullscreen; **Esc** exits borderless fullscreen.

**Quit** closes the application. **Clean Up and Quit**, next to **Retry Last Task**, removes the toolkit's own files after a confirmation prompt: the verified installer cache under `%LOCALAPPDATA%\Python-System-Utility-Toolkit`, the temporary helper downloads and prerequisite staging folders in `%TEMP%`, and the repository folders that `bootstrap.bat` cloned under `%USERPROFILE%\Python-System-Utility-Toolkit*`. A folder the toolkit is still running from is removed by a hidden script after the window closes. Everything the toolkit provisioned is kept: installed applications, registry policies, the timezone, the power plan, and the `hosts` file. The Git and Python prerequisite installations are also left in place, and a development checkout outside the user profile is never deleted.

Both categories include matching **Check / Sync Time**, **Windows Update**, **Download AMD Drivers**, and **Scan Current State** action tiles. Clock check synchronizes time without changing the selected timezone. Windows Update opens its Windows Settings page so you can check for updates. The AMD action downloads the supplied `26.8.1` minimal installer from `drivers.amd.com` to the running user's `Downloads` folder, verifies its Windows digital signature, and reports the saved path in the log. It does not run the installer automatically. Download or verification failures enable retry and open [AMD's official driver support page](https://www.amd.com/en/support/download/drivers.html), where you can find Ryzen chipset/Radeon drivers and the auto-detect tool.

**Scan Current State** is read-only. It reports every application the toolkit installs, with the detected display name and version, and the current value of each configuration it manages: timezone, power plan, USB storage, mobile hotspot sharing, blocked hosts entries, browser extension policy, and the Outlook large file limit. Applications that ship as MSIX packages, such as Microsoft Teams and Windows App, are detected through their package folder because they have no uninstall entry. Update a fresh image with the scan first if you want a before-and-after record.

The output log shows timestamps, download percentages, checksum/signature verification, the current installer, command output, failures, and restart requirements. Success messages are green and errors are red. The status line shows the current step and elapsed time. Installer and policy tasks run in a background worker while the log remains responsive; another action is blocked until the running job finishes.

Installer output is streamed line by line as it is produced, so the log keeps moving while an installer runs instead of staying silent until it exits. When a job writes nothing for 20 seconds, a keep-alive line reports the elapsed time. Together these stop Windows from marking the window as not responding during long installs such as Microsoft Office. The event queue is also drained in bounded batches per tick, so a burst of installer output cannot freeze the window.

Install Software first reports which applications are already installed, then installs only the missing ones and logs each skip, so an existing installation is never reinstalled.

Installers run sequentially, and their exit codes are checked. MSI restart codes are reported without requesting an automatic restart. Failed applications are listed at the end of the setup. A successful installer exit indicates installer completion, not account sign-in or license activation.

## Time checks, fallbacks, and retrying

Clock accuracy and timezone are checked separately. The application checks time on startup and before installing apps. It starts Windows Time, enables it if disabled, and tries synchronization up to three times without replacing existing domain time settings. If NTP is blocked, it can verify UTC time using HTTPS server timestamps. A clock difference greater than five minutes stops installation with instructions to correct the Windows date/time. A failed clock check leaves the GUI open.

Use **Check / Sync Time** to check again. After a task fails, **Retry Last Task** becomes available. Fix the cause shown in the log and click it. The retry repeats the selected setup; previously verified release downloads are reused.

Downloads retry transient failures up to three times with short delays. HTTPS certificate failures identify incorrect date/time as a possible cause; verification is never disabled. Git/Python WinGet attempts and repository downloads also retry up to three times. Missing WinGet source data (`0x8a15000f`) triggers community source reset/update and retries; Git/Python can fall back to vendor installers. Windows App also repairs that source error and retries up to three times, then reports a clear failure. A busy Windows Installer is retried up to three times. Other installer errors are reported for IT to resolve before an explicit retry.

If the initial curl command fails with a certificate error before the bootstrap is downloaded, correct **Settings > Time & language > Date & time**, click **Sync now**, and paste the command again. For network failures, check internet access, proxy settings, and access to GitHub/Microsoft/Front download servers. A failed prerequisite leaves its error visible in CMD.

## Copy-command webpage

The separate [pc-setup-launcher repository](https://github.com/iantolentino/pc-setup-launcher) contains a single `index.html` page ready for Vercel. After deploying it, open the page and click **Copy CMD command**. It copies the exact quick-start command above, which downloads the bootstrap directly from this repository's `main` branch.

## Verification and rebuilding

```cmd
python -m unittest discover -s tests -v
python -m py_compile master_gui.py setup_service.py installer_store.py clock_service.py
```

Tests cover real Tkinter category switching, fullscreen controls, threaded log handling, failed actions, checksum verification, caching, malformed filenames, installer commands, restart codes, timezone verification, and partial installation failures. Windows tests exercise the PowerShell prerequisite orchestration, including negative WinGet exit codes, source repair, bounded retries, missing WinGet, vendor fallbacks, and signature rejection. CMD tests exercise both launchers with simulated normal/admin privileges and cancelled elevation, including paths containing spaces. Repository selection tests use real local Git repositories to verify URL recognition, Git's line endings, and preservation of occupied folders. Tests mock installation, elevation, and timezone changes to avoid provisioning the development PC.

To rebuild the optional executable in a Python environment with Tkinter:

```cmd
python -m pip install pyinstaller
python -m PyInstaller --clean master_gui.spec
```

The build specification includes `installers.json`. Test the new-PC bootstrap and actual software installations on a dedicated Windows workstation before broad rollout; they have not been executed end to end on a fresh PC during development.
