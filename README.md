# Python System Utility Toolkit

A Windows workstation setup application for IT. Run one CMD command to prepare the prerequisites and open the application, then choose **Category 1: Normal Setup** or **Category 2: CNG Setup**.

## Start on a new PC

The command downloads the current bootstrap from this repository's `main` branch.

Open **Command Prompt as Administrator** and paste:

```cmd
curl.exe --fail --location --retry 2 -o "%TEMP%\bootstrap.bat" https://raw.githubusercontent.com/iantolentino/Python-System-Utility-Toolkit/main/bootstrap.bat && call "%TEMP%\bootstrap.bat"
```

Accept the Windows administrator prompt if shown. The bootstrap:

1. Installs Microsoft App Installer/WinGet and its dependencies if WinGet is absent, using Microsoft's release assets and SHA256 digests.
2. Installs Git if absent and makes it available in the same CMD session.
3. Clones this repository to `%USERPROFILE%\Python-System-Utility-Toolkit`, or updates an existing checkout with `git pull --ff-only`.
4. Finds a working Python 3.10+ with Tkinter, or installs Python 3.12 for all users.
5. Automatically opens the maximized application. No third-party Python dependencies are required.

An internet connection and a supported Windows 10/11 installation are required. Windows application deployment must be permitted by the workstation's policies. A failed prerequisite stops the launch and leaves its error visible in CMD.

For a local copy, double-click `install_and_run.bat`. Use this source launcher; the repository's existing `dist/master_gui.exe` predates these changes.

## Setup categories

| Category | Applications | Timezone behavior |
| --- | --- | --- |
| Normal Setup | OBS Studio, AnyDesk, TeamLogger, Zoom, Microsoft Teams, WinRAR, Microsoft Office, RustDesk | No automatic timezone change; the existing Sync Time PH action remains available. |
| CNG Setup | Front desktop from [front.com](https://front.com/), Microsoft Windows App | Selecting CNG applies and verifies Sydney's `AUS Eastern Standard Time`, including daylight saving. |

Choose **Install Normal Apps** to prepare and run the general installers. Files come from the [installers-v1 release](https://github.com/eazyboytt/Python-System-Utility-Toolkit/releases/tag/installers-v1); `installers.json` copies its catalog and pins each asset's SHA256. Verified files are cached under `%LOCALAPPDATA%\Python-System-Utility-Toolkit\installers\installers-v1` and reused. Software installation no longer requires a flash drive. The Block Sites action still needs a drive containing your `hosts` file.

Normal Setup uses Microsoft's [current Teams bootstrapper](https://learn.microsoft.com/en-us/microsoftteams/teams-client-bulk-install) for supported Teams installation, rather than executing the release's older Squirrel installer. Microsoft Office uses its supplied interactive bootstrapper; complete its setup window when prompted. Office activation and app sign-in remain separate from installation.

CNG offers **Install CNG Apps** for both applications, plus individual **Front** and **Windows App** buttons. Front uses its [official machine-wide MSI](https://help.front.com/en/articles/2297) with signature verification. Microsoft Windows App uses the official Microsoft package in WinGet, which resolves its dependencies. Front installs for all users; Windows App installs for the Windows user running the toolkit. Run provisioning in the intended Windows user account, particularly when elevation could use another administrator's credentials.

CNG installation verifies Sydney's timezone before installing either app. A timezone failure stops that installation attempt. Selecting a category does not start app installations.

## Window and progress log

The window starts maximized and is resizable. Press **F11** or use **Full Screen** to toggle borderless fullscreen; **Esc** exits borderless fullscreen.

The output log shows timestamps, download percentages, checksum/signature verification, the current installer, command output, failures, and restart requirements. Success messages are green and errors are red. The status line shows the current step and elapsed time. Installer and policy tasks run in a background worker while the log remains responsive; another action is blocked until the running job finishes.

Installers run sequentially, and their exit codes are checked. MSI restart codes are reported without requesting an automatic restart. Failed applications are listed at the end of the setup. A successful installer exit indicates installer completion, not account sign-in or license activation.

## Time checks, fallbacks, and retrying

Clock accuracy and timezone are checked separately. The application checks time on startup and before installing apps. It starts Windows Time, enables it if disabled, and tries synchronization up to three times without replacing existing domain time settings. If NTP is blocked, it can verify UTC time using HTTPS server timestamps. A clock difference greater than five minutes stops installation with instructions to correct the Windows date/time. A failed clock check leaves the GUI open.

Use **Check / Sync Time** to check again. After a task fails, **Retry Last Task** becomes available. Fix the cause shown in the log and click it. The retry repeats the selected setup; previously verified release downloads are reused.

Downloads retry transient failures up to three times with short delays. HTTPS certificate failures identify incorrect date/time as a possible cause; verification is never disabled. Git/Python prerequisite installation and repository downloads also retry up to three times. A busy Windows Installer is retried up to three times. Other installer errors are reported for IT to resolve before an explicit retry.

If the initial curl command fails with a certificate error before the bootstrap is downloaded, correct **Settings > Time & language > Date & time**, click **Sync now**, and paste the command again. For network failures, check internet access, proxy settings, and access to GitHub/Microsoft/Front download servers. A failed prerequisite leaves its error visible in CMD.

## Short URL launcher

The separate [pc-setup-launcher repository](https://github.com/iantolentino/pc-setup-launcher) contains a static Vercel page and `/setup.bat` endpoint. After you deploy it, open the page and click **Copy CMD command**. The page fills in its actual deployed domain automatically.

For a domain named `YOUR-PROJECT.vercel.app`, the short command is:

```cmd
curl.exe --fail --location --retry 2 -o "%TEMP%\setup.bat" https://YOUR-PROJECT.vercel.app/setup.bat && call "%TEMP%\setup.bat"
```

The launcher uses this repository's `main` branch for the bootstrap, toolkit checkout, and WinGet helper.

## Verification and rebuilding

```cmd
python -m unittest discover -s tests -v
python -m py_compile master_gui.py setup_service.py installer_store.py clock_service.py
```

Tests cover real Tkinter category switching, fullscreen controls, threaded log handling, failed actions, checksum verification, caching, malformed filenames, installer commands, restart codes, timezone verification, and partial installation failures. Tests mock installation and timezone changes to avoid provisioning the development PC.

To rebuild the optional executable in a Python environment with Tkinter:

```cmd
python -m pip install pyinstaller
python -m PyInstaller --clean master_gui.spec
```

The build specification includes `installers.json`. Test the new-PC bootstrap and actual software installations on a dedicated Windows workstation before broad rollout; they have not been executed end to end on a fresh PC during development.
