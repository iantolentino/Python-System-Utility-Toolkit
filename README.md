# Python-System-Utility-Toolkit
A Python-based application that provides system administration tools such as website blocking via the hosts file, silent software installation, and automation scripts for system configuration. The project is designed to simplify common system configuration and management tasks through a single, easy-to-use interface.

## Quick Start (new workstation)

Open an **elevated** (Run as administrator) Command Prompt on the target PC and paste one line:

```cmd
curl -o "%TEMP%\bootstrap.bat" https://raw.githubusercontent.com/James-push/Python-System-Utility-Toolkit/main/bootstrap.bat && call "%TEMP%\bootstrap.bat"
```

This will:
1. Install Git automatically via `winget` if it isn't already present
2. Clone (or update) this repo to `%USERPROFILE%\Python-System-Utility-Toolkit`
3. Install Python automatically via `winget` if it isn't already present
4. Launch `master_gui.py`

No pre-existing dev tools required on the target PC — Windows 10 1809+/Windows 11 ship `curl` and
`winget` by default.

If you already have the repo cloned locally, just run `install_and_run.bat` from inside it.
