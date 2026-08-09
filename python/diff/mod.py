from __future__ import annotations

import difflib
import enum
import itertools
import math
import os
import shutil
import sys
from dataclasses import dataclass

from jiff_config import ColorScheme, ColorStyle
from rich.console import Console
from rich.style import Style
from rich.text import Text

from .align import align

console = Console()
debug = os.environ.get("JIFF_DEBUG", "0") == "1"


# =========================
# Diff Types
# =========================


class DiffType(enum.Enum):
    SAME = enum.auto()
    ADD = enum.auto()
    REMOVE = enum.auto()
    REPLACE = enum.auto()

    def __repr__(self) -> str:
        return self.name


@dataclass
class Diff:
    kind: DiffType
    left: str
    right: str | None = None


@dataclass
class DiffStyling:
    same: Style
    add: Style
    add_highlight: Style
    remove: Style
    remove_highlight: Style


def _line_styling(colors: ColorScheme) -> DiffStyling:
    return DiffStyling(
        same=colors.same.rich_style(),
        add=colors.add.rich_style(),
        add_highlight=colors.add_highlight.rich_style(),
        remove=colors.remove.rich_style(),
        remove_highlight=colors.remove_highlight.rich_style(),
    )


def _indicator_style(style: ColorStyle) -> Style:
    if style == ColorStyle():
        return Style()
    return Style(color=style.color, bgcolor=style.bgcolor, bold=True)


def _indicator_styling(colors: ColorScheme) -> DiffStyling:
    # Bold change indicators remain legible beside highlighted text without
    # introducing a second colour scheme for margins and line numbers.
    return DiffStyling(
        same=_indicator_style(colors.same),
        add=_indicator_style(colors.add),
        add_highlight=_indicator_style(colors.add),
        remove=_indicator_style(colors.remove),
        remove_highlight=_indicator_style(colors.remove),
    )


def _colors(color: bool, colors: ColorScheme | None) -> ColorScheme:
    if not color:
        return ColorScheme.plain()
    return colors or ColorScheme.default()


def render_file_header(
    path: str, color: bool = True, colors: ColorScheme | None = None
) -> str:
    """Renders Git-style labels for a repository path."""
    colors = _colors(color, colors)
    with console.capture() as capture:
        console.print(Text(f"--- a/{path}", style=colors.remove.rich_style()))
        console.print(Text(f"+++ b/{path}", style=colors.add.rich_style()))
    return capture.get()


# =========================
# Diff Calculation
# =========================


def calculate_line_diff(left: str, right: str) -> list[Diff]:
    return calculate_diff(left, right, "\n")


def calculate_char_diff(left: str, right: str) -> list[Diff]:
    return calculate_diff(left, right, "")


def calculate_diff(left: str, right: str, split: str) -> list[Diff]:
    if split:
        # An empty file has no lines. `str.split` would otherwise invent one
        # empty line and make additions and deletions look like replacements.
        left_parts = left.split(split) if left else []
        right_parts = right.split(split) if right else []
    else:
        left_parts = list(left)
        right_parts = list(right)

    matcher = difflib.SequenceMatcher(None, left_parts, right_parts)
    diffs: list[Diff] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        l = split.join(left_parts[i1:i2])
        r = split.join(right_parts[j1:j2])

        if tag == "equal":
            diffs.append(Diff(DiffType.SAME, l))
        elif tag == "insert":
            diffs.append(Diff(DiffType.ADD, r))
        elif tag == "delete":
            diffs.append(Diff(DiffType.REMOVE, l))
        elif tag == "replace":
            diffs.append(Diff(DiffType.REPLACE, l, r))

    return diffs


# =========================
# Unified Print
# =========================


