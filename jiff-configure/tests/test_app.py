import tempfile
import unittest
from importlib.resources import files
from pathlib import Path
from unittest import mock

import syntax_highlighting
from diff.mod import DiffType
from jiff_config import (
    CANONICAL_COLORS,
    STYLE_NAMES,
    ColorConfig,
    ColorDepth,
    ColorScheme,
    parse_color_config,
)
from jiff_configure.app import (
    ANSI256_GRID,
    COLOR_OPTIONS,
    THREE_WAY_BASE,
    THREE_WAY_LOCAL,
    THREE_WAY_REMOTE,
    ColorSwatch,
    ConfirmDialog,
    IndexedColorPicker,
    JiffConfigureApp,
    PreviewSource,
    SavePathDialog,
    TrueColorPicker,
    load_preview_source,
    load_starting_themes,
    load_themes,
)
from textual.widgets import Button, Input, Label, Select, Static, Switch, TabbedContent

import diff


class PreviewSourceTests(unittest.TestCase):
    def test_no_paths_uses_the_built_in_python_diff(self):
        source = load_preview_source([])

        self.assertEqual("before.py", source.left_path)
        self.assertEqual("after.py", source.right_path)
        self.assertEqual(4, source.context_lines)

    def test_built_in_diff_exercises_every_diff_and_syntax_style(self):
        # Every control should have a visible example on both sides of a change.
        source = PreviewSource.built_in()
        changes = diff.limit_context(
            diff.calculate_line_diff(source.left, source.right),
            source.context_lines,
        )
        highlighting = syntax_highlighting.highlight_files(
            source.left,
            source.right,
            source.left_path,
            source.right_path,
            None,
            None,
            ColorScheme.default(),
        )

        self.assertEqual(set(DiffType), {change.kind for change in changes})

        common_lines = set(source.left.splitlines()) & set(source.right.splitlines())
        unchanged_syntax = set()
        changed_syntax = set()
        for content, highlighted in (
            (source.left, highlighting.left),
            (source.right, highlighting.right),
        ):
            for index, line in enumerate(content.splitlines()):
                line_highlighting = highlighted.lines[index]
                colors = {
                    span.style.color.name
                    for span in line_highlighting.spans
                    if span.style.color is not None
                }
                if line in common_lines:
                    unchanged_syntax.update(colors)
                else:
                    changed_syntax.update(colors)

        expected_syntax = {"bright_black", "magenta", "cyan", "blue", "yellow"}
        self.assertEqual(expected_syntax, unchanged_syntax)
        self.assertEqual(expected_syntax, changed_syntax)

    def test_three_way_example_lines_fit_its_narrow_panes(self):
        for content in (THREE_WAY_LOCAL, THREE_WAY_BASE, THREE_WAY_REMOTE):
            with self.subTest(content=content):
                self.assertLessEqual(
                    max(map(len, content.splitlines()), default=0),
                    25,
                )

    def test_two_paths_load_their_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "kermit.py"
            after = root / "gonzo.py"
            before.write_text("print('Kermit')\n", encoding="utf-8")
            after.write_text("print('Gonzo')\n", encoding="utf-8")

            source = load_preview_source([str(before), str(after)])

        self.assertEqual("print('Kermit')", source.left)
        self.assertEqual("print('Gonzo')", source.right)
        self.assertIsNone(source.context_lines)

    def test_one_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no files or OLD NEW"):
            load_preview_source(["lonely-kermit.py"])

    def test_binary_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "animal.dat"
            other = Path(directory) / "gonzo.txt"
            binary.write_bytes(b"Animal\0drums")
            other.write_text("Gonzo", encoding="utf-8")

            with self.assertRaisesRegex(TypeError, "not a UTF-8 text file"):
                load_preview_source([str(binary), str(other)])

    def test_unreadable_path_is_reported(self):
        with self.assertRaises(FileNotFoundError):
            load_preview_source(["statler.txt", "waldorf.txt"])


