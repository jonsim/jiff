import unittest

import syntax_highlighting
from jiff_config import ColorScheme
from rich.console import Console
from rich.style import Style


class SyntaxDetectionTests(unittest.TestCase):
    def test_filename_selects_the_python_lexer(self):
        # A normal Python filename should be enough to pick the lexer.
        source = "def kermit():\n    return 3"

        highlighted = syntax_highlighting.highlight_file(
            source, "muppet_show.py", None, ColorScheme.default()
        )

        self.assertEqual("magenta", str(highlighted.lines[0].spans[0].style))

    def test_explicit_syntax_overrides_a_plain_filename(self):
        # Git and process-substitution paths often have no useful extension.
        highlighted = syntax_highlighting.highlight_file(
            "def kermit():", "temporary.txt", "python", ColorScheme.default()
        )

        self.assertEqual("magenta", str(highlighted.lines[0].spans[0].style))

    def test_unknown_detected_syntax_falls_back_to_plain_text(self):
        highlighted = syntax_highlighting.highlight_file(
            "Kermit and Fozzie",
            "muppets.unknown",
            None,
            ColorScheme.default(),
        )

        self.assertEqual(syntax_highlighting.HighlightedFile(), highlighted)

    def test_unknown_explicit_syntax_is_reported(self):
        with self.assertRaisesRegex(
            syntax_highlighting.UnknownSyntaxError, "great-gonzo"
        ):
            syntax_highlighting.highlight_file(
                "Kermit", "muppets.txt", "great-gonzo", ColorScheme.default()
            )

    def test_explicit_syntax_is_validated_without_highlighting(self):
        # `--no-color` must not make a misspelled explicit language valid.
        with self.assertRaisesRegex(
            syntax_highlighting.UnknownSyntaxError, "great-gonzo"
        ):
            syntax_highlighting.validate_syntax("great-gonzo")

    def test_repository_path_identifies_git_temporary_files(self):
        # Both Git sides should use the real path supplied through `--path`.
        highlighted = syntax_highlighting.highlight_files(
            "def kermit(): pass",
            "def fozzie(): pass",
            "/tmp/old",
            "/tmp/new",
            "muppets.py",
            None,
            ColorScheme.default(),
        )

        self.assertTrue(highlighted.left.lines[0].spans)
        self.assertTrue(highlighted.right.lines[0].spans)


class SyntaxRenderingTests(unittest.TestCase):
    def test_tabs_expand_relative_to_the_source_line(self):
        # Margins differ between output modes, but source tab stops must not.
        rendered = syntax_highlighting.HighlightedFile().render_line(0, "a\tb", Style())

        self.assertEqual("a   b", rendered.plain)

    def test_syntax_foreground_keeps_the_diff_background(self):
        # Diff background matters more than token colour.
        highlighted = syntax_highlighting.highlight_file(
            "def kermit():", "muppets.py", None, ColorScheme.default()
        )

        rendered = highlighted.render_line(
            0, "def kermit():", Style(color="green", bgcolor="red")
        )
        style = rendered.get_style_at_offset(Console(color_system="standard"), 0)

        self.assertEqual("magenta", style.color.name)
        self.assertEqual("red", style.bgcolor.name)

    def test_multiline_lexer_state_is_kept(self):
        # The second line stays a string because we highlight the whole file at
        # once.
        highlighted = syntax_highlighting.highlight_file(
            '"""Kermit\nthe Frog"""',
            "muppets.py",
            None,
            ColorScheme.default(),
        )

        second_line = highlighted.lines[1]

        self.assertEqual("cyan", str(second_line.spans[0].style))


if __name__ == "__main__":
    unittest.main()
