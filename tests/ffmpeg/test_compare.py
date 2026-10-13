"""Regression checks for recorder termination, without Docker or media fixtures."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
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


class ImageSetupTest(unittest.TestCase):
    def test_uncached_server_is_pulled_before_inspection(self):
        pulled = False

        def docker(*args, **kwargs):
            nonlocal pulled
            if args == ("pull", "server"):
                pulled = True
            elif args == ("inspect", "server") and not pulled:
                raise subprocess.CalledProcessError(1, args)
            return SimpleNamespace(stdout=json.dumps([{"Id": "id", "Architecture": "amd64"}]))

        with patch.object(compare, "docker", side_effect=docker):
            images = compare.image_metadata(SimpleNamespace(
                baseline="baseline", candidate="alpine", server_image="server"
            ))
        self.assertTrue(pulled)
        self.assertEqual(images["server"]["architecture"], "amd64")

    def test_failed_image_setup_does_not_create_output_directory(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "recordings"
            args = SimpleNamespace(output=output, baseline="baseline",
                                   candidate="alpine", server_image="server")
            with patch.object(compare.argparse.ArgumentParser, "parse_args", return_value=args), \
                    patch.object(compare, "docker", side_effect=subprocess.CalledProcessError(1, "docker")):
                with self.assertRaises(subprocess.CalledProcessError):
                    compare.main()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