class ThemeTests(unittest.TestCase):
    def test_colour_controls_offer_every_canonical_ansi_colour(self):
        # Aliases would duplicate choices without adding a distinct colour.
        self.assertEqual(
            list(CANONICAL_COLORS),
            [value for _label, value in COLOR_OPTIONS],
        )

    def test_packaged_themes_include_default_and_all_examples(self):
        themes = load_themes()

        self.assertEqual(ColorConfig.default(), themes["Default"])
        self.assertEqual(
            {
                "Default",
                "1337",
                "Catppuccin Frappe",
                "Catppuccin Latte",
                "Catppuccin Macchiato",
                "Catppuccin Mocha",
                "Coldark-Cold",
                "Coldark-Dark",
                "DarkNeon",
                "Dracula",
                "GitHub",
                "Gruvbox Dark",
                "Gruvbox Light",
                "High Contrast Dark",
                "High Contrast Light",
                "Monokai Extended",
                "Monokai Extended Bright",
                "Monokai Extended Light",
                "Monokai Extended Origin",
                "Nord",
                "OneHalfDark",
                "OneHalfLight",
                "Solarized (dark)",
                "Solarized (light)",
                "Sublime Snazzy",
                "Tokyo Night",
                "Twilight Dark",
                "TwoDark",
                "Chalkboard",
                "Zenburn",
            },
            set(themes),
        )

    def test_standard_config_is_added_as_the_starting_theme(self):
        # A saved config should appear first rather than masquerading as Default.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                '[color.ansi16]\nadd = { color = "blue" }\n',
                encoding="utf-8",
            )
            with mock.patch(
                "jiff_configure.app.find_color_config_path",
                return_value=path,
            ):
                themes, selected_theme = load_starting_themes()

        self.assertEqual("Current configuration", selected_theme)
        self.assertEqual("Current configuration", next(iter(themes)))
        self.assertEqual("blue", themes[selected_theme].ansi16.add.color)

    @mock.patch("jiff_configure.app.find_color_config_path", return_value=None)
    def test_default_theme_is_used_without_a_standard_config(self, _find_config):
        # Avoid a duplicate Current configuration entry when Jiff has no config.
        themes, selected_theme = load_starting_themes()

        self.assertEqual("Default", selected_theme)
        self.assertNotIn("Current configuration", themes)

    def test_bat_themes_keep_their_distinct_syntax_colours(self):
        # These were loaded from bat rather than approximated from the theme names.
        themes = load_themes()

        catppuccin = themes["Catppuccin Mocha"].truecolor
        self.assertEqual("#cba6f7", catppuccin.syntax_keyword.color)
        self.assertEqual("#a6e3a1", catppuccin.syntax_string.color)
        self.assertTrue(catppuccin.syntax_comment.italic)

        dracula = themes["Dracula"].truecolor
        self.assertEqual("#8be9fd", dracula.syntax_keyword.color)
        self.assertEqual("#f1fa8c", dracula.syntax_string.color)
        self.assertTrue(dracula.syntax_keyword.italic)

        gruvbox = themes["Gruvbox Dark"].truecolor
        self.assertEqual("#8ec07c", gruvbox.syntax_keyword.color)
        self.assertEqual("#d3869b", gruvbox.syntax_number.color)

        nord = themes["Nord"].truecolor
        self.assertEqual("#81a1c1", nord.syntax_keyword.color)
        self.assertEqual("#a3be8c", nord.syntax_string.color)

    def test_twilight_dark_uses_the_tilix_palette(self):
        twilight = load_themes()["Twilight Dark"]

        self.assertEqual(ColorDepth.TRUECOLOR, twilight.depth)
        self.assertEqual("green", twilight.ansi16.add.color)
        self.assertEqual("white", twilight.ansi16.line_number.color)
        self.assertTrue(twilight.ansi16.line_number.bold)
        self.assertEqual("red", twilight.ansi16.remove.color)
        self.assertEqual(248, twilight.ansi256.same.color)
        self.assertEqual(248, twilight.ansi256.line_number.color)
        self.assertEqual(59, twilight.ansi256.omitted.color)
        self.assertEqual(107, twilight.ansi256.add.color)
        self.assertEqual(167, twilight.ansi256.remove.color)
        self.assertEqual(228, twilight.ansi256.overlap_highlight.bgcolor)
        self.assertEqual(139, twilight.ansi256.syntax_keyword.color)

    def test_every_packaged_theme_contains_all_complete_palettes(self):
        resources = files("jiff_configure.themes")
        for resource in resources.iterdir():
            if not resource.name.endswith(".toml"):
                continue
            with self.subTest(theme=resource.name):
                contents = resource.read_text(encoding="utf-8")
                config = parse_color_config(contents)

                self.assertEqual(ColorDepth.TRUECOLOR, config.depth)
                self.assertIn("[color.ansi16]", contents)
                self.assertIn("[color.ansi256]", contents)
                self.assertIn("[color.truecolor]", contents)
                self.assertEqual(3 * len(STYLE_NAMES), contents.count("bold ="))
                self.assertEqual(3 * len(STYLE_NAMES), contents.count("italic ="))
                for name in STYLE_NAMES:
                    style_count = sum(
                        line.startswith(f"{name} =") for line in contents.splitlines()
                    )
                    self.assertEqual(3, style_count, name)


class ConfigureAppTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self) -> JiffConfigureApp:
        return JiffConfigureApp(PreviewSource.built_in(), load_themes())

    async def test_preview_uses_the_terminal_ansi_palette(self):
        # Textual's normal RGB conversion would make this differ from Jiff.
        app = self.make_app()
        async with app.run_test(size=(140, 42)):
            preview = app.query_one("#side-preview")

            self.assertTrue(app.native_ansi_color)
            self.assertEqual(-1, preview.styles.color.ansi)
            self.assertEqual(-1, preview.styles.background.ansi)

    async def test_three_way_tab_uses_the_three_pane_renderer(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            preview = app.query_one("#three-way-preview")
            content = str(preview.content)
            tabs = app.query_one("#preview-tabs", TabbedContent)

            self.assertEqual("Three-way", tabs.get_tab("three-way").label_text)
            self.assertIn("1: local.py", content)
            self.assertIn("2: base.py", content)
            self.assertIn("3: remote.py", content)
            self.assertIn('CAST = ["K"]', content)
            self.assertIn('CAST = ["K", "Fozzie"]', content)

    async def test_selecting_a_theme_updates_the_scheme_and_previews(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#theme", Select).value = "Dracula"
            await pilot.pause()

            self.assertEqual(app.themes["Dracula"], app.config)
            self.assertTrue(app.dirty)
            self.assertIn(
                'syntax_keyword = { color = "#8be9fd"',
                str(app.query_one("#toml-preview").content),
            )

    async def test_loaded_config_can_switch_to_a_packaged_theme(self):
        # The loaded config behaves like any other starting point in the picker.
        loaded = parse_color_config('[color.ansi16]\nadd = { color = "blue" }\n')
        themes = {"Current configuration": loaded, **load_themes()}
        app = JiffConfigureApp(
            PreviewSource.built_in(),
            themes,
            selected_theme="Current configuration",
        )
        async with app.run_test(size=(140, 42)) as pilot:
            theme = app.query_one("#theme", Select)

            self.assertEqual("Current configuration", theme.value)
            self.assertEqual("blue", app.config.ansi16.add.color)

            theme.value = "Dracula"
            await pilot.pause()

            self.assertEqual("Dracula", app.selected_theme)
            self.assertEqual(app.themes["Dracula"], app.config)

    async def test_editing_a_colour_updates_the_live_toml(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            add_colour = app.query_one("#add-color", Select)
            add_colour.value = "blue"
            await pilot.pause()

            self.assertEqual("blue", app.scheme.add.color)
            self.assertTrue(app.dirty)
            self.assertIn(
                'add = { color = "blue"',
                str(app.query_one("#toml-preview").content),
            )

    async def test_changed_gutter_background_excludes_the_live_divider(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#depth", Select).value = 16
            await pilot.pause()
            app.query_one("#line_number_remove-bgcolor", Select).value = "blue"
            await pilot.pause()

            preview = app.query_one("#side-preview", Static).content
            gutter = next(span for span in preview.spans if span.start == 0)

            self.assertTrue(preview.plain.startswith(" 1│"))
            self.assertEqual(2, gutter.end)
            self.assertEqual(4, gutter.style.bgcolor.number)
            self.assertFalse(
                any(
                    span.start <= 2 < span.end and span.style.bgcolor is not None
                    for span in preview.spans
                )
            )
            self.assertIn(
                'line_number_remove = { color = "default", bgcolor = "blue"',
                str(app.query_one("#toml-preview").content),
            )

    async def test_added_line_number_style_updates_the_preview(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#depth", Select).value = 16
            await pilot.pause()
            app.query_one("#line_number_add-bgcolor", Select).value = "green"
            await pilot.pause()

            preview = app.query_one("#side-preview", Static).content

            self.assertTrue(
                any(
                    span.style.bgcolor is not None and span.style.bgcolor.number == 2
                    for span in preview.spans
                )
            )
            self.assertIn(
                'line_number_add = { color = "default", bgcolor = "green"',
                str(app.query_one("#toml-preview").content),
            )

    async def test_depth_and_palette_selectors_are_independent(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#depth", Select).value = 256
            app.query_one("#palette", Select).value = "ansi256"
            await pilot.pause()

            self.assertEqual(256, app.config.depth)
            self.assertEqual("ansi256", app.edit_palette)
            self.assertIsInstance(app.query_one("#add-color"), Button)

    async def test_control_buttons_are_one_line_high(self):
        # Repeating a three-line colour button for every style wastes most of the panel.
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#palette", Select).value = "ansi256"
            await pilot.pause()

            colour = app.query_one("#add-color", Button)
            save = app.query_one("#save-config", Button)
            self.assertEqual(1, colour.size.height)
            self.assertEqual(1, colour.parent.size.height)
            self.assertEqual(1, save.size.height)
            self.assertEqual(1, save.parent.size.height)

    async def test_indexed_picker_supports_keyboard_and_mouse_selection(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#palette", Select).value = "ansi256"
            await pilot.pause()
            add_colour = app.query_one("#add-color", Button)
            add_colour.press()
            await pilot.pause()

            self.assertIsInstance(app.screen, IndexedColorPicker)
            self.assertEqual(256, len(app.screen.query(ColorSwatch)))
            self.assertEqual(32, len(app.screen.query(".indexed-empty")))
            self.assertEqual(1, len(app.screen.query(Button)))
            self.assertEqual("indexed-2", app.screen.focused.id)
            await pilot.press("right")
            self.assertEqual("indexed-10", app.screen.focused.id)
            self.assertIn(
                "ANSI256 colour 10",
                str(app.screen.query_one("#indexed-readout", Label).content),
            )
            await pilot.click("#indexed-114")
            await pilot.pause()

            self.assertEqual(114, app.config.ansi256.add.color)
            self.assertEqual("114", str(app.query_one("#add-color", Button).label))

    async def test_truecolor_picker_validates_and_applies_rgb(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#palette", Select).value = "truecolor"
            await pilot.pause()
            app.query_one("#add-color", Button).press()
            await pilot.pause()

            self.assertIsInstance(app.screen, TrueColorPicker)
            rgb = app.screen.query_one("#rgb-value", Input)
            rgb.value = "Gonzo"
            await pilot.click("#rgb-accept")
            self.assertIn(
                "#RRGGBB",
                str(app.screen.query_one("#rgb-error", Label).content),
            )

            rgb.value = "#12Ab34"
            await pilot.pause()
            await pilot.click("#rgb-accept")
            await pilot.pause()

            self.assertEqual("#12ab34", app.config.truecolor.add.color)
            self.assertEqual("#12ab34", str(app.query_one("#add-color", Button).label))

    async def test_editing_from_another_tab_keeps_the_preview_width(self):
        # Hidden tabs have no width, but edits still refresh every preview.
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            previews = (
                app.query_one("#side-preview", Static),
                app.query_one("#three-way-preview", Static),
            )
            original_widths = [
                max(map(len, preview.content.plain.splitlines()))
                for preview in previews
            ]

            app.query_one("#preview-tabs", TabbedContent).active = "three-way"
            await pilot.pause()
            app.query_one("#overlap_highlight-bgcolor", Select).value = "blue"
            await pilot.pause()

            updated_widths = [
                max(map(len, preview.content.plain.splitlines()))
                for preview in previews
            ]
            self.assertEqual(original_widths, updated_widths)

    async def test_indexed_picker_renders_coloured_swatches_in_a_narrow_terminal(self):
        app = self.make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            app.push_screen(IndexedColorPicker(app.config.ansi256.add.color))
            await pilot.pause()

            swatch = app.screen.query_one("#indexed-130", ColorSwatch)
            segments = list(swatch.render_line(0))
            empty = app.screen.query_one(".indexed-empty", Static)
            grid = app.screen.query_one("#indexed-grid")

            self.assertEqual(130, segments[0].style.bgcolor.number)
            self.assertTrue(
                all(not segment.text.strip() for segment in empty.render_line(0))
            )
            self.assertGreaterEqual(grid.region.x, 0)
            self.assertLessEqual(grid.region.right, app.size.width)
            self.assertLessEqual(grid.region.bottom, app.size.height)

    def test_indexed_picker_groups_related_colours(self):
        self.assertEqual(
            set(range(256)), {value for value in ANSI256_GRID if value is not None}
        )
        self.assertEqual((16, 22, 28, 34, 40, 46), ANSI256_GRID[:6])
        self.assertEqual((82, 76, 70, 64, 58, 52), ANSI256_GRID[6:12])
        self.assertEqual((232, 255, 0, 8), ANSI256_GRID[12:16])

    async def test_ansi256_edit_updates_the_live_preview(self):
        app = self.make_app()
        app.terminal_depth = ColorDepth.ANSI256
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#depth", Select).value = 256
            app.query_one("#palette", Select).value = "ansi256"
            await pilot.pause()
            app._indexed_colour_chosen("add", "color", 114)
            await pilot.pause()

            preview = app.query_one("#inline-preview").content
            colour_numbers = {
                span.style.color.number
                for span in preview.spans
                if not isinstance(span.style, str) and span.style.color is not None
            }
            self.assertIn(114, colour_numbers)

    async def test_fallback_notice_appears_when_ansi256_is_unavailable(self):
        app = self.make_app()
        app.terminal_depth = ColorDepth.ANSI16
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#depth", Select).value = 256
            await pilot.pause()

            notice = app.query_one("#fallback-notice", Label)
            self.assertTrue(notice.display)
            self.assertIn("ANSI16 fallback", str(notice.content))

    async def test_palette_text_attributes_are_independent(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#palette", Select).value = "ansi256"
            await pilot.pause()
            app.query_one("#add-bold", Switch).value = False
            app.query_one("#add-italic", Switch).value = True
            await pilot.pause()

            self.assertFalse(app.config.ansi256.add.bold)
            self.assertTrue(app.config.ansi256.add.italic)
            self.assertFalse(app.config.ansi16.add.bold)
            self.assertFalse(app.config.ansi16.add.italic)

            app.query_one("#palette", Select).value = "ansi16"
            await pilot.pause()
            app.query_one("#add-bold", Switch).value = True
            await pilot.pause()
            self.assertTrue(app.config.ansi16.add.bold)
            self.assertFalse(app.config.ansi16.add.italic)
            self.assertFalse(app.config.ansi256.add.bold)
            self.assertTrue(app.config.ansi256.add.italic)

    async def test_attribute_switches_share_one_row(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)):
            bold = app.query_one("#add-bold", Switch)
            italic = app.query_one("#add-italic", Switch)

            self.assertEqual(1, bold.size.height)
            self.assertEqual(1, bold.parent.size.height)
            self.assertEqual(bold.parent, italic.parent)

    async def test_save_dialog_defaults_to_xdg_and_writes_valid_toml(self):
        app = self.make_app()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "jiff" / "config.toml"
            with mock.patch(
                "jiff_configure.app.default_config_path",
                return_value=destination,
            ):
                async with app.run_test(size=(140, 42)) as pilot:
                    app.query_one("#add-color", Select).value = "blue"
                    await pilot.pause()
                    await pilot.press("ctrl+s")
                    await pilot.pause()

                    self.assertIsInstance(app.screen, SavePathDialog)
                    self.assertEqual(
                        str(destination),
                        app.screen.query_one("#save-path", Input).value,
                    )
                    await pilot.click("#accept-save")
                    await pilot.pause()

                    self.assertFalse(app.dirty)
                    self.assertEqual(
                        "blue",
                        parse_color_config(destination.read_text()).ansi16.add.color,
                    )

    async def test_existing_file_requires_overwrite_confirmation(self):
        app = self.make_app()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "config.toml"
            destination.write_text("Statler says no", encoding="utf-8")
            with mock.patch(
                "jiff_configure.app.default_config_path",
                return_value=destination,
            ):
                async with app.run_test(size=(140, 42)) as pilot:
                    await pilot.press("ctrl+s")
                    await pilot.pause()
                    await pilot.click("#accept-save")
                    await pilot.pause()

                    self.assertIsInstance(app.screen, ConfirmDialog)
                    self.assertEqual("Statler says no", destination.read_text())
                    await pilot.click("#accept-confirm")
                    await pilot.pause()

                    parse_color_config(destination.read_text())

    async def test_unsaved_changes_require_confirmation_before_quit(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#add-color", Select).value = "blue"
            await pilot.pause()
            await pilot.press("ctrl+q")
            await pilot.pause()

            self.assertIsInstance(app.screen, ConfirmDialog)
            await pilot.click("#cancel-confirm")
            await pilot.pause()
            self.assertTrue(app.is_running)

    async def test_changing_theme_with_unsaved_edits_requires_confirmation(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#add-color", Select).value = "blue"
            await pilot.pause()
            app.query_one("#theme", Select).value = "Dracula"
            await pilot.pause()

            self.assertIsInstance(app.screen, ConfirmDialog)
            self.assertEqual("Default", app.selected_theme)
            await pilot.click("#cancel-confirm")
            await pilot.pause()
            self.assertEqual("Default", app.selected_theme)

    async def test_changing_an_unedited_theme_does_not_require_confirmation(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            theme = app.query_one("#theme", Select)
            theme.value = "Dracula"
            await pilot.pause()
            theme.value = "Nord"
            await pilot.pause()

            self.assertEqual("Nord", app.selected_theme)
            self.assertEqual(app.themes["Nord"], app.config)


if __name__ == "__main__":
    unittest.main()
