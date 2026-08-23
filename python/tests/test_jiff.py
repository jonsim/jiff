import argparse
import unittest
from unittest import mock

import jiff
from jiff_config import ColorScheme


class CommandLineValueTests(unittest.TestCase):
    def test_zero_context_is_valid(self):
        self.assertEqual(0, jiff._non_negative_int("0"))

    def test_negative_context_is_rejected(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "non-negative integer"):
            jiff._non_negative_int("-1")

    def test_non_numeric_context_is_rejected(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "non-negative integer"):
            jiff._non_negative_int("many")

    def test_ordinary_inputs_are_exactly_two_paths(self):
        self.assertEqual(
            jiff.ComparisonPaths("local.txt", "remote.txt", "muppet.txt"),
            jiff._parse_input_paths(["local.txt", "remote.txt"], False, "muppet.txt"),
        )
        with self.assertRaisesRegex(ValueError, "expects two or three files"):
            jiff._parse_input_paths(["local.txt"], False, None)
        with self.assertRaisesRegex(ValueError, "expects two or three files"):
            jiff._parse_input_paths(
                ["local.txt", "base.txt", "remote.txt", "fourth.txt"], False, None
            )

    def test_ordinary_inputs_accept_three_way_file_paths(self):
        self.assertEqual(
            jiff.ThreeWayPaths("local.txt", "base.txt", "remote.txt"),
            jiff._parse_input_paths(
                ["local.txt", "base.txt", "remote.txt"], False, None
            ),
        )

    def test_repository_headings_are_rejected_for_three_way_input(self):
        with self.assertRaisesRegex(ValueError, "--path cannot be used"):
            jiff._parse_input_paths(
                ["local.txt", "base.txt", "remote.txt"], False, "muppet.txt"
            )

    def test_git_external_diff_extracts_only_the_paths_jiff_uses(self):
        self.assertEqual(
            jiff.ComparisonPaths("/tmp/old", "/tmp/new", "muppet.txt"),
            jiff._parse_input_paths(
                [
                    "muppet.txt",
                    "/tmp/old",
                    "old-object",
                    "100644",
                    "/tmp/new",
                    "new-object",
                    "100644",
                ],
                True,
                None,
            ),
        )

    def test_git_external_diff_accepts_an_unmerged_path(self):
        self.assertEqual(
            jiff.UnmergedPath("muppet.txt"),
            jiff._parse_input_paths(["muppet.txt"], True, None),
        )

    def test_git_arguments_are_rejected_without_git_external_diff_mode(self):
        git_arguments = [
            "muppet.txt",
            "/tmp/old",
            "old-object",
            "100644",
            "/tmp/new",
            "new-object",
            "100644",
        ]

        with self.assertRaisesRegex(ValueError, "expects two or three files"):
            jiff._parse_input_paths(git_arguments, False, None)


class FileReadingTests(unittest.TestCase):
    def test_text_loses_one_terminal_newline(self):
        # The renderer owns line endings, but meaningful blank lines remain.
        with mock.patch("builtins.open", mock.mock_open(read_data=b"Kermit\n\n")):
            content = jiff.read_file("muppet.txt")

        self.assertEqual("Kermit\n", content)

    def test_nul_bytes_mark_a_file_as_binary(self):
        content = b"Kermit\0Fozzie"
        with mock.patch("builtins.open", mock.mock_open(read_data=content)):
            result = jiff.read_file("muppet.dat")

        self.assertEqual(content, result)

    def test_invalid_utf8_marks_a_file_as_binary(self):
        content = bytes([0x4B, 0xFF, 0x21])
        with mock.patch("builtins.open", mock.mock_open(read_data=content)):
            result = jiff.read_file("muppet.dat")

        self.assertEqual(content, result)


class GitIndexTests(unittest.TestCase):
    def test_unmerged_entries_are_collected_by_stage(self):
        output = (
            b"100644 base-object 1\tmuppet cast.txt\0"
            b"100644 local-object 2\tmuppet cast.txt\0"
            b"100644 remote-object 3\tmuppet cast.txt\0"
        )

        self.assertEqual(
            (
                jiff.GitIndexStage("100644", "base-object"),
                jiff.GitIndexStage("100644", "local-object"),
                jiff.GitIndexStage("100644", "remote-object"),
            ),
            jiff._parse_unmerged_stages(output, "muppet cast.txt"),
        )

    def test_unmerged_entries_may_omit_the_base(self):
        output = b"\0".join(
            [
                b"100644 local-object 2\tnew.txt",
                b"100644 remote-object 3\tnew.txt",
            ]
        )

        self.assertEqual(
            (
                None,
                jiff.GitIndexStage("100644", "local-object"),
                jiff.GitIndexStage("100644", "remote-object"),
            ),
            jiff._parse_unmerged_stages(output, "new.txt"),
        )

    def test_duplicate_unmerged_stage_is_rejected(self):
        output = b"\0".join(
            [
                b"100644 first-object 2\tkermit.txt",
                b"100644 second-object 2\tkermit.txt",
            ]
        )

        with self.assertRaisesRegex(jiff.GitError, "stage 2 more than once"):
            jiff._parse_unmerged_stages(output, "kermit.txt")

    def test_unmerged_inputs_are_reordered_for_the_three_panes(self):
        entries = (
            b"100644 base-object 1\tmuppet.txt\0"
            b"100644 local-object 2\tmuppet.txt\0"
            b"100644 remote-object 3\tmuppet.txt\0"
        )
        with mock.patch(
            "jiff._run_git",
            side_effect=[entries, b"Local\n", b"Base\n", b"Remote\n"],
        ):
            contents = jiff._read_unmerged_inputs("muppet.txt")

        self.assertEqual(("Local", "Base", "Remote"), contents)

    def test_gitlink_stage_is_rendered_as_a_subproject_commit(self):
        stage = jiff.GitIndexStage("160000", "deadbeef")

        self.assertEqual(
            "Subproject commit deadbeef",
            jiff._read_git_stage(stage, "muppets"),
        )


