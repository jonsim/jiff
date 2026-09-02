from __future__ import annotations

import enum
import itertools
import math
import os
import sys
from dataclasses import dataclass

from jiff_config import ColorScheme, ColorStyle
from rich.cells import cell_len, chop_cells
from rich.console import Console
from rich.style import Style
from rich.text import Span, Text
from syntax_highlighting import HighlightedFile, HighlightedFiles

from .align import align
from .myers import EditKind, calculate_edits

debug = os.environ.get("JIFF_DEBUG", "0") == "1"


def _console(color: bool) -> Console:
    # By this point the CLI has already decided whether colour is safe. Give
    # Rich the answer directly so embedded renders don't inherit terminal state.
    return Console(force_terminal=color)


def _terminal_width() -> int:
    try:
        columns = int(os.environ.get("COLUMNS", ""))
        if columns > 0:
            return columns
    except ValueError:
        pass

    # Git may pipe stdout to its pager while stdin or stderr still points at
    # the terminal. Try those before falling back to 120 columns.
    for stream in (sys.__stdout__, sys.__stdin__, sys.__stderr__):
        try:
            return os.get_terminal_size(stream.fileno()).columns
        except (AttributeError, OSError, ValueError):
            continue
    return 120


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
    """One contiguous region in a text diff.

    ``SAME``, ``ADD`` and ``REMOVE`` store their text in ``left``.
    ``REPLACE`` stores the before and after text in ``left`` and ``right``.
    ``OMITTED`` leaves both text fields empty and records the hidden line count.
    """

    kind: DiffType
    left: str = ""
    right: str | None = None
    # Only OMITTED uses this; those lines aren't present in either text field.
    omitted_lines: int = 0


@dataclass
class DiffStyling:
    """Resolved Rich styles for every kind of diff text."""

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
    rich_style = style.rich_style()
    return Style(color=rich_style.color, bgcolor=rich_style.bgcolor, bold=True)


def _indicator_styling(colors: ColorScheme) -> DiffStyling:
    # Bold indicators are easier to pick out beside highlighted text. Reuse the
    # line colours rather than inventing another palette for the margins.
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
    output_console = _console(color)
    with output_console.capture() as capture:
        output_console.print(Text(f"--- a/{path}", style=colors.remove.rich_style()))
        output_console.print(Text(f"+++ b/{path}", style=colors.add.rich_style()))
    return capture.get()


# =========================
# Diff Calculation
# =========================


def calculate_line_diff(left: str, right: str) -> list[Diff]:
    """Calculates contiguous changes between newline-separated source lines."""
    return calculate_diff(left, right, "\n")


def calculate_char_diff(left: str, right: str) -> list[Diff]:
    return _coalesce_dissimilar_middle(calculate_diff(left, right, ""))


def _coalesce_dissimilar_middle(changes: list[Diff]) -> list[Diff]:
    if len(changes) < 2:
        return changes

    # The first and last matches are good anchors. Check the bit between them
    # on its own, otherwise a long prefix can make random character matches
    # look meaningful.
    prefix = changes[:1] if changes[0].kind == DiffType.SAME else []
    suffix = changes[-1:] if changes[-1].kind == DiffType.SAME else []
    middle = changes[len(prefix) : len(changes) - len(suffix)]
    replacement = _dissimilar_replacement(middle, coalesce_phrases=False)
    if replacement is not None:
        return prefix + [replacement] + suffix

    # A real common phrase can still hide a noisy replacement inside it. Use
    # matches of three or more characters as anchors, then check the gaps again.
    refined: list[Diff] = []
    region: list[Diff] = []
    for change in middle:
        if change.kind == DiffType.SAME and len(change.left) >= 3:
            replacement = _dissimilar_replacement(region, coalesce_phrases=True)
            refined.extend([replacement] if replacement is not None else region)
            refined.append(change)
            region = []
        else:
            region.append(change)
    replacement = _dissimilar_replacement(region, coalesce_phrases=True)
    refined.extend([replacement] if replacement is not None else region)
    return prefix + refined + suffix


