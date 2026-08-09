from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

JIFF_COMMAND: list[str] = []


class GitDifftoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="jiff-git-")
        # A space in the checkout path catches shell commands which quote the
        # temporary Git paths incorrectly.
        self.repository = Path(self.temporary_directory.name) / "Muppet repository"
        self.repository.mkdir()

        self.git("init", "--quiet")
        self.git("config", "user.name", "Kermit the Frog")
        self.git("config", "user.email", "kermit@muppets.example")
        self.configure_difftool()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Runs Git in the temporary repository and captures its output."""
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=check,
        )

    def configure_difftool(self, command: str | None = None) -> None:
        """Configures Jiff as a trusted, non-prompting custom difftool."""
        if command is None:
            executable = shlex.join(
                [*JIFF_COMMAND, "--no-pager", "--no-color", "--path"]
            )
            command = f'{executable} "$MERGED" "$LOCAL" "$REMOTE"'

        self.git("config", "diff.tool", "jiff")
        self.git("config", "difftool.jiff.cmd", command)
        self.git("config", "difftool.prompt", "false")
        self.git("config", "difftool.trustExitCode", "true")

    def write(self, path: str, content: str | bytes) -> None:
        """Writes text or binary test content below the repository root."""
        destination = self.repository / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content, encoding="utf-8")

    def commit(self, message: str) -> None:
        """Commits the complete working tree with the given message."""
        self.git("add", "--all")
        self.git("commit", "--quiet", "--message", message)

    def difftool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Runs the configured Jiff difftool without an interactive prompt."""
        return self.git(
            "difftool", "--no-prompt", "--tool=jiff", *arguments, check=False
        )

    def test_worktree_diff_handles_multiple_files_and_spaces(self) -> None:
        # Git invokes the tool once per file and retains each repository path.
        self.write("kermit.txt", "green\n")
        self.write("muppet cast.txt", "Kermit\n")
        self.commit("Introduce the cast")
        self.write("kermit.txt", "still green\n")
        self.write("muppet cast.txt", "Kermit\nFozzie\n")

        result = self.difftool()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--- a/kermit.txt\n+++ b/kermit.txt\n", result.stdout)
        self.assertIn("--- a/muppet cast.txt\n+++ b/muppet cast.txt\n", result.stdout)

    def test_cached_diff_handles_add_delete_and_an_empty_side(self) -> None:
        # Adds and deletes arrive as an empty temporary file on one side.
        self.write("statler.txt", "Boo!\n")
        self.write("empty.txt", "")
        self.commit("Prepare the balcony")
        (self.repository / "statler.txt").unlink()
        self.write("gonzo.txt", "The Great Gonzo\n")
        self.write("empty.txt", "Fozzie was here\n")
        self.git("add", "--all")

        result = self.difftool("--cached")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--- a/statler.txt\n+++ b/statler.txt\n", result.stdout)
        self.assertIn("--- a/gonzo.txt\n+++ b/gonzo.txt\n", result.stdout)
        self.assertIn("--- a/empty.txt\n+++ b/empty.txt\n", result.stdout)

    def test_revision_diff_handles_a_rename(self) -> None:
        # Git supplies the source path through `$MERGED` for a detected rename.
        self.write("old name.txt", "Miss Piggy\nKermit\nFozzie\nGonzo\n")
        self.commit("Write the programme")
        (self.repository / "old name.txt").rename(self.repository / "new name.txt")
        self.write("new name.txt", "Miss Piggy\nKermit\nFozzie Bear\nGonzo\n")
        self.commit("Rename the programme")

        result = self.difftool("--find-renames", "HEAD^", "HEAD")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--- a/old name.txt\n+++ b/old name.txt\n", result.stdout)

    def test_binary_diff_reports_the_repository_path(self) -> None:
        # Binary input is useful information, not a UTF-8 decoding failure.
        self.write("animal.dat", bytes([0, 1, 2, 3]))
        self.commit("Record Animal")
        self.write("animal.dat", bytes([0, 1, 2, 4]))

        result = self.difftool()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "Binary files a/animal.dat and b/animal.dat differ\n", result.stdout
        )

    def test_extcmd_supports_a_one_off_invocation(self) -> None:
        # In extcmd mode Git appends the temporary files and exposes the path
        # as `$BASE`, so no persistent configuration is needed.
        self.write("rowlf.txt", "Piano\n")
        self.commit("Seat Rowlf at the piano")
        self.write("rowlf.txt", "Grand piano\n")
        executable = shlex.join([*JIFF_COMMAND, "--no-pager", "--no-color", "--path"])

        result = self.git(
            "difftool",
            "--no-prompt",
            f'--extcmd={executable} "$BASE"',
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--- a/rowlf.txt\n+++ b/rowlf.txt\n", result.stdout)

    def test_trusted_tool_failure_reaches_git(self) -> None:
        # Git only reports a custom tool failure when trustExitCode is enabled.
        self.write("scooter.txt", "Stage manager\n")
        self.commit("Hire Scooter")
        self.write("scooter.txt", "Very busy stage manager\n")
        executable = shlex.join([*JIFF_COMMAND, "--no-pager", "--no-color", "--path"])
        self.configure_difftool(f'{executable} "$MERGED" "$LOCAL.missing" "$REMOTE"')

        result = self.difftool()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Could not read", result.stderr)

    def test_directory_inputs_fail_cleanly(self) -> None:
        # Git's --dir-diff contract is deliberately outside Jiff's file mode.
        result = subprocess.run(
            [*JIFF_COMMAND, "--no-pager", str(self.repository), str(self.repository)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("Could not read", result.stderr)

    def test_early_pipe_closure_is_successful(self) -> None:
        # Closing a consumer after one line must not turn a useful diff into a
        # failure. Make the output larger than a pipe so the close is observed.
        content = "".join(f"Kermit line {line}\n" for line in range(20_000))
        self.write("left.txt", content)
        self.write("right.txt", content)
        process = subprocess.Popen(
            [
                *JIFF_COMMAND,
                "--inline",
                "--no-color",
                str(self.repository / "left.txt"),
                str(self.repository / "right.txt"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdout.readline()
        process.stdout.close()

        returncode = process.wait(timeout=20)
        stderr = process.stderr.read()

        self.assertEqual(0, returncode, stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jiff", nargs=argparse.REMAINDER, required=True)
    arguments = parser.parse_args()
    if not arguments.jiff:
        parser.error("--jiff requires a command")
    JIFF_COMMAND.extend(arguments.jiff)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GitDifftoolTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
