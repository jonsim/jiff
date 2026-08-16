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
        with self.assertRaisesRegex(ValueError, "expects two files"):
            jiff._parse_input_paths(["local.txt"], False, None)
        with self.assertRaisesRegex(ValueError, "expects two files"):
            jiff._parse_input_paths(
                ["local.txt", "base.txt", "remote.txt"], False, None
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

        with self.assertRaisesRegex(ValueError, "expects two files"):
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
