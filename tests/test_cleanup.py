import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cleanup_service


class CleanupTargetTests(unittest.TestCase):
    def test_targets_stay_within_cache_and_temp(self):
        local = r"C:\Users\Test\AppData\Local"
        with patch.dict(os.environ, {"LOCALAPPDATA": local}, clear=False), \
             patch.object(cleanup_service.tempfile, "gettempdir",
                          return_value=local + r"\Temp"):
            for path in cleanup_service.toolkit_files():
                self.assertTrue(str(path).startswith(local), path)

    def test_cleanup_removes_toolkit_files_and_keeps_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temp = root / "temp"
            temp.mkdir()
            (temp / "toolkit-prerequisites.ps1").write_text("helper")
            (temp / "bootstrap.bat").write_text("bootstrap")
            staging = temp / "toolkit-prerequisite-abcd"
            staging.mkdir()
            (staging / "installer.exe").write_bytes(b"12345")
            winget = temp / "toolkit-winget-ef01"
            winget.mkdir()
            unrelated = temp / "unrelated.txt"
            unrelated.write_text("keep me")

            local = root / "localappdata"
            cache = local / cleanup_service.CACHE_FOLDER
            (cache / "installers-v1").mkdir(parents=True)
            (cache / "installers-v1" / "obs.exe").write_bytes(b"installer")

            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}, clear=False), \
                 patch.object(cleanup_service.tempfile, "gettempdir", return_value=str(temp)):
                removed, freed = cleanup_service.clean_toolkit_files()

            self.assertFalse((temp / "toolkit-prerequisites.ps1").exists())
            self.assertFalse((temp / "bootstrap.bat").exists())
            self.assertFalse(staging.exists())
            self.assertFalse(winget.exists())
            self.assertFalse(cache.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(removed, 5)
            self.assertGreaterEqual(freed, 14)

    def test_cleanup_script_files_are_never_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / (cleanup_service.CLEANUP_SCRIPT_PREFIX + "abc.ps1")).write_text("script")
            with patch.object(cleanup_service.tempfile, "gettempdir", return_value=str(temp)):
                self.assertEqual(cleanup_service.temporary_files(), [])

    def test_missing_cache_directory_is_not_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": str(Path(directory) / "absent")}, clear=False), \
                 patch.object(cleanup_service.tempfile, "gettempdir", return_value=directory):
                self.assertEqual(cleanup_service.toolkit_files(), [])


class RepositoryScopeTests(unittest.TestCase):
    def test_repository_folders_only_match_user_profile_checkouts(self):
        with tempfile.TemporaryDirectory() as profile:
            base = Path(profile)
            (base / "Python-System-Utility-Toolkit").mkdir()
            (base / "Python-System-Utility-Toolkit-iantolentino").mkdir()
            (base / "Python-System-Utility-Toolkit-iantolentino-2").mkdir()
            (base / "SomeOtherFolder").mkdir()
            with patch.dict(os.environ, {"USERPROFILE": str(base)}, clear=False):
                names = sorted(path.name for path in cleanup_service.repository_folders())
        self.assertEqual(names, ["Python-System-Utility-Toolkit",
                                 "Python-System-Utility-Toolkit-iantolentino",
                                 "Python-System-Utility-Toolkit-iantolentino-2"])

    def test_running_development_checkout_is_never_deferred(self):
        with tempfile.TemporaryDirectory() as profile:
            development = Path(tempfile.gettempdir()) / "dev" / "Python-System-Utility-Toolkit"
            with patch.dict(os.environ, {"USERPROFILE": str(profile)}, clear=False), \
                 patch.object(cleanup_service, "running_directory", return_value=development):
                self.assertEqual(cleanup_service.deferred_folders(), [])

    def test_running_bootstrap_checkout_is_deferred(self):
        with tempfile.TemporaryDirectory() as profile:
            base = Path(profile).resolve()
            checkout = base / "Python-System-Utility-Toolkit"
            checkout.mkdir()
            with patch.dict(os.environ, {"USERPROFILE": str(profile)}, clear=False), \
                 patch.object(cleanup_service, "running_directory", return_value=checkout):
                self.assertIn(checkout, cleanup_service.deferred_folders())


class ScheduledRemovalTests(unittest.TestCase):
    def test_schedule_folder_removal_waits_for_pid_and_targets_folders(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as profile:
            folder = Path(profile) / "Python-System-Utility-Toolkit"
            folder.mkdir()
            with patch.object(cleanup_service.tempfile, "gettempdir", return_value=temp), \
                 patch.object(cleanup_service.subprocess, "Popen") as popen:
                script = cleanup_service.schedule_folder_removal([folder], pid=4321)
            content = script.read_text(encoding="utf-8")
            self.assertTrue(script.name.startswith(cleanup_service.CLEANUP_SCRIPT_PREFIX))
            self.assertIn("Wait-Process -Id 4321", content)
            self.assertIn(str(folder), content)
            self.assertIn("Remove-Item -LiteralPath $path -Recurse -Force", content)
            self.assertEqual(popen.call_args.args[0][0], "powershell.exe")
            self.assertIn("-WindowStyle", popen.call_args.args[0])

    def test_schedule_folder_removal_returns_none_without_targets(self):
        with patch.object(cleanup_service.subprocess, "Popen") as popen:
            self.assertIsNone(cleanup_service.schedule_folder_removal([Path("C:/does/not/exist")]))
        popen.assert_not_called()

    def test_single_quotes_in_paths_are_escaped(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "quote'd"
            folder.mkdir()
            with patch.object(cleanup_service.tempfile, "gettempdir", return_value=temp), \
                 patch.object(cleanup_service.subprocess, "Popen"):
                script = cleanup_service.schedule_folder_removal([folder], pid=1)
            self.assertIn("''", script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
