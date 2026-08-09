import unittest

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


if __name__ == "__main__":
    unittest.main()
