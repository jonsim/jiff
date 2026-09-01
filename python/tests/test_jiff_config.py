import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jiff_config


class ColorConfigTests(unittest.TestCase):
    def test_complete_config_round_trips(self):
        # Generated files must retain every style understood by both renderers.
        config = jiff_config.ColorConfig.default()

        contents = jiff_config.color_config_to_toml(config)

        self.assertEqual(config, jiff_config.parse_color_config(contents))
        self.assertIn("[color.ansi16]", contents)
        self.assertIn("[color.ansi256]", contents)
        self.assertEqual(2 * len(jiff_config.STYLE_NAMES), contents.count(" = {"))

    def test_invalid_toml_is_reported_by_the_public_parser(self):
        with self.assertRaisesRegex(jiff_config.ConfigError, "invalid TOML"):
            jiff_config.parse_color_config("[color")

    def test_depth_defaults_to_16(self):
        config = jiff_config.parse_color_config("[color]\n")

        self.assertEqual(16, config.depth)

    def test_depth_accepts_256(self):
        config = jiff_config.parse_color_config("[color]\ndepth = 256\n")

        self.assertEqual(256, config.depth)

    def test_invalid_depth_is_rejected(self):
        for value in (0, 24, 257, '"256"', "true"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(jiff_config.ConfigError, "depth.*16 or 256"),
            ):
                jiff_config.parse_color_config(f"[color]\ndepth = {value}\n")

    def test_partial_ansi16_styles_merge_with_the_defaults(self):
        config = jiff_config._parse_color_config(
            {"color": {"ansi16": {"add": {"color": "blue", "bold": True}}}}
        )

        self.assertEqual("blue", config.ansi16.add.color)
        self.assertTrue(config.ansi16.add.bold)
        self.assertEqual("red", config.ansi16.remove.color)

    def test_ansi256_inherits_the_resolved_ansi16_palette(self):
        config = jiff_config._parse_color_config(
            {
                "color": {
                    "ansi16": {"add": {"color": "bright_green", "bold": True}},
                    "ansi256": {"add": {"color": 114}},
                }
            }
        )

        self.assertEqual(114, config.ansi256.add.color)
        self.assertTrue(config.ansi256.add.bold)
        self.assertEqual(1, config.ansi256.remove.color)

    def test_default_clears_an_inherited_colour(self):
        config = jiff_config._parse_color_config(
            {"color": {"ansi256": {"add": {"color": "default"}}}}
        )

        self.assertIsNone(config.ansi256.add.color)

    def test_all_ansi16_colours_are_configurable(self):
        for colour in jiff_config.CANONICAL_COLORS:
            with self.subTest(colour=colour):
                config = jiff_config._parse_color_config(
                    {"color": {"ansi16": {"add": {"color": colour}}}}
                )

                expected = None if colour == "default" else colour
                self.assertEqual(expected, config.ansi16.add.color)

    def test_ansi256_accepts_every_index(self):
        for index in range(256):
            config = jiff_config._parse_color_config(
                {"color": {"ansi256": {"add": {"color": index}}}}
            )
            self.assertEqual(index, config.ansi256.add.color)

    def test_invalid_ansi256_values_are_rejected(self):
        for value in (-1, 256, "green", True):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(jiff_config.ConfigError, "0 to 255"),
            ):
                jiff_config._parse_color_config(
                    {"color": {"ansi256": {"add": {"color": value}}}}
                )

    def test_indexed_colour_builds_a_rich_style(self):
        style = jiff_config.ColorStyle(color=114, bgcolor=52).rich_style()

        self.assertEqual(114, style.color.number)
        self.assertEqual(52, style.bgcolor.number)

    def test_old_palette_layout_is_rejected(self):
        with self.assertRaisesRegex(
            jiff_config.ConfigError, "unknown option color.add"
        ):
            jiff_config.parse_color_config('[color]\nadd = { color = "green" }\n')

    def test_syntax_colours_cannot_have_backgrounds(self):
        with self.assertRaisesRegex(
            jiff_config.ConfigError, "color.ansi256.syntax_keyword.bgcolor"
        ):
            jiff_config._parse_color_config(
                {"color": {"ansi256": {"syntax_keyword": {"bgcolor": 52}}}}
            )

    @mock.patch("jiff_config.Console")
    def test_true_colour_terminal_can_use_ansi256(self, console):
        console.return_value.color_system = "truecolor"

        self.assertTrue(jiff_config.terminal_supports_ansi256())

    @mock.patch("jiff_config.Console")
    def test_standard_terminal_uses_ansi16(self, console):
        console.return_value.color_system = "standard"

        self.assertFalse(jiff_config.terminal_supports_ansi256())


class ConfigPathTests(unittest.TestCase):
    def test_default_path_uses_an_absolute_xdg_home(self):
        path = jiff_config._default_config_path(
            {"XDG_CONFIG_HOME": "/the-muppet-theatre"}, Path("/home/kermit")
        )

        self.assertEqual(Path("/the-muppet-theatre/jiff/config.toml"), path)

    def test_default_path_ignores_a_relative_xdg_home(self):
        path = jiff_config._default_config_path(
            {"XDG_CONFIG_HOME": "backstage"}, Path("/home/kermit")
        )

        self.assertEqual(Path("/home/kermit/.config/jiff/config.toml"), path)

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
