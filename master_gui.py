import os
import hashlib
import subprocess
import webbrowser
import winreg
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import shutil
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from setup_service import install_normal, install_cng, set_sydney_timezone, download_signed
from clock_service import check_system_time
import cleanup_service
import state_service

VERSION = "1.2.0"
HEARTBEAT_SECONDS = 20
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
AMD_DOWNLOAD_URL = "https://drivers.amd.com/drivers/installer/26.10/whql/amd-software-adrenalin-edition-26.8.1-minimalsetup-260818_web.exe"
AMD_SUPPORT_URL = "https://www.amd.com/en/support/download/drivers.html"

class MasterScriptApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Master Script v{VERSION}")
        self.root.geometry("1280x900")
        self.root.minsize(980, 720)
        self.root.resizable(True, True)
        self.root.state("zoomed")
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", lambda event: self.root.attributes("-fullscreen", False))
        self.root.configure(bg="#f3f6fb")

        self.flashdrive = None
        self.category = "Normal Setup"
        self.events = queue.Queue()
        self.busy = False
        self.job_failed = False
        self.job_started = 0
        self.job_name = "Ready"
        self.current_step = "Ready"
        self.last_job = None
        self.track_log_errors = False
        self.last_output = time.monotonic()
        self.job_sequence = 0
        self.colors = {
            "bg": "#f3f6fb",
            "surface": "#ffffff",
            "border": "#d9e2ef",
            "text": "#14213d",
            "muted": "#617089",
            "primary": "#2563eb",
            "success": "#16803c",
            "danger": "#c2410c",
            "console": "#0f172a",
        }
        self.configure_styles()
        self.build_layout(root)
        self.root.after(100, self.process_events)
        self.log_message("Ready. Choose Normal Setup or CNG Setup. F11: full screen; Esc: exit full screen.")
        self.root.after(250, lambda: self.start_job("Clock check", check_system_time))

    def configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.colors["bg"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background=self.colors["bg"], foreground=self.colors["muted"], font=("Segoe UI", 10))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 10))
        style.configure("Ghost.TButton", font=("Segoe UI", 10), padding=(12, 8))

    def build_layout(self, root):
        shell = ttk.Frame(root, padding=18)
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="Master Script", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text=f"Pre Setup Tool v{VERSION} | Provisioning utilities for Windows workstations",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)

        main = ttk.Frame(body)
        main.pack(fill="both", expand=True)

        categories = ttk.Frame(main)
        categories.pack(fill="x", pady=(0, 8))
        ttk.Button(categories, text="Category 1: Normal Setup", style="Primary.TButton",
            command=lambda: self.select_category("Normal Setup")).pack(side="left", padx=(0, 8))
        ttk.Button(categories, text="Category 2: CNG Setup", style="Primary.TButton",
                   command=lambda: self.select_category("CNG Setup")).pack(side="left")
        self.category_label = ttk.Label(main, text="Normal Setup", font=("Segoe UI", 14, "bold"))
        self.category_label.pack(anchor="w", pady=(0, 4))
        self.category_note = ttk.Label(main, text="Install the general apps from the installers-v1 release.", style="Subtitle.TLabel")
        self.category_note.pack(anchor="w", pady=(0, 8))

        action_area = ttk.Frame(main)
        action_area.pack(fill="x")
        self.action_canvas = tk.Canvas(action_area, bg=self.colors["bg"], height=350,
                                       highlightthickness=0)
        action_scroll = ttk.Scrollbar(action_area, orient="vertical", command=self.action_canvas.yview)
        action_scroll.pack(side="right", fill="y")
        self.action_canvas.pack(side="left", fill="x", expand=True)
        self.action_canvas.configure(yscrollcommand=action_scroll.set)
        action_grid = ttk.Frame(self.action_canvas)
        action_window = self.action_canvas.create_window((0, 0), window=action_grid, anchor="nw")
        action_grid.bind("<Configure>", lambda event: self.action_canvas.configure(
            scrollregion=self.action_canvas.bbox("all")))
        self.action_canvas.bind("<Configure>", lambda event: self.action_canvas.itemconfigure(
            action_window, width=event.width))
        self.root.bind("<MouseWheel>", self.scroll_actions, add="+")
        self.root.bind("<Configure>", self.resize_action_area, add="+")
        self.action_grid = action_grid
        self.common_actions = [
            ("\ue895", "Check / Sync Time", "Check and sync the clock while keeping the current timezone.", self.check_sync_time, "#0284c7"),
            ("\ue777", "Windows Update", "Open Windows Settings directly to Windows Update.", self.open_windows_update, "#2563eb"),
            ("\ue896", "Download AMD Drivers", "Download the AMD installer; open AMD support if it fails.", self.download_amd_drivers, "#c2410c"),
            ("\ue721", "Scan Current State", "Report installed applications and already-applied configurations.", self.scan_state, "#0f766e"),
        ]

        actions = [
            ("\ue8a5", "Block Sites", "Detect a flash drive and replace the hosts file from it.", self.block_sites, "#2563eb"),
            ("\ue7ba", "Disable Hotspot", "Apply Windows policy to hide mobile hotspot sharing.", self.disable_hotspot, "#0f766e"),
            ("\ue88e", "Disable USB Storage", "Turn off USB mass storage access through USBSTOR.", self.disable_usb, "#7c3aed"),
            ("\ue7e8", "High Performance", "Set AC power profile and prevent idle sleep.", self.set_power_plan, "#d97706"),
            ("\ue895", "Sync Time PH", "Set the Windows timezone used by the provisioning flow.", self.sync_time, "#0284c7"),
            ("\ue896", "Install Normal Apps", "Download, verify and install the general app packages.", self.install_software, "#16a34a"),
            ("\ue8b0", "Disable Extensions", "Block browser extensions for installed supported browsers.", self.disable_all_browser_extensions, "#be123c"),
            ("\ue715", "Outlook 100GB", "Increase OST/PST size limits for Outlook profiles.", self.increase_outlook_limit, "#4f46e5"),
            ("\ue77b", "Clear Teams Profile", "Remove Teams and Microsoft identity login cache.", self.clear_teams_profile, "#0891b2"),
        ]

        self.normal_actions = actions
        self.render_actions(actions)

        for column in range(3):
            action_grid.columnconfigure(column, weight=1, uniform="actions")

        log_frame = tk.Frame(main, bg=self.colors["surface"], highlightbackground=self.colors["border"], highlightthickness=1)
        log_frame.pack(fill="both", expand=True, pady=(16, 0))

        log_header = tk.Frame(log_frame, bg=self.colors["surface"])
        log_header.pack(fill="x", padx=14, pady=(12, 8))
        tk.Label(log_header, text="Output Log", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(log_header, text="Clear", style="Ghost.TButton", command=self.clear_log).pack(side="right")
        ttk.Button(log_header, text="Full Screen (F11)", style="Ghost.TButton", command=self.toggle_fullscreen).pack(side="right", padx=8)
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill="x", padx=14, pady=(0, 8))
        self.retry_button = ttk.Button(log_controls, text="Retry Last Task", style="Ghost.TButton",
                                       command=self.retry_last_task, state="disabled")
        self.retry_button.pack(side="left")
        self.clean_button = ttk.Button(log_controls, text="Clean Up and Quit", style="Ghost.TButton",
                                       command=self.clean_up_and_quit)
        self.clean_button.pack(side="right")
        self.quit_button = ttk.Button(log_controls, text="Quit", style="Ghost.TButton",
                                      command=self.quit_app)
        self.quit_button.pack(side="right", padx=8)
        self.status = tk.StringVar(value="Ready")
        self.status_label = tk.Label(log_frame, textvariable=self.status, bg=self.colors["surface"],
                                    fg=self.colors["primary"], font=("Segoe UI", 10, "bold"), anchor="w")
        self.status_label.pack(fill="x", padx=14, pady=(0, 8))
        self.progress = ttk.Progressbar(log_frame, mode="indeterminate")
        self.progress.pack(fill="x", padx=14, pady=(0, 8))

        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            state="disabled",
            wrap="word",
            bg=self.colors["console"],
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief="flat",
            bd=0,
            font=("Consolas", 11)
        )
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.log.tag_configure("error", foreground="#fca5a5")
        self.log.tag_configure("success", foreground="#86efac")
        self.log.tag_configure("info", foreground="#dbeafe")

    def toggle_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def render_actions(self, actions):
        for child in self.action_grid.winfo_children():
            child.destroy()
        for index, action in enumerate(self.common_actions + actions):
            self._make_action_tile(self.action_grid, *action).grid(row=index // 3, column=index % 3,
                                                                  sticky="nsew", padx=6, pady=6)
        self.action_canvas.yview_moveto(0)

    def scroll_actions(self, event):
        widget = event.widget
        while widget is not None:
            if widget == self.action_canvas:
                self.action_canvas.yview_scroll(-int(event.delta / 120), "units")
                return "break"
            widget = getattr(widget, "master", None)

    def resize_action_area(self, event):
        if event.widget == self.root:
            self.action_canvas.configure(height=max(180, min(420, event.height - 500)))

    def check_sync_time(self):
        self.start_job("Clock check", check_system_time)

    def scan_state(self):
        self.start_job("System state scan", state_service.log_system_state)

    def open_windows_update(self):
        os.startfile("ms-settings:windowsupdate")
        self.log_message("Windows Update settings opened. Check for updates in that window.")

    def download_amd_drivers(self):
        def download(log):
            destination = Path.home() / "Downloads" / AMD_DOWNLOAD_URL.rsplit("/", 1)[-1]
            try:
                log("Downloading the AMD driver installer...")
                download_signed(AMD_DOWNLOAD_URL, destination, log)
            except Exception:
                log("Opening AMD support to choose a driver or download its auto-detect tool.")
                self.events.put(("amd_support", None))
                raise
            log(f"SUCCESS: AMD installer downloaded and signature verified: {destination}")
            log("Open the downloaded installer when ready to update this PC's AMD drivers.")
        self.start_job("AMD driver download", download)

    def select_category(self, category):
        if self.busy:
            self.log_message("A task is running. Wait for it to finish before changing setup category.")
            return
        self.category = category
        self.category_label.config(text=category)
        self.log_message(f"Selected {category}.")
        if category == "Normal Setup":
            self.category_note.config(text="Install the general apps from the installers-v1 release.")
            self.render_actions(self.normal_actions)
        else:
            self.category_note.config(text="Sydney timezone is applied on selection. Install Front and Microsoft Windows App below.")
            self.render_actions([
                ("\ue896", "Install CNG Apps", "Install both Front and Microsoft Windows App.", lambda: self.start_job("CNG Setup", install_cng), "#16a34a"),
                ("\ue715", "Front", "Install Front desktop for all Windows users.", lambda: self.start_job("Front", lambda log: install_cng(log, ("Front",))), "#2563eb"),
                ("\ue7f4", "Windows App", "Install Microsoft's Windows App for this user.", lambda: self.start_job("Windows App", lambda log: install_cng(log, ("Windows App",))), "#7c3aed"),
            ])
            def prepare_timezone(log):
                check_system_time(log)
                set_sydney_timezone(log)
            self.start_job("Sydney timezone", prepare_timezone)

    def start_job(self, name, operation, track_log_errors=False):
        if self.busy:
            self.log_message("A task is already running. Wait for its result before starting another.")
            return
        self.busy = True
        self.last_job = (name, operation, track_log_errors)
        self.track_log_errors = track_log_errors
        self.retry_button.config(state="disabled")
        self.job_failed = False
        self.job_name = name
        self.current_step = name
        self.job_started = time.monotonic()
        self.status.set(f"Working: {name}")
        self.progress.start(12)
        self.log_message(f"START: {name}")

        def work():
            success = False
            try:
                operation(lambda message: self.events.put(("log", message)))
                success = True
            except Exception as exc:
                self.events.put(("log", f"ERROR: {name}: {exc}"))
            finally:
                self.events.put(("done", success))

        self.job_sequence += 1
        sequence = self.job_sequence
        threading.Thread(target=work, daemon=True).start()
        threading.Thread(target=self.watch_job, args=(name, sequence), daemon=True).start()

    def heartbeat_message(self, name):
        """Return a keep-alive line when the job has been quiet for too long."""
        if time.monotonic() - self.last_output < HEARTBEAT_SECONDS:
            return None
        elapsed = int(time.monotonic() - self.job_started)
        return (f"Still working on {name} ({elapsed}s elapsed). "
                "Some installers stay quiet while they run.")

    def watch_job(self, name, sequence):
        """Log a heartbeat during quiet phases so the window never looks hung.

        Long installers (Office especially) can run for minutes without writing
        anything, which is when Windows starts showing the window as not responding.
        The sequence stops a watchdog left over from a finished job from reporting
        the wrong task name.
        """
        while self.busy and sequence == self.job_sequence:
            time.sleep(5)
            if not self.busy or sequence != self.job_sequence:
                return
            message = self.heartbeat_message(name)
            if message:
                self.events.put(("log", message))

    def process_events(self):
        # Bound the work per tick so a burst of installer output can never block
        # the window long enough for Windows to mark it as not responding.
        processed = 0
        try:
            while processed < 200:
                kind, value = self.events.get_nowait()
                processed += 1
                if kind == "log":
                    if self.track_log_errors and ("ERROR" in value or "Failed" in value or "failed" in value or value.startswith("Error")):
                        self.job_failed = True
                    self.log_message(value)
                elif kind == "amd_support":
                    try:
                        if not webbrowser.open(AMD_SUPPORT_URL):
                            self.log_message(f"Open AMD support in your browser: {AMD_SUPPORT_URL}")
                    except Exception as exc:
                        self.log_message(f"ERROR: Could not open AMD support: {exc}. Visit {AMD_SUPPORT_URL}")
                elif kind == "done":
                    self.busy = False
                    self.progress.stop()
                    elapsed = int(time.monotonic() - self.job_started)
                    value = value and not self.job_failed
                    self.retry_button.config(state="disabled" if value else "normal")
                    result = "Completed" if value else "Failed - see log"
                    self.status.set(f"{self.job_name}: {result} ({elapsed}s)")
                    self.log_message(f"{'SUCCESS' if value else 'ERROR'}: {self.job_name} finished after {elapsed}s.")
        except queue.Empty:
            pass
        if self.busy:
            self.status.set(f"{self.current_step} | {int(time.monotonic() - self.job_started)}s elapsed")
        self.root.after(100, self.process_events)

    def retry_last_task(self):
        if not self.busy and self.last_job:
            name, operation, track_log_errors = self.last_job
            self.log_message(f"Retry requested: {name}")
            self.start_job(name, operation, track_log_errors)

    def _make_action_tile(self, parent, icon, title, description, command, accent):
        action = command
        command = lambda: self.invoke_action(title, action)
        tile = tk.Frame(parent, bg=self.colors["surface"], highlightbackground=self.colors["border"], highlightthickness=1, width=208, height=128, cursor="hand2")
        tile.grid_propagate(False)

        top = tk.Frame(tile, bg=self.colors["surface"])
        top.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(top, text=icon, bg=self.colors["surface"], fg=accent, font=("Segoe MDL2 Assets", 19)).pack(side="left")
        tk.Label(top, text=title, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 10, "bold")).pack(side="left", padx=(9, 0))

        description_label = tk.Label(tile, text=description, bg=self.colors["surface"], fg=self.colors["muted"], font=("Segoe UI", 9), wraplength=180, justify="left")
        description_label.pack(fill="x", anchor="w", padx=12, pady=(0, 8))
        tile.bind("<Configure>", lambda event: description_label.config(wraplength=max(150, event.width - 24)))
        tk.Button(
            tile,
            text="Run",
            command=command,
            bg=accent,
            fg="white",
            activebackground=accent,
            activeforeground="white",
            relief="flat",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        ).pack(anchor="w", padx=12, pady=(0, 12), ipadx=12, ipady=4)

        for widget in (tile, top):
            widget.bind("<Button-1>", lambda _event, action=command: action())

        return tile

    def invoke_action(self, title, action):
        if self.busy:
            self.log_message("A task is running. Wait for it to finish before starting another action.")
            return
        if title in ("Disable Hotspot", "Disable USB Storage", "High Performance", "Sync Time PH", "Disable Extensions", "Outlook 100GB"):
            self.start_job(title, lambda log: action(), track_log_errors=True)
            return
        self.log_message(f"START: {title}")
        self.status.set(f"Working: {title}")
        self.root.update_idletasks()
        try:
            action()
        except Exception as exc:
            self.log_message(f"ERROR: {title}: {exc}")
        finally:
            if not self.busy:
                self.status.set(f"{title}: finished - see log for the result")

    def clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def quit_app(self):
        self.root.quit()

    def clean_up_and_quit(self):
        if self.busy:
            self.log_message("A task is running. Wait for it to finish before cleaning up toolkit files.")
            return
        files = cleanup_service.toolkit_files()
        folders = cleanup_service.deferred_folders()
        targets = files + folders
        count, size = cleanup_service.describe(targets)
        if count == 0:
            self.log_message("No toolkit files were found to clean up.")
            self.root.after(600, self.quit_app)
            return
        listing = "\n".join(str(path) for path in targets[:10])
        if len(targets) > 10:
            listing += "\n..."
        if not messagebox.askyesno(
            "Clean Up Toolkit Files",
            "Remove the toolkit's own files?\n\n"
            f"{count} item(s), about {size / 1048576:.1f} MB:\n\n{listing}\n\n"
            "Installed applications, registry policies, the timezone, the power plan "
            "and the hosts file are kept. The window closes afterwards."
        ):
            self.log_message("Clean up cancelled. No toolkit files were removed.")
            return
        self.log_message("Cleaning up toolkit files...")
        removed, freed = cleanup_service.clean_toolkit_files(self.log_message)
        self.log_message(f"SUCCESS: Removed {removed} item(s) and freed {freed / 1048576:.1f} MB.")
        try:
            cleanup_service.schedule_folder_removal(folders, self.log_message)
        except OSError as exc:
            self.log_message(f"ERROR: Could not schedule folder removal: {exc}")
            self.log_message("Delete these folders manually: " + ", ".join(str(path) for path in folders))
        if not folders:
            self.log_message("Installed applications and configuration changes were kept.")
        self.root.after(900, self.quit_app)

    def log_message(self, msg):
        self.last_output = time.monotonic()
        if threading.current_thread() is not threading.main_thread():
            self.events.put(("log", msg))
            return
        self.log.config(state="normal")
        tag = "error" if "ERROR" in msg or "Failed" in msg else "success" if "SUCCESS" in msg or "successfully" in msg else "info"
        timestamp = datetime.now().strftime("%H:%M:%S")
        for line in str(msg).splitlines():
            self.log.insert("end", f"[{timestamp}] {line}\n", tag)
        self.log.see("end")
        if self.busy and str(msg).splitlines():
            self.current_step = str(msg).splitlines()[-1][:110]
        self.log.config(state="disabled")

    def detect_flash_drive(self):
        self.log_message("Detecting flash drive...")
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = f"{letter}:\\"
            if os.path.exists(os.path.join(drive_path, "hosts")):
                self.flashdrive = drive_path
                self.log_message(f"Flash drive found at {drive_path}")
                return True
        self.flashdrive = None
        self.log_message("Error: No flash drive with 'hosts' found.")
        messagebox.showerror("Error", "Could not find a flash drive with a 'hosts' file.")
        return False

    def require_flashdrive(self):
        if not self.flashdrive:
            return self.detect_flash_drive()
        return True

    def run_cmd(self, cmd):
        self.log_message(f"Running: {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout:
                self.log_message(result.stdout.strip())
            if result.stderr:
                self.log_message(result.stderr.strip())
            if result.returncode != 0:
                self.log_message(f"ERROR: Command failed with exit code {result.returncode}.")
                return False
            return True
        except Exception as e:
            self.log_message(f"ERROR: {e}")
            return False

    @staticmethod
    def _hosts_entries(path):
        """Return the usable (non-comment, non-empty) lines of a hosts file."""
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return [line.strip() for line in handle
                        if line.strip() and not line.lstrip().startswith("#")]
        except OSError:
            return []

    @staticmethod
    def _file_digest(path):
        try:
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            return None

    def block_sites(self):
        if not self.require_flashdrive():
            return
        src = os.path.join(self.flashdrive, "hosts")
        dest = HOSTS_PATH
        entries = self._hosts_entries(src)
        if not entries:
            message = (f"{src} has no blocked site entries, so the current hosts file "
                       "was left unchanged.")
            self.log_message(f"ERROR: {message}")
            messagebox.showerror("Block Sites", message)
            return
        self.log_message(f"Blocking sites from {src} ({len(entries)} entries)...")
        if os.path.exists(dest):
            backup = f"{dest}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            try:
                shutil.copy2(dest, backup)
            except OSError as exc:
                message = f"Could not back up the current hosts file: {exc}"
                self.log_message(f"ERROR: {message}")
                messagebox.showerror("Block Sites", f"{message}\n\nNothing was changed.")
                return
            self.log_message(f"Backed up the current hosts file to {backup}")
            # A read-only hosts file makes copy fail with "Access is denied".
            self.run_cmd(f'attrib -R "{dest}"')
        if not self.run_cmd(f'copy /Y "{src}" "{dest}"'):
            self.log_message("ERROR: Could not replace the hosts file. Sites were not blocked.")
            return
        if self._file_digest(src) != self._file_digest(dest):
            self.log_message("ERROR: The hosts file did not match after copying. Sites may not be blocked.")
            return
        # DNS lookups already resolved stay cached, so the block would not apply
        # to recently visited sites until the cache is flushed.
        self.run_cmd("ipconfig /flushdns")
        self.log_message(f"Sites blocked successfully ({len(entries)} entries) and the DNS cache was flushed.")

    def disable_hotspot(self):
        try:
            key_path = r"SOFTWARE\Policies\Microsoft\Windows\Network Connections"
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                winreg.SetValueEx(key, "NC_ShowSharedAccessUI", 0, winreg.REG_DWORD, 0)
            self.log_message("Internet Connection Sharing prohibition applied successfully. Restart Windows to apply the policy.")
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
                    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, info["path"] + r"\ExtensionInstallBlocklist") as key:
                        winreg.SetValueEx(key, "1", 0, winreg.REG_SZ, "*")
                    self.log_message(f"{name}: Extensions disabled successfully.")
                except Exception as e:
                    self.log_message(f"Failed to apply policy for {name}: {e}")

            # Handle Firefox
            if browser_exists(browsers["Firefox"]["exe"]):
                import json
                policy = json.dumps({"*": {"installation_mode": "blocked"}})
                with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Mozilla\Firefox") as key:
                    winreg.SetValueEx(key, "ExtensionSettings", 0, winreg.REG_MULTI_SZ, [policy])
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
        results = [self.run_cmd(command) for command in ("powercfg /setactive SCHEME_MIN", "powercfg /change monitor-timeout-ac 0", "powercfg /change standby-timeout-ac 0")]
        if all(results):
            self.log_message("Power plan set successfully.")

    def sync_time(self):
        self.log_message("Syncing timezone to PH...")
        if self.run_cmd('tzutil /s "Taipei Standard Time"'):
            self.log_message("Timezone synced.")

    def install_software(self):
        self.start_job("Normal Setup", install_normal)

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


if __name__ == "__main__":
    root = tk.Tk()
    app = MasterScriptApp(root)
    root.mainloop()
