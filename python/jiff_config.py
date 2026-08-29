from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

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
COLOR_ALIASES = {
    "gray": "bright_black",
    "grey": "bright_black",
    "purple": "magenta",
}
SUPPORTED_COLORS = (*CANONICAL_COLORS, *COLOR_ALIASES)
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
    "syntax_keyword",
    "syntax_string",
    "syntax_number",
    "syntax_definition",
)
STYLE_NAMES = DIFF_STYLE_NAMES + SYNTAX_STYLE_NAMES


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ColorStyle:
    color: str | None = None
    bgcolor: str | None = None
    bold: bool = False

    def rich_style(self) -> Style:
        return Style(color=self.color, bgcolor=self.bgcolor, bold=self.bold)


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
    syntax_keyword: ColorStyle
    syntax_string: ColorStyle
    syntax_number: ColorStyle
    syntax_definition: ColorStyle

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
            syntax_keyword=ColorStyle(color="magenta"),
            syntax_string=ColorStyle(color="cyan"),
            syntax_number=ColorStyle(color="blue"),
            syntax_definition=ColorStyle(color="yellow"),
        )

    @classmethod
    def plain(cls) -> ColorScheme:
        plain = ColorStyle()
        return cls(
            same=plain,
            omitted=plain,
            add=plain,
            add_highlight=plain,
            remove=plain,
            remove_highlight=plain,
            overlap_highlight=plain,
            syntax_comment=plain,
            syntax_keyword=plain,
            syntax_string=plain,
            syntax_number=plain,
            syntax_definition=plain,
        )

    def without_additions(self) -> ColorScheme:
        """Returns the palette with addition diff styles disabled."""
        return replace(self, add=ColorStyle(), add_highlight=ColorStyle())

    def without_removals(self) -> ColorScheme:
        """Returns the palette with removal diff styles disabled."""
        return replace(self, remove=ColorStyle(), remove_highlight=ColorStyle())


def load_color_scheme() -> ColorScheme:
    path = _find_config_file(os.environ, Path.home())
    if path is None:
        return ColorScheme.default()

    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"{path}: could not read file: {error}") from error

    try:
        return parse_color_scheme(contents)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from error


def parse_color_scheme(contents: str) -> ColorScheme:
    """Parses one Jiff TOML configuration into its resolved colour scheme."""
    try:
        document = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"invalid TOML: {error}") from error
    return _parse_color_scheme(document)


def color_scheme_to_toml(scheme: ColorScheme) -> str:
    """Returns a complete Jiff TOML configuration for a colour scheme."""
    lines = ["[color]"]
    for name in STYLE_NAMES:
        style = getattr(scheme, name)
        fields = [f'color = "{style.color or "default"}"']
        if not name.startswith("syntax_"):
            fields.append(f'bgcolor = "{style.bgcolor or "default"}"')
        fields.append(f"bold = {str(style.bold).lower()}")
        lines.append(f"{name} = {{ {', '.join(fields)} }}")
    return "\n".join(lines) + "\n"


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

    candidates = [_default_config_path(environment, home)]
    candidates.append(home / ".jiffconfig")

    for path in candidates:
        try:
            path.stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ConfigError(f"{path}: could not inspect file: {error}") from error
        return path
    return None


def _parse_color_scheme(document: object) -> ColorScheme:
    root = _table(document, "root")
    _reject_unknown_fields(root, {"color"}, "root")
    if "color" not in root:
        return ColorScheme.default()

    color = _table(root["color"], "color")
    _reject_unknown_fields(color, set(STYLE_NAMES), "color")
    defaults = ColorScheme.default()
    styles = {
        name: _parse_style(
            color.get(name),
            getattr(defaults, name),
            f"color.{name}",
            allow_background=not name.startswith("syntax_"),
        )
        for name in STYLE_NAMES
    }
    return ColorScheme(**styles)


def _parse_style(
    value: object,
    default: ColorStyle,
    field: str,
    allow_background: bool = True,
) -> ColorStyle:
    if value is None:
        return default
    table = _table(value, field)
    expected = {"color", "bold"}
    if allow_background:
        expected.add("bgcolor")
    _reject_unknown_fields(table, expected, field)

    color = _color_field(table, "color", field, default.color)
    bgcolor = (
        _color_field(table, "bgcolor", field, default.bgcolor)
        if allow_background
        else None
    )
    bold = table.get("bold", default.bold)
    if not isinstance(bold, bool):
        raise ConfigError(f"{field}.bold must be true or false")
    return ColorStyle(color=color, bgcolor=bgcolor, bold=bold)


def _color_field(
    table: dict[str, object], name: str, parent: str, default: str | None
) -> str | None:
    if name not in table:
        return default
    value = table[name]
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
