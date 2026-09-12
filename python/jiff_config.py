from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import IntEnum
from pathlib import Path

from rich.console import Console
from rich.style import Style

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.9 and 3.10
    import tomli as tomllib

CANONICAL_COLORS = (
    "default",
    "black",
    "bright_black",
    "red",
    "bright_red",
    "green",
    "bright_green",
    "yellow",
    "bright_yellow",
    "blue",
    "bright_blue",
    "magenta",
    "bright_magenta",
    "cyan",
    "bright_cyan",
    "white",
    "bright_white",
)
COLOR_ALIASES = {"gray": "bright_black", "grey": "bright_black", "purple": "magenta"}
SUPPORTED_COLORS = (*CANONICAL_COLORS, *COLOR_ALIASES)
ANSI16_INDEXES = {
    "black": 0,
    "red": 1,
    "green": 2,
    "yellow": 3,
    "blue": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7,
    "bright_black": 8,
    "bright_red": 9,
    "bright_green": 10,
    "bright_yellow": 11,
    "bright_blue": 12,
    "bright_magenta": 13,
    "bright_cyan": 14,
    "bright_white": 15,
}
ANSI16_RGB = (
    (0, 0, 0),
    (128, 0, 0),
    (0, 128, 0),
    (128, 128, 0),
    (0, 0, 128),
    (128, 0, 128),
    (0, 128, 128),
    (192, 192, 192),
    (128, 128, 128),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (0, 0, 255),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
)
DIFF_STYLE_NAMES = (
    "same",
    "line_number",
    "line_number_add",
    "line_number_remove",
    "omitted",
    "add",
    "add_highlight",
    "remove",
    "remove_highlight",
    "overlap_highlight",
)
SYNTAX_STYLE_NAMES = (
    "syntax_comment",
    "syntax_comment_highlight",
    "syntax_keyword",
    "syntax_keyword_highlight",
    "syntax_string",
    "syntax_string_highlight",
    "syntax_number",
    "syntax_number_highlight",
    "syntax_definition",
    "syntax_definition_highlight",
)
STYLE_NAMES = DIFF_STYLE_NAMES + SYNTAX_STYLE_NAMES


class ConfigError(Exception):
    """A Jiff colour configuration could not be loaded or parsed."""


class ColorDepth(IntEnum):
    """One of the colour depths understood by Jiff."""

    ANSI16 = 16
    ANSI256 = 256
    TRUECOLOR = 24


@dataclass(frozen=True)
class ColorStyle:
    """The foreground, background and attributes for one part of a diff."""

    color: str | int | None = None
    bgcolor: str | int | None = None
    bold: bool = False
    italic: bool = False

    def rich_style(self) -> Style:
        def rich_color(value: str | int | None) -> str | None:
            return f"color({value})" if isinstance(value, int) else value

        return Style(
            color=rich_color(self.color),
            bgcolor=rich_color(self.bgcolor),
            bold=self.bold,
            italic=self.italic,
        )


