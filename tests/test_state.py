import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import state_service as state


class ApplicationDetectionTests(unittest.TestCase):
    def test_exact_display_name_match_is_preferred_over_substring(self):
        programs = {"Zoom Workplace Extended": "7.0", "Zoom Workplace": "6.0"}
        display, version = state.match_application("Zoom", programs)
        self.assertEqual((display, version), ("Zoom Workplace", "6.0"))

    def test_substring_match_finds_variant_display_names(self):
        programs = {"WinRAR 6.24 (64-bit)": "6.24"}
        display, version = state.match_application("WinRAR", programs)
        self.assertEqual((display, version), ("WinRAR 6.24 (64-bit)", "6.24"))

    def test_missing_application_is_reported_as_not_installed(self):
        report = state.application_report(("RustDesk",), programs={})
        self.assertEqual(report, [{"name": "RustDesk", "installed": False,
                                   "display": None, "version": None}])

    def test_report_marks_each_application_independently(self):
        programs = {"AnyDesk": "8.0.4", "WinRAR 6.24 (64-bit)": "6.24"}
        report = state.application_report(("AnyDesk", "WinRAR", "RustDesk"), programs)
        by_name = {entry["name"]: entry for entry in report}
        self.assertTrue(by_name["AnyDesk"]["installed"])
        self.assertTrue(by_name["WinRAR"]["installed"])
        self.assertFalse(by_name["RustDesk"]["installed"])

    def test_report_logs_installed_and_missing_entries(self):
        log = Mock()
        report = state.log_application_report(log, ("AnyDesk", "RustDesk"), {"AnyDesk": "8.0.4"})
        output = "\n".join(str(call.args[0]) for call in log.call_args_list)
        self.assertIn("[installed] AnyDesk 8.0.4", output)
        self.assertIn("[missing]   RustDesk", output)
        self.assertIn("1 of 2", output)
        self.assertEqual(len(report), 2)

    def test_registry_scan_survives_missing_keys(self):
        with patch.object(state.winreg, "OpenKey", side_effect=OSError("denied")):
            self.assertEqual(state.installed_programs(), {})

    def test_teams_meeting_addin_is_not_mistaken_for_teams(self):
        programs = {"Microsoft Teams Meeting Add-in for Microsoft Office": "1.26"}
        display, _ = state.match_application("Microsoft Teams", programs)
        self.assertIsNone(display)

    def test_teams_machine_wide_installer_is_accepted(self):
        programs = {"Teams Machine-Wide Installer": "1.8"}
        display, version = state.match_application("Microsoft Teams", programs)
        self.assertEqual((display, version), ("Teams Machine-Wide Installer", "1.8"))

    def test_excluded_frontpage_is_not_treated_as_front(self):
        display, _ = state.match_application("Front", {"Microsoft FrontPage": "2003"})
        self.assertIsNone(display)

    def test_msix_package_folder_counts_as_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "Packages" / "MSTeams_8wekyb3d8bbwe").mkdir(parents=True)
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=False):
                self.assertTrue(state.package_installed("Microsoft Teams"))
                self.assertFalse(state.package_installed("Windows App"))
                self.assertFalse(state.package_installed("RustDesk"))

    def test_msix_detection_marks_the_application_installed(self):
        with patch.object(state, "package_installed", side_effect=lambda name: name == "Microsoft Teams"):
            report = state.application_report(("Microsoft Teams",), programs={})
        self.assertTrue(report[0]["installed"])
        self.assertIn("MSIX package", report[0]["display"])


class ConfigurationReportTests(unittest.TestCase):
    def test_usb_storage_reports_disabled_state(self):
        key = MagicMock()
        with patch.object(state.winreg, "OpenKey", return_value=key), \
             patch.object(state, "_registry_value", return_value=4):
            self.assertEqual(state.usb_storage_state(), "Disabled (USBSTOR Start=4)")

    def test_hotspot_policy_reports_hidden_state(self):
        key = MagicMock()
        with patch.object(state.winreg, "OpenKey", return_value=key), \
             patch.object(state, "_registry_value", return_value=0):
            self.assertEqual(state.hotspot_state(), "Hidden (policy applied)")

    def test_missing_policy_is_reported_as_not_applied(self):
        with patch.object(state.winreg, "OpenKey", side_effect=OSError("absent")):
            self.assertEqual(state.hotspot_state(), "Not hidden (policy absent)")

    def test_hosts_state_counts_only_real_entries(self):
        with patch.object(state, "HOSTS_PATH") as hosts:
            hosts.read_text.return_value = "# comment\n\n127.0.0.1 ads.example\n0.0.0.0 tracker.example\n"
            self.assertEqual(state.hosts_state(), "2 blocked entries")

    def test_hosts_state_reports_none_when_unmodified(self):
        with patch.object(state, "HOSTS_PATH") as hosts:
            hosts.read_text.return_value = "# default hosts file\n"
            self.assertEqual(state.hosts_state(), "No blocked entries")

    def test_outlook_limit_is_converted_to_gigabytes(self):
        key = MagicMock()
        with patch.object(state.winreg, "OpenKey", return_value=key), \
             patch.object(state, "_registry_value", return_value=102400):
            self.assertIn("100 GB", state.outlook_limit_state())

    def test_configuration_report_covers_every_managed_setting(self):
        with patch.object(state, "timezone_state", return_value="t"), \
             patch.object(state, "power_plan_state", return_value="p"), \
             patch.object(state, "usb_storage_state", return_value="u"), \
             patch.object(state, "hotspot_state", return_value="h"), \
             patch.object(state, "hosts_state", return_value="b"), \
             patch.object(state, "browser_policy_state", return_value="e"), \
             patch.object(state, "outlook_limit_state", return_value="o"):
            report = dict(state.configuration_report())
        self.assertEqual(sorted(report), sorted([
            "Timezone", "Power plan", "USB storage", "Mobile hotspot sharing",
            "Blocked sites (hosts file)", "Browser extensions", "Outlook large file limit"]))

    def test_system_state_scan_logs_applications_and_configurations(self):
        log = Mock()
        with patch.object(state, "log_application_report"), \
             patch.object(state, "configuration_report", return_value=[("Timezone", "Taipei Standard Time")]):
            state.log_system_state(log)
        output = "\n".join(str(call.args[0]) for call in log.call_args_list)
        self.assertIn("Timezone: Taipei Standard Time", output)
        self.assertIn("SUCCESS: System state scan completed.", output)


if __name__ == "__main__":
    unittest.main()
