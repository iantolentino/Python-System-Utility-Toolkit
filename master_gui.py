import os
import subprocess
import webbrowser
import winreg
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sys
import shutil

VERSION = "1.0.4"

class MasterScriptApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Master Script v{VERSION}")
        self.root.geometry("650x500")
        self.root.resizable(False, False)

        self.flashdrive = None

        # Title
        ttk.Label(root, text="⚙️ Master Script - Pre Setup Tool", font=("Segoe UI", 16, "bold")).pack(pady=10)

        # Flash Drive Detection
        detect_frame = ttk.LabelFrame(root, text="Flash Drive")
        detect_frame.pack(fill="x", padx=20, pady=5)
        ttk.Button(detect_frame, text="Detect Flash Drive", command=self.detect_flash_drive).pack(pady=5)
        self.drive_label = ttk.Label(detect_frame, text="No flash drive detected", foreground="red")
        self.drive_label.pack()

        # Actions
        action_frame = ttk.LabelFrame(root, text="Actions")
        action_frame.pack(fill="both", expand=True, padx=20, pady=5)

        actions = [
            ("Block Sites (Hosts)", self.block_sites),
            ("Disable Mobile Hotspot", self.disable_hotspot),
            ("Disable USB Storage", self.disable_usb),
            ("Set High Performance Power Plan", self.set_power_plan),
            ("Sync Time (PH)", self.sync_time),
            ("Install Software", self.install_software),
            ("Disable Browser Extensions (Installed Browsers Only)", self.disable_all_browser_extensions),
            ("Increase Outlook Limit (100GB)", self.increase_outlook_limit),
            ("Clear Teams Profile", self.clear_teams_profile),
        ]

        for name, func in actions:
            ttk.Button(action_frame, text=name, command=func).pack(fill="x", pady=3, padx=10)

        # Log output area
        ttk.Label(root, text="Output Log").pack()
        self.log = scrolledtext.ScrolledText(root, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", padx=10, pady=5)

        ttk.Button(root, text="Exit", command=self.root.quit).pack(pady=5)

    def log_message(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def detect_flash_drive(self):
        self.log_message("Detecting flash drive...")
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = f"{letter}:\\"
            if os.path.exists(os.path.join(drive_path, "hosts")):
                self.flashdrive = drive_path
                self.drive_label.config(text=f"Detected: {drive_path}", foreground="green")
                self.log_message(f"Flash drive found at {drive_path}")
                return
        self.flashdrive = None
        self.drive_label.config(text="No flash drive detected", foreground="red")
        self.log_message("Error: No flash drive with 'hosts' found.")
        messagebox.showerror("Error", "Could not find a flash drive with a 'hosts' file.")

    def require_flashdrive(self):
        if not self.flashdrive:
            messagebox.showwarning("Flash Drive Not Found", "Please detect the flash drive first.")
            return False
        return True

    def run_cmd(self, cmd):
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout:
                self.log_message(result.stdout.strip())
            if result.stderr:
                self.log_message(result.stderr.strip())
        except Exception as e:
            self.log_message(str(e))

    import subprocess

    def run_installer_as_admin(path, args=""):
        try:
            cmd = [
                "powershell",
                "-Command",
                f'Start-Process -FilePath "{path}" -ArgumentList \'{args}\' -Verb RunAs'
            ]
            subprocess.run(cmd, shell=True)
        except Exception as e:
            print(f"Failed to run {path}: {e}")

    def block_sites(self):
        if not self.require_flashdrive():
            return
        src = os.path.join(self.flashdrive, "hosts")
        dest = r"C:\Windows\System32\drivers\etc\hosts"
        self.log_message("Blocking sites...")
        self.run_cmd(f'copy /Y "{src}" "{dest}"')
        self.log_message("Sites blocked successfully.")

    def disable_hotspot(self):
        try:
            key_path = r"SOFTWARE\Policies\Microsoft\Windows\Network Connections"
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                winreg.SetValueEx(key, "NC_ShowSharedAccessUI", 0, winreg.REG_DWORD, 1)
            self.log_message("Mobile hotspot disabled successfully.")
        except Exception as e:
            self.log_message(f"Failed to disable hotspot: {e}")

    
    def disable_all_browser_extensions(self):
        try:
            self.log_message("Disabling browser extensions for installed browsers only...")

            browsers = {
                "Google Chrome": {
                    "path": r"SOFTWARE\Policies\Google\Chrome",
                    "exe": r"Google\Chrome\Application\chrome.exe"
                },
                "Microsoft Edge": {
                    "path": r"SOFTWARE\Policies\Microsoft\Edge",
                    "exe": r"Microsoft\Edge\Application\msedge.exe"
                },
                "Brave Browser": {
                    "path": r"SOFTWARE\Policies\BraveSoftware\Brave",
                    "exe": r"BraveSoftware\Brave-Browser\Application\brave.exe"
                },
                "Opera Browser": {
                    "path": r"SOFTWARE\Policies\Opera Software\Opera",
                    "exe": r"Opera\launcher.exe"
                },
                "Firefox": {
                    "exe": r"Mozilla Firefox\firefox.exe"
                }
            }

            def browser_exists(exe_relative_path):
                program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
                program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
                possible_paths = [
                    os.path.join(program_files, exe_relative_path),
                    os.path.join(program_files_x86, exe_relative_path)
                ]
                return any(os.path.exists(p) for p in possible_paths)

            # Apply GPO for Chromium-based browsers
            for name, info in browsers.items():
                if name == "Firefox":
                    continue  # handle Firefox separately
                if not browser_exists(info["exe"]):
                    self.log_message(f"{name} not installed — skipping.")
                    continue
                try:
                    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, info["path"]) as key:
                        winreg.SetValueEx(key, "ExtensionInstallBlocklist", 0, winreg.REG_MULTI_SZ, ["*"])
                    self.log_message(f"{name}: Extensions disabled successfully.")
                except Exception as e:
                    self.log_message(f"Failed to apply policy for {name}: {e}")

            # Handle Firefox
            if browser_exists(browsers["Firefox"]["exe"]):
                firefox_policy_path = r"C:\Program Files\Mozilla Firefox\distribution\policies.json"
                os.makedirs(os.path.dirname(firefox_policy_path), exist_ok=True)
                firefox_policy = {
                    "policies": {
                        "Extensions": {
                            "Install": False
                        }
                    }
                }
                import json
                with open(firefox_policy_path, "w") as f:
                    json.dump(firefox_policy, f, indent=4)
                self.log_message("Firefox: Extensions disabled successfully.")
            else:
                self.log_message("Firefox not installed — skipping.")

            self.log_message("Browser extension restrictions applied to all detected browsers.")
            self.log_message("Restart browsers to enforce policy changes.")

        except Exception as e:
            self.log_message(f"Error disabling browser extensions: {e}")




    def disable_usb(self):
        try:
            key_path = r"SYSTEM\CurrentControlSet\Services\USBSTOR"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Start", 0, winreg.REG_DWORD, 4)
            self.log_message("USB storage disabled successfully.")
        except Exception as e:
            self.log_message(f"Failed to disable USB storage: {e}")

    def set_power_plan(self):
        self.log_message("Setting High Performance power plan...")
        self.run_cmd("powercfg /setactive SCHEME_MIN")
        self.run_cmd("powercfg /change monitor-timeout-ac 0")
        self.run_cmd("powercfg /change standby-timeout-ac 0")
        self.log_message("Power plan set successfully.")

    def sync_time(self):
        self.log_message("Syncing timezone to PH...")
        self.run_cmd('tzutil /s "Taipei Standard Time"')
        self.log_message("Timezone synced.")

    def install_software(self):
        if not self.require_flashdrive():
            return

        import shutil
        import tempfile

        self.log_message("Installing software automatically...")

        installers = {
            "OBS Studio": (os.path.join(self.flashdrive, "installers", "obs.exe"), "/S"),
            "AnyDesk": (os.path.join(self.flashdrive, "installers", "anydesk.exe"), None),  # special handling
            "TeamLogger": (os.path.join(self.flashdrive, "installers", "teamlogger.msi"), "/quiet /qn"),
            "Zoom": (os.path.join(self.flashdrive, "installers", "zoom.exe"), "/quiet"),
            "Microsoft Teams": (os.path.join(self.flashdrive, "installers", "teams.exe"), "/s"),
            "WinRAR": (os.path.join(self.flashdrive, "installers", "winrar.exe"), "/S"),
            "Jabra Direct": (os.path.join(self.flashdrive, "installers", "jabra.exe"), "/quiet"),  
        }

        processes = []

        for name, (path, args) in installers.items():
            if not os.path.exists(path):
                self.log_message(f"{name} installer not found at: {path}")
                continue

            self.log_message(f"Launching {name} installation...")

            try:
                # 🔹 Special handling for AnyDesk
                if name == "AnyDesk":
                    install_dir = r"C:\Program Files (x86)\AnyDesk"
                    cmd = f'"{path}" --install "{install_dir}" --silent --create-shortcuts --start-with-win'
                    p = subprocess.Popen(cmd, shell=True)

                # 🔹 Fix for Zoom (EXE, needs copy to temp + proper elevation)
                elif name == "Zoom":
                    temp_zoom_path = os.path.join(tempfile.gettempdir(), "zoom_installer.exe")
                    shutil.copy2(path, temp_zoom_path)
                    cmd = [
                        "powershell",
                        "-Command",
                        f'Start-Process -FilePath "{temp_zoom_path}" -ArgumentList \'/quiet\' -Verb RunAs'
                    ]
                    p = subprocess.Popen(cmd, shell=True)

                # 🔹 Fix for TeamLogger (MSI, needs admin and msiexec)
                elif name == "TeamLogger":
                    temp_team_path = os.path.join(tempfile.gettempdir(), "teamlogger.msi")
                    shutil.copy2(path, temp_team_path)
                    cmd = [
                        "powershell",
                        "-Command",
                        f'Start-Process -FilePath "msiexec.exe" -ArgumentList \'/i "{temp_team_path}" /quiet /qn\' -Verb RunAs'
                    ]
                    p = subprocess.Popen(cmd, shell=True)
                
                elif name == "Jabra Direct":
                    temp_jabra_path = os.path.join(tempfile.gettempdir(), "jabradirect_installer.exe")
                    shutil.copy2(path, temp_jabra_path)
                    cmd = [
                        "powershell",
                        "-Command",
                        f'Start-Process -FilePath "{temp_jabra_path}" -ArgumentList \'/quiet\' -Verb RunAs'
                    ]
                    p = subprocess.Popen(cmd, shell=True)


                # 🔹 Normal EXE installers
                elif path.endswith(".exe"):
                    cmd = [
                        "powershell",
                        "-Command",
                        f'Start-Process -FilePath "{path}" -ArgumentList \'{args}\' -Verb RunAs'
                    ]
                    p = subprocess.Popen(cmd, shell=True)

                # 🔹 MSI installers
                elif path.endswith(".msi"):
                    cmd = [
                        "powershell",
                        "-Command",
                        f'Start-Process -FilePath "msiexec.exe" -ArgumentList \'/i "{path}" {args}\' -Verb RunAs'
                    ]
                    p = subprocess.Popen(cmd, shell=True)

                else:
                    self.log_message(f"Unknown installer type for {name}, skipping.")
                    continue

                processes.append((name, p))

            except Exception as e:
                self.log_message(f"Error launching {name}: {e}")

        self.log_message("All installers have been launched in the background. You can continue using this tool.")

        # Optional: Monitor background installs
        self.root.after(5000, lambda: self.check_installers_status(processes))



    def increase_outlook_limit(self):
        self.log_message("Increasing Outlook OST/PST limit to 100GB...")
        max_size = 102400
        warn_size = 102000
        versions = ["15.0", "16.0"]
        for version in versions:
            try:
                base_path = f"Software\\Microsoft\\Office\\{version}\\Outlook\\PST"
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base_path) as key:
                    winreg.SetValueEx(key, "MaxLargeFileSize", 0, winreg.REG_DWORD, max_size)
                    winreg.SetValueEx(key, "WarnLargeFileSize", 0, winreg.REG_DWORD, warn_size)
                self.log_message(f"Outlook {version}: Updated successfully.")
            except Exception as e:
                self.log_message(f"Failed Outlook {version}: {e}")
        self.log_message("Restart Outlook to apply changes.")

    def clear_teams_profile(self):
        if not messagebox.askyesno(
            "Clear Teams Profile",
            "This will close Microsoft Teams and delete stored Teams login data for the current Windows user. Continue?"
        ):
            self.log_message("Clear Teams Profile cancelled.")
            return

        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            self.log_message("Error: LOCALAPPDATA environment variable was not found.")
            messagebox.showerror("Error", "Could not locate the current user's Local AppData folder.")
            return

        self.log_message("Closing Microsoft Teams...")
        for process_name in ("ms-teams.exe", "Teams.exe", "msteams.exe"):
            self.run_cmd(f'taskkill /F /IM "{process_name}"')

        target_folders = [
            os.path.join(local_app_data, "Packages", "MSTeams_8wekyb3d8bbwe"),
            os.path.join(local_app_data, "Packages", "Microsoft.AAD.BrokerPlugin_cw5n1h2txyewy"),
            os.path.join(local_app_data, "Microsoft", "OneAuth"),
            os.path.join(local_app_data, "Microsoft", "TokenBroker"),
            os.path.join(local_app_data, "Microsoft", "IdentityCache"),
        ]

        self.log_message("Deleting stored Teams login data...")
        deleted_count = 0
        for folder in target_folders:
            if not os.path.isdir(folder):
                self.log_message(f"Not found, skipping: {folder}")
                continue

            for item_name in os.listdir(folder):
                item_path = os.path.join(folder, item_name)
                try:
                    if os.path.isdir(item_path) and not os.path.islink(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                    deleted_count += 1
                except Exception as e:
                    self.log_message(f"Failed to delete {item_path}: {e}")

            self.log_message(f"Cleared contents: {folder}")

        self.log_message(f"Clear Teams Profile completed. Items deleted: {deleted_count}")
        self.log_message("Open Teams again and sign in with the correct account.")

    def check_installers_status(self, processes):
        still_running = []
        for name, p in processes:
            ret = p.poll()
            if ret is None:
                still_running.append((name, p))
            else:
                if ret == 0:
                    self.log_message(f"{name} finished successfully.")
                else:
                    self.log_message(f"{name} exited with code {ret}.")

        if still_running:
            self.root.after(5000, lambda: self.check_installers_status(still_running))
        else:
            self.log_message("✅ All background installations completed.")



if __name__ == "__main__":
    root = tk.Tk()
    app = MasterScriptApp(root)
    root.mainloop()