@dataclass(frozen=True)
class ColorScheme:
    """The complete set of diff and syntax styles for one colour depth."""

    same: ColorStyle
    line_number: ColorStyle
    line_number_add: ColorStyle
    line_number_remove: ColorStyle
    omitted: ColorStyle
    add: ColorStyle
    add_highlight: ColorStyle
    remove: ColorStyle
    remove_highlight: ColorStyle
    overlap_highlight: ColorStyle
    syntax_comment: ColorStyle
    syntax_comment_highlight: ColorStyle
    syntax_keyword: ColorStyle
    syntax_keyword_highlight: ColorStyle
    syntax_string: ColorStyle
    syntax_string_highlight: ColorStyle
    syntax_number: ColorStyle
    syntax_number_highlight: ColorStyle
    syntax_definition: ColorStyle
    syntax_definition_highlight: ColorStyle

    @classmethod
    def default(cls) -> ColorScheme:
        return cls(
            same=ColorStyle(),
            line_number=ColorStyle(),
            line_number_add=ColorStyle(),
            line_number_remove=ColorStyle(),
            omitted=ColorStyle(color="bright_black"),
            add=ColorStyle(color="green"),
            add_highlight=ColorStyle(color="black", bgcolor="green"),
            remove=ColorStyle(color="red"),
            remove_highlight=ColorStyle(color="black", bgcolor="red"),
            overlap_highlight=ColorStyle(color="black", bgcolor="yellow"),
            syntax_comment=ColorStyle(color="bright_black"),
            syntax_comment_highlight=ColorStyle(color="bright_black"),
            syntax_keyword=ColorStyle(color="magenta"),
            syntax_keyword_highlight=ColorStyle(color="magenta"),
            syntax_string=ColorStyle(color="cyan"),
            syntax_string_highlight=ColorStyle(color="cyan"),
            syntax_number=ColorStyle(color="blue"),
            syntax_number_highlight=ColorStyle(color="blue"),
            syntax_definition=ColorStyle(color="yellow"),
            syntax_definition_highlight=ColorStyle(color="yellow"),
        )

    @classmethod
    def plain(cls) -> ColorScheme:
        return cls(**dict.fromkeys(STYLE_NAMES, ColorStyle()))

    def without_additions(self) -> ColorScheme:
        """Returns the palette with addition diff styles disabled."""
        return replace(
            self,
            line_number_add=ColorStyle(),
            add=ColorStyle(),
            add_highlight=ColorStyle(),
        )

    def without_removals(self) -> ColorScheme:
        """Returns the palette with removal diff styles disabled."""
        return replace(
            self,
            line_number_remove=ColorStyle(),
            remove=ColorStyle(),
            remove_highlight=ColorStyle(),
        )


@dataclass(frozen=True)
class ColorConfig:
    """The preferred colour depth and its resolved fallback palettes."""

    depth: ColorDepth
    ansi16: ColorScheme
    ansi256: ColorScheme
    truecolor: ColorScheme

    @classmethod
    def default(cls) -> ColorConfig:
        ansi16 = ColorScheme.default()
        ansi256 = _ansi256_scheme(ansi16)
        return cls(ColorDepth.TRUECOLOR, ansi16, ansi256, _truecolor_scheme(ansi256))

    def scheme(self, terminal_depth: ColorDepth) -> ColorScheme:
        """Returns the preferred palette supported by the terminal."""
        return {
            ColorDepth.ANSI16: self.ansi16,
            ColorDepth.ANSI256: self.ansi256,
            ColorDepth.TRUECOLOR: self.truecolor,
        }[self.scheme_depth(terminal_depth)]

    def scheme_depth(self, terminal_depth: ColorDepth) -> ColorDepth:
        """Returns the depth selected for the terminal."""
        if (
            self.depth == ColorDepth.TRUECOLOR
            and terminal_depth == ColorDepth.TRUECOLOR
        ):
            return ColorDepth.TRUECOLOR
        if self.depth in (
            ColorDepth.TRUECOLOR,
            ColorDepth.ANSI256,
        ) and terminal_depth in (
            ColorDepth.TRUECOLOR,
            ColorDepth.ANSI256,
        ):
            return ColorDepth.ANSI256
        return ColorDepth.ANSI16


def find_color_config_path() -> Path | None:
    """Finds the configuration file Jiff would load, if one exists."""
    return _find_config_file(os.environ, Path.home())


def load_color_config(path: Path | None = None) -> ColorConfig:
    """Loads an explicit configuration or Jiff's discovered configuration."""
    if path is None:
        path = find_color_config_path()
    if path is None:
        return ColorConfig.default()
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"{path}: could not read file: {error}") from error
    try:
        return parse_color_config(contents)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from error


def terminal_color_depth(force_terminal: bool = False) -> ColorDepth:
    """Returns the colour depth Rich detects for the terminal."""
    console = Console(force_terminal=True if force_terminal else None)
    if console.color_system == "truecolor":
        return ColorDepth.TRUECOLOR
    if console.color_system == "256":
        return ColorDepth.ANSI256
    return ColorDepth.ANSI16


def terminal_supports_ansi256(force_terminal: bool = False) -> bool:
    """Reports whether the terminal supports at least 256 colours."""
    return terminal_color_depth(force_terminal) != ColorDepth.ANSI16


def load_color_scheme(force_terminal: bool = False) -> ColorScheme:
    """Loads the palette suitable for the current terminal."""
    config = load_color_config()
    return config.scheme(terminal_color_depth(force_terminal))


def parse_color_config(contents: str) -> ColorConfig:
    """Parses and resolves one Jiff TOML configuration."""
    try:
        document = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"invalid TOML: {error}") from error
    return _parse_color_config(document)


