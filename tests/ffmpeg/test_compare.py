"""Regression checks for recorder termination, without Docker or media fixtures."""

import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import compare


class TerminationTest(unittest.TestCase):
    def run_case(self, running_before_stop, exit_code):
        stopped = False

        def docker(*args, **kwargs):
            nonlocal stopped
            if args[0] == "stop":
                stopped = True
            return SimpleNamespace(stdout="", stderr="")

        def inspect(name):
            running = not stopped and (name.endswith("publisher") or running_before_stop)
            return {"State": {"Running": running, "ExitCode": exit_code}}

        with patch.object(compare, "docker", side_effect=docker), \
                patch.object(compare, "inspect", side_effect=inspect), \
                patch.object(compare, "wait_for"), \
                patch.object(compare, "probe_outputs", return_value=[{"valid": True}] * 3), \
                patch.object(compare.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            return compare.run_case(
                SimpleNamespace(baseline="baseline", candidate="alpine"),
                MagicMock(), "network", "server", "h264", "input-ended", [],
            )

    def test_premature_or_abnormal_exit_cannot_pass_with_valid_files(self):
        for running, exit_code in ((False, 0), (False, 1), (True, 1)):
            with self.subTest(running=running, exit_code=exit_code):
                case = self.run_case(running, exit_code)
                self.assertTrue(all(not v["valid"] for v in case["variants"].values()))

    def test_running_recorder_then_clean_exit_passes(self):
        case = self.run_case(True, 0)
        self.assertTrue(all(v["valid"] for v in case["variants"].values()))


if __name__ == "__main__":
    unittest.main()
