from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import ClassVar

import jiff
from jiff_config import (
    ColorScheme,
    ColorStyle,
    ConfigError,
    color_scheme_to_toml,
    default_config_path,
    parse_color_scheme,
)
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

import diff

DIFF_STYLE_NAMES = (
    "same",
    "omitted",
    "add",
    "add_highlight",
    "remove",
    "remove_highlight",
)
SYNTAX_STYLE_NAMES = (
    "syntax_comment",
    "syntax_keyword",
    "syntax_string",
    "syntax_number",
    "syntax_definition",
)
STYLE_NAMES = DIFF_STYLE_NAMES + SYNTAX_STYLE_NAMES
STYLE_LABELS = {
    "same": "Unchanged text",
    "omitted": "Omitted lines",
    "add": "Added text",
    "add_highlight": "Added highlights",
    "remove": "Removed text",
    "remove_highlight": "Removed highlights",
    "syntax_comment": "Syntax: comments",
    "syntax_keyword": "Syntax: keywords",
    "syntax_string": "Syntax: strings",
    "syntax_number": "Syntax: numbers",
    "syntax_definition": "Syntax: definitions",
}
COLOR_NAMES = (
    "default",
    "black",
    "bright_black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
)
COLOR_OPTIONS = tuple(
    ("Terminal default" if name == "default" else name.replace("_", " ").title(), name)
    for name in COLOR_NAMES
)

BUILTIN_LEFT = """from dataclasses import dataclass

# Everyone needs a role before curtain-up.
@dataclass
class Muppet:
    name: str
    entrances: int = 1

def introduce(muppet: Muppet) -> str:
    return f"Please welcome {muppet.name}!"

kermit = Muppet("Kermit", 42)
print(introduce(kermit))"""

BUILTIN_RIGHT = """from dataclasses import dataclass

# Even Gonzo needs a role before curtain-up.
@dataclass
class Performer:
    name: str
    entrances: int = 2

def introduce(performer: Performer) -> str:
    return f"Please welcome the Great {performer.name}!"

gonzo = Performer("Gonzo", 47)
print(introduce(gonzo))"""


@dataclass(frozen=True)
class PreviewSource:
    """The two text files shown by the live Jiff previews."""

    left: str
    right: str
    left_path: str
    right_path: str
    context_lines: int | None

    @classmethod
    def built_in(cls) -> PreviewSource:
        """The compact Python example which exercises every style category."""
        return cls(BUILTIN_LEFT, BUILTIN_RIGHT, "before.py", "after.py", 1)


def load_preview_source(paths: Sequence[str]) -> PreviewSource:
    """Loads an optional pair of UTF-8 files for the preview.

    Args:
        paths: No paths for the built-in example, or exactly two file paths.

    Returns:
        The source text and rendering metadata for the previews.

    Raises:
        TypeError: A supplied file is not UTF-8 text.
        ValueError: The caller supplied the wrong number of paths.
        OSError: A supplied path could not be read.
    """
    if not paths:
        return PreviewSource.built_in()
    if len(paths) != 2:
        raise ValueError("jiff-configure expects either no files or OLD NEW")

    left = jiff.read_file(paths[0])
    right = jiff.read_file(paths[1])
    if isinstance(left, bytes):
        raise TypeError(f"{paths[0]} is not a UTF-8 text file")
    if isinstance(right, bytes):
        raise TypeError(f"{paths[1]} is not a UTF-8 text file")
    return PreviewSource(left, right, paths[0], paths[1], None)


def load_themes() -> dict[str, ColorScheme]:
    """Loads the built-in default and every packaged TOML theme."""
    themes = {"Default": ColorScheme.default()}
    resources = files("jiff_configure.themes")
    for resource in sorted(resources.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".toml"):
            continue
        name = resource.name.removesuffix(".toml").replace("-", " ").title()
        try:
            themes[name] = parse_color_scheme(resource.read_text(encoding="utf-8"))
        except ConfigError as error:
            raise ConfigError(f"bundled theme {resource.name}: {error}") from error
    return themes


def _configured_colour(colour: str) -> str | None:
    return None if colour == "default" else colour


class StyleControl(Vertical):
    """Foreground, optional background and bold controls for one Jiff style."""

    def __init__(self, style_name: str, style: ColorStyle) -> None:
        super().__init__(classes="style-control")
        self.style_name = style_name
        self.style = style

    def compose(self) -> ComposeResult:
        yield Label(STYLE_LABELS[self.style_name], classes="style-title")
        with Horizontal(classes="colour-fields"):
            yield Label("Text", classes="field-label")
            yield Select(
                COLOR_OPTIONS,
                value=self.style.color or "default",
                allow_blank=False,
                compact=True,
                id=f"{self.style_name}-color",
                name=f"{self.style_name}.color",
                classes="colour-select",
            )
            if self.style_name in DIFF_STYLE_NAMES:
                yield Label("Background", classes="field-label background-label")
                yield Select(
                    COLOR_OPTIONS,
                    value=self.style.bgcolor or "default",
                    allow_blank=False,
                    compact=True,
                    id=f"{self.style_name}-bgcolor",
                    name=f"{self.style_name}.bgcolor",
                    classes="colour-select",
                )
        with Horizontal(classes="bold-field"):
            yield Label("Bold", classes="field-label")
            yield Switch(
                self.style.bold,
                animate=False,
                id=f"{self.style_name}-bold",
                name=f"{self.style_name}.bold",
                classes="bold-switch",
            )


