import unittest

import jiff


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
