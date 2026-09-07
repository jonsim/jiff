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
    CANONICAL_COLORS,
    DIFF_STYLE_NAMES,
    SYNTAX_STYLE_NAMES,
    ColorConfig,
    ColorScheme,
    ColorStyle,
    ConfigError,
    color_config_to_toml,
    default_config_path,
    parse_color_config,
    terminal_supports_ansi256,
)
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
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

STYLE_NAMES = DIFF_STYLE_NAMES + SYNTAX_STYLE_NAMES
STYLE_LABELS = {
    "same": "Unchanged text",
    "line_number": "Line-number gutters",
    "omitted": "Omitted lines",
    "add": "Added text",
    "add_highlight": "Added highlights",
    "remove": "Removed text",
    "remove_highlight": "Removed highlights",
    "overlap_highlight": "Three-way overlap",
    "syntax_comment": "Syntax: comments",
    "syntax_comment_highlight": "Syntax: highlighted comments",
    "syntax_keyword": "Syntax: keywords",
    "syntax_keyword_highlight": "Syntax: highlighted keywords",
    "syntax_string": "Syntax: strings",
    "syntax_string_highlight": "Syntax: highlighted strings",
    "syntax_number": "Syntax: numbers",
    "syntax_number_highlight": "Syntax: highlighted numbers",
    "syntax_definition": "Syntax: definitions",
    "syntax_definition_highlight": "Syntax: highlighted definitions",
}
COLOR_OPTIONS = tuple(
    ("Terminal default" if name == "default" else name.replace("_", " ").title(), name)
    for name in CANONICAL_COLORS
)


def _ansi256_grid() -> tuple[int | None, ...]:
    """Arranges the xterm colour cube, greys and ANSI colours by similarity."""
    cells: list[int | None] = []
    for row in range(18):
        red_pair = row // 6
        blue = row % 6 if red_pair % 2 == 0 else 5 - row % 6

        for column in range(12):
            red = red_pair * 2 + column // 6
            green = column % 6 if column < 6 else 5 - column % 6
            cells.append(16 + 36 * red + 6 * green + blue)

        cells.append(232 + row if row < 12 else None)
        cells.append(255 - row if row < 12 else None)
        cells.append(row if row < 8 else None)
        cells.append(8 + row if row < 8 else None)

    return tuple(cells)


ANSI256_GRID = _ansi256_grid()
ANSI256_POSITIONS = {
    value: position for position, value in enumerate(ANSI256_GRID) if value is not None
}

BUILTIN_LEFT = r'''"""Plan tonight's Muppet Theatre show."""

from dataclasses import dataclass
from enum import Enum

VENUE = "Muppet Theatre"
HOUSE_CAPACITY = 120

# The balcony is reserved for Statler and Waldorf.
class Stage(Enum):
    MAIN = "main"
    BALCONY = "balcony"


@dataclass(frozen=True)
class Act:
    name: str
    stage: Stage
    entrances: int = 1
    is_surprise: bool = False

    def introduction(self) -> str:
        return f"Please welcome {self.name}!"

    def needs_rehearsal(self) -> bool:
        return self.entrances > 1


def running_order(acts: list[Act]) -> list[str]:
    announced: list[str] = []
    for act in acts:
        if act.entrances > 0:
            announced.append(act.introduction())
    return announced


# Sam keeps one dependable act ready in the wings.
acts = [
    Act("Kermit", Stage.MAIN, 1),
    Act("Fozzie", Stage.BALCONY, 2),
]
backup_act = Act("Rowlf", Stage.MAIN)
print("\n".join(running_order(acts)))'''

BUILTIN_RIGHT = r'''"""Plan tonight's spectacular Muppet Theatre show."""

from dataclasses import dataclass
from enum import Enum

VENUE = "Muppet Theatre"
HOUSE_CAPACITY = 144

# The balcony is reserved for Statler and Waldorf.
class Stage(Enum):
    MAIN = "main"
    BALCONY = "balcony"


@dataclass(frozen=True)
class Act:
    name: str
    stage: Stage
    entrances: int = 2
    is_surprise: bool = True

    def announcement(self) -> str:
        return f"Please welcome the magnificent {self.name}!"

    def needs_rehearsal(self) -> bool:
        return self.entrances > 1


def running_order(acts: list[Act]) -> list[str]:
    announced: list[str] = []
    for act in acts:
        if act.entrances >= 1:
            announced.append(act.announcement())
    return announced


# Scooter keeps two unpredictable acts ready in the wings.
acts = [
    Act("Kermit", Stage.MAIN, 1),
    Act("Gonzo", Stage.BALCONY, 3),
]
print("\n".join(running_order(acts)))
audience = HOUSE_CAPACITY - 4'''

