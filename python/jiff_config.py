from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
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
DIFF_STYLE_NAMES = (
    "same",
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
    pass


@dataclass(frozen=True)
class ColorStyle:
    color: str | int | None = None
    bgcolor: str | int | None = None
    bold: bool = False

    def rich_style(self) -> Style:
        def rich_color(value: str | int | None) -> str | None:
            return f"color({value})" if isinstance(value, int) else value

        return Style(
            color=rich_color(self.color),
            bgcolor=rich_color(self.bgcolor),
            bold=self.bold,
        )


@dataclass(frozen=True)
class ColorScheme:
    same: ColorStyle
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
        return replace(self, add=ColorStyle(), add_highlight=ColorStyle())

    def without_removals(self) -> ColorScheme:
        """Returns the palette with removal diff styles disabled."""
        return replace(self, remove=ColorStyle(), remove_highlight=ColorStyle())


@dataclass(frozen=True)
class ColorConfig:
    """The preferred colour depth and its resolved fallback palettes."""

    depth: int
    ansi16: ColorScheme
    ansi256: ColorScheme

    @classmethod
    def default(cls) -> ColorConfig:
        ansi16 = ColorScheme.default()
        return cls(16, ansi16, _ansi256_scheme(ansi16))

    def scheme(self, ansi256_supported: bool) -> ColorScheme:
        if self.depth == 256 and ansi256_supported:
            return self.ansi256
        return self.ansi16


def load_color_config() -> ColorConfig:
    path = _find_config_file(os.environ, Path.home())
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


def terminal_supports_ansi256(force_terminal: bool = False) -> bool:
    """Reports whether Rich detects indexed or true-colour output support."""
    console = Console(force_terminal=True if force_terminal else None)
    return console.color_system in ("256", "truecolor")


def load_color_scheme(force_terminal: bool = False) -> ColorScheme:
    """Loads the ANSI16 palette."""
    del force_terminal
    return load_color_config().ansi16


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
    lines = ["[color]", f"depth = {config.depth}"]
    for palette_name, scheme in (
        ("ansi16", config.ansi16),
        ("ansi256", config.ansi256),
    ):
        lines.extend(("", f"[color.{palette_name}]"))
        for name in STYLE_NAMES:
            style = getattr(scheme, name)
            fields = [f"color = {_toml_color(style.color, palette_name)}"]
            if name in DIFF_STYLE_NAMES:
                fields.append(f"bgcolor = {_toml_color(style.bgcolor, palette_name)}")
            fields.append(f"bold = {str(style.bold).lower()}")
            lines.append(f"{name} = {{ {', '.join(fields)} }}")
    return "\n".join(lines) + "\n"


def color_scheme_to_toml(scheme: ColorScheme) -> str:
    """Returns a complete depth-16 config for an existing scheme."""
    return color_config_to_toml(ColorConfig(16, scheme, _ansi256_scheme(scheme)))


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
    _reject_unknown_fields(color, {"depth", "ansi16", "ansi256"}, "color")
    depth = color.get("depth", 16)
    if not isinstance(depth, int) or isinstance(depth, bool) or depth not in (16, 256):
        raise ConfigError("color.depth must be 16 or 256")

    ansi16 = _parse_scheme(
        color.get("ansi16"), ColorScheme.default(), "color.ansi16", False
    )
    ansi256 = _parse_scheme(
        color.get("ansi256"), _ansi256_scheme(ansi16), "color.ansi256", True
    )
    return ColorConfig(depth, ansi16, ansi256)


def _parse_scheme(
    value: object, defaults: ColorScheme, field: str, indexed: bool
) -> ColorScheme:
    if value is None:
        return defaults
    table = _table(value, field)
    _reject_unknown_fields(table, set(STYLE_NAMES), field)
    return ColorScheme(
        **{
            name: _parse_style(
                table.get(name),
                getattr(defaults, name),
                f"{field}.{name}",
                indexed,
                name in DIFF_STYLE_NAMES,
            )
            for name in STYLE_NAMES
        }
    )


def _parse_style(
    value: object,
    default: ColorStyle,
    field: str,
    indexed: bool,
    allow_background: bool,
) -> ColorStyle:
    if value is None:
        return default
    table = _table(value, field)
    expected = {"color", "bold"}
    if allow_background:
        expected.add("bgcolor")
    _reject_unknown_fields(table, expected, field)
    color = _color_field(table, "color", field, default.color, indexed)
    bgcolor = (
        _color_field(table, "bgcolor", field, default.bgcolor, indexed)
        if allow_background
        else None
    )
    bold = table.get("bold", default.bold)
    if not isinstance(bold, bool):
        raise ConfigError(f"{field}.bold must be true or false")
    return ColorStyle(color, bgcolor, bold)


def _color_field(
    table: dict[str, object],
    name: str,
    parent: str,
    default: str | int | None,
    indexed: bool,
) -> str | int | None:
    if name not in table:
        return default
    value = table[name]
    if indexed:
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255:
            return value
        if isinstance(value, str) and value.strip().lower() == "default":
            return None
        raise ConfigError(
            f'{parent}.{name} must be an index from 0 to 255 or "default"'
        )
    if not isinstance(value, str):
        raise ConfigError(f"{parent}.{name} must be a string")
    normalized = value.strip().lower()
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

    return ColorScheme(
        **{
            name: replace(
                getattr(scheme, name),
                color=indexed(getattr(scheme, name).color),
                bgcolor=indexed(getattr(scheme, name).bgcolor),
            )
            for name in STYLE_NAMES
        }
    )


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
