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


if __name__ == "__main__":
    unittest.main()
