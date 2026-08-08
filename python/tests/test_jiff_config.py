import tempfile
import unittest
from pathlib import Path

import jiff_config


class ColorConfigTests(unittest.TestCase):
    def test_partial_styles_merge_with_the_default_palette(self):
        scheme = jiff_config._parse_color_scheme(
            {"color": {"add": {"color": "blue", "bold": True}}}
        )

        self.assertEqual("blue", scheme.add.color)
        self.assertTrue(scheme.add.bold)
        self.assertEqual("red", scheme.remove.color)

    def test_default_clears_an_existing_colour(self):
        scheme = jiff_config._parse_color_scheme(
            {"color": {"add_highlight": {"bgcolor": "default"}}}
        )

        self.assertIsNone(scheme.add_highlight.bgcolor)
        self.assertEqual("black", scheme.add_highlight.color)

    def test_unsupported_colours_report_the_field(self):
        with self.assertRaisesRegex(jiff_config.ConfigError, "color.add.color.*orange"):
            jiff_config._parse_color_scheme({"color": {"add": {"color": "orange"}}})

    def test_unknown_options_are_rejected(self):
        with self.assertRaisesRegex(
            jiff_config.ConfigError, "unknown option color.kermit"
        ):
            jiff_config._parse_color_scheme({"color": {"kermit": {"color": "green"}}})


class ConfigPathTests(unittest.TestCase):
    def test_xdg_config_takes_precedence_over_the_home_dotfile(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            xdg_config = home / ".config" / "jiff" / "config.toml"
            xdg_config.parent.mkdir(parents=True)
            xdg_config.touch()
            (home / ".jiffconfig").touch()

            path = jiff_config._find_config_file({}, home)

        self.assertEqual(xdg_config, path)

    def test_explicit_config_does_not_need_to_exist_during_discovery(self):
        path = jiff_config._find_config_file(
            {"JIFF_CONFIG": "/the-great-gonzo.toml"}, Path("/unused")
        )

        self.assertEqual(Path("/the-great-gonzo.toml"), path)


if __name__ == "__main__":
    unittest.main()
