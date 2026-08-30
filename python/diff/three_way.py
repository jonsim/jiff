from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from heapq import merge

from jiff_config import ColorScheme
from rich.cells import cell_len
from rich.console import Console
from rich.style import Style
from rich.text import Span, Text
from syntax_highlighting import HighlightedFile

from . import mod as diff_mod
from .align import align
from .mod import DiffStyling, DiffType


@dataclass(frozen=True)
class IndexedLine:
    """A source line with its zero-based index in the original file."""

    index: int
    text: str


@dataclass(frozen=True)
class LinePair:
    """One Local-to-Base or Base-to-Remote alignment row."""

    left: IndexedLine | None
    right: IndexedLine | None


@dataclass(frozen=True)
class ThreeWayLine:
    """A display row anchored by a base line or shared insertion boundary."""

    left: IndexedLine | None
    middle: IndexedLine | None
    right: IndexedLine | None

    def is_unchanged(self) -> bool:
        return (
            self.left is not None
            and self.middle is not None
            and self.right is not None
            and self.left.text == self.middle.text == self.right.text
        )


@dataclass(frozen=True)
class OmittedLines:
    """A run of unchanged lines hidden by the context limit."""

    line_count: int


@dataclass(frozen=True)
class PaneLine:
    """Styled content and margins for one pane of a display row."""

    lineno: Text
    wrapno: Text
    text: Text
    present: bool


def _append_line_pairs(
    pairs: list[LinePair],
    left_index: int,
    right_index: int,
    alignment: Iterable[tuple[str | None, str | None]],
) -> tuple[int, int]:
    for left, right in alignment:
        indexed_left = None
        indexed_right = None
        if left is not None:
            indexed_left = IndexedLine(left_index, left)
            left_index += 1
        if right is not None:
            indexed_right = IndexedLine(right_index, right)
            right_index += 1
        pairs.append(LinePair(indexed_left, indexed_right))
    return left_index, right_index


def _aligned_lines(left: str, right: str) -> list[LinePair]:
    pairs: list[LinePair] = []
    left_index = 0
    right_index = 0

    for change in diff_mod.calculate_line_diff(left, right):
        if change.kind == DiffType.SAME:
            alignment = ((line, line) for line in change.left.split("\n"))
        elif change.kind == DiffType.ADD:
            alignment = ((None, line) for line in change.left.split("\n"))
        elif change.kind == DiffType.REMOVE:
            alignment = ((line, None) for line in change.left.split("\n"))
        elif change.kind == DiffType.REPLACE:
            alignment = align(change.left.split("\n"), change.right.split("\n"))
        else:
            raise AssertionError("unlimited line diffs contain no omissions")
        left_index, right_index = _append_line_pairs(
            pairs, left_index, right_index, alignment
        )

    return pairs


def _take_left_only(
    pairs: list[LinePair], cursor: int
) -> tuple[list[IndexedLine], int]:
    lines = []
    while cursor < len(pairs) and pairs[cursor].right is None:
        line = pairs[cursor].left
        if line is None:
            raise AssertionError("an aligned row cannot omit both sides")
        lines.append(line)
        cursor += 1
    return lines, cursor


def _take_right_only(
    pairs: list[LinePair], cursor: int
) -> tuple[list[IndexedLine], int]:
    lines = []
    while cursor < len(pairs) and pairs[cursor].left is None:
        line = pairs[cursor].right
        if line is None:
            raise AssertionError("an aligned row cannot omit both sides")
        lines.append(line)
        cursor += 1
    return lines, cursor


def _append_outer_lines(
    rows: list[ThreeWayLine],
    left: list[IndexedLine],
    right: list[IndexedLine],
) -> None:
    # Put insertions at the same base-file boundary on one row. That doesn't
    # mean the outer lines match; it just keeps the three panes compact.
    line_count = max(len(left), len(right))
    rows.extend(
        ThreeWayLine(
            left[index] if index < len(left) else None,
            None,
            right[index] if index < len(right) else None,
        )
        for index in range(line_count)
    )


