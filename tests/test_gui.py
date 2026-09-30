import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    import tkinter as tk
    import master_gui
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Tkinter is unavailable")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(master_gui, "check_system_time").start()
        self.addCleanup(patch.stopall)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = master_gui.MasterScriptApp(self.root)
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def finish_job(self):
        deadline = time.monotonic() + 3
        while self.app.busy and time.monotonic() < deadline:
            self.app.process_events()
            time.sleep(0.01)
        self.assertFalse(self.app.busy)

    def test_normal_setup_layout_is_resizable_with_thirteen_actions(self):
        self.assertEqual(self.root.resizable(), (1, 1))
        self.assertEqual(len(self.app.action_grid.winfo_children()), 13)
        self.assertIn("Ready", self.app.log.get("1.0", "end"))

    def test_cng_selection_applies_timezone_and_shows_app_buttons(self):
        with patch.object(master_gui, "set_sydney_timezone") as timezone:
            self.app.select_category("CNG Setup")
            self.finish_job()
        timezone.assert_called_once()
        self.assertEqual(self.app.category, "CNG Setup")
        self.assertEqual(len(self.app.action_grid.winfo_children()), 7)
        self.assertIn("Completed", self.app.status.get())

    def test_background_failure_is_visible_and_marks_job_failed(self):
        def fail(log):
            log("Downloading Front...")
            raise RuntimeError("Network unavailable")
        self.app.start_job("Front", fail)
        self.finish_job()
        output = self.app.log.get("1.0", "end")
        self.assertIn("Network unavailable", output)
        self.assertIn("Failed", self.app.status.get())
        self.assertTrue(self.app.log.tag_ranges("error"))

    def test_handled_utility_failure_is_not_reported_as_success(self):
        self.app.start_job("Utility", lambda log: self.app.log_message("Failed to change registry: denied"), track_log_errors=True)
        self.finish_job()
        self.assertIn("Failed", self.app.status.get())

    def test_running_task_blocks_new_actions(self):
        self.app.busy = True
        action = Mock()
        self.app.invoke_action("Other task", action)
        action.assert_not_called()

    def test_retry_button_reruns_failed_operation_and_disables_on_success(self):
        operation = Mock(side_effect=[RuntimeError("network"), None])
        self.app.start_job("Download", operation)
        self.finish_job()
        self.assertEqual(str(self.app.retry_button.cget("state")), "normal")
        self.app.retry_last_task()
        self.finish_job()
        self.assertEqual(operation.call_count, 2)
        self.assertEqual(str(self.app.retry_button.cget("state")), "disabled")

    def test_clock_action_runs_existing_clock_check(self):
        self.app.check_sync_time()
        self.finish_job()
        self.clock.assert_called_once()
        self.assertIn("Completed", self.app.status.get())

    def test_scan_state_runs_the_state_report(self):
        with patch.object(master_gui.state_service, "log_system_state") as scan:
            self.app.scan_state()
            self.finish_job()
        scan.assert_called_once()
        self.assertIn("Completed", self.app.status.get())

    def test_heartbeat_only_fires_after_a_quiet_period(self):
        self.app.job_started = time.monotonic() - 45
        self.app.last_output = time.monotonic()
        self.assertIsNone(self.app.heartbeat_message("Install"))
        self.app.last_output = time.monotonic() - master_gui.HEARTBEAT_SECONDS - 1
        message = self.app.heartbeat_message("Install")
        self.assertIn("Still working on Install", message)
        self.assertIn("45s elapsed", message)

    def test_event_pump_is_bounded_per_tick(self):
        for index in range(500):
            self.app.events.put(("log", f"queued {index}"))
        self.app.process_events()
        self.assertGreater(self.app.events.qsize(), 0)
        self.assertIn("queued 0", self.app.log.get("1.0", "end"))

    def test_stale_watchdog_stops_when_a_newer_job_started(self):
        self.app.busy = True
        self.app.job_sequence = 5
        with patch.object(master_gui.time, "sleep"):
            self.app.watch_job("Finished job", 3)
        self.assertEqual(self.app.events.qsize(), 0)

    def test_current_watchdog_emits_exactly_one_heartbeat_per_quiet_window(self):
        self.app.busy = True
        self.app.job_sequence = 7
        self.app.job_started = time.monotonic() - 50
        self.app.last_output = time.monotonic() - 50
        calls = {"count": 0}

        def fake_sleep(_seconds):
            calls["count"] += 1
            if calls["count"] >= 2:
                self.app.busy = False

        with patch.object(master_gui.time, "sleep", side_effect=fake_sleep):
            self.app.watch_job("Install", 7)
        kind, value = self.app.events.get_nowait()
        self.assertEqual(kind, "log")
        self.assertIn("Still working on Install", value)
        self.assertEqual(self.app.events.qsize(), 0)

    def test_windows_update_opens_settings_uri(self):
        with patch.object(master_gui.os, "startfile") as start:
            self.app.open_windows_update()
        start.assert_called_once_with("ms-settings:windowsupdate")

    def test_amd_download_saves_supplied_installer_without_running_it(self):
        with patch.object(master_gui, "download_signed") as download, patch.object(master_gui.os, "startfile") as start, patch.object(master_gui.webbrowser, "open") as browser:
            self.app.download_amd_drivers()
            self.finish_job()
        self.assertEqual(download.call_args.args[0], master_gui.AMD_DOWNLOAD_URL)
        self.assertEqual(download.call_args.args[1].parent, master_gui.Path.home() / "Downloads")
        self.assertEqual(download.call_args.args[1].name, master_gui.AMD_DOWNLOAD_URL.rsplit("/", 1)[-1])
        start.assert_not_called()
        browser.assert_not_called()
        self.assertIn("Completed", self.app.status.get())

    def test_amd_download_failure_opens_support_and_enables_retry(self):
        with patch.object(master_gui, "download_signed", side_effect=RuntimeError("Download unavailable")), patch.object(master_gui.webbrowser, "open", return_value=True) as browser:
            self.app.download_amd_drivers()
            self.finish_job()
        browser.assert_called_once_with(master_gui.AMD_SUPPORT_URL)
        self.assertIn("Download unavailable", self.app.log.get("1.0", "end"))
        self.assertIn("Failed", self.app.status.get())
        self.assertEqual(str(self.app.retry_button.cget("state")), "normal")

    def test_amd_support_browser_failure_still_completes_failed_job(self):
        with patch.object(master_gui, "download_signed", side_effect=RuntimeError("Download unavailable")), patch.object(master_gui.webbrowser, "open", side_effect=OSError("No browser")):
            self.app.download_amd_drivers()
            self.finish_job()
        self.assertIn(master_gui.AMD_SUPPORT_URL, self.app.log.get("1.0", "end"))
        self.assertEqual(str(self.app.retry_button.cget("state")), "normal")

    def test_block_sites_detects_drive_before_copying(self):
        with patch.object(master_gui.os.path, "exists",
                          side_effect=lambda path: path == "E:\\hosts"), \
             patch.object(self.app, "_hosts_entries", return_value=["0.0.0.0 ads.example"]), \
             patch.object(self.app, "run_cmd", return_value=True) as run:
            self.app.block_sites()
        self.assertEqual(self.app.flashdrive, "E:\\")
        self.assertTrue(any('"E:\\hosts"' in call.args[0] for call in run.call_args_list))

    def test_block_sites_without_drive_reports_error_and_does_not_copy(self):
        with patch.object(master_gui.os.path, "exists", return_value=False), patch.object(master_gui.messagebox, "showerror") as error, patch.object(self.app, "run_cmd") as run:
            self.app.block_sites()
        error.assert_called_once()
        run.assert_not_called()
        self.assertIsNone(self.app.flashdrive)

    def test_block_sites_backs_up_clears_readonly_copies_and_flushes_dns(self):
        with patch.object(self.app, "require_flashdrive", return_value=True), \
             patch.object(self.app, "_hosts_entries", return_value=["0.0.0.0 ads.example"]), \
             patch.object(self.app, "_file_digest", return_value="same"), \
             patch.object(master_gui.os.path, "exists", return_value=True), \
             patch.object(master_gui.shutil, "copy2") as copy2, \
             patch.object(self.app, "run_cmd", return_value=True) as run:
            self.app.flashdrive = "E:\\"
            self.app.block_sites()
        copy2.assert_called_once()
        log = self.app.log.get("1.0", "end")
        self.assertIn("Backed up the current hosts file", log)
        self.assertIn("Sites blocked successfully", log)
        self.assertIn("DNS cache was flushed", log)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any(command.startswith("attrib -R") for command in commands))
        self.assertTrue(any(command.startswith("copy /Y") for command in commands))
        self.assertEqual(commands[-1], "ipconfig /flushdns")

    def test_block_sites_refuses_a_hosts_file_with_no_entries(self):
        with patch.object(self.app, "require_flashdrive", return_value=True), \
             patch.object(self.app, "_hosts_entries", return_value=[]), \
             patch.object(master_gui.messagebox, "showerror") as error, \
             patch.object(self.app, "run_cmd") as run:
            self.app.flashdrive = "E:\\"
            self.app.block_sites()
        error.assert_called_once()
        run.assert_not_called()
        self.assertIn("no blocked site entries", self.app.log.get("1.0", "end"))

    def test_block_sites_reports_failure_when_the_copy_fails(self):
        with patch.object(self.app, "require_flashdrive", return_value=True), \
             patch.object(self.app, "_hosts_entries", return_value=["0.0.0.0 ads.example"]), \
             patch.object(master_gui.os.path, "exists", return_value=True), \
             patch.object(master_gui.shutil, "copy2"), \
             patch.object(self.app, "run_cmd", side_effect=lambda command: not command.startswith("copy /Y")) as run:
            self.app.flashdrive = "E:\\"
            self.app.block_sites()
        log = self.app.log.get("1.0", "end")
        self.assertIn("Could not replace the hosts file", log)
        self.assertNotIn("Sites blocked successfully", log)
        self.assertNotIn("ipconfig /flushdns", [call.args[0] for call in run.call_args_list])

    def test_block_sites_reports_a_mismatch_and_skips_the_dns_flush(self):
        digests = iter(["aaa", "bbb"])
        with patch.object(self.app, "require_flashdrive", return_value=True), \
             patch.object(self.app, "_hosts_entries", return_value=["0.0.0.0 ads.example"]), \
             patch.object(self.app, "_file_digest", side_effect=lambda path: next(digests)), \
             patch.object(master_gui.os.path, "exists", return_value=True), \
             patch.object(master_gui.shutil, "copy2"), \
             patch.object(self.app, "run_cmd", return_value=True) as run:
            self.app.flashdrive = "E:\\"
            self.app.block_sites()
        self.assertIn("did not match after copying", self.app.log.get("1.0", "end"))
        self.assertNotIn("ipconfig /flushdns", [call.args[0] for call in run.call_args_list])

    def test_block_sites_aborts_when_the_backup_fails(self):
        with patch.object(self.app, "require_flashdrive", return_value=True), \
             patch.object(self.app, "_hosts_entries", return_value=["0.0.0.0 ads"]), \
             patch.object(master_gui.os.path, "exists", return_value=True), \
             patch.object(master_gui.shutil, "copy2", side_effect=OSError("denied")), \
             patch.object(master_gui.messagebox, "showerror") as error, \
             patch.object(self.app, "run_cmd") as run:
            self.app.flashdrive = "E:\\"
            self.app.block_sites()
        error.assert_called_once()
        run.assert_not_called()
        self.assertIn("Could not back up", self.app.log.get("1.0", "end"))

    def test_hosts_entries_ignores_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            hosts = Path(folder) / "hosts"
            hosts.write_text("# comment\n\n0.0.0.0 ads.example\n  127.0.0.1 tracker.example\n",
                             encoding="utf-8")
            self.assertEqual(len(self.app._hosts_entries(str(hosts))), 2)
            self.assertEqual(self.app._hosts_entries(str(Path(folder) / "missing")), [])

    def test_action_area_fits_its_content_instead_of_always_scrolling(self):
        self.app.action_grid.update_idletasks()
        required = self.app.action_grid.winfo_reqheight()
        self.assertGreater(required, 1)
        self.app.resize_action_area(Mock(widget=self.app.root,
                                         height=required + master_gui.ACTION_AREA_RESERVED))
        self.assertEqual(int(self.app.action_canvas.cget("height")), required)

    def test_action_area_clamps_to_the_room_available(self):
        self.app.action_grid.update_idletasks()
        self.app.resize_action_area(Mock(widget=self.app.root,
                                         height=master_gui.ACTION_AREA_RESERVED + 200))
        self.assertEqual(int(self.app.action_canvas.cget("height")), 200)
        self.app.resize_action_area(Mock(widget=self.app.root,
                                         height=master_gui.ACTION_AREA_RESERVED - 400))
        self.assertEqual(int(self.app.action_canvas.cget("height")), 180)

    def test_action_area_ignores_events_from_other_widgets(self):
        self.app.action_canvas.configure(height=333)
        self.app.resize_action_area(Mock(widget=self.app.log, height=900))
        self.assertEqual(int(self.app.action_canvas.cget("height")), 333)

    def test_clear_teams_profile_prompts_then_runs_in_the_background(self):
        with patch.object(master_gui.messagebox, "askyesno", return_value=True), \
             patch.object(self.app, "start_job") as start:
            self.app.clear_teams_profile()
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], "Clear Teams Profile")

    def test_clear_teams_profile_cancel_starts_no_job(self):
        with patch.object(master_gui.messagebox, "askyesno", return_value=False), \
             patch.object(self.app, "start_job") as start:
            self.app.clear_teams_profile()
        start.assert_not_called()
        self.assertIn("cancelled", self.app.log.get("1.0", "end"))

    def test_remove_teams_profile_data_clears_the_package_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "Packages" / "MSTeams_8wekyb3d8bbwe"
            (package / "nested").mkdir(parents=True)
            (package / "token.bin").write_text("x", encoding="utf-8")
            (package / "nested" / "deep.bin").write_text("y", encoding="utf-8")
            with patch.object(self.app, "run_cmd", return_value=True):
                self.app.remove_teams_profile_data(folder)
            self.assertEqual(list(package.iterdir()), [])
            log = self.app.log.get("1.0", "end")
            self.assertIn("Items deleted: 2", log)
            self.assertIn("Not found, skipping", log)

    def test_clear_log_and_fullscreen_toggle(self):
        self.app.log_message("SUCCESS: test")
        self.assertTrue(self.app.log.tag_ranges("success"))
        self.app.clear_log()
        self.assertEqual(self.app.log.get("1.0", "end").strip(), "")
        self.app.toggle_fullscreen()
        self.assertTrue(self.root.attributes("-fullscreen"))
        self.app.toggle_fullscreen()
        self.assertFalse(self.root.attributes("-fullscreen"))

    def test_log_controls_expose_quit_and_cleanup_buttons(self):
        self.assertEqual(self.app.quit_button.cget("text"), "Quit")
        self.assertEqual(self.app.clean_button.cget("text"), "Clean Up and Quit")

    def test_quit_app_stops_the_mainloop(self):
        with patch.object(self.root, "quit") as quit_:
            self.app.quit_app()
        quit_.assert_called_once()

    def test_clean_up_reports_when_nothing_to_remove(self):
        with patch.object(master_gui.cleanup_service, "toolkit_files", return_value=[]), \
             patch.object(master_gui.cleanup_service, "deferred_folders", return_value=[]), \
             patch.object(master_gui.messagebox, "askyesno") as ask, \
             patch.object(master_gui.cleanup_service, "clean_toolkit_files") as clean, \
             patch.object(self.app, "quit_app") as quit_app, \
             patch.object(self.root, "after") as after:
            self.app.clean_up_and_quit()
        ask.assert_not_called()
        clean.assert_not_called()
        self.assertIn("No toolkit files", self.app.log.get("1.0", "end"))
        after.assert_called_once_with(600, quit_app)

    def test_clean_up_cancelled_keeps_everything(self):
        target = Path("C:/fake/Python-System-Utility-Toolkit")
        with patch.object(master_gui.cleanup_service, "toolkit_files", return_value=[target]), \
             patch.object(master_gui.cleanup_service, "deferred_folders", return_value=[]), \
             patch.object(master_gui.cleanup_service, "describe", return_value=(1, 1024)), \
             patch.object(master_gui.messagebox, "askyesno", return_value=False), \
             patch.object(master_gui.cleanup_service, "clean_toolkit_files") as clean, \
             patch.object(master_gui.cleanup_service, "schedule_folder_removal") as schedule, \
             patch.object(self.app, "quit_app") as quit_app, \
             patch.object(self.root, "after") as after:
            self.app.clean_up_and_quit()
        clean.assert_not_called()
        schedule.assert_not_called()
        quit_app.assert_not_called()
        after.assert_not_called()
        self.assertIn("cancelled", self.app.log.get("1.0", "end"))

    def test_clean_up_removes_files_schedules_folder_then_quits(self):
        target = Path("C:/fake/Python-System-Utility-Toolkit")
        with patch.object(master_gui.cleanup_service, "toolkit_files", return_value=[target]), \
             patch.object(master_gui.cleanup_service, "deferred_folders", return_value=[target]), \
             patch.object(master_gui.cleanup_service, "describe", return_value=(1, 1048576)), \
             patch.object(master_gui.messagebox, "askyesno", return_value=True), \
             patch.object(master_gui.cleanup_service, "clean_toolkit_files", return_value=(1, 1048576)) as clean, \
             patch.object(master_gui.cleanup_service, "schedule_folder_removal") as schedule, \
             patch.object(self.app, "quit_app") as quit_app, \
             patch.object(self.root, "after") as after:
            self.app.clean_up_and_quit()
        clean.assert_called_once()
        schedule.assert_called_once_with([target], self.app.log_message)
        self.assertIn("SUCCESS", self.app.log.get("1.0", "end"))
        after.assert_called_once_with(900, quit_app)

    def test_clean_up_blocks_while_a_task_is_running(self):
        self.app.busy = True
        with patch.object(master_gui.cleanup_service, "toolkit_files") as files:
            self.app.clean_up_and_quit()
        self.app.busy = False
        files.assert_not_called()
        self.assertIn("Wait for it to finish", self.app.log.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
