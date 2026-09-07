from __future__ import annotations

from rich.color import Color
from rich.console import Console
from rich.text import Text

_CONSOLE = Console(color_system="standard")


def output_should_contain_ansi_style(
    output: str,
    foreground: str | None = None,
    background: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    """Checks at least one character has the requested ANSI style."""
    if _contains_style(output, foreground, background, bold, italic):
        return

    raise AssertionError(
        "Output does not contain text with "
        f"{_describe_style(foreground, background, bold, italic)}"
    )


def output_should_not_contain_ansi_style(
    output: str,
    foreground: str | None = None,
    background: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    """Checks no character has the requested ANSI style."""
    if not _contains_style(output, foreground, background, bold, italic):
        return

    raise AssertionError(
        "Output contains text with "
        f"{_describe_style(foreground, background, bold, italic)}"
    )


def _contains_style(
    output: str,
    foreground: str | None,
    background: str | None,
    bold: bool | None,
    italic: bool | None,
) -> bool:
    text = Text.from_ansi(output)
    foreground_number = _colour_number(foreground)
    background_number = _colour_number(background)

    for offset in range(len(text)):
        style = text.get_style_at_offset(_CONSOLE, offset)
        if foreground_number is not None and (
            style.color is None or style.color.number != foreground_number
        ):
            continue
        if background_number is not None and (
            style.bgcolor is None or style.bgcolor.number != background_number
        ):
            continue
        if bold is not None and bool(style.bold) != bold:
            continue
        if italic is not None and bool(style.italic) != italic:
            continue
        return True

    return False


def _colour_number(colour: str | None) -> int | None:
    if colour is None:
        return None
    return Color.parse(colour).number


def _describe_style(
    foreground: str | None,
    background: str | None,
    bold: bool | None,
    italic: bool | None,
) -> str:
    parts = []
    if foreground is not None:
        parts.append(f"{foreground} text")
    if background is not None:
        parts.append(f"a {background} background")
    if bold is not None:
        parts.append("bold text" if bold else "non-bold text")
    if italic is not None:
        parts.append("italic text" if italic else "non-italic text")
    return ", ".join(parts)
