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
