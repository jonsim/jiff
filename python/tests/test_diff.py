import unittest

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
