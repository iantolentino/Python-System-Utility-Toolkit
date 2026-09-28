"""Exercise bootstrap destination selection with real local Git repositories."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git.exe")


@unittest.skipUnless(os.name == "nt" and GIT, "Windows and Git required")
class BootstrapRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix="toolkit repo test ")
        self.addCleanup(self.fixture.cleanup)
        self.profile = Path(self.fixture.name)
        self.default = self.profile / "Python-System-Utility-Toolkit"

    def repo(self, path, url):
        subprocess.run([GIT, "init", str(path)], check=True, capture_output=True)
        subprocess.run([GIT, "-C", str(path), "remote", "add", "origin", url], check=True, capture_output=True)

    def select(self):
        source = (ROOT / "bootstrap.bat").read_text(encoding="utf-8")
        selection = source.split("\n:select_repo\n", 1)[1].split("\n:fetch_repo\n", 1)[0]
        script = self.profile / "select.bat"
        body = '@echo off\nsetlocal EnableExtensions DisableDelayedExpansion\nset "DEST=%USERPROFILE%\\Python-System-Utility-Toolkit"\ncall :select_repo\nif errorlevel 1 exit /b 1\necho RESULT=%DEST%\nexit /b 0\n:select_repo\n' + selection
        script.write_bytes(body.replace("\n", "\r\n").encode())
        result = subprocess.run([os.environ["ComSpec"], "/d", "/c", "call", str(script)],
                                env={**os.environ, "USERPROFILE": str(self.profile),
                                     "PATH": str(Path(GIT).parent) + os.pathsep + os.environ["PATH"]},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = next(line.removeprefix("RESULT=") for line in result.stdout.splitlines() if line.startswith("RESULT="))
        return Path(selected)

    def test_correct_https_checkout_with_git_lf_output_is_reused(self):
        self.repo(self.default, "https://github.com/iantolentino/Python-System-Utility-Toolkit.git")
        output = subprocess.check_output([GIT, "-C", str(self.default), "remote", "get-url", "origin"])
        self.assertTrue(output.endswith(b"\n"))
        self.assertEqual(self.select(), self.default)

    def test_valid_origin_variants_are_reused(self):
        self.repo(self.default, "https://github.com/iantolentino/Python-System-Utility-Toolkit")
        for url in ("https://github.com/iantolentino/Python-System-Utility-Toolkit/",
                    "git@github.com:iantolentino/Python-System-Utility-Toolkit.git",
                    "ssh://git@github.com/iantolentino/Python-System-Utility-Toolkit.git"):
            with self.subTest(url=url):
                subprocess.run([GIT, "-C", str(self.default), "remote", "set-url", "origin", url], check=True)
                self.assertEqual(self.select(), self.default)

    def test_foreign_repo_is_preserved_and_alternate_is_selected(self):
        url = "https://github.com/eazyboytt/Python-System-Utility-Toolkit.git"
        self.repo(self.default, url)
        self.assertEqual(self.select(), self.profile / "Python-System-Utility-Toolkit-iantolentino")
        self.assertEqual(subprocess.check_output([GIT, "-C", str(self.default), "remote", "get-url", "origin"], text=True).strip(), url)

    def test_non_repo_files_are_preserved(self):
        self.default.mkdir()
        marker = self.default / "keep.txt"
        marker.write_text("keep my files")
        self.assertEqual(self.select(), self.profile / "Python-System-Utility-Toolkit-iantolentino")
        self.assertEqual(marker.read_text(), "keep my files")

    def test_existing_correct_alternate_is_reused(self):
        self.default.mkdir()
        alternate = self.profile / "Python-System-Utility-Toolkit-iantolentino"
        self.repo(alternate, "https://github.com/iantolentino/Python-System-Utility-Toolkit.git")
        self.assertEqual(self.select(), alternate)

    def test_multiple_occupied_folders_use_numbered_alternative(self):
        self.default.mkdir()
        (self.profile / "Python-System-Utility-Toolkit-iantolentino").mkdir()
        self.assertEqual(self.select(), self.profile / "Python-System-Utility-Toolkit-iantolentino-2")

    def test_similar_but_different_origin_is_not_accepted(self):
        self.repo(self.default, "https://github.com/iantolentino/Python-System-Utility-Toolkit-other.git")
        self.assertNotEqual(self.select(), self.default)

    def test_missing_origin_uses_alternate_without_changing_repo(self):
        subprocess.run([GIT, "init", str(self.default)], check=True, capture_output=True)
        self.assertEqual(self.select(), self.profile / "Python-System-Utility-Toolkit-iantolentino")