def print_diffs(
    diffs: list[Diff], color: bool = True, colors: ColorScheme | None = None
) -> None:
    colors = _colors(color, colors)
    margin_styling = _indicator_styling(colors)
    lines = _line_styling(colors)

    for change in diffs:
        if change.kind == DiffType.SAME:
            for line in change.left.split("\n"):
                console.print(
                    Text("  ", style=margin_styling.same) + Text(line, style=lines.same)
                )

        elif change.kind == DiffType.ADD:
            for line in change.left.split("\n"):
                console.print(
                    Text("+ ", style=margin_styling.add) + Text(line, style=lines.add)
                )

        elif change.kind == DiffType.REMOVE:
            for line in change.left.split("\n"):
                console.print(
                    Text("- ", style=margin_styling.remove)
                    + Text(line, style=lines.remove)
                )

        elif change.kind == DiffType.REPLACE:
            lines_b = change.left.split("\n")
            lines_a = change.right.split("\n")
            alignment = align(lines_b, lines_a)
            text_b = Text()
            text_a = Text()
            for before, after in alignment:
                if before is None and after is not None:
                    text_a.append("+ ", style=margin_styling.add_highlight)
                    text_a.append(after + "\n", style=lines.add_highlight)
                elif before is not None and after is None:
                    text_b.append("- ", style=margin_styling.remove_highlight)
                    text_b.append(before + "\n", style=lines.remove_highlight)
                elif before is not None and after is not None:
                    text_b.append("- ", style=margin_styling.remove_highlight)
                    text_a.append("+ ", style=margin_styling.add_highlight)
                    _style_diff_line(before + "\n", after + "\n", lines, text_b, text_a)
            console.print(text_b, end="")
            console.print(text_a, end="")


def render_diffs(
    diffs: list[Diff], color: bool = True, colors: ColorScheme | None = None
) -> str:
    with console.capture() as capture:
        print_diffs(diffs, color, colors)
    return capture.get()


# =========================
# Character-Level Styling
# =========================


def _style_diff_line(
    before: str,
    after: str,
    styling: DiffStyling,
    before_text: Text,
    after_text: Text,
) -> None:
    for change in calculate_char_diff(before, after):
        if change.kind == DiffType.SAME:
            before_text.append(change.left, style=styling.remove)
            after_text.append(change.left, style=styling.add)
        elif change.kind == DiffType.ADD:
            after_text.append(change.left, style=styling.add_highlight)
        elif change.kind == DiffType.REMOVE:
            before_text.append(change.left, style=styling.remove_highlight)
        elif change.kind == DiffType.REPLACE:
            before_text.append(change.left, style=styling.remove_highlight)
            after_text.append(change.right, style=styling.add_highlight)


# =========================
# Side-by-Side Print
# =========================


