import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jiff_config import ColorScheme, parse_color_scheme
from jiff_configure.app import (
    ConfirmDialog,
    JiffConfigureApp,
    PreviewSource,
    SavePathDialog,
    load_preview_source,
    load_themes,
)
from textual.widgets import Input, Select


class PreviewSourceTests(unittest.TestCase):
    def test_no_paths_uses_the_built_in_python_diff(self):
        source = load_preview_source([])

        self.assertEqual("before.py", source.left_path)
        self.assertEqual("after.py", source.right_path)
        self.assertEqual(1, source.context_lines)

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
    def test_packaged_themes_include_default_and_all_examples(self):
        themes = load_themes()

        self.assertEqual(ColorScheme.default(), themes["Default"])
        self.assertEqual(
            {
                "Default",
                "Catppuccin Mocha",
                "Dracula",
                "Gruvbox Dark",
                "High Contrast Dark",
                "High Contrast Light",
                "Nord",
                "Tokyo Night",
            },
            set(themes),
        )


class ConfigureAppTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self) -> JiffConfigureApp:
        return JiffConfigureApp(PreviewSource.built_in(), load_themes())

    async def test_selecting_a_theme_updates_the_scheme_and_previews(self):
        app = self.make_app()
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one("#theme", Select).value = "Dracula"
            await pilot.pause()

            self.assertEqual(app.themes["Dracula"], app.scheme)
            self.assertTrue(app.dirty)
            self.assertIn(
                'syntax_keyword = { color = "magenta"',
                str(app.query_one("#toml-preview").content),
            )

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
                        parse_color_scheme(destination.read_text()).add.color,
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

                    parse_color_scheme(destination.read_text())

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


if __name__ == "__main__":
    unittest.main()
