"""Exercise the real PowerShell orchestration with fake installers/WinGet."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HELPER = Path(__file__).resolve().parents[1] / "setup-prerequisites.ps1"


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell required")
class PrerequisiteTests(unittest.TestCase):
    def run_script(self, body):
        with tempfile.TemporaryDirectory(prefix="toolkit test ") as directory:
            script = Path(directory) / "test.ps1"
            script.write_text(". '" + str(HELPER).replace("'", "''") + "' -Library\n" + body, encoding="utf-8")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                                    capture_output=True, text=True, timeout=30,
                                    env={**os.environ, "TEMP": directory})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout.strip().splitlines()[-1])

    def scenario(self, codes, direct_failure=False):
        return self.run_script("""
$script:codes = @(%s)
$script:installs = 0; $script:resets = 0; $script:updates = 0; $script:direct = 0
$script:ready = $false; $script:failed = $false
function Get-Command { [CmdletBinding()] param([string]$Name); return @{Source='fake-winget'} }
function Start-Sleep { param($Seconds) }
function Find-Tool { param($Name); if ($script:ready) { return 'C:\\Fake Tools\\tool.exe' } }
function Invoke-Native {
    param($File, $Arguments)
    if ($Arguments[0] -eq 'install') {
        $code = $script:codes[[Math]::Min($script:installs, $script:codes.Count - 1)]
        $script:installs++
        if ($code -eq 0) { $script:ready = $true }
        return $code
    }
    if ($Arguments[1] -eq 'reset') { $script:resets++ }
    if ($Arguments[1] -eq 'update') { $script:updates++ }
    return 0
}
function Install-Direct { param($Name); $script:direct++; %s }
try { Install-Prerequisite git } catch { $script:failed = $true }
@{installs=$script:installs; resets=$script:resets; updates=$script:updates; direct=$script:direct; ready=$script:ready; failed=$script:failed} | ConvertTo-Json -Compress
""" % (",".join(map(str, codes)), "throw 'fake failure'" if direct_failure else "$script:ready = $true"))

    def test_reported_negative_hresult_retries_repairs_then_uses_fallback(self):
        self.assertEqual(self.scenario([-1978335217]),
                         dict(installs=3, resets=1, updates=1, direct=1, ready=True, failed=False))

    def test_source_repair_allows_second_attempt_without_fallback(self):
        self.assertEqual(self.scenario([-1978335217, 0]),
                         dict(installs=2, resets=1, updates=1, direct=0, ready=True, failed=False))

    def test_failed_fallback_does_not_claim_success(self):
        result = self.scenario([-1978335217], direct_failure=True)
        self.assertTrue(result["failed"])
        self.assertFalse(result["ready"])

    def test_native_wrapper_preserves_negative_exit_code(self):
        result = self.run_script("$code = Invoke-Native $env:ComSpec @('/d', '/c', 'exit -1978335217'); @{code=$code} | ConvertTo-Json -Compress")
        self.assertEqual(result["code"], -1978335217)

    def test_missing_winget_uses_direct_fallback(self):
        result = self.run_script("""
$script:ready = $false; $script:direct = 0
function Get-Command { [CmdletBinding()] param([string]$Name); return $null }
function Find-Tool { param($Name); if ($script:ready) { return 'C:\\Fake Tools\\python.exe' } }
function Install-Direct { param($Name); $script:direct++; $script:ready = $true }
Install-Prerequisite python
@{direct=$script:direct; ready=$script:ready} | ConvertTo-Json -Compress
""")
        self.assertEqual(result, dict(direct=1, ready=True))

    def test_existing_tool_is_reused_without_installing(self):
        result = self.run_script("""
function Find-Tool { param($Name); return 'C:\\Existing Tools\\tool.exe' }
function Install-WithWinget { throw 'should not install' }
function Install-Direct { throw 'should not install' }
Install-Prerequisite git
@{ok=$true} | ConvertTo-Json -Compress
""")
        self.assertTrue(result["ok"])

    def test_success_exit_without_usable_tool_still_requires_fallback(self):
        result = self.run_script("""
$script:ready = $false; $script:installs = 0; $script:direct = 0
function Get-Command { [CmdletBinding()] param([string]$Name); return @{Source='fake-winget'} }
function Find-Tool { param($Name); if ($script:ready) { return 'C:\\Fake Tools\\tool.exe' } }
function Invoke-Native { param($File, $Arguments); if ($Arguments[0] -eq 'install') { $script:installs++ }; return 0 }
function Start-Sleep { param($Seconds) }
function Install-Direct { param($Name); $script:direct++; $script:ready = $true }
Install-Prerequisite git
@{installs=$script:installs; direct=$script:direct} | ConvertTo-Json -Compress
""")
        self.assertEqual(result, dict(installs=3, direct=1))

    def test_invalid_vendor_signature_prevents_installer_execution(self):
        result = self.run_script("""
$script:executed = $false; $script:failed = $false; $script:verified = 0
function Get-Architecture { return 'x64' }
function Invoke-WebRequest { param([switch]$UseBasicParsing, $Uri, $OutFile, $TimeoutSec); Set-Content -LiteralPath $OutFile -Value 'fake installer' }
function Get-AuthenticodeSignature { param($LiteralPath); $script:verified++; return @{Status='NotSigned'} }
function Start-Process { $script:executed = $true }
try { Install-Direct python } catch { $script:failed = $true }
@{executed=$script:executed; failed=$script:failed; verified=$script:verified} | ConvertTo-Json -Compress
""")
        self.assertEqual(result, dict(executed=False, failed=True, verified=1))
