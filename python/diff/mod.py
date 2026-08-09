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
from syntax_highlighting import HighlightedFile, HighlightedFiles

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
    OMITTED = enum.auto()

    def __repr__(self) -> str:
        return self.name


@dataclass
class Diff:
    kind: DiffType
    left: str = ""
    right: str | None = None
    # Only OMITTED diffs set this; their source lines are deliberately absent.
    omitted_lines: int = 0


@dataclass
class DiffStyling:
    same: Style
    omitted: Style
    add: Style
    add_highlight: Style
    remove: Style
    remove_highlight: Style


def _line_styling(colors: ColorScheme) -> DiffStyling:
    return DiffStyling(
        same=colors.same.rich_style(),
        omitted=colors.omitted.rich_style(),
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
        omitted=_indicator_style(colors.omitted),
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


def limit_context(diffs: list[Diff], context_lines: int) -> list[Diff]:
    """Limits unchanged regions to the requested lines around each change.

    Omitted regions retain their line count so side-by-side output can continue
    with the real source line numbers after each gap.
    """
    limited: list[Diff] = []
    for index, change in enumerate(diffs):
        if change.kind != DiffType.SAME:
            limited.append(change)
            continue

        lines = change.left.split("\n")
        # A leading unchanged region only contributes lines before the first
        # change; a trailing region only contributes lines after the last.
        prefix_count = min(context_lines, len(lines)) if index > 0 else 0
        suffix_count = (
            min(context_lines, len(lines) - prefix_count)
            if index + 1 < len(diffs)
            else 0
        )
        omitted_count = len(lines) - prefix_count - suffix_count

        if not omitted_count:
            limited.append(change)
            continue
        if prefix_count:
            limited.append(Diff(DiffType.SAME, "\n".join(lines[:prefix_count])))
        limited.append(Diff(DiffType.OMITTED, omitted_lines=omitted_count))
        if suffix_count:
            limited.append(Diff(DiffType.SAME, "\n".join(lines[-suffix_count:])))

    return limited


def _omission_text(line_count: int) -> str:
    noun = "line" if line_count == 1 else "lines"
    return f"... {line_count} unchanged {noun} ..."


# =========================
# Unified Print
# =========================


def print_diffs(
    diffs: list[Diff],
    color: bool = True,
    colors: ColorScheme | None = None,
    highlighting: HighlightedFiles | None = None,
) -> None:
    colors = _colors(color, colors)
    margin_styling = _indicator_styling(colors)
    lines = _line_styling(colors)
    highlighting = highlighting or HighlightedFiles()
    left_index = 0
    right_index = 0

    for change in diffs:
        if change.kind == DiffType.SAME:
            for line in change.left.split("\n"):
                console.print(
                    Text("  ", style=margin_styling.same)
                    + highlighting.right.render_line(right_index, line, lines.same)
                )
                left_index += 1
                right_index += 1

        elif change.kind == DiffType.ADD:
            for line in change.left.split("\n"):
                console.print(
                    Text("+ ", style=margin_styling.add)
                    + highlighting.right.render_line(right_index, line, lines.add)
                )
                right_index += 1

        elif change.kind == DiffType.REMOVE:
            for line in change.left.split("\n"):
                console.print(
                    Text("- ", style=margin_styling.remove)
                    + highlighting.left.render_line(left_index, line, lines.remove)
                )
                left_index += 1

        elif change.kind == DiffType.OMITTED:
            console.print(
                Text("  ", style=margin_styling.same)
                + Text(_omission_text(change.omitted_lines), style=lines.omitted)
            )
            left_index += change.omitted_lines
            right_index += change.omitted_lines

        elif change.kind == DiffType.REPLACE:
            lines_b = change.left.split("\n")
            lines_a = change.right.split("\n")
            alignment = align(lines_b, lines_a)
            text_b = Text()
            text_a = Text()
            for before, after in alignment:
                if before is None and after is not None:
                    text_a.append("+ ", style=margin_styling.add_highlight)
                    text_a.append_text(
                        highlighting.right.render_line(
                            right_index, after, lines.add_highlight
                        )
                    )
                    text_a.append("\n")
                    right_index += 1
                elif before is not None and after is None:
                    text_b.append("- ", style=margin_styling.remove_highlight)
                    text_b.append_text(
                        highlighting.left.render_line(
                            left_index, before, lines.remove_highlight
                        )
                    )
                    text_b.append("\n")
                    left_index += 1
                elif before is not None and after is not None:
                    text_b.append("- ", style=margin_styling.remove_highlight)
                    text_a.append("+ ", style=margin_styling.add_highlight)
                    _style_diff_line(
                        before,
                        after,
                        lines,
                        text_b,
                        text_a,
                        highlighting.left,
                        highlighting.right,
                        left_index,
                        right_index,
                    )
                    text_b.append("\n")
                    text_a.append("\n")
                    left_index += 1
                    right_index += 1
            console.print(text_b, end="")
            console.print(text_a, end="")


def render_diffs(
    diffs: list[Diff],
    color: bool = True,
    colors: ColorScheme | None = None,
    highlighting: HighlightedFiles | None = None,
) -> str:
    with console.capture() as capture:
        print_diffs(diffs, color, colors, highlighting)
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
    before_highlighting: HighlightedFile,
    after_highlighting: HighlightedFile,
    before_index: int,
    after_index: int,
) -> None:
    before_line = before_highlighting.render_line(before_index, before, styling.remove)
    after_line = after_highlighting.render_line(after_index, after, styling.add)
    before_offset = 0
    after_offset = 0

    for change in calculate_char_diff(before, after):
        if change.kind == DiffType.SAME:
            before_offset += len(change.left)
            after_offset += len(change.left)
        elif change.kind == DiffType.ADD:
            end = after_offset + len(change.left)
            after_line.stylize(styling.add_highlight, after_offset, end)
            after_offset = end
        elif change.kind == DiffType.REMOVE:
            end = before_offset + len(change.left)
            before_line.stylize(styling.remove_highlight, before_offset, end)
            before_offset = end
        elif change.kind == DiffType.REPLACE:
            before_end = before_offset + len(change.left)
            after_end = after_offset + len(change.right)
            before_line.stylize(styling.remove_highlight, before_offset, before_end)
            after_line.stylize(styling.add_highlight, after_offset, after_end)
            before_offset = before_end
            after_offset = after_end
        elif change.kind == DiffType.OMITTED:
            raise AssertionError("character diffs are never context-limited")

    before_text.append_text(before_line)
    after_text.append_text(after_line)