def _dissimilar_replacement(changes: list[Diff], coalesce_phrases: bool) -> Diff | None:
    """Collapses a region whose internal matches are too fragmented."""
    before = ""
    after = ""
    matched_characters = 0

    for change in changes:
        if change.kind == DiffType.SAME:
            matched_characters += len(change.left)
            before += change.left
            after += change.left
        elif change.kind == DiffType.ADD:
            after += change.left
        elif change.kind == DiffType.REMOVE:
            before += change.left
        elif change.kind == DiffType.REPLACE:
            before += change.left
            after += change.right or ""
        elif change.kind == DiffType.OMITTED:
            raise AssertionError("character diffs are never context-limited")

    fragmented_phrase = (
        coalesce_phrases
        and any(character.isspace() for character in before)
        and any(character.isspace() for character in after)
    )
    if (
        before
        and after
        and (matched_characters * 3 < max(len(before), len(after)) or fragmented_phrase)
    ):
        return Diff(DiffType.REPLACE, before, after)
    return None


def calculate_diff(left: str, right: str, split: str) -> list[Diff]:
    if split:
        # An empty file has no lines. `str.split` would otherwise invent one
        # empty line and make additions and deletions look like replacements.
        left_parts = left.split(split) if left else []
        right_parts = right.split(split) if right else []
    else:
        left_parts = list(left)
        right_parts = list(right)

    diffs: list[Diff] = []
    same: list[str] = []
    removed: list[str] = []
    added: list[str] = []

    def flush_same() -> None:
        if same:
            diffs.append(Diff(DiffType.SAME, split.join(same)))
            same.clear()

    def flush_change() -> None:
        if removed and added:
            diffs.append(Diff(DiffType.REPLACE, split.join(removed), split.join(added)))
        elif removed:
            diffs.append(Diff(DiffType.REMOVE, split.join(removed)))
        elif added:
            diffs.append(Diff(DiffType.ADD, split.join(added)))
        removed.clear()
        added.clear()

    # Myers may alternate additions and removals. Keep everything between two
    # matches in one replacement so the line aligner sees the whole block.
    for edit in calculate_edits(left_parts, right_parts):
        if edit.kind == EditKind.SAME:
            flush_change()
            same.append(edit.value)
        elif edit.kind == EditKind.REMOVE:
            flush_same()
            removed.append(edit.value)
        else:
            flush_same()
            added.append(edit.value)

    flush_same()
    flush_change()
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
        # At either end, only keep context on the side facing a change.
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
    *,
    output_console: Console,
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
                output_console.print(
                    Text("  ", style=margin_styling.same)
                    + highlighting.right.render_line(right_index, line, lines.same)
                )
                left_index += 1
                right_index += 1

        elif change.kind == DiffType.ADD:
            for line in change.left.split("\n"):
                output_console.print(
                    Text("+ ", style=margin_styling.add)
                    + highlighting.right.render_line(right_index, line, lines.add)
                )
                right_index += 1

        elif change.kind == DiffType.REMOVE:
            for line in change.left.split("\n"):
                output_console.print(
                    Text("- ", style=margin_styling.remove)
                    + highlighting.left.render_line(left_index, line, lines.remove)
                )
                left_index += 1

        elif change.kind == DiffType.OMITTED:
            output_console.print(
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
            output_console.print(text_b, end="")
            output_console.print(text_a, end="")


def render_diffs(
    diffs: list[Diff],
    color: bool = True,
    colors: ColorScheme | None = None,
    highlighting: HighlightedFiles | None = None,
) -> str:
    """Renders calculated changes as one unified stream."""
    output_console = _console(color)
    with output_console.capture() as capture:
        print_diffs(
            diffs,
            color,
            colors,
            highlighting,
            output_console=output_console,
        )
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
    before_spans, after_spans = _line_diff_spans(before, after, styling)
    before_line = before_highlighting.render_line(
        before_index, before, styling.remove, before_spans
    )
    after_line = after_highlighting.render_line(
        after_index, after, styling.add, after_spans
    )

    before_text.append_text(before_line)
    after_text.append_text(after_line)


def _line_diff_spans(
    before: str,
    after: str,
    styling: DiffStyling,
) -> tuple[list[Span], list[Span]]:
    """Returns the changed character spans for both versions of a line."""
    before_spans: list[Span] = []
    after_spans: list[Span] = []
    before_offset = 0
    after_offset = 0

    for change in calculate_char_diff(before, after):
        if change.kind == DiffType.SAME:
            before_offset += len(change.left)
            after_offset += len(change.left)
        elif change.kind == DiffType.ADD:
            end = after_offset + len(change.left)
            after_spans.append(Span(after_offset, end, styling.add_highlight))
            after_offset = end
        elif change.kind == DiffType.REMOVE:
            end = before_offset + len(change.left)
            before_spans.append(Span(before_offset, end, styling.remove_highlight))
            before_offset = end
        elif change.kind == DiffType.REPLACE:
            before_end = before_offset + len(change.left)
            after_end = after_offset + len(change.right)
            before_spans.append(
                Span(before_offset, before_end, styling.remove_highlight)
            )
            after_spans.append(Span(after_offset, after_end, styling.add_highlight))
            before_offset = before_end
            after_offset = after_end
        elif change.kind == DiffType.OMITTED:
            raise AssertionError("character diffs are never context-limited")

    return before_spans, after_spans


# =========================
# Side-by-Side Print
# =========================


def print_diffs_side_by_side(
    diffs: list[Diff],
    max_line_count: int,
    color: bool = True,
    colors: ColorScheme | None = None,
    highlighting: HighlightedFiles | None = None,
    terminal_width: int | None = None,
    *,
    output_console: Console,
) -> None:
    colors = _colors(color, colors)
    lineno_styling = _indicator_styling(colors)
    lines = _line_styling(colors)
    highlighting = highlighting or HighlightedFiles()

    sep = "\u2502"
    sep_width = len(sep)

    lineno_width = int(math.log10(max_line_count)) + 1 if max_line_count > 0 else 1
    if terminal_width is None:
        terminal_width = _terminal_width()
    line_width = max(((terminal_width - sep_width) // 2) - (lineno_width + 2), 1)

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
                    output_console,
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
                    output_console,
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
                    output_console,
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
                output_console,
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
                        output_console,
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
                        output_console,
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
                        output_console,
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
    terminal_width: int | None = None,
) -> str:
    """Renders calculated changes in two terminal-width panes."""
    output_console = _console(color)
    with output_console.capture() as capture:
        print_diffs_side_by_side(
            diffs,
            max_line_count,
            color,
            colors,
            highlighting,
            terminal_width,
            output_console=output_console,
        )
    return capture.get()


def _print_side_by_side_line(
    output_console: Console,
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
    lines_l = _hard_wrap(line_l, line_width)
    lines_r = _hard_wrap(line_r, line_width)
    first_iteration = True
    for wrapped_l, wrapped_r in itertools.zip_longest(lines_l, lines_r):
        if wrapped_l is None:
            wrapped_l = Text()
        if wrapped_r is None:
            wrapped_r = Text()
        left_padding = " " * (line_width - cell_len(wrapped_l.plain))
        if not margin_r.plain.strip() and not wrapped_r.plain:
            # There's nothing useful after the separator for a missing line.
            output_console.print(
                margin_l,
                " ",
                wrapped_l,
                left_padding,
                separator,
                sep="",
                soft_wrap=True,
            )
        else:
            output_console.print(
                margin_l,
                " ",
                wrapped_l,
                left_padding,
                separator,
                margin_r,
                " ",
                wrapped_r,
                sep="",
                soft_wrap=True,
            )
        if first_iteration:
            margin_l = wrapno_l
            margin_r = wrapno_r
            first_iteration = False


def _hard_wrap(line: Text, width: int) -> list[Text]:
    # Side-by-side columns are fixed-width panes rather than paragraphs. Split
    # at the pane edge so Python and Rust do not move words independently.
    line = line.copy()
    line.expand_tabs(4)
    chunks = chop_cells(line.plain, max(width, 1))
    if not chunks:
        return [Text()]

    offset = 0
    offsets = []
    for chunk in chunks[:-1]:
        offset += len(chunk)
        offsets.append(offset)
    return list(line.divide(offsets))
