import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import installer_store
import setup_service as setup


class InstallerTests(unittest.TestCase):
    def test_transient_download_retries_then_succeeds(self):
        with patch.object(installer_store, "_download_once", side_effect=[installer_store.InstallerStoreError("network"), None]) as download, patch.object(installer_store.time, "sleep"):
            installer_store._download("https://example.com/test.exe", Path("test.exe"), Mock())
        self.assertEqual(download.call_count, 2)

    def test_download_retries_are_bounded(self):
        with patch.object(installer_store, "_download_once", side_effect=installer_store.InstallerStoreError("network")) as download, patch.object(installer_store.time, "sleep"):
            with self.assertRaisesRegex(installer_store.InstallerStoreError, "3 attempts"):
                installer_store._download("https://example.com/test.exe", Path("test.exe"), Mock())
        self.assertEqual(download.call_count, 3)

    def catalog(self, content=b"installer"):
        return {"repository": "owner/repo", "release_tag": "test", "installers": [
            {"name": "Test", "asset": "test.exe", "sha256": hashlib.sha256(content).hexdigest()}]}

    def test_download_then_reuse_verified_cache_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            def download(url, destination, log):
                destination.write_bytes(b"installer")
            with patch.object(installer_store, "_download", side_effect=download) as mock:
                first = installer_store.prepare_installers(self.catalog(), directory)
                second = installer_store.prepare_installers(self.catalog(), directory)
            self.assertEqual(mock.call_count, 1)
            self.assertEqual(first, second)

    def test_tampered_download_is_removed_and_never_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(installer_store, "_download", side_effect=lambda url, destination, log: destination.write_bytes(b"bad")):
                with self.assertRaises(installer_store.InstallerStoreError):
                    installer_store.prepare_installers(self.catalog(), directory)
            self.assertFalse((Path(directory) / "test/test.exe").exists())

    def test_corrupt_cache_is_downloaded_again(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "test"
            cache.mkdir()
            (cache / "test.exe").write_bytes(b"corrupt")
            with patch.object(installer_store, "_download", side_effect=lambda url, destination, log: destination.write_bytes(b"installer")) as download:
                installer_store.prepare_installers(self.catalog(), directory)
            download.assert_called_once()

    def test_path_escape_is_rejected(self):
        catalog = self.catalog()
        catalog["installers"][0]["asset"] = "../test.exe"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(installer_store.InstallerStoreError):
                installer_store.prepare_installers(catalog, directory)

    def test_real_catalog_has_all_eight_pinned_release_assets(self):
        catalog = installer_store.load_catalog(setup.RESOURCE_DIR / "installers.json")
        self.assertEqual(catalog["repository"], "iantolentino/Python-System-Utility-Toolkit")
        self.assertEqual(catalog["release_tag"], "installers-v1")
        self.assertEqual(len(catalog["installers"]), 8)
        self.assertTrue(all(len(entry["sha256"]) == 64 for entry in catalog["installers"]))


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(setup, "check_system_time").start()
        self.addCleanup(patch.stopall)

    def test_timezone_sets_sydney_and_verifies_it(self):
        with patch.object(setup, "require_admin"), patch.object(setup, "run_process", return_value=Mock(stdout=setup.SYDNEY_TIMEZONE)) as run:
            setup.set_sydney_timezone(Mock())
        self.assertEqual(run.call_args_list[0].args[0], ["tzutil", "/s", "AUS Eastern Standard Time"])
        self.assertEqual(run.call_args_list[1].args[0], ["tzutil", "/g"])

    def test_timezone_mismatch_fails(self):
        with patch.object(setup, "require_admin"), patch.object(setup, "run_process", return_value=Mock(stdout="Taipei Standard Time")):
            with self.assertRaises(RuntimeError):
                setup.set_sydney_timezone(Mock())

    def test_timezone_failure_prevents_app_installation(self):
        with patch.object(setup, "set_sydney_timezone", side_effect=RuntimeError("Denied")), patch.object(setup, "install_front") as front:
            with self.assertRaises(RuntimeError):
                setup.install_cng(Mock())
        front.assert_not_called()

    def test_cng_continues_after_app_failure_and_reports_incomplete(self):
        with patch.object(setup, "set_sydney_timezone"), patch.object(setup, "install_front", side_effect=RuntimeError("bad")), patch.object(setup, "install_windows_app") as windows:
            with self.assertRaisesRegex(RuntimeError, "Front"):
                setup.install_cng(Mock())
        windows.assert_called_once()

    def test_single_cng_app_still_applies_timezone(self):
        with patch.object(setup, "set_sydney_timezone") as timezone, patch.object(setup, "install_front") as front, patch.object(setup, "install_windows_app") as windows:
            setup.install_cng(Mock(), ("Windows App",))
        timezone.assert_called_once()
        front.assert_not_called()
        windows.assert_called_once()

    def test_missing_winget_is_reported(self):
        with patch.object(setup.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "WinGet"):
                setup.install_windows_app(Mock())

    def test_installer_failure_cannot_report_success(self):
        log = Mock()
        with patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess(["installer"], 1, "", "failed")):
            with self.assertRaises(RuntimeError):
                setup.run_process(["installer"], log)

    def test_busy_windows_installer_retries_without_reporting_success_early(self):
        with patch.object(setup.subprocess, "run", side_effect=[subprocess.CompletedProcess(["msiexec"], 1618, "", ""), subprocess.CompletedProcess(["msiexec"], 0, "", "")]) as run, patch.object(setup.time, "sleep"):
            setup.run_process(["msiexec"], Mock())
        self.assertEqual(run.call_count, 2)

    def test_reboot_code_reports_restart_without_automatic_reboot(self):
        log = Mock()
        with patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess(["msiexec"], 3010, "", "")):
            setup.run_process(["msiexec"], log, success_codes=(0, 3010))
        self.assertIn("Restart required", log.call_args.args[0])

    def test_msi_path_with_spaces_is_one_argument_and_prevents_reboot(self):
        command = setup.installer_command({"name": "TeamLogger", "local_path": r"C:\Test Folder\teamlogger.msi", "silent_args": "/quiet /qn"})
        self.assertEqual(command, ["msiexec.exe", "/i", r"C:\Test Folder\teamlogger.msi", "/quiet", "/qn", "/norestart"])

    def test_invalid_front_signature_prevents_execution(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(setup, "CACHE_DIR", Path(directory)), patch.object(setup, "require_admin"), patch.object(setup, "_download"), patch.object(setup, "run_process", side_effect=RuntimeError("Invalid signature")) as run:
            with self.assertRaises(RuntimeError):
                setup.install_front(Mock())
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], "powershell.exe")

    def test_normal_setup_continues_and_reports_partial_failure(self):
        entries = [{"name": "Test One", "local_path": "one.exe"}, {"name": "Test Two", "local_path": "two.exe"}]
        with patch.object(setup, "require_admin"), patch.object(setup, "load_catalog", return_value={}), patch.object(setup, "prepare_installers", return_value=entries), patch.object(setup, "run_process", side_effect=[RuntimeError("installer failed"), Mock()]) as run:
            with self.assertRaisesRegex(RuntimeError, "Test One"):
                setup.install_normal(Mock())
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