# =========================
# Side-by-Side Print
# =========================


def print_diffs_side_by_side(
    diffs: list[Diff],
    max_line_count: int,
    color: bool = True,
    colors: ColorScheme | None = None,
    highlighting: HighlightedFiles | None = None,
) -> None:
    colors = _colors(color, colors)
    lineno_styling = _indicator_styling(colors)
    lines = _line_styling(colors)
    highlighting = highlighting or HighlightedFiles()

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
                    highlighting.left.render_line(lineno_l - 1, line, lines.same),
                    highlighting.right.render_line(lineno_r - 1, line, lines.same),
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
                    highlighting.right.render_line(
                        lineno_r - 1, line, lines.add_highlight
                    ),
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
                    highlighting.left.render_line(
                        lineno_l - 1, line, lines.remove_highlight
                    ),
                    Text("", style=lines.same),
                    line_width,
                    sep,
                )
                lineno_l += 1

        elif change.kind == DiffType.OMITTED:
            message = Text(_omission_text(change.omitted_lines), style=lines.omitted)
            _print_side_by_side_line(
                Text(empty_lineno, style=lineno_styling.same),
                Text(empty_lineno, style=lineno_styling.same),
                Text(empty_lineno, style=lineno_styling.same),
                Text(empty_lineno, style=lineno_styling.same),
                message,
                message.copy(),
                line_width,
                sep,
            )
            lineno_l += change.omitted_lines
            lineno_r += change.omitted_lines

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
                        highlighting.right.render_line(
                            lineno_r - 1, line_r, lines.add_highlight
                        ),
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
                        highlighting.left.render_line(
                            lineno_l - 1, line_l, lines.remove_highlight
                        ),
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
                    _style_diff_line(
                        line_l,
                        line_r,
                        lines,
                        line_l_text,
                        line_r_text,
                        highlighting.left,
                        highlighting.right,
                        lineno_l - 1,
                        lineno_r - 1,
                    )
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
    highlighting: HighlightedFiles | None = None,
) -> str:
    with console.capture() as capture:
        print_diffs_side_by_side(diffs, max_line_count, color, colors, highlighting)
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