def parse_color_scheme(contents: str) -> ColorScheme:
    """Parses the ANSI16 scheme from a Jiff configuration."""
    return parse_color_config(contents).ansi16


def color_config_to_toml(config: ColorConfig) -> str:
    """Returns a complete Jiff TOML configuration."""
    lines = ["[color]", f"depth = {int(config.depth)}"]
    for palette_name, scheme in (
        ("ansi16", config.ansi16),
        ("ansi256", config.ansi256),
        ("truecolor", config.truecolor),
    ):
        lines.extend(("", f"[color.{palette_name}]"))
        for name in STYLE_NAMES:
            style = getattr(scheme, name)
            fields = [f"color = {_toml_color(style.color, palette_name)}"]
            if name in DIFF_STYLE_NAMES:
                fields.append(f"bgcolor = {_toml_color(style.bgcolor, palette_name)}")
            fields.append(f"bold = {str(style.bold).lower()}")
            fields.append(f"italic = {str(style.italic).lower()}")
            lines.append(f"{name} = {{ {', '.join(fields)} }}")
    return "\n".join(lines) + "\n"


def color_scheme_to_toml(scheme: ColorScheme) -> str:
    """Returns a complete depth-16 config for an existing scheme."""
    ansi256 = _ansi256_scheme(scheme)
    return color_config_to_toml(
        ColorConfig(ColorDepth.ANSI16, scheme, ansi256, _truecolor_scheme(ansi256))
    )


def _toml_color(value: str | int | None, palette_name: str) -> str:
    if value is None:
        return '"default"'
    if palette_name == "ansi256":
        if isinstance(value, str):
            value = ANSI16_INDEXES[value]
        return str(value)
    return f'"{value}"'


def default_config_path() -> Path:
    """The standard XDG path offered when saving a Jiff configuration."""
    return _default_config_path(os.environ, Path.home())


def _default_config_path(environment: Mapping[str, str], home: Path) -> Path:
    xdg_home = Path(environment.get("XDG_CONFIG_HOME", ""))
    if xdg_home.is_absolute():
        return xdg_home / "jiff" / "config.toml"
    return home / ".config" / "jiff" / "config.toml"


def _find_config_file(environment: Mapping[str, str], home: Path) -> Path | None:
    if explicit := environment.get("JIFF_CONFIG", "").strip():
        return Path(explicit)
    for path in (_default_config_path(environment, home), home / ".jiffconfig"):
        try:
            path.stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ConfigError(f"{path}: could not inspect file: {error}") from error
        return path
    return None


def _parse_color_config(document: object) -> ColorConfig:
    root = _table(document, "root")
    _reject_unknown_fields(root, {"color"}, "root")
    if "color" not in root:
        return ColorConfig.default()
    color = _table(root["color"], "color")
    _reject_unknown_fields(color, {"depth", "ansi16", "ansi256", "truecolor"}, "color")
    depth = color.get("depth", ColorDepth.TRUECOLOR)
    if (
        not isinstance(depth, int)
        or isinstance(depth, bool)
        or depth not in (16, 24, 256)
    ):
        raise ConfigError("color.depth must be 16, 24 or 256")
    depth = ColorDepth(depth)

    ansi16 = _parse_scheme(
        color.get("ansi16"),
        ColorScheme.default(),
        "color.ansi16",
        ColorDepth.ANSI16,
    )
    ansi256 = _parse_scheme(
        color.get("ansi256"),
        _ansi256_scheme(ansi16),
        "color.ansi256",
        ColorDepth.ANSI256,
    )
    truecolor = _parse_scheme(
        color.get("truecolor"),
        _truecolor_scheme(ansi256),
        "color.truecolor",
        ColorDepth.TRUECOLOR,
    )
    return ColorConfig(depth, ansi16, ansi256, truecolor)


def _parse_scheme(
    value: object, defaults: ColorScheme, field: str, depth: ColorDepth
) -> ColorScheme:
    if value is None:
        return defaults
    table = _table(value, field)
    _reject_unknown_fields(table, set(STYLE_NAMES), field)
    styles = {
        name: _parse_style(
            table.get(name),
            getattr(defaults, name),
            f"{field}.{name}",
            depth,
            name in DIFF_STYLE_NAMES,
        )
        for name in STYLE_NAMES
    }

    # A configured general gutter style still applies to changed lines unless
    # the corresponding specialised style is present.
    if "line_number" in table:
        for name in ("line_number_add", "line_number_remove"):
            if name not in table:
                styles[name] = styles["line_number"]
    return ColorScheme(**styles)