class OutputTests(unittest.TestCase):
    def test_repository_path_adds_git_style_headings(self):
        output = jiff.render_output(
            "Kermit",
            "Fozzie",
            "/tmp/local",
            "/tmp/remote",
            "muppet cast.txt",
            True,
            False,
            ColorScheme.plain(),
        )

        self.assertTrue(
            output.startswith("--- a/muppet cast.txt\n+++ b/muppet cast.txt\n")
        )

    def test_differing_binary_files_are_reported_without_decoding_them(self):
        output = jiff.render_output(
            bytes([0, 1]),
            bytes([0, 2]),
            "/tmp/local",
            "/tmp/remote",
            "animal.dat",
            False,
            False,
            ColorScheme.plain(),
        )

        self.assertEqual("Binary files a/animal.dat and b/animal.dat differ\n", output)

    def test_identical_binary_files_are_reported(self):
        output = jiff.render_output(
            bytes([0, 1]),
            bytes([0, 1]),
            "/tmp/kermit.dat",
            "/tmp/kermit-copy.dat",
            None,
            False,
            False,
            ColorScheme.plain(),
        )

        self.assertEqual(
            "Binary files /tmp/kermit.dat and /tmp/kermit-copy.dat are identical\n",
            output,
        )

    def test_three_way_output_labels_both_comparisons(self):
        output = jiff.render_three_way_output(
            "Local choice",
            "Common base",
            "Remote choice",
            "local.txt",
            "base.txt",
            "remote.txt",
            True,
            False,
            ColorScheme.plain(),
        )

        self.assertEqual(
            "=== 1: local.txt vs 2: base.txt ===\n"
            "- Local choice\n"
            "+ Common base\n"
            "\n"
            "=== 2: base.txt vs 3: remote.txt ===\n"
            "- Common base\n"
            "+ Remote choice\n",
            output,
        )

    def test_three_way_side_by_side_output_draws_three_panes(self):
        output = jiff.render_three_way_output(
            "same\nLocal choice",
            "same\nCommon base",
            "same\nRemote choice",
            "/tmp/local.txt",
            "/tmp/base.txt",
            "/tmp/remote.txt",
            False,
            False,
            ColorScheme.plain(),
            terminal_width=120,
        )

        self.assertIn("1: local.txt", output)
        self.assertIn("2: base.txt", output)
        self.assertIn("3: remote.txt", output)
        self.assertTrue(all(line.count("│") == 2 for line in output.splitlines()))

    def test_three_way_output_accepts_explicit_pane_labels(self):
        output = jiff.render_three_way_output(
            "Local choice",
            "Common base",
            "Remote choice",
            "muppet.txt",
            "muppet.txt",
            "muppet.txt",
            True,
            False,
            ColorScheme.plain(),
            labels=("Local", "Base", "Remote"),
        )

        self.assertIn("=== 1: Local vs 2: Base ===\n", output)
        self.assertIn("=== 2: Base vs 3: Remote ===\n", output)

    def test_three_way_palettes_disable_diff_styles_for_the_middle_file(self):
        colors = ColorScheme.default()

        self.assertEqual(ColorScheme.plain().add, colors.without_additions().add)
        self.assertEqual(
            ColorScheme.plain().add_highlight,
            colors.without_additions().add_highlight,
        )
        self.assertEqual(ColorScheme.plain().remove, colors.without_removals().remove)
        self.assertEqual(
            ColorScheme.plain().remove_highlight,
            colors.without_removals().remove_highlight,
        )


class PagerDecisionTests(unittest.TestCase):
    def test_output_that_fits_exactly_does_not_page(self):
        # An exact fit is still visible without taking over the terminal.
        output = "Kermit\nFozzie\n"

        self.assertFalse(jiff._should_page(output, False, True, (80, 2)))

    def test_output_taller_than_the_terminal_pages(self):
        output = "Kermit\nFozzie\nGonzo\n"

        self.assertTrue(jiff._should_page(output, False, True, (80, 2)))

    def test_wrapped_lines_count_towards_terminal_height(self):
        output = "Kermit the Frog\n"

        self.assertTrue(jiff._should_page(output, False, True, (6, 2)))

    def test_ansi_colours_do_not_make_lines_look_wider(self):
        output = "\x1b[31mKermit\x1b[0m\n"

        self.assertFalse(jiff._should_page(output, False, True, (6, 1)))

    def test_no_pager_overrides_a_tall_output(self):
        output = "Kermit\nFozzie\nGonzo\n"

        self.assertFalse(jiff._should_page(output, True, True, (80, 2)))

    def test_redirected_output_never_pages(self):
        output = "Kermit\nFozzie\nGonzo\n"

        self.assertFalse(jiff._should_page(output, False, False, (80, 2)))


if __name__ == "__main__":
    unittest.main()
