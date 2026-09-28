import subprocess
import unittest
from unittest.mock import Mock, patch

import clock_service
import setup_service


class ClockTests(unittest.TestCase):
    def setUp(self):
        patch.object(setup_service, "require_admin").start()
        patch.object(clock_service.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def result(self, code=0):
        return subprocess.CompletedProcess(["command"], code, "", "")

    def test_ntp_unavailable_uses_verified_https_clock(self):
        with patch.object(setup_service, "run_process", side_effect=[self.result(), RuntimeError("No NTP"), RuntimeError("No NTP"), RuntimeError("No NTP")]) as run, patch.object(clock_service, "check_online_clock") as online:
            clock_service.check_system_time(Mock())
        self.assertEqual(run.call_count, 4)
        online.assert_called_once()

    def test_ntp_success_allows_https_date_service_outage(self):
        with patch.object(setup_service, "run_process", return_value=self.result()), patch.object(clock_service, "check_online_clock", side_effect=RuntimeError("HTTPS offline")):
            clock_service.check_system_time(Mock())

    def test_inaccurate_clock_is_rejected_even_after_sync(self):
        with patch.object(setup_service, "run_process", return_value=self.result()), patch.object(clock_service, "check_online_clock", side_effect=RuntimeError("Windows clock differs from the online clock")):
            with self.assertRaisesRegex(RuntimeError, "differs"):
                clock_service.check_system_time(Mock())

    def test_no_time_sources_is_reported(self):
        with patch.object(setup_service, "run_process", side_effect=RuntimeError("Service unavailable")), patch.object(clock_service, "check_online_clock", side_effect=RuntimeError("HTTPS offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                clock_service.check_system_time(Mock())

    def test_disabled_service_is_enabled_before_sync(self):
        with patch.object(setup_service, "run_process", side_effect=[self.result(1058), self.result(), self.result(), self.result()]) as run, patch.object(clock_service, "check_online_clock"):
            clock_service.check_system_time(Mock())
        self.assertEqual(run.call_args_list[1].args[0], ["sc.exe", "config", "w32time", "start=", "demand"])

    def test_service_timeout_can_fall_back_to_https(self):
        with patch.object(setup_service, "run_process", side_effect=subprocess.TimeoutExpired("sc", 30)), patch.object(clock_service, "check_online_clock"):
            clock_service.check_system_time(Mock())


if __name__ == "__main__":
    unittest.main()
