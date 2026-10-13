"""Exercise the real entrypoint's signal and exit behavior with a child fixture."""

import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest


ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "ffmpeg.sh"


class ShutdownTest(unittest.TestCase):
    def run_entrypoint(self, stop_signal=None, child_exit=None):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            commands = {
                "date": "#!/bin/sh\nprintf '2026/10/13\\n'\n",
                "mkdir": "#!/bin/sh\nexit 0\n",
                "ffprobe": "#!/bin/sh\nexit 0\n",
                "timeout": '#!/bin/sh\nshift\nexec "$@"\n',
                "ffmpeg": f"#!{sys.executable}\n" + '''
import os
from pathlib import Path
import signal
import sys
import time
root = Path(os.environ["FIXTURE_ROOT"])
def finish(signum, frame):
    (root / "received").write_text(str(signum))
    time.sleep(0.2)
    (root / "finalized").write_text("finalized")
    sys.exit(0)
signal.signal(signal.SIGTERM, finish)
(root / "child_pid").write_text(str(os.getpid()))
(root / "ready").touch()
if "CHILD_EXIT" in os.environ:
    sys.exit(int(os.environ["CHILD_EXIT"]))
while True:
    time.sleep(0.05)
''',
            }
            for name, contents in commands.items():
                path = binary / name
                path.write_text(contents)
                path.chmod(0o755)
            env = {**os.environ, "PATH": f"{binary}:{os.defpath}",
                   "RTSP_URL": "rtsp://fixture/live", "SEGMENT_TIME": "4",
                   "FIXTURE_ROOT": str(root)}
            if child_exit is not None:
                env["CHILD_EXIT"] = str(child_exit)
            process = subprocess.Popen(
                ["/bin/sh", str(ENTRYPOINT)], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            try:
                deadline = time.monotonic() + 10
                while not (root / "ready").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue((root / "ready").exists(), "recording child did not start")
                if stop_signal is not None:
                    process.send_signal(stop_signal)
                output, _ = process.communicate(timeout=3)
                return process.returncode, (root / "finalized").exists(), output
            finally:
                if process.poll() is None:
                    process.kill()
                if (root / "child_pid").exists():
                    try:
                        os.kill(int((root / "child_pid").read_text()), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                process.communicate(timeout=3)

    def test_stop_signals_forward_to_child_and_wait_for_finalization(self):
        for stop_signal in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=stop_signal):
                code, finalized, output = self.run_entrypoint(stop_signal=stop_signal)
                self.assertEqual(code, 0, output)
                self.assertTrue(finalized, "entrypoint exited before the child's finalizer")

    def test_child_failure_is_preserved(self):
        code, _, output = self.run_entrypoint(child_exit=17)
        self.assertEqual(code, 17, output)


if __name__ == "__main__":
    unittest.main()