def _parse_style(
    value: object,
    default: ColorStyle,
    field: str,
    depth: ColorDepth,
    allow_background: bool,
) -> ColorStyle:
    if value is None:
        return default
    table = _table(value, field)
    expected = {"color", "bold", "italic"}
    if allow_background:
        expected.add("bgcolor")
    _reject_unknown_fields(table, expected, field)
    color = _color_field(table, "color", field, default.color, depth)
    bgcolor = (
        _color_field(table, "bgcolor", field, default.bgcolor, depth)
        if allow_background
        else None
    )
    bold = table.get("bold", default.bold)
    if not isinstance(bold, bool):
        raise ConfigError(f"{field}.bold must be true or false")
    italic = table.get("italic", default.italic)
    if not isinstance(italic, bool):
        raise ConfigError(f"{field}.italic must be true or false")
    return ColorStyle(color, bgcolor, bold, italic)


def _color_field(
    table: dict[str, object],
    name: str,
    parent: str,
    default: str | int | None,
    depth: ColorDepth,
) -> str | int | None:
    if name not in table:
        return default
    value = table[name]
    if depth == ColorDepth.ANSI256:
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255:
            return value
        if isinstance(value, str) and value.strip().lower() == "default":
            return None
        raise ConfigError(
            f'{parent}.{name} must be an index from 0 to 255 or "default"'
        )
    if depth == ColorDepth.TRUECOLOR and not isinstance(value, str):
        raise ConfigError(f'{parent}.{name} must be #RRGGBB or "default"')
    if not isinstance(value, str):
        raise ConfigError(f"{parent}.{name} must be a string")
    normalized = value.strip().lower()
    if depth == ColorDepth.TRUECOLOR:
        if normalized == "default":
            return None
        if not re.fullmatch(r"#[0-9a-f]{6}", normalized):
            raise ConfigError(f'{parent}.{name} must be #RRGGBB or "default"')
        return normalized
    if normalized not in SUPPORTED_COLORS:
        expected = ", ".join(SUPPORTED_COLORS)
        raise ConfigError(
            f"{parent}.{name} has unsupported colour {value!r}; expected {expected}"
        )
    if normalized == "default":
        return None
    return COLOR_ALIASES.get(normalized, normalized)


def _ansi256_scheme(scheme: ColorScheme) -> ColorScheme:
    def indexed(value: str | int | None) -> int | None:
        return ANSI16_INDEXES[value] if isinstance(value, str) else value

    def indexed_style(style: ColorStyle) -> ColorStyle:
        return replace(
            style,
            color=indexed(style.color),
            bgcolor=indexed(style.bgcolor),
        )

    return ColorScheme(
        **{name: indexed_style(getattr(scheme, name)) for name in STYLE_NAMES}
    )


def _truecolor_scheme(scheme: ColorScheme) -> ColorScheme:
    def rgb(value: str | int | None) -> str | None:
        if value is None or isinstance(value, str):
            return value
        red, green, blue = _ansi256_rgb(value)
        return f"#{red:02x}{green:02x}{blue:02x}"

    def rgb_style(style: ColorStyle) -> ColorStyle:
        return replace(style, color=rgb(style.color), bgcolor=rgb(style.bgcolor))

    return ColorScheme(
        **{name: rgb_style(getattr(scheme, name)) for name in STYLE_NAMES}
    )


def _ansi256_rgb(index: int) -> tuple[int, int, int]:
    if index < 16:
        return ANSI16_RGB[index]
    if index < 232:
        index -= 16
        levels = (0, 95, 135, 175, 215, 255)
        return levels[index // 36], levels[index // 6 % 6], levels[index % 6]
    level = 8 + (index - 232) * 10
    return level, level, level


def _table(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{field} must be a table")
    return value


def _reject_unknown_fields(
    table: dict[str, object], expected: set[str], parent: str
) -> None:
    unknown = sorted(set(table) - expected)
    if unknown:
        raise ConfigError(f"unknown option {parent}.{unknown[0]}")
