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
from test_coverage import segment


class TerminationTest(unittest.TestCase):
    def run_case(self, running_before_stop, exit_code, logs="", files=None):
        stopped = False
        now = 0

        def sleep(seconds):
            nonlocal now
            now += seconds

        def docker(*args, **kwargs):
            nonlocal stopped
            if args[0] == "stop":
                stopped = True
            return SimpleNamespace(stdout=logs if args[0] == "logs" else "", stderr="")

        def inspect(name):
            running = not stopped and (name.endswith("publisher") or running_before_stop)
            return {"State": {"Running": running, "ExitCode": exit_code}}

        with patch.object(compare, "docker", side_effect=docker), \
                patch.object(compare, "inspect", side_effect=inspect), \
                patch.object(compare, "wait_for"), \
                patch.object(compare, "wait_for_publisher"), \
                patch.object(compare, "probe_outputs", return_value=files or [segment(4.5)] * 3), \
                patch.object(compare.time, "monotonic", side_effect=lambda: now), \
                patch.object(compare.time, "sleep", side_effect=sleep), \
                contextlib.redirect_stdout(io.StringIO()):
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

    def test_running_recorder_with_three_short_valid_files_fails(self):
        case = self.run_case(True, 0, files=[segment(0.4)] * 3)
        self.assertTrue(all(not v["valid"] for v in case["variants"].values()))

    def test_overwritten_segments_cannot_pass_with_valid_remaining_files(self):
        opening = "[segment] Opening '/videos/2026/10/13/120000.mp4' for writing\n"
        for logs in (opening * 2, opening + "    Last message repeated 2 times\n"):
            with self.subTest(logs=logs):
                case = self.run_case(True, 0, logs)
                self.assertTrue(all(not v["valid"] for v in case["variants"].values()))

    def test_repeated_other_messages_do_not_mark_segment_as_overwritten(self):
        logs = ("[segment] Opening '/videos/2026/10/13/120000.mp4' for writing\n"
                "[rtsp] Non-monotonic DTS\n    Last message repeated 2 times\n")
        self.assertEqual(compare.duplicate_output_paths(logs), [])


class ImageSetupTest(unittest.TestCase):
    def test_records_binary_and_package_versions(self):
        def docker(*args, **kwargs):
            if args[0] == "inspect":
                output = json.dumps([{"Id": "id", "Architecture": "amd64"}])
            elif "--entrypoint" in args and args[args.index("--entrypoint") + 1] == "ffmpeg":
                output = "ffmpeg version " + ("7.1.1" if "baseline" in args else "8.1.2")
            elif "apk" in args:
                output = "" if "baseline" in args else "ffmpeg-8.1.2-r0 x86_64 [installed]"
            else:
                output = ""
            return SimpleNamespace(stdout=output, stderr="")

        with patch.object(compare, "docker", side_effect=docker):
            images = compare.image_metadata(SimpleNamespace(
                baseline="baseline", candidate="alpine", server_image="server"
            ))
        self.assertEqual(images["baseline"]["ffmpeg_version"], "ffmpeg version 7.1.1")
        self.assertIsNone(images["baseline"]["ffmpeg_package"])
        self.assertEqual(images["alpine"]["ffmpeg_version"], "ffmpeg version 8.1.2")
        self.assertIn("ffmpeg-8.1.2-r0", images["alpine"]["ffmpeg_package"])

    def test_uncached_server_is_pulled_before_inspection(self):
        pulled = False

        def docker(*args, **kwargs):
            nonlocal pulled
            if args == ("pull", "server"):
                pulled = True
            elif args == ("inspect", "server") and not pulled:
                raise subprocess.CalledProcessError(1, args)
            return SimpleNamespace(stdout=json.dumps([{"Id": "id", "Architecture": "amd64"}]), stderr="")

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


class PacketValidationTest(unittest.TestCase):
    def probe(self, video_dts):
        packets = [{"stream_index": 0, "pts_time": "0.0", "flags": "K"},
                   {"stream_index": 0, "pts_time": "0.04", "flags": "_"},
                   {"stream_index": 1, "pts_time": "0.0", "dts_time": "0.0", "flags": "K"}]
        for packet, value in zip(packets, video_dts):
            if value is not None:
                packet["dts_time"] = value
        data = {"format": {"duration": "4.0"}, "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {"index": 1, "codec_type": "audio", "codec_name": "aac"},
        ], "packets": packets}
        results = [SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr=""),
                   SimpleNamespace(returncode=0, stdout="", stderr="")]
        with TemporaryDirectory() as temporary, patch.object(compare, "media", side_effect=results):
            directory = Path(temporary)
            (directory / "test.mp4").write_bytes(b"fixture")
            return compare.probe_outputs(SimpleNamespace(), directory, "h264")[0]

    def test_missing_or_invalid_dts_cannot_pass_after_successful_decode(self):
        for dts in ((None, None), ("0.0", None), ("0.0", "N/A"), ("nan", "nan")):
            with self.subTest(dts=dts):
                result = self.probe(dts)
                self.assertFalse(result["valid"])
                self.assertFalse(result["streams"][0]["monotonic_dts"])

    def test_complete_ordered_dts_passes(self):
        self.assertTrue(self.probe(("0.0", "0.04"))["valid"])


if __name__ == "__main__":
    unittest.main()
