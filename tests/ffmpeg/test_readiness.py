"""RTSP startup regressions without a camera or Docker daemon."""

import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import compare


class ReadinessTest(unittest.TestCase):
    def wait(self, ready_at=None, exits_at=None, seconds=5):
        self.now = 0.0
        self.probes = []

        def sleep(seconds):
            self.now += seconds

        def inspect(name):
            return {"State": {"Running": exits_at is None or self.now < exits_at,
                              "ExitCode": 1}}

        def docker(*args, **kwargs):
            if args[0] == "logs":
                return SimpleNamespace(stdout="publisher failure", stderr="")
            self.probes.append(args)
            self.now += 0.25
            ready = ready_at is not None and self.now >= ready_at
            return SimpleNamespace(returncode=0 if ready else 1,
                                   stdout=json.dumps({"packets": [{"stream_index": 0}]}),
                                   stderr="path unavailable")

        with patch.object(compare.time, "monotonic", side_effect=lambda: self.now), \
                patch.object(compare.time, "sleep", side_effect=sleep), \
                patch.object(compare, "inspect", side_effect=inspect), \
                patch.object(compare, "docker", side_effect=docker):
            return compare.wait_for_publisher("publisher", "rtsp://server:8554/live", seconds)

    def test_waits_for_packets_after_more_than_two_seconds(self):
        self.wait(ready_at=3)
        self.assertGreaterEqual(self.now, 3)
        self.assertGreater(len(self.probes), 1)
        self.assertTrue(all("rtsp://server:8554/live" in args for args in self.probes))

    def test_detects_publisher_exit_before_and_during_successful_probe(self):
        for exits_at, ready_at in ((0, None), (0.25, 0.25)):
            with self.subTest(exits_at=exits_at):
                with self.assertRaisesRegex(RuntimeError, "publisher.*exited.*publisher failure"):
                    self.wait(ready_at=ready_at, exits_at=exits_at)

    def test_unavailable_path_times_out(self):
        with self.assertRaisesRegex(RuntimeError, "timed out.*rtsp://server:8554/live"):
            self.wait()
        self.assertLessEqual(self.now, 5.25)

    def test_success_without_packets_is_not_ready(self):
        with patch.object(compare, "docker", return_value=SimpleNamespace(
                returncode=0, stdout='{"packets": []}', stderr="")), \
                patch.object(compare, "inspect", return_value={"State": {"Running": True}}), \
                patch.object(compare.time, "monotonic", side_effect=[0, 0, 1, 5]), \
                patch.object(compare.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                compare.wait_for_publisher("publisher", "rtsp://server:8554/live", 5)


class ReadinessCleanupTest(unittest.TestCase):
    def test_failure_cleans_server_publisher_and_network_without_starting_recorders(self):
        for error in (RuntimeError("publisher exited"), RuntimeError("path timed out"),
                      subprocess.TimeoutExpired("docker exec", 5)):
            with self.subTest(error=error), TemporaryDirectory() as temporary:
                output = Path(temporary) / "recordings"
                args = SimpleNamespace(output=output, baseline="baseline", candidate="alpine",
                                       server_image="server")
                with patch.object(compare.argparse.ArgumentParser, "parse_args", return_value=args), \
                        patch.object(compare, "image_metadata", return_value={}), \
                        patch.object(compare, "media", return_value=SimpleNamespace(returncode=0)), \
                        patch.object(compare, "wait_for"), \
                        patch.object(compare, "wait_for_publisher", side_effect=error), \
                        patch.object(compare, "docker", return_value=SimpleNamespace(
                            stdout="", stderr="")) as docker:
                    with self.assertRaises(type(error)):
                        compare.main()
                calls = [call.args for call in docker.call_args_list]
                started = [args[args.index("--name") + 1] for args in calls if "--name" in args]
                self.assertEqual(len(started), 2)
                self.assertTrue(started[0].endswith("-server"))
                self.assertTrue(started[1].endswith("-publisher"))
                for name in started:
                    self.assertIn(("rm", "-f", name), calls)
                self.assertTrue(any(args[:2] == ("network", "rm") for args in calls))
                self.assertEqual(json.loads((output / "report.json").read_text())["cases"], [])


class RecorderStartTest(unittest.TestCase):
    def test_parses_docker_nanosecond_and_variable_precision_timestamps(self):
        for fraction in ("123456789", "123456", "123", "1", ""):
            with self.subTest(fraction=fraction):
                value = "2026-10-13T18:31:03" + ("." + fraction if fraction else "") + "Z"
                microsecond = int(fraction[:6].ljust(6, "0"))
                expected = datetime(2026, 10, 13, 18, 31, 3, microsecond, timezone.utc).timestamp()
                self.assertEqual(compare.docker_timestamp(value), expected)
        with self.assertRaises(ValueError):
            compare.docker_timestamp("2026-10-13T18:31:03")

    def test_timestamped_markers_include_starts_before_the_first_poll(self):
        for starts in ({"baseline": 1, "alpine": 12}, {"baseline": 12, "alpine": 1}):
            for first_poll in (0, 12):
                with self.subTest(starts=starts, first_poll=first_poll):
                    self.check_starts(starts, first_poll)

    def check_starts(self, starts, first_poll):
        now = first_poll

        def sleep(seconds):
            nonlocal now
            now += seconds

        def docker(*args, **kwargs):
            variant = args[-1]
            timestamp = datetime.fromtimestamp(starts[variant], timezone.utc).isoformat()
            marker = f"{timestamp} Starting FFmpeg recording..." if now >= starts[variant] else ""
            return SimpleNamespace(stdout=marker, stderr="")

        with patch.object(compare, "docker", side_effect=docker), \
                patch.object(compare, "inspect", return_value={"State": {"Running": True}}), \
                patch.object(compare.time, "monotonic", side_effect=lambda: now), \
                patch.object(compare.time, "sleep", side_effect=sleep):
            observed = compare.wait_for_recorders({name: name for name in starts})
        self.assertEqual(observed, starts)


if __name__ == "__main__":
    unittest.main()