# Three panes leave little room once the controls are visible. Keep this
# example intentionally terse so its changes remain readable without wrapping.
THREE_WAY_LOCAL = r'''"""Three-way show."""

COUNT = 3
HOST = "Kermit"
MODE = "local"

def cue(name: str):
    return f"Hi {name}!"

CAST = ["K"]
REMOTE_DROP = "yes"
LOCAL_ONLY = True'''

THREE_WAY_BASE = r'''"""Three-way show."""

COUNT = 2
HOST = "Kermit"
MODE = "base"

def cue(name: str):
    return f"Hi {name}"

CAST = ["K", "Fozzie"]
LOCAL_DROP = "yes"
REMOTE_DROP = "yes"'''

THREE_WAY_REMOTE = r'''"""Three-way show."""

COUNT = 2
HOST = "Gonzo"
MODE = "remote"

def cue(name: str):
    return f"Hey {name}"

CAST = ["K", "Fozzie"]
LOCAL_DROP = "yes"
REMOTE_ONLY = 7'''


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
        """The Python example which exercises every two-way style category."""
        return cls(BUILTIN_LEFT, BUILTIN_RIGHT, "before.py", "after.py", 4)


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


def load_themes() -> dict[str, ColorConfig]:
    """Loads the built-in default and every packaged TOML theme."""
    themes = {"Default": ColorConfig.default()}
    resources = files("jiff_configure.themes")
    for resource in sorted(resources.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".toml"):
            continue
        name = resource.name.removesuffix(".toml").replace("-", " ").title()
        try:
            themes[name] = parse_color_config(resource.read_text(encoding="utf-8"))
        except ConfigError as error:
            raise ConfigError(f"bundled theme {resource.name}: {error}") from error
    return themes


def _configured_colour(colour: str) -> str | None:
    return None if colour == "default" else colour


class StyleControl(Vertical):
    """Colour and text-attribute controls for one Jiff style."""

    def __init__(self, style_name: str, style: ColorStyle, palette: str) -> None:
        super().__init__(classes="style-control")
        self.style_name = style_name
        self.style = style
        self.palette = palette

    def color_control(self, field: str, value: str | int | None):
        name = f"{self.style_name}.{field}"
        if self.palette == "ansi16":
            return Select(
                COLOR_OPTIONS,
                value=value or "default",
                allow_blank=False,
                compact=True,
                id=f"{self.style_name}-{field}",
                name=name,
                classes="colour-select",
            )
        return Button(
            "Default" if value is None else str(value),
            id=f"{self.style_name}-{field}",
            name=name,
            classes="indexed-colour",
        )

    def compose(self) -> ComposeResult:
        yield Label(STYLE_LABELS[self.style_name], classes="style-title")
        with Horizontal(classes="colour-fields"):
            yield Label("Text", classes="field-label")
            yield self.color_control("color", self.style.color)
            if self.style_name in DIFF_STYLE_NAMES:
                yield Label("Background", classes="field-label background-label")
                yield self.color_control("bgcolor", self.style.bgcolor)
        with Horizontal(classes="attribute-fields"):
            yield Label("Bold", classes="field-label")
            yield Switch(
                self.style.bold,
                animate=False,
                id=f"{self.style_name}-bold",
                name=f"{self.style_name}.bold",
                classes="style-switch",
            )
            yield Label("Italic", classes="field-label")
            yield Switch(
                self.style.italic,
                animate=False,
                id=f"{self.style_name}-italic",
                name=f"{self.style_name}.italic",
                classes="style-switch",
            )


