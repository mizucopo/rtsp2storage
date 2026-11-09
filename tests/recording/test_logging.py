"""Run the entrypoint with noisy children, without a camera or Docker."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "ffmpeg.sh"
URL = "rtsp://dummy-user:p%40ss+[.*]\\word@camera.invalid/live?token=private&x=1"


class LoggingTest(unittest.TestCase):
    def run_entrypoint(self, url=URL, probe_exit=0, child_exit=0, failed_command=None):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            temporary_logs = root / "tmp"
            temporary_logs.mkdir()
            commands = {
                "date": "#!/bin/sh\nprintf '2026/11/09\\n'\n",
                "mkdir": "#!/bin/sh\nexit 0\n",
                "timeout": '#!/bin/sh\nshift\nexec "$@"\n',
                "ffprobe": f"#!{sys.executable}\n" + '''
import os
import sys
print("Probe input " + os.environ["RTSP_URL"], flush=True)
print("Probe error " + os.environ["RTSP_URL"], file=sys.stderr, flush=True)
sys.exit(int(os.environ["PROBE_EXIT"]))
''',
                "ffmpeg": f"#!{sys.executable}\n" + '''
import json
import os
from pathlib import Path
import sys
url = os.environ["RTSP_URL"]
Path(os.environ["FIXTURE_ROOT"], "args.json").write_text(json.dumps(sys.argv[1:]))
print("Input from " + url + "; again " + url, flush=True)
print("Error opening input " + url + ": Connection refused", file=sys.stderr, flush=True)
print("Redirect from rtsps://other-user:other-password@other.invalid/live", flush=True)
print("Redirect from rtsp://other-user:quoted'password@other.invalid/live", flush=True)
sys.stderr.write("Last diagnostic " + url)
sys.stderr.flush()
sys.exit(int(os.environ["CHILD_EXIT"]))
''',
            }
            if failed_command is not None:
                commands[failed_command] = "#!/bin/sh\nexit 1\n"
            for name, contents in commands.items():
                path = binary / name
                path.write_text(contents)
                path.chmod(0o755)
            env = {**os.environ, "PATH": f"{binary}:{os.defpath}",
                   "RTSP_URL": url, "SEGMENT_TIME": "4",
                   "PROBE_EXIT": str(probe_exit), "CHILD_EXIT": str(child_exit),
                   "FIXTURE_ROOT": str(root), "TMPDIR": str(temporary_logs)}
            result = subprocess.run(
                ["/bin/sh", str(ENTRYPOINT)], env=env,
                capture_output=True, text=True, timeout=10,
            )
            args_file = root / "args.json"
            args = json.loads(args_file.read_text()) if args_file.exists() else None
            self.assertEqual(list(temporary_logs.iterdir()), [], "temporary log files remain")
            return result, args

    def test_child_output_is_redacted_without_hiding_diagnostics(self):
        for url in (URL, "rtsps://user:pass@camera.invalid/live", "rtsp://camera.invalid/live"):
            with self.subTest(url=url):
                result, args = self.run_entrypoint(url=url)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = result.stdout + result.stderr
                self.assertNotIn(url, output)
                self.assertNotIn("dummy-user", output)
                self.assertNotIn("private&x=1", output)
                self.assertNotIn("other-password", output)
                self.assertNotIn("quoted", output)
                self.assertNotIn("password@other.invalid", output)
                self.assertIn("Input from [REDACTED]; again [REDACTED]", output)
                self.assertIn("Connection refused", output)
                self.assertIn("Last diagnostic [REDACTED]", output)
                self.assertIn("RTSP connection successful", output)
                self.assertEqual(args[args.index("-i") + 1], url)
                self.assertEqual(args[args.index("-segment_time") + 1], "4")
                self.assertEqual(args[args.index("-c") + 1], "copy")

    def test_probe_failure_and_encoder_exit_are_preserved(self):
        result, _ = self.run_entrypoint(probe_exit=1, child_exit=17)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 17, output)
        self.assertIn("RTSP connection failed. Continuing anyway...", output)
        self.assertIn("Connection refused", output)
        self.assertNotIn(URL, output)

    def test_line_breaks_in_url_fail_before_starting_children(self):
        for separator in ("\r", "\n"):
            with self.subTest(separator=repr(separator)):
                result, args = self.run_entrypoint(url="rtsp://user:secret" + separator + "tail@camera/live")
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(args)
                self.assertIn("RTSP_URL must not contain line breaks", result.stderr)
                self.assertNotIn("secret", result.stdout + result.stderr)
                self.assertNotIn("tail@camera", result.stdout + result.stderr)

    def test_filter_setup_fails_closed(self):
        for command in ("mktemp", "mkfifo"):
            with self.subTest(command=command):
                result, args = self.run_entrypoint(failed_command=command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(args, "FFmpeg started without the log filter")
                self.assertNotIn(URL, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
