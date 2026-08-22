import unittest
from dataclasses import replace

from diff.three_way import (
    IndexedLine,
    OmittedLines,
    ThreeWayLine,
    _limit_context,
    _line_width,
    _merge_middle_spans,
    _style_three_way_line,
    _three_way_lines,
    render_three_way_side_by_side,
)
from jiff_config import ColorScheme, ColorStyle
from rich.style import Style
from rich.text import Span
from syntax_highlighting import HighlightedFile


class ThreeWayAlignmentTests(unittest.TestCase):
    def test_middle_file_anchors_both_outer_alignments(self):
        lines = _three_way_lines(
            "start\nLOCAL ONLY\nanchor",
            "start\nanchor",
            "start\nREMOTE ONLY\nanchor",
        )

        self.assertEqual(3, len(lines))
        self.assertTrue(lines[0].is_unchanged())
        self.assertEqual("LOCAL ONLY", lines[1].left.text)
        self.assertIsNone(lines[1].middle)
        self.assertEqual("REMOTE ONLY", lines[1].right.text)
        self.assertTrue(lines[2].is_unchanged())

    def test_context_is_measured_from_changes_on_either_side(self):
        lines = _three_way_lines(
            "zero\nvalue = 11\ntwo\nthree\nfour",
            "zero\nvalue = 10\ntwo\nthree\nfour",
            "zero\nvalue = 10\ntwo\nthree\nfour",
        )

        rows = _limit_context(lines, 1)

        self.assertEqual(4, len(rows))
        self.assertEqual(OmittedLines(2), rows[3])


class ThreeWayStylingTests(unittest.TestCase):
    highlighting = (HighlightedFile(), HighlightedFile(), HighlightedFile())

    def test_partially_overlapping_middle_spans_are_split(self):
        add = Style(color="black", bgcolor="green")
        remove = Style(color="black", bgcolor="red")
        overlap = Style(color="black", bgcolor="yellow")

        merged = _merge_middle_spans([Span(1, 5, add)], [Span(3, 7, remove)], overlap)

        self.assertEqual(
            [Span(1, 3, add), Span(3, 5, overlap), Span(5, 7, remove)],
            merged,
        )

    def test_middle_uses_configured_style_when_both_sides_change_text(self):
        colors = replace(
            ColorScheme.default(),
            overlap_highlight=ColorStyle(color="white", bgcolor="blue"),
        )
        line = ThreeWayLine(
            IndexedLine(0, "AAAAA"),
            IndexedLine(0, "MMMMM"),
            IndexedLine(0, "ZZZZZ"),
        )

        _, middle, _ = _style_three_way_line(line, colors, self.highlighting)

        self.assertIn(Span(0, 5, colors.overlap_highlight.rich_style()), middle.spans)

    def test_middle_marks_text_deleted_by_the_local_file(self):
        colors = ColorScheme.default()
        line = ThreeWayLine(
            IndexedLine(0, "hello world"),
            IndexedLine(0, "hello cruel world"),
            IndexedLine(0, "hello cruel world"),
        )

        _, middle, _ = _style_three_way_line(line, colors, self.highlighting)

        self.assertIn(Span(6, 12, colors.add_highlight.rich_style()), middle.spans)

    def test_middle_marks_text_deleted_by_the_remote_file(self):
        colors = ColorScheme.default()
        line = ThreeWayLine(
            IndexedLine(0, "hello cruel world"),
            IndexedLine(0, "hello cruel world"),
            IndexedLine(0, "hello world"),
        )

        _, middle, _ = _style_three_way_line(line, colors, self.highlighting)

        self.assertIn(Span(6, 12, colors.remove_highlight.rich_style()), middle.spans)


class ThreeWayRenderingTests(unittest.TestCase):
    def test_renderer_draws_three_panes_without_trailing_whitespace(self):
        output = render_three_way_side_by_side(
            ("same\nlocal", "same\nbase", "same\nremote"),
            ("local.txt", "base.txt", "remote.txt"),
            color=False,
            terminal_width=120,
        )

        self.assertIn("1: local.txt", output)
        self.assertIn("2: base.txt", output)
        self.assertIn("3: remote.txt", output)
        self.assertTrue(all(line.count("│") == 2 for line in output.splitlines()))
        self.assertTrue(all(not line.endswith(" ") for line in output.splitlines()))
        self.assertNotIn("\x1b[", output)

    def test_width_accounts_for_two_separators_and_three_margins(self):
        self.assertEqual(36, _line_width(120, 1))


if __name__ == "__main__":
    unittest.main()