def _three_way_lines(left: str, middle: str, right: str) -> list[ThreeWayLine]:
    left_pairs = _aligned_lines(left, middle)
    right_pairs = _aligned_lines(middle, right)
    middle_line_count = len(middle.split("\n")) if middle else 0
    left_cursor = 0
    right_cursor = 0
    rows: list[ThreeWayLine] = []

    for middle_index in range(middle_line_count):
        # Each pairwise diff puts outer-only rows just before the next base
        # line. Bring both sides together before adding that base line.
        left_only, left_cursor = _take_left_only(left_pairs, left_cursor)
        right_only, right_cursor = _take_right_only(right_pairs, right_cursor)
        _append_outer_lines(rows, left_only, right_only)

        left_pair = left_pairs[left_cursor]
        right_pair = right_pairs[right_cursor]
        middle_line = left_pair.right
        if middle_line is None or right_pair.left != middle_line:
            raise AssertionError("pairwise alignments disagree on the middle file")
        if middle_line.index != middle_index:
            raise AssertionError("middle-file lines are out of order")
        rows.append(ThreeWayLine(left_pair.left, middle_line, right_pair.right))
        left_cursor += 1
        right_cursor += 1

    left_only, left_cursor = _take_left_only(left_pairs, left_cursor)
    right_only, right_cursor = _take_right_only(right_pairs, right_cursor)
    _append_outer_lines(rows, left_only, right_only)
    if left_cursor != len(left_pairs) or right_cursor != len(right_pairs):
        raise AssertionError("pairwise alignment was not fully consumed")
    return rows


def _limit_context(
    lines: list[ThreeWayLine], context_lines: int
) -> list[ThreeWayLine | OmittedLines]:
    keep = [False] * len(lines)

    # Make one pass in each direction so a change on either outer side keeps
    # nearby context. A single pairwise pass would miss the other side.
    distance = len(lines) + 1
    for index, line in enumerate(lines):
        distance = distance + 1 if line.is_unchanged() else 0
        keep[index] = distance <= context_lines
    distance = len(lines) + 1
    for index in range(len(lines) - 1, -1, -1):
        distance = distance + 1 if lines[index].is_unchanged() else 0
        keep[index] |= distance <= context_lines

    rows: list[ThreeWayLine | OmittedLines] = []
    omitted = 0
    for line, retain in zip(lines, keep, strict=True):
        if not retain:
            omitted += 1
            continue
        if omitted:
            rows.append(OmittedLines(omitted))
            omitted = 0
        rows.append(line)
    if omitted:
        rows.append(OmittedLines(omitted))
    return rows


def _merge_middle_spans(
    from_left: list[Span],
    from_right: list[Span],
    overlap: Style,
) -> list[Span]:
    # Both span lists are already ordered and non-overlapping. Merge their
    # boundary streams and advance through each list once; rescanning the full
    # lists for every small changed region is painfully slow on minified text.
    boundaries = list(
        dict.fromkeys(
            merge(
                (boundary for span in from_left for boundary in (span.start, span.end)),
                (
                    boundary
                    for span in from_right
                    for boundary in (span.start, span.end)
                ),
            )
        )
    )
    merged: list[Span] = []
    left_index = 0
    right_index = 0
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        while left_index < len(from_left) and from_left[left_index].end <= start:
            left_index += 1
        while right_index < len(from_right) and from_right[right_index].end <= start:
            right_index += 1

        left_span = from_left[left_index] if left_index < len(from_left) else None
        right_span = from_right[right_index] if right_index < len(from_right) else None
        left_style = (
            left_span.style
            if left_span is not None and left_span.start <= start < left_span.end
            else None
        )
        right_style = (
            right_span.style
            if right_span is not None and right_span.start <= start < right_span.end
            else None
        )
        if left_style is not None and not isinstance(left_style, Style):
            raise AssertionError("three-way spans must contain resolved styles")
        if right_style is not None and not isinstance(right_style, Style):
            raise AssertionError("three-way spans must contain resolved styles")
        if left_style is not None and right_style is not None:
            style = overlap
        elif left_style is not None:
            style = left_style
        elif right_style is not None:
            style = right_style
        else:
            continue

        if merged and merged[-1].end == start and merged[-1].style == style:
            merged[-1] = Span(merged[-1].start, end, style)
        else:
            merged.append(Span(start, end, style))
    return merged


