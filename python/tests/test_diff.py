import os
import unittest
from dataclasses import replace
from unittest import mock

from diff.align import _edit_distance, align
from diff.mod import Diff, DiffType
from jiff_config import ColorScheme, ColorStyle
from rich.text import Text

import diff


class SideBySideRenderingTests(unittest.TestCase):
    def test_explicit_terminal_width_skips_terminal_detection(self):
        # A preview gets its width from the widget, not the terminal which
        # launched it.
        diffs = diff.calculate_line_diff("Kermit", "Kermit the Frog")

        with mock.patch("diff.mod._terminal_width") as terminal_width:
            output = diff.render_diffs_side_by_side(diffs, 1, False, terminal_width=40)

        terminal_width.assert_not_called()
        self.assertIn("Kermit", output)

    def test_uneven_wrapped_lines_render_to_completion(self):
        # The shorter side still needs an empty styled line while the other
        # side wraps.
        left = "Kermit " * 100
        diffs = diff.calculate_line_diff(left, "")

        output = diff.render_diffs_side_by_side(diffs, 1, False)

        self.assertIn("Kermit", output)

    def test_line_number_gutters_continue_through_wrapped_lines(self):
        diffs = diff.calculate_line_diff("Kermit the Frog", "Kermit the Frog")

        output = diff.render_diffs_side_by_side(diffs, 1, False, terminal_width=20)
        lines = output.splitlines()

        self.assertTrue(lines[0].startswith("1│ "))
        self.assertTrue(lines[1].startswith(" │ "))
        self.assertIn("│1│ ", lines[0])
        self.assertIn("│ │ ", lines[1])

    def test_missing_right_line_keeps_its_gutter(self):
        output = diff.render_diffs_side_by_side(
            [Diff(DiffType.REMOVE, "Kermit")], 1, False, terminal_width=40
        )

        self.assertTrue(output.rstrip("\n").endswith("│"))

    def test_gutter_background_covers_the_line_number_padding(self):
        colors = replace(
            ColorScheme.default(),
            line_number=ColorStyle(color="bright_white", bgcolor="blue", bold=True),
        )

        output = diff.render_diffs_side_by_side(
            [Diff(DiffType.SAME, "Kermit")],
            10,
            True,
            colors,
            terminal_width=40,
        )
        rendered = Text.from_ansi(output)
        gutter = next(span for span in rendered.spans if span.start == 0)

        self.assertEqual(" 1│", rendered.plain[:3])
        self.assertEqual((0, 2), (gutter.start, gutter.end))
        self.assertEqual(4, gutter.style.bgcolor.number)
        self.assertTrue(gutter.style.bold)
        self.assertFalse(
            any(
                span.start <= 2 < span.end and span.style.bgcolor is not None
                for span in rendered.spans
            )
        )

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


class ColourRenderingTests(unittest.TestCase):
    def test_each_render_uses_its_explicit_colour_policy(self):
        changes = [Diff(DiffType.REMOVE, "Kermit")]

        coloured = diff.render_diffs(changes, True, ColorScheme.default())
        plain = diff.render_diffs(changes, False, ColorScheme.default())

        self.assertIn("\x1b[", coloured)
        self.assertNotIn("\x1b[", plain)


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

    def test_repeated_line_at_the_end_is_used_as_the_stable_anchor(self):
        # Using the final Kermit as the anchor keeps both preceding lines in
        # one insertion.
        diffs = diff.calculate_line_diff("Kermit", "Fozzie\nKermit\nKermit")

        self.assertEqual(
            [
                Diff(DiffType.ADD, "Fozzie\nKermit"),
                Diff(DiffType.SAME, "Kermit"),
            ],
            diffs,
        )


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

    def test_coalesces_a_noisy_phrase_between_stable_anchors(self):
        # Shared surrounding text shouldn't make scattered matching letters
        # look useful.
        before = "Sam keeps one dependable act ready in the wings."
        after = "Scooter keeps two unpredictable acts ready in the wings."

        diffs = diff.mod.calculate_char_diff(before, after)

        self.assertEqual(
            [
                Diff(DiffType.SAME, "S"),
                Diff(DiffType.REPLACE, "am", "cooter"),
                Diff(DiffType.SAME, " keeps "),
                Diff(DiffType.REPLACE, "one depend", "two unpredict"),
                Diff(DiffType.SAME, "able act"),
                Diff(DiffType.ADD, "s"),
                Diff(DiffType.SAME, " ready in the wings."),
            ],
            diffs,
        )


class LineAlignmentTests(unittest.TestCase):
    def test_edit_distance_stops_above_the_pairing_cutoff(self):
        # The aligner only needs to know that Animal is too far from Kermit.
        self.assertEqual(3, _edit_distance("Kermit", "Animal", 2))

    def test_pairs_lines_with_a_shared_prefix_and_unrelated_suffixes(self):
        # These lines clearly belong together because of the stable prefix. The
        # unrelated tail should still be one character replacement.
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

        self.assertIn("10│ Kermit", output)


if __name__ == "__main__":
    unittest.main()
