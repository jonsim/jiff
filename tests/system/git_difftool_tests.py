from __future__ import annotations

import argparse
import re
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

    def configure_external_diff(self) -> None:
        """Configures Jiff to parse Git's external diff arguments."""
        command = shlex.join([*JIFF_COMMAND, "--git-external-diff", "--no-color"])
        self.git("config", "diff.external", command)

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

    def assert_side_by_side_header(self, output: str, path: str) -> None:
        """Checks that Git's path labels both side-by-side panes."""
        self.assertRegex(output, rf"(?m)^ {re.escape(path)} +│ {re.escape(path)}$")
        self.assertNotIn(f"--- a/{path}", output)

    def test_worktree_diff_handles_multiple_files_and_spaces(self) -> None:
        # Git calls the tool once per file and should pass each repository path
        # through untouched.
        self.write("kermit.txt", "green\n")
        self.write("muppet cast.txt", "Kermit\n")
        self.commit("Introduce the cast")
        self.write("kermit.txt", "still green\n")
        self.write("muppet cast.txt", "Kermit\nFozzie\n")

        result = self.difftool()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_side_by_side_header(result.stdout, "kermit.txt")
        self.assert_side_by_side_header(result.stdout, "muppet cast.txt")
        self.assertIn("still green", result.stdout)
        self.assertIn("Fozzie", result.stdout)

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
        self.assert_side_by_side_header(result.stdout, "statler.txt")
        self.assert_side_by_side_header(result.stdout, "gonzo.txt")
        self.assert_side_by_side_header(result.stdout, "empty.txt")
        self.assertIn("Boo!", result.stdout)
        self.assertIn("The Great Gonzo", result.stdout)
        self.assertIn("Fozzie was here", result.stdout)

    def test_revision_diff_handles_a_rename(self) -> None:
        # Git supplies the source path through `$MERGED` for a detected rename.
        self.write("old name.txt", "Miss Piggy\nKermit\nFozzie\nGonzo\n")
        self.commit("Write the programme")
        (self.repository / "old name.txt").rename(self.repository / "new name.txt")
        self.write("new name.txt", "Miss Piggy\nKermit\nFozzie Bear\nGonzo\n")
        self.commit("Rename the programme")

        result = self.difftool("--find-renames", "HEAD^", "HEAD")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_side_by_side_header(result.stdout, "old name.txt")

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
        self.assert_side_by_side_header(result.stdout, "rowlf.txt")

    def test_external_diff_mode_supports_git_diff(self) -> None:
        self.write("kermit.txt", "Green\n")
        self.commit("Paint Kermit")
        self.write("kermit.txt", "Still green\n")
        self.configure_external_diff()

        result = self.git("diff", "HEAD", check=False)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_side_by_side_header(result.stdout, "kermit.txt")
        self.assertIn("Still green", result.stdout)

    def test_external_diff_mode_supports_git_show(self) -> None:
        self.write("fozzie.txt", "Bear\n")
        self.commit("Introduce Fozzie")
        self.write("fozzie.txt", "Funny bear\n")
        self.commit("Give Fozzie a job")
        self.configure_external_diff()

        result = self.git("show", "--format=", "--ext-diff", "HEAD", check=False)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_side_by_side_header(result.stdout, "fozzie.txt")
        self.assertIn("Funny bear", result.stdout)

    def test_unmerged_protocol_renders_a_three_way_diff(self) -> None:
        path = "muppet cast.txt"
        self.write(path, "same\nbase tune\n")
        self.commit("Write the original tune")
        base = self.git("rev-parse", "HEAD").stdout.strip()

        self.git("switch", "--quiet", "--create", "remote")
        self.write(path, "same\nremote tune\n")
        self.commit("Rewrite the remote tune")
        self.git("switch", "--quiet", "--create", "local", base)
        self.write(path, "same\nlocal tune\n")
        self.commit("Rewrite the local tune")
        merge = self.git("merge", "--no-edit", "remote", check=False)
        self.assertNotEqual(0, merge.returncode)
        result = subprocess.run(
            [*JIFF_COMMAND, "--git-external-diff", "--no-color", path],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("=== Unmerged: muppet cast.txt ===\n", result.stdout)
        self.assertIn("1: Local", result.stdout)
        self.assertIn("2: Base", result.stdout)
        self.assertIn("3: Remote", result.stdout)
        self.assertIn("local tune", result.stdout)
        self.assertIn("base tune", result.stdout)
        self.assertIn("remote tune", result.stdout)

    def test_unmerged_protocol_renders_an_add_add_conflict(self) -> None:
        self.git("commit", "--quiet", "--allow-empty", "--message", "Start empty")
        base = self.git("rev-parse", "HEAD").stdout.strip()

        self.git("switch", "--quiet", "--create", "remote")
        self.write("new song.txt", "Remote song\n")
        self.commit("Add the remote song")
        self.git("switch", "--quiet", "--create", "local", base)
        self.write("new song.txt", "Local song\n")
        self.commit("Add the local song")
        merge = self.git("merge", "--no-edit", "remote", check=False)
        self.assertNotEqual(0, merge.returncode)
        result = subprocess.run(
            [
                *JIFF_COMMAND,
                "--git-external-diff",
                "--no-color",
                "new song.txt",
            ],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("=== Unmerged: new song.txt ===\n", result.stdout)
        self.assertIn("1: Local", result.stdout)
        self.assertIn("2: Base", result.stdout)
        self.assertIn("3: Remote", result.stdout)
        self.assertIn("Local song", result.stdout)
        self.assertIn("Remote song", result.stdout)

    def test_unmerged_protocol_renders_a_modify_delete_conflict(self) -> None:
        path = "closing number.txt"
        self.write(path, "Original song\n")
        self.commit("Write the closing number")
        base = self.git("rev-parse", "HEAD").stdout.strip()

        self.git("switch", "--quiet", "--create", "remote")
        (self.repository / path).unlink()
        self.commit("Cut the remote closing number")
        self.git("switch", "--quiet", "--create", "local", base)
        self.write(path, "Local rewrite\n")
        self.commit("Rewrite the local closing number")
        merge = self.git("merge", "--no-edit", "remote", check=False)
        self.assertNotEqual(0, merge.returncode)

        result = subprocess.run(
            [*JIFF_COMMAND, "--git-external-diff", "--no-color", path],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("=== Unmerged: closing number.txt ===\n", result.stdout)
        panes = [line.split("│") for line in result.stdout.splitlines()]
        # Git's missing remote stage should show up as an empty third pane while
        # the base and local edit stay visible.
        self.assertTrue(
            any(
                "Local rewrite" in row[1] and not row[5].strip()
                for row in panes
                if len(row) == 6
            ),
            result.stdout,
        )
        self.assertTrue(
            any(
                "Original song" in row[3] and not row[5].strip()
                for row in panes
                if len(row) == 6
            ),
            result.stdout,
        )

    def test_unmerged_protocol_renders_a_delete_modify_conflict(self) -> None:
        path = "opening number.txt"
        self.write(path, "Original song\n")
        self.commit("Write the opening number")
        base = self.git("rev-parse", "HEAD").stdout.strip()

        self.git("switch", "--quiet", "--create", "remote")
        self.write(path, "Remote rewrite\n")
        self.commit("Rewrite the remote opening number")
        self.git("switch", "--quiet", "--create", "local", base)
        (self.repository / path).unlink()
        self.commit("Cut the local opening number")
        merge = self.git("merge", "--no-edit", "remote", check=False)
        self.assertNotEqual(0, merge.returncode)

        result = subprocess.run(
            [*JIFF_COMMAND, "--git-external-diff", "--no-color", path],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("=== Unmerged: opening number.txt ===\n", result.stdout)
        panes = [line.split("│") for line in result.stdout.splitlines()]
        # This is the same case the other way round: the missing local stage
        # should show up as an empty first pane.
        self.assertTrue(
            any(
                not row[1].strip() and "Remote rewrite" in row[5]
                for row in panes
                if len(row) == 6
            ),
            result.stdout,
        )
        self.assertTrue(
            any(
                not row[1].strip() and "Original song" in row[3]
                for row in panes
                if len(row) == 6
            ),
            result.stdout,
        )

    def test_unmerged_protocol_rejects_a_merged_path(self) -> None:
        result = subprocess.run(
            [
                *JIFF_COMMAND,
                "--git-external-diff",
                "--no-color",
                "ordinary.txt",
            ],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("Git has no unmerged entries for ordinary.txt", result.stderr)

    def test_external_diff_mode_keeps_colours_when_git_owns_the_pager(self) -> None:
        self.write("old.txt", "Kermit\n")
        self.write("new.txt", "Fozzie\n")

        result = subprocess.run(
            [
                *JIFF_COMMAND,
                "--git-external-diff",
                "muppet.txt",
                str(self.repository / "old.txt"),
                "old-object",
                "100644",
                str(self.repository / "new.txt"),
                "new-object",
                "100644",
            ],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("\x1b[", result.stdout)

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

    def test_directory_diff_combines_all_changed_files(self) -> None:
        # Git launches directory mode once. Jiff must keep each path attached
        # to the right content, including empty and binary files.
        self.write("animal.dat", bytes([0, 1, 2, 3]))
        self.write("kermit.txt", "Green\n")
        self.write("statler.txt", "Boo!\n")
        self.commit("Prepare the theatre")
        self.write("animal.dat", bytes([0, 1, 2, 4]))
        self.write("kermit.txt", "Still green\n")
        (self.repository / "statler.txt").unlink()
        self.write("nested/muppet cast.txt", "Kermit\nFozzie\n")
        self.write("empty.txt", "")
        self.git("add", "--all")

        result = self.difftool("--dir-diff", "--cached")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            "Binary files a/animal.dat and b/animal.dat differ\n", result.stdout
        )
        self.assertNotIn("--- a/empty.txt", result.stdout)
        for path in (
            "empty.txt",
            "kermit.txt",
            "nested/muppet cast.txt",
            "statler.txt",
        ):
            self.assert_side_by_side_header(result.stdout, path)
        self.assertIn("┬", result.stdout)
        self.assertIn("┼", result.stdout)
        self.assertIn("Still green", result.stdout)
        self.assertIn("Fozzie", result.stdout)
        self.assertIn("Boo!", result.stdout)

    def test_file_and_directory_inputs_fail_cleanly(self) -> None:
        self.write("kermit.txt", "Green\n")

        result = subprocess.run(
            [
                *JIFF_COMMAND,
                "--no-pager",
                str(self.repository),
                str(self.repository / "kermit.txt"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("both inputs must be files or both directories", result.stderr)

    def test_early_pipe_closure_is_successful(self) -> None:
        # Read one line, then close the pipe. Make the output larger than the
        # pipe buffer so Jiff definitely notices.
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
