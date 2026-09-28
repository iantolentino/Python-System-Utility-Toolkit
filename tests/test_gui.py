import time
import unittest
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

    def test_normal_setup_layout_is_resizable_with_nine_actions(self):
        self.assertEqual(self.root.resizable(), (1, 1))
        self.assertEqual(len(self.app.action_grid.winfo_children()), 9)
        self.assertIn("Ready", self.app.log.get("1.0", "end"))

    def test_cng_selection_applies_timezone_and_shows_app_buttons(self):
        with patch.object(master_gui, "set_sydney_timezone") as timezone:
            self.app.select_category("CNG Setup")
            self.finish_job()
        timezone.assert_called_once()
        self.assertEqual(self.app.category, "CNG Setup")
        self.assertEqual(len(self.app.action_grid.winfo_children()), 3)
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

    def test_clear_log_and_fullscreen_toggle(self):
        self.app.log_message("SUCCESS: test")
        self.assertTrue(self.app.log.tag_ranges("success"))
        self.app.clear_log()
        self.assertEqual(self.app.log.get("1.0", "end").strip(), "")
        self.app.toggle_fullscreen()
        self.assertTrue(self.root.attributes("-fullscreen"))
        self.app.toggle_fullscreen()
        self.assertFalse(self.root.attributes("-fullscreen"))


if __name__ == "__main__":
    unittest.main()
