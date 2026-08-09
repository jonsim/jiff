from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from rich.style import Style

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.9 and 3.10
    import tomli as tomllib

SUPPORTED_COLORS = (
    "default",
    "black",
    "bright_black",
    "gray",
    "grey",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "purple",
    "cyan",
    "white",
)
STYLE_NAMES = (
    "same",
    "omitted",
    "add",
    "add_highlight",
    "remove",
    "remove_highlight",
    "syntax_comment",
    "syntax_keyword",
    "syntax_string",
    "syntax_number",
    "syntax_definition",
)


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
            syntax_comment=plain,
            syntax_keyword=plain,
            syntax_string=plain,
            syntax_number=plain,
            syntax_definition=plain,
        )


def load_color_scheme() -> ColorScheme:
    path = _find_config_file(os.environ, Path.home())
    if path is None:
        return ColorScheme.default()

    try:
        with path.open("rb") as config_file:
            document = tomllib.load(config_file)
    except OSError as error:
        raise ConfigError(f"{path}: could not read file: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: invalid TOML: {error}") from error

    try:
        return _parse_color_scheme(document)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from error


def _find_config_file(environment: Mapping[str, str], home: Path) -> Path | None:
    if explicit := environment.get("JIFF_CONFIG", "").strip():
        return Path(explicit)

    xdg_home = Path(environment.get("XDG_CONFIG_HOME", ""))
    if xdg_home.is_absolute():
        candidates = [xdg_home / "jiff" / "config.toml"]
    else:
        candidates = [home / ".config" / "jiff" / "config.toml"]
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
    if normalized in ("gray", "grey"):
        return "bright_black"
    if normalized == "purple":
        return "magenta"
    return normalized


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
