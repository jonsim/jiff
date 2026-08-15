import os
import unittest
from unittest import mock

from diff.align import align
from diff.mod import Diff, DiffType

import diff


class SideBySideRenderingTests(unittest.TestCase):
    def test_uneven_wrapped_lines_render_to_completion(self):
        # Once the shorter side is exhausted, wrapping still needs an empty
        # styled line with the same interface as the remaining chunks.
        left = "Kermit " * 100
        diffs = diff.calculate_line_diff(left, "")

        output = diff.render_diffs_side_by_side(diffs, 1, False)

        self.assertIn("Kermit", output)

    def test_terminal_width_falls_back_to_an_attached_standard_stream(self):
        # Git sends stdout to its pager, leaving another stream attached to the
        # terminal which launched it.
        terminal_size = os.terminal_size((173, 40))
        with (
            mock.patch.dict(os.environ, {"COLUMNS": ""}),
            mock.patch(
                "diff.mod.os.get_terminal_size",
                side_effect=[OSError, OSError, terminal_size],
            ),
        ):
            width = diff.mod._terminal_width()

        self.assertEqual(173, width)


class LineDiffTests(unittest.TestCase):
    def test_empty_left_file_is_a_pure_addition(self):
        # An absent Git side is represented by an empty file, not an empty line.
        diffs = diff.calculate_line_diff("", "Kermit")

        self.assertEqual(1, len(diffs))
        self.assertEqual("ADD", diffs[0].kind.name)
        self.assertEqual("Kermit", diffs[0].left)

    def test_empty_right_file_is_a_pure_removal(self):
        diffs = diff.calculate_line_diff("Kermit", "")

        self.assertEqual(1, len(diffs))
        self.assertEqual("REMOVE", diffs[0].kind.name)
        self.assertEqual("Kermit", diffs[0].left)


class CharacterDiffTests(unittest.TestCase):
    def test_coalesces_accidental_matches_in_an_unrelated_suffix(self):
        before = "version is more portable. Tests assert that the two versions are"
        after = "version is more portable. The core diff behaviour is identical"

        diffs = diff.mod.calculate_char_diff(before, after)

        self.assertEqual(
            [
                Diff(DiffType.SAME, "version is more portable. T"),
                Diff(
                    DiffType.REPLACE,
                    "ests assert that the two versions are",
                    "he core diff behaviour is identical",
                ),
            ],
            diffs,
        )

    def test_retains_dense_fragmented_matches(self):
        diffs = diff.mod.calculate_char_diff("aXaXaXa", "aYaYaYa")

        self.assertEqual(
            [
                Diff(DiffType.SAME, "a"),
                Diff(DiffType.REPLACE, "X", "Y"),
                Diff(DiffType.SAME, "a"),
                Diff(DiffType.REPLACE, "X", "Y"),
                Diff(DiffType.SAME, "a"),
                Diff(DiffType.REPLACE, "X", "Y"),
                Diff(DiffType.SAME, "a"),
            ],
            diffs,
        )


class LineAlignmentTests(unittest.TestCase):
    def test_pairs_lines_with_a_shared_prefix_and_unrelated_suffixes(self):
        # The stable prefix makes these the most useful side-by-side pairing,
        # even though the remaining text should be one character replacement.
        before = "version is more portable. Tests assert that the two versions are"
        after = "version is more portable. The core diff behaviour is identical"

        alignment = align([before], [after])

        self.assertEqual([(before, after)], alignment)

    def test_keeps_unrelated_lines_unpaired(self):
        alignment = align(["Kermit"], ["Gonzo"])

        self.assertEqual([("Kermit", None), (None, "Gonzo")], alignment)

    def test_keeps_scattered_sentence_matches_unpaired(self):
        # Common letters and spaces must not turn unrelated prose into a line pair.
        before = (
            "are configured under `[color]`; every style and field is optional, "
            "and omitted"
        )
        after = (
            "Each entry below `[color]` names a style. A style has up to three fields:"
        )

        alignment = align([before], [after])

        self.assertEqual([(before, None), (None, after)], alignment)


class ContextTests(unittest.TestCase):
    def test_context_keeps_lines_on_each_side_of_a_change(self):
        # Leading and trailing ranges keep the lines nearest the replacement.
        diffs = [
            Diff(DiffType.SAME, "one\ntwo\nthree\nfour"),
            Diff(DiffType.REPLACE, "Kermit", "Fozzie"),
            Diff(DiffType.SAME, "five\nsix\nseven\neight"),
        ]

        limited = diff.limit_context(diffs, 2)

        self.assertEqual(
            [
                Diff(DiffType.OMITTED, omitted_lines=2),
                Diff(DiffType.SAME, "three\nfour"),
                Diff(DiffType.REPLACE, "Kermit", "Fozzie"),
                Diff(DiffType.SAME, "five\nsix"),
                Diff(DiffType.OMITTED, omitted_lines=2),
            ],
            limited,
        )

    def test_context_joins_nearby_changes_without_an_omission(self):
        # Overlapping context belongs to one continuous hunk.
        diffs = [
            Diff(DiffType.REMOVE, "Kermit"),
            Diff(DiffType.SAME, "one\ntwo\nthree"),
            Diff(DiffType.ADD, "Fozzie"),
        ]

        limited = diff.limit_context(diffs, 2)

        self.assertEqual(diffs, limited)

    def test_zero_context_omits_every_unchanged_line(self):
        diffs = [
            Diff(DiffType.SAME, "one\ntwo"),
            Diff(DiffType.REPLACE, "Kermit", "Fozzie"),
            Diff(DiffType.SAME, "three\nfour"),
        ]

        limited = diff.limit_context(diffs, 0)

        self.assertEqual(
            [
                Diff(DiffType.OMITTED, omitted_lines=2),
                Diff(DiffType.REPLACE, "Kermit", "Fozzie"),
                Diff(DiffType.OMITTED, omitted_lines=2),
            ],
            limited,
        )

    def test_side_by_side_line_numbers_advance_over_omitted_lines(self):
        # The first visible line after a gap keeps its source line number.
        diffs = [
            Diff(DiffType.OMITTED, omitted_lines=9),
            Diff(DiffType.SAME, "Kermit"),
        ]

        output = diff.render_diffs_side_by_side(diffs, 10, False)

        self.assertIn("10: Kermit", output)


if __name__ == "__main__":
    unittest.main()