def _full_line_span(line: IndexedLine, style: Style) -> list[Span]:
    return [Span(0, len(line.text), style)] if line.text else []


def _style_three_way_line(
    line: ThreeWayLine,
    colors: ColorScheme,
    highlighting: tuple[HighlightedFile, HighlightedFile, HighlightedFile],
) -> tuple[Text, Text, Text]:
    styling = diff_mod._line_styling(colors)

    if line.left is not None and line.middle is not None:
        if line.left.text == line.middle.text:
            left = highlighting[0].render_line(
                line.left.index, line.left.text, styling.same
            )
            middle_from_left = []
        else:
            left_spans, middle_from_left = diff_mod._line_diff_spans(
                line.left.text, line.middle.text, styling
            )
            left = highlighting[0].render_line(
                line.left.index, line.left.text, styling.remove, left_spans
            )
    elif line.left is not None:
        left = highlighting[0].render_line(
            line.left.index, line.left.text, styling.remove_highlight
        )
        middle_from_left = []
    elif line.middle is not None:
        left = Text("", style=styling.same)
        middle_from_left = _full_line_span(line.middle, styling.add_highlight)
    else:
        left = Text("", style=styling.same)
        middle_from_left = []

    if line.middle is not None and line.right is not None:
        if line.middle.text == line.right.text:
            middle_from_right = []
            right = highlighting[2].render_line(
                line.right.index, line.right.text, styling.same
            )
        else:
            middle_from_right, right_spans = diff_mod._line_diff_spans(
                line.middle.text, line.right.text, styling
            )
            right = highlighting[2].render_line(
                line.right.index, line.right.text, styling.add, right_spans
            )
    elif line.middle is not None:
        middle_from_right = _full_line_span(line.middle, styling.remove_highlight)
        right = Text("", style=styling.same)
    elif line.right is not None:
        middle_from_right = []
        right = highlighting[2].render_line(
            line.right.index, line.right.text, styling.add_highlight
        )
    else:
        middle_from_right = []
        right = Text("", style=styling.same)

    if line.middle is None:
        middle = Text("", style=styling.same)
    else:
        middle_spans = _merge_middle_spans(
            middle_from_left,
            middle_from_right,
            colors.overlap_highlight.rich_style(),
        )
        middle = highlighting[1].render_line(
            line.middle.index, line.middle.text, styling.same, middle_spans
        )
    return left, middle, right


def _margin_styles(
    line: ThreeWayLine, styling: DiffStyling
) -> tuple[Style, Style, Style]:
    if line.left is not None and line.middle is not None:
        left = styling.same if line.left.text == line.middle.text else styling.remove
    elif line.left is not None:
        left = styling.remove_highlight
    else:
        left = styling.same

    if line.middle is not None and line.right is not None:
        right = styling.same if line.middle.text == line.right.text else styling.add
    elif line.right is not None:
        right = styling.add_highlight
    else:
        right = styling.same
    return left, styling.same, right