class ConfirmDialog(ModalScreen[bool]):
    """Asks before an action which would discard or overwrite user data."""

    def __init__(self, message: str, confirm_label: str) -> None:
        super().__init__()
        self.message = message
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.message, classes="dialog-message")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="cancel-confirm")
                yield Button(
                    self.confirm_label,
                    id="accept-confirm",
                    variant="error",
                )

    @on(Button.Pressed, "#cancel-confirm")
    def cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#accept-confirm")
    def confirm(self) -> None:
        self.dismiss(True)


class SavePathDialog(ModalScreen[str | None]):
    """Prompts for the destination of a generated Jiff configuration."""

    def __init__(self, suggested_path: Path) -> None:
        super().__init__()
        self.suggested_path = suggested_path

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog save-dialog"):
            yield Label("Save Jiff configuration", classes="dialog-title")
            yield Input(str(self.suggested_path), id="save-path")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="cancel-save")
                yield Button("Save", id="accept-save", variant="primary")

    def _submit(self) -> None:
        value = self.query_one("#save-path", Input).value.strip()
        if value:
            self.dismiss(value)
        else:
            self.query_one("#save-path", Input).focus()

    @on(Input.Submitted, "#save-path")
    def submit_path(self) -> None:
        self._submit()

    @on(Button.Pressed, "#accept-save")
    def save(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel-save")
    def cancel(self) -> None:
        self.dismiss(None)


class JiffConfigureApp(App[None]):
    """Interactive editor for Jiff colour configuration files."""

    CSS_PATH = "app.tcss"
    TITLE = "Jiff Configure"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+s", "save_config", "Save"),
        Binding("ctrl+q", "request_quit", "Quit"),
        Binding("ctrl+c", "request_quit", "Quit", show=False, priority=True),
    ]

    def __init__(
        self,
        preview_source: PreviewSource,
        themes: dict[str, ColorScheme],
    ) -> None:
        super().__init__()
        self.preview_source = preview_source
        self.themes = themes
        self.scheme = themes["Default"]
        self.selected_theme = "Default"
        self.dirty = False
        diff.force_terminal_colors()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="workspace"):
            with VerticalScroll(id="controls"):
                yield Label("Starting theme", classes="section-title")
                yield Select(
                    ((name, name) for name in self.themes),
                    value=self.selected_theme,
                    allow_blank=False,
                    id="theme",
                )
                yield Label("Diff styles", classes="section-title")
                for name in DIFF_STYLE_NAMES:
                    yield StyleControl(name, getattr(self.scheme, name))
                yield Label("Syntax styles", classes="section-title")
                for name in SYNTAX_STYLE_NAMES:
                    yield StyleControl(name, getattr(self.scheme, name))
                with Horizontal(id="main-actions"):
                    yield Button("Save", id="save-config", variant="primary")
                    yield Button("Quit", id="quit")
            with TabbedContent(initial="side-by-side", id="preview-tabs"):
                with (
                    TabPane("Side-by-side", id="side-by-side"),
                    VerticalScroll(classes="preview-scroll"),
                ):
                    yield Static(id="side-preview", classes="preview")
                with (
                    TabPane("Inline", id="inline"),
                    VerticalScroll(classes="preview-scroll"),
                ):
                    yield Static(id="inline-preview", classes="preview")
                with (
                    TabPane("TOML", id="toml"),
                    VerticalScroll(classes="preview-scroll"),
                ):
                    yield Static(id="toml-preview", classes="preview toml-preview")
        yield Footer()

    def on_mount(self) -> None:
        self._update_subtitle()
        self.call_after_refresh(self.refresh_previews)

    def on_resize(self, _event: events.Resize) -> None:
        if self.is_mounted:
            self.call_after_refresh(self.refresh_previews)

    def _update_subtitle(self) -> None:
        marker = " - unsaved" if self.dirty else ""
        self.sub_title = f"{self.preview_source.left_path} → {self.preview_source.right_path}{marker}"

    def _set_dirty(self, dirty: bool = True) -> None:
        self.dirty = dirty
        self._update_subtitle()

    def refresh_previews(self) -> None:
        """Renders all views from the current controls and preview source."""
        side_preview = self.query_one("#side-preview", Static)
        terminal_width = max(side_preview.size.width, 20)
        source = self.preview_source
        common = {
            "left": source.left,
            "right": source.right,
            "lpath": source.left_path,
            "rpath": source.right_path,
            "repository_path": None,
            "color": True,
            "colors": self.scheme,
            "context_lines": source.context_lines,
        }
        side = jiff.render_output(
            **common,
            inline=False,
            terminal_width=terminal_width,
        )
        inline = jiff.render_output(**common, inline=True)
        side_preview.update(Text.from_ansi(side.rstrip("\n")))
        self.query_one("#inline-preview", Static).update(
            Text.from_ansi(inline.rstrip("\n"))
        )
        self.query_one("#toml-preview", Static).update(
            Text(color_scheme_to_toml(self.scheme))
        )

    def _apply_theme(self, name: str, mark_dirty: bool) -> None:
        self.selected_theme = name
        self.scheme = self.themes[name]
        theme = self.query_one("#theme", Select)
        if theme.value != name:
            theme.value = name

        # Assigning matching values is harmless and avoids rebuilding the
        # scroll position and focus state by remounting all the controls.
        for style_name in STYLE_NAMES:
            style = getattr(self.scheme, style_name)
            self.query_one(f"#{style_name}-color", Select).value = (
                style.color or "default"
            )
            if style_name in DIFF_STYLE_NAMES:
                self.query_one(f"#{style_name}-bgcolor", Select).value = (
                    style.bgcolor or "default"
                )
            self.query_one(f"#{style_name}-bold", Switch).value = style.bold
        self._set_dirty(mark_dirty)
        self.refresh_previews()

    def _finish_theme_change(self, name: str, confirmed: bool) -> None:
        if confirmed:
            self._apply_theme(name, mark_dirty=True)

    @on(Select.Changed, "#theme")
    def theme_changed(self, event: Select.Changed) -> None:
        name = str(event.value)
        if name == self.selected_theme:
            return

        # Put the selector back while the confirmation dialog is open. This
        # also means cancelling leaves the entire editor exactly as it was.
        event.select.value = self.selected_theme
        if self.dirty:
            self.push_screen(
                ConfirmDialog(
                    "Replace the unsaved palette with another theme?",
                    "Replace",
                ),
                lambda confirmed: self._finish_theme_change(name, confirmed),
            )
        else:
            self._apply_theme(name, mark_dirty=True)

    @on(Select.Changed, ".colour-select")
    def colour_changed(self, event: Select.Changed) -> None:
        style_name, field = event.select.name.split(".", maxsplit=1)
        style = getattr(self.scheme, style_name)
        updated = replace(style, **{field: _configured_colour(str(event.value))})
        if updated == style:
            return
        self.scheme = replace(self.scheme, **{style_name: updated})
        self._set_dirty()
        self.refresh_previews()

    @on(Switch.Changed, ".bold-switch")
    def bold_changed(self, event: Switch.Changed) -> None:
        style_name, _field = event.switch.name.split(".", maxsplit=1)
        style = getattr(self.scheme, style_name)
        updated = replace(style, bold=event.value)
        if updated == style:
            return
        self.scheme = replace(self.scheme, **{style_name: updated})
        self._set_dirty()
        self.refresh_previews()

    @on(Button.Pressed, "#save-config")
    def save_button_pressed(self) -> None:
        self.action_save_config()

    @on(Button.Pressed, "#quit")
    def quit_button_pressed(self) -> None:
        self.action_request_quit()

    def action_save_config(self) -> None:
        self.push_screen(SavePathDialog(default_config_path()), self._save_path_chosen)

    def _save_path_chosen(self, value: str | None) -> None:
        if value is None:
            return
        path = Path(value).expanduser()
        if path.exists():
            self.push_screen(
                ConfirmDialog(f"Overwrite {path}?", "Overwrite"),
                lambda confirmed: self._finish_save(path, confirmed),
            )
        else:
            self._write_config(path)

    def _finish_save(self, path: Path, confirmed: bool) -> None:
        if confirmed:
            self._write_config(path)

    def _write_config(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(color_scheme_to_toml(self.scheme), encoding="utf-8")
        except OSError as error:
            self.notify(f"Could not save {path}: {error}", severity="error")
            return
        self._set_dirty(False)
        self.notify(f"Saved {path}")

    def action_request_quit(self) -> None:
        if self.dirty:
            self.push_screen(
                ConfirmDialog("Discard the unsaved palette and quit?", "Discard"),
                self._finish_quit,
            )
        else:
            self.exit()

    def _finish_quit(self, confirmed: bool) -> None:
        if confirmed:
            self.exit()


def argument_parser() -> argparse.ArgumentParser:
    """Builds the command-line parser for the separate configuration tool."""
    parser = argparse.ArgumentParser(
        prog="jiff-configure",
        description="Build and preview a Jiff colour configuration",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="optional OLD NEW files to use instead of the built-in preview",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = argument_parser()
    args = parser.parse_args(argv)
    try:
        source = load_preview_source(args.files)
        themes = load_themes()
    except (ConfigError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    JiffConfigureApp(source, themes).run()


if __name__ == "__main__":
    main(sys.argv[1:])
