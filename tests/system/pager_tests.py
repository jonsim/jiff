from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import shlex
import struct
import subprocess
import sys
import tempfile
import termios
import unittest
from pathlib import Path

JIFF_COMMAND: list[str] = []
FAKE_PAGER = Path(__file__).with_name("fake_pager.py")


class PagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="jiff-pager-")
        self.directory = Path(self.temporary_directory.name) / "Pager files"
        self.directory.mkdir()
        self.left = self.directory / "left.txt"
        self.right = self.directory / "right.txt"
        self.capture = self.directory / "pager capture.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_equal_inputs(self, line_count: int) -> None:
        """Writes an easily aligned diff of the requested display height."""
        contents = "".join(f"Kermit line {line}\n" for line in range(line_count))
        self.left.write_text(contents, encoding="utf-8")
        self.right.write_text(contents, encoding="utf-8")

    def run_jiff(
        self,
        mode: str,
        *,
        height: int = 3,
        less: str | None = None,
        timeout: int = 20,
    ) -> tuple[int, str, str]:
        """Runs Jiff with a real terminal on stdout and a controlled pager."""
        environment = os.environ.copy()
        environment["COLUMNS"] = "80"
        environment["LINES"] = str(height)
        environment["JIFF_CONFIG"] = str(
            Path(__file__).with_name("default-config.toml")
        )
        environment["PAGER"] = shlex.join(
            [sys.executable, str(FAKE_PAGER), mode, str(self.capture)]
        )
        if less is None:
            environment.pop("LESS", None)
        else:
            environment["LESS"] = less

        master, slave = pty.openpty()
        fcntl.ioctl(
            slave,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", height, 80, 0, 0),
        )
        try:
            process = subprocess.Popen(
                [
                    *JIFF_COMMAND,
                    "--no-color",
                    "--no-syntax",
                    str(self.left),
                    str(self.right),
                ],
                stdout=slave,
                stderr=subprocess.PIPE,
                env=environment,
            )
            os.close(slave)
            slave = -1
            _, stderr = process.communicate(timeout=timeout)
            terminal_output = bytearray()
            while True:
                try:
                    chunk = os.read(master, 8192)
                except OSError:
                    # Linux reports EIO once the final slave descriptor closes.
                    break
                if not chunk:
                    break
                terminal_output.extend(chunk)
        finally:
            if slave >= 0:
                os.close(slave)
            os.close(master)

        return (
            process.returncode,
            stderr.decode("utf-8", errors="replace"),
            terminal_output.decode("utf-8", errors="replace"),
        )

    def test_configured_pager_receives_the_complete_diff(self) -> None:
        self.write_equal_inputs(10)

        returncode, stderr, terminal_output = self.run_jiff("capture")

        self.assertEqual(0, returncode, stderr)
        self.assertEqual("", terminal_output)
        capture = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual("FRX", capture["less"])
        self.assertIn("Kermit line 0", capture["input"])
        self.assertIn("Kermit line 9", capture["input"])

    def test_existing_less_options_are_preserved(self) -> None:
        self.write_equal_inputs(10)

        returncode, stderr, _ = self.run_jiff("capture", less="-S")

        self.assertEqual(0, returncode, stderr)
        capture = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual("-S", capture["less"])

    def test_short_output_bypasses_the_pager(self) -> None:
        self.write_equal_inputs(1)

        returncode, stderr, terminal_output = self.run_jiff("capture", height=20)

        self.assertEqual(0, returncode, stderr)
        self.assertFalse(self.capture.exists())
        self.assertIn("Kermit line 0", terminal_output)

    def test_quitting_the_pager_early_is_successful(self) -> None:
        # Identical lines are cheap to diff but still make the pipe larger than
        # its kernel buffer.
        self.write_equal_inputs(20_000)

        returncode, stderr, _ = self.run_jiff("close")

        self.assertEqual(0, returncode, stderr)

    def test_pager_failure_reaches_the_user(self) -> None:
        self.write_equal_inputs(10)

        returncode, stderr, _ = self.run_jiff("fail")

        self.assertEqual(1, returncode)
        self.assertIn("Could not display diff", stderr)
        self.assertRegex(stderr, r"status(?::)? 7")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jiff", nargs=argparse.REMAINDER, required=True)
    arguments = parser.parse_args()
    if not arguments.jiff:
        parser.error("--jiff requires a command")
    JIFF_COMMAND.extend(arguments.jiff)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PagerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