def _render_line(
    output_console: Console,
    panes: tuple[PaneLine, PaneLine, PaneLine],
    width: int,
) -> None:
    separator = "\u2502"
    wrapped = [diff_mod._hard_wrap(pane.text, width) for pane in panes]
    height = max(len(lines) for lines in wrapped)

    for row_index in range(height):
        row = Text()
        for pane_index in range(2):
            pane = panes[pane_index]
            margin = pane.lineno if row_index == 0 else pane.wrapno
            content = (
                wrapped[pane_index][row_index]
                if row_index < len(wrapped[pane_index])
                else Text()
            )
            row.append_text(margin)
            row.append(" ")
            row.append_text(content)
            row.append(" " * (width - cell_len(content.plain)))
            row.append(separator)

        right = panes[2]
        if right.present and row_index < len(wrapped[2]):
            margin = right.lineno if row_index == 0 else right.wrapno
            content = wrapped[2][row_index]
            row.append_text(margin)
            if content.plain:
                row.append(" ")
                row.append_text(content)
        output_console.print(row, soft_wrap=True)


def _line_width(terminal_width: int, lineno_width: int) -> int:
    fixed_width = 2 + 3 * (lineno_width + 2)
    return max((terminal_width - fixed_width) // 3, 1)


def render_three_way_side_by_side(
    contents: tuple[str, str, str],
    labels: tuple[str, str, str],
    color: bool = True,
    colors: ColorScheme | None = None,
    highlighting: tuple[HighlightedFile, HighlightedFile, HighlightedFile]
    | None = None,
    context_lines: int | None = None,
    terminal_width: int | None = None,
) -> str:
    """Renders two pairwise alignments as three panes around their shared input."""
    colors = diff_mod._colors(color, colors)
    highlighting = highlighting or (
        HighlightedFile(),
        HighlightedFile(),
        HighlightedFile(),
    )
    lines = _three_way_lines(*contents)
    rows: list[ThreeWayLine | OmittedLines]
    if context_lines is None:
        rows = list(lines)
    else:
        rows = _limit_context(lines, context_lines)

    max_line_count = max(
        (len(content.split("\n")) if content else 0 for content in contents),
        default=0,
    )
    lineno_width = max(len(str(max_line_count)), 1)
    empty_lineno = " " * (lineno_width + 1)
    if terminal_width is None:
        terminal_width = diff_mod._terminal_width()
    line_width = _line_width(terminal_width, lineno_width)
    line_styling = diff_mod._line_styling(colors)
    margin_styling = diff_mod._indicator_styling(colors)

    output_console = diff_mod._console(color)
    with output_console.capture() as capture:
        headings = tuple(
            Text(f"{index}: {label}", style=line_styling.same)
            for index, label in enumerate(labels, start=1)
        )
        heading_margin = Text(empty_lineno, style=margin_styling.same)
        _render_line(
            output_console,
            tuple(
                PaneLine(
                    heading_margin.copy(),
                    heading_margin.copy(),
                    heading,
                    True,
                )
                for heading in headings
            ),
            line_width,
        )

        for row in rows:
            if isinstance(row, OmittedLines):
                message = Text(
                    diff_mod._omission_text(row.line_count),
                    style=line_styling.omitted,
                )
                margin = Text(empty_lineno, style=margin_styling.same)
                _render_line(
                    output_console,
                    tuple(
                        PaneLine(margin.copy(), margin.copy(), message.copy(), True)
                        for _ in range(3)
                    ),
                    line_width,
                )
                continue

            rendered = _style_three_way_line(row, colors, highlighting)
            styles = _margin_styles(row, margin_styling)
            source_lines = (row.left, row.middle, row.right)
            panes = []
            for source_line, text, style in zip(
                source_lines, rendered, styles, strict=True
            ):
                number = (
                    f"{source_line.index + 1:>{lineno_width}}:"
                    if source_line is not None
                    else empty_lineno
                )
                panes.append(
                    PaneLine(
                        Text(number, style=style),
                        Text(empty_lineno, style=style),
                        text,
                        source_line is not None,
                    )
                )
            _render_line(output_console, tuple(panes), line_width)
    return capture.get()