class ColorSwatch(Widget, can_focus=True):
    """One focusable ANSI256 colour in the picker grid."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "select", "Select", show=False),
    ]

    class Selected(Message):
        """The swatch was selected with the keyboard or mouse."""

        def __init__(self, value: int) -> None:
            super().__init__()
            self.value = value

    class Focused(Message):
        """The swatch gained keyboard focus."""

        def __init__(self, value: int) -> None:
            super().__init__()
            self.value = value

    def __init__(self, value: int) -> None:
        super().__init__(id=f"indexed-{value}", classes="indexed-swatch")
        self.value = value
        self.styles.background = Color(0, 0, 0, ansi=value)
        self.tooltip = f"ANSI256 colour {value}"

    def render(self) -> Text:
        return Text("  ")

    def on_focus(self) -> None:
        self.post_message(self.Focused(self.value))

    def action_select(self) -> None:
        self.post_message(self.Selected(self.value))

    async def _on_click(self, event: events.Click) -> None:
        event.stop()
        self.focus()
        self.action_select()


class IndexedColorPicker(ModalScreen[int | None]):
    """Selects terminal default or one ANSI256 colour index."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("left", "move(-1)", "Left", show=False),
        Binding("right", "move(1)", "Right", show=False),
        Binding("up", "move(-16)", "Up", show=False),
        Binding("down", "move(16)", "Down", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, value: int | None) -> None:
        super().__init__()
        self.value = value

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog indexed-dialog"):
            yield Label("Choose an ANSI256 colour", classes="dialog-title")
            yield Label(id="indexed-readout")
            yield Button("Terminal default", id="indexed-default")
            with Grid(id="indexed-grid"):
                for index in ANSI256_GRID:
                    if index is None:
                        yield Static("", classes="indexed-empty")
                    else:
                        yield ColorSwatch(index)

    def on_mount(self) -> None:
        if self.value is None:
            self.query_one("#indexed-default", Button).focus()
            self._update_readout(None)
        else:
            self.query_one(f"#indexed-{self.value}", ColorSwatch).focus()

    def _update_readout(self, value: int | None) -> None:
        label = "Terminal default" if value is None else f"ANSI256 colour {value}"
        if value == self.value:
            label += " (current)"
        self.query_one("#indexed-readout", Label).update(label)

    def action_move(self, offset: int) -> None:
        focused = self.focused
        if isinstance(focused, Button) and focused.id == "indexed-default":
            index = self.value if self.value is not None else ANSI256_GRID[0]
        elif isinstance(focused, ColorSwatch):
            position = ANSI256_POSITIONS[focused.value]
            while True:
                position = (position + offset) % len(ANSI256_GRID)
                index = ANSI256_GRID[position]
                if index is not None:
                    break
        else:
            return
        assert index is not None
        self.query_one(f"#indexed-{index}", ColorSwatch).focus()

    def action_cancel(self) -> None:
        self.dismiss(self.value)

    @on(Button.Pressed, "#indexed-default")
    def choose_default(self) -> None:
        self.dismiss(None)

    @on(ColorSwatch.Selected)
    def choose_swatch(self, event: ColorSwatch.Selected) -> None:
        self.dismiss(event.value)

    @on(ColorSwatch.Focused)
    def swatch_focused(self, event: ColorSwatch.Focused) -> None:
        self._update_readout(event.value)


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
        themes: dict[str, ColorConfig],
    ) -> None:
        # Textual normally replaces the terminal's 16 ANSI colours with its own
        # RGB palette. If it does that here, the preview won't match Jiff.
        super().__init__(ansi_color=True)
        self.preview_source = preview_source
        self.themes = themes
        self.config = themes["Default"]
        self.edit_palette = "ansi16"
        self.ansi256_supported = terminal_supports_ansi256(force_terminal=True)
        self.selected_theme = "Default"
        self.dirty = False

    @property
    def scheme(self) -> ColorScheme:
        """The palette currently shown in the style controls."""
        return getattr(self.config, self.edit_palette)

    @scheme.setter
    def scheme(self, value: ColorScheme) -> None:
        self.config = replace(self.config, **{self.edit_palette: value})

    def compose_style_controls(self) -> ComposeResult:
        yield Label("Diff styles", classes="section-title")
        for name in DIFF_STYLE_NAMES:
            yield StyleControl(name, getattr(self.scheme, name), self.edit_palette)
        yield Label("Syntax styles", classes="section-title")
        for name in SYNTAX_STYLE_NAMES:
            yield StyleControl(name, getattr(self.scheme, name), self.edit_palette)

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
                yield Label("Preferred output", classes="section-title")
                yield Select(
                    (("ANSI16", 16), ("ANSI256", 256)),
                    value=self.config.depth,
                    allow_blank=False,
                    id="depth",
                )
                yield Label("Palette to edit", classes="section-title")
                yield Select(
                    (("ANSI16 fallback", "ansi16"), ("ANSI256", "ansi256")),
                    value=self.edit_palette,
                    allow_blank=False,
                    id="palette",
                )
                with Container(id="style-controls"):
                    yield from self.compose_style_controls()
                with Horizontal(id="main-actions"):
                    yield Button("Save", id="save-config", variant="primary")
                    yield Button("Quit", id="quit")
            with Vertical(id="previews"):
                yield Label(id="fallback-notice", classes="fallback-notice")
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
                        TabPane("Three-way", id="three-way"),
                        VerticalScroll(classes="preview-scroll"),
                    ):
                        yield Static(id="three-way-preview", classes="preview")
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
        preview_scheme = self.config.scheme(self.ansi256_supported)
        fallback = self.config.depth == 256 and not self.ansi256_supported
        notice = self.query_one("#fallback-notice", Label)
        notice.update("ANSI256 is unavailable here - previewing the ANSI16 fallback.")
        notice.display = fallback
        common = {
            "left": source.left,
            "right": source.right,
            "left_path": source.left_path,
            "right_path": source.right_path,
            "repository_path": None,
            "color": True,
            "colors": preview_scheme,
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
        three_way = jiff.render_three_way_output(
            THREE_WAY_LOCAL,
            THREE_WAY_BASE,
            THREE_WAY_REMOTE,
            "local.py",
            "base.py",
            "remote.py",
            inline=False,
            color=True,
            colors=preview_scheme,
            terminal_width=terminal_width,
        )
        self.query_one("#three-way-preview", Static).update(
            Text.from_ansi(three_way.rstrip("\n"))
        )
        self.query_one("#toml-preview", Static).update(
            Text(color_config_to_toml(self.config))
        )

    def _apply_theme(self, name: str, mark_dirty: bool) -> None:
        self.selected_theme = name
        self.config = self.themes[name]
        theme = self.query_one("#theme", Select)
        if theme.value != name:
            theme.value = name
        self.query_one("#depth", Select).value = self.config.depth
        self._rebuild_style_controls()
        self._set_dirty(mark_dirty)
        self.refresh_previews()

    def _rebuild_style_controls(self) -> None:
        controls = self.query_one("#style-controls", Container)
        controls.remove_children()
        controls.mount(*list(self.compose_style_controls()))

    def _finish_theme_change(self, name: str, confirmed: bool) -> None:
        if confirmed:
            self._apply_theme(name, mark_dirty=True)

    @on(Select.Changed, "#theme")
    def theme_changed(self, event: Select.Changed) -> None:
        name = str(event.value)
        if name == self.selected_theme:
            return

        selected_config_changed = self.config != self.themes[self.selected_theme]
        if self.dirty and selected_config_changed:
            # Put the old theme back while the dialog is open. If the user
            # cancels, the editor then stays exactly as it was.
            event.select.value = self.selected_theme
            self.push_screen(
                ConfirmDialog(
                    "Replace the unsaved palette with another theme?",
                    "Replace",
                ),
                lambda confirmed: self._finish_theme_change(name, confirmed),
            )
        else:
            self._apply_theme(name, mark_dirty=True)

    @on(Select.Changed, "#depth")
    def depth_changed(self, event: Select.Changed) -> None:
        depth = int(event.value)
        if depth == self.config.depth:
            return
        self.config = replace(self.config, depth=depth)
        self._set_dirty()
        self.refresh_previews()

    @on(Select.Changed, "#palette")
    def palette_changed(self, event: Select.Changed) -> None:
        palette = str(event.value)
        if palette == self.edit_palette:
            return
        self.edit_palette = palette
        self._rebuild_style_controls()

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

    @on(Button.Pressed, ".indexed-colour")
    def indexed_colour_pressed(self, event: Button.Pressed) -> None:
        style_name, field = event.button.name.split(".", maxsplit=1)
        style = getattr(self.scheme, style_name)
        value = getattr(style, field)
        self.push_screen(
            IndexedColorPicker(value),
            lambda selected: self._indexed_colour_chosen(style_name, field, selected),
        )

    def _indexed_colour_chosen(
        self, style_name: str, field: str, value: int | None
    ) -> None:
        style = getattr(self.scheme, style_name)
        if getattr(style, field) == value:
            return
        self.scheme = replace(
            self.scheme,
            **{style_name: replace(style, **{field: value})},
        )
        button = self.query_one(f"#{style_name}-{field}", Button)
        button.label = "Default" if value is None else str(value)
        self._set_dirty()
        self.refresh_previews()

    @on(Switch.Changed, ".style-switch")
    def style_attribute_changed(self, event: Switch.Changed) -> None:
        style_name, field = event.switch.name.split(".", maxsplit=1)
        style = getattr(self.scheme, style_name)
        updated = replace(style, **{field: event.value})
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
            path.write_text(color_config_to_toml(self.config), encoding="utf-8")
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
