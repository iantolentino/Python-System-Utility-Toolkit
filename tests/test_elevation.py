"""Run each launcher's real CMD elevation branch using a fake PowerShell host."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows required")
class ElevationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="toolkit elevation test ")
        cls.directory = Path(cls.fixture.name)
        source = r'''
using System;
using System.IO;
public class FakePowerShell {
    public static int Main(string[] args) {
        string command = String.Join(" ", args);
        File.AppendAllText(Environment.GetEnvironmentVariable("TOOLKIT_TEST_LOG"), command + "\n");
        if (command.Contains("WindowsIdentity"))
            return Environment.GetEnvironmentVariable("TOOLKIT_TEST_ADMIN") == "yes" ? 0 : 1;
        if (command.Contains("Start-Process"))
            return Environment.GetEnvironmentVariable("TOOLKIT_TEST_APPROVE") == "yes" ? 0 : 1;
        return 2;
    }
}
'''
        compile_script = cls.directory / "compile.ps1"
        compile_script.write_text("$ErrorActionPreference='Stop'\nAdd-Type -OutputAssembly $env:TOOLKIT_TEST_STUB -OutputType ConsoleApplication -TypeDefinition @'\n" + source + "\n'@\n", encoding="utf-8")
        result = subprocess.run([shutil.which("powershell.exe"), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(compile_script)],
                                env={**os.environ, "TOOLKIT_TEST_STUB": str(cls.directory / "powershell.exe")},
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            cls.fixture.cleanup()
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def run_launcher(self, name, admin, approve):
        source = (ROOT / name).read_text(encoding="utf-8")
        # Everything through the actual elevation block; system setup is replaced
        # with a marker so these checks cannot change the workstation.
        boundary = 'if exist "%ProgramFiles%\\Git' if name == "bootstrap.bat" else "echo ============================================"
        header = source.split(boundary, 1)[0]
        script = self.directory / name
        script.write_bytes((header + "echo SETUP_BODY_REACHED\nexit /b 0\n").replace("\n", "\r\n").encode())
        log = self.directory / "calls.txt"
        if log.exists():
            log.unlink()
        # Match the README command, which uses CALL to preserve batch exit status.
        result = subprocess.run([os.environ["ComSpec"], "/d", "/c", "call", str(script)], cwd=self.directory,
                                env={**os.environ, "TOOLKIT_TEST_LOG": str(log),
                                     "TOOLKIT_TEST_ADMIN": "yes" if admin else "no",
                                     "TOOLKIT_TEST_APPROVE": "yes" if approve else "no",
                                     "PATH": str(self.directory) + os.pathsep + os.environ["PATH"]},
                                capture_output=True, text=True, timeout=10)
        return result, log.read_text().splitlines()

    def test_admin_cmd_continues_without_elevation(self):
        for name in ("bootstrap.bat", "install_and_run.bat"):
            with self.subTest(launcher=name):
                result, calls = self.run_launcher(name, admin=True, approve=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("SETUP_BODY_REACHED", result.stdout)
                self.assertEqual(len(calls), 1)

    def test_normal_cmd_requests_runas_and_waits_for_child(self):
        for name in ("bootstrap.bat", "install_and_run.bat"):
            with self.subTest(launcher=name):
                result, calls = self.run_launcher(name, admin=False, approve=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("SETUP_BODY_REACHED", result.stdout)
                self.assertEqual(len(calls), 2)
                self.assertIn("-Verb RunAs -Wait -PassThru", calls[1])

    def test_declined_elevation_stops_with_failure(self):
        for name in ("bootstrap.bat", "install_and_run.bat"):
            with self.subTest(launcher=name):
                result, calls = self.run_launcher(name, admin=False, approve=False)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("SETUP_BODY_REACHED", result.stdout)
                self.assertEqual(len(calls), 2)