def print_diffs_side_by_side(
    diffs: list[Diff],
    max_line_count: int,
    color: bool = True,
    colors: ColorScheme | None = None,
) -> None:
    colors = _colors(color, colors)
    lineno_styling = _indicator_styling(colors)
    lines = _line_styling(colors)

    # Define separator.
    sep = "\u2502"
    sep_width = len(sep)

    # Calculate widths to draw to.
    lineno_width = int(math.log10(max_line_count)) + 1 if max_line_count > 0 else 1
    terminal_width = shutil.get_terminal_size((120, 40)).columns
    line_width = ((terminal_width - sep_width) // 2) - (lineno_width + 2)

    # Print all diffs.
    lineno_l = 1
    lineno_r = 1
    empty_lineno = " " * (lineno_width + 1)
    for change in diffs:
        if debug:
            print(f"Diff: {change}", file=sys.stderr)
        if change.kind == DiffType.SAME:
            for line in change.left.split("\n"):
                lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                _print_side_by_side_line(
                    Text(lineno_l_fmt, style=lineno_styling.same),
                    Text(lineno_r_fmt, style=lineno_styling.same),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(line, style=lines.same),
                    Text(line, style=lines.same),
                    line_width,
                    sep,
                )
                lineno_l += 1
                lineno_r += 1

        elif change.kind == DiffType.ADD:
            for line in change.left.split("\n"):
                lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                _print_side_by_side_line(
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(lineno_r_fmt, style=lineno_styling.add_highlight),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(empty_lineno, style=lineno_styling.add_highlight),
                    Text("", style=lines.same),
                    Text(line, style=lines.add_highlight),
                    line_width,
                    sep,
                )
                lineno_r += 1

        elif change.kind == DiffType.REMOVE:
            for line in change.left.split("\n"):
                lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                _print_side_by_side_line(
                    Text(lineno_l_fmt, style=lineno_styling.remove_highlight),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(empty_lineno, style=lineno_styling.remove_highlight),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(line, style=lines.remove_highlight),
                    Text("", style=lines.same),
                    line_width,
                    sep,
                )
                lineno_l += 1

        elif change.kind == DiffType.REPLACE:
            lines_b = change.left.split("\n")
            lines_a = change.right.split("\n")
            alignment = align(lines_b, lines_a)
            for line_l, line_r in alignment:
                if debug:
                    print(f"  Aligned: {line_l!r}, {line_r!r}", file=sys.stderr)
                if line_l is None and line_r is not None:
                    lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                    _print_side_by_side_line(
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(lineno_r_fmt, style=lineno_styling.add_highlight),
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(empty_lineno, style=lineno_styling.add_highlight),
                        Text("", style=lines.same),
                        Text(line_r, style=lines.add_highlight),
                        line_width,
                        sep,
                    )
                    lineno_r += 1
                elif line_l is not None and line_r is None:
                    lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                    _print_side_by_side_line(
                        Text(lineno_l_fmt, style=lineno_styling.remove_highlight),
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(empty_lineno, style=lineno_styling.remove_highlight),
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(line_l, style=lines.remove_highlight),
                        Text("", style=lines.same),
                        line_width,
                        sep,
                    )
                    lineno_l += 1
                elif line_l is not None and line_r is not None:
                    lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                    lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                    line_l_text = Text()
                    line_r_text = Text()
                    _style_diff_line(line_l, line_r, lines, line_l_text, line_r_text)
                    _print_side_by_side_line(
                        Text(lineno_l_fmt, style=lineno_styling.remove),
                        Text(lineno_r_fmt, style=lineno_styling.add),
                        Text(empty_lineno, style=lineno_styling.remove),
                        Text(empty_lineno, style=lineno_styling.add),
                        line_l_text,
                        line_r_text,
                        line_width,
                        sep,
                    )
                    lineno_l += 1
                    lineno_r += 1


def render_diffs_side_by_side(
    diffs: list[Diff],
    max_line_count: int,
    color: bool = True,
    colors: ColorScheme | None = None,
) -> str:
    with console.capture() as capture:
        print_diffs_side_by_side(diffs, max_line_count, color, colors)
    return capture.get()


def _print_side_by_side_line(
    lineno_l: Text,
    lineno_r: Text,
    wrapno_l: Text,
    wrapno_r: Text,
    line_l: Text,
    line_r: Text,
    line_width: int,
    separator: str,
):
    margin_l = lineno_l
    margin_r = lineno_r
    lines_l = line_l.wrap(None, line_width, tab_size=4)
    lines_r = line_r.wrap(None, line_width, tab_size=4)
    first_iteration = True
    for wrapped_l, wrapped_r in itertools.zip_longest(lines_l, lines_r):
        if wrapped_l is None:
            wrapped_l = Text()
        if wrapped_r is None:
            wrapped_r = Text()
        left_padding = " " * (line_width - len(wrapped_l))
        if not margin_r.plain.strip() and not wrapped_r.plain:
            # A missing right line has no line number or text worth padding.
            console.print(margin_l, " ", wrapped_l, left_padding, separator, sep="")
        else:
            console.print(
                margin_l,
                " ",
                wrapped_l,
                left_padding,
                separator,
                margin_r,
                " ",
                wrapped_r,
                sep="",
            )
        if first_iteration:
            margin_l = wrapno_l
            margin_r = wrapno_r
            first_iteration = False
