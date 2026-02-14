from dataclasses import dataclass
from typing import List, Optional, Tuple

import difflib
import enum
import itertools
import math
import os
import shutil
import sys

from rich.console import Console
from rich.text import Text
from rich.style import Style

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
    right: Optional[str] = None


@dataclass
class DiffStyling:
    same: Style
    add: Style
    add_highlight: Style
    remove: Style
    remove_highlight: Style


# =========================
# Diff Calculation
# =========================

def calculate_line_diff(left: str, right: str) -> List[Diff]:
    return calculate_diff(left, right, "\n")


def calculate_char_diff(left: str, right: str) -> List[Diff]:
    return calculate_diff(left, right, "")


def calculate_diff(left: str, right: str, split: str) -> List[Diff]:
    if split:
        left_parts = left.split(split)
        right_parts = right.split(split)
    else:
        left_parts = list(left)
        right_parts = list(right)

    matcher = difflib.SequenceMatcher(None, left_parts, right_parts)
    diffs: List[Diff] = []

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

def print_diffs(diffs: List[Diff]) -> None:
    # Define styling constants.
    margin_styling = DiffStyling(
        same             = Style(),
        add              = Style(),
        add_highlight    = Style(),
        remove           = Style(),
        remove_highlight = Style(),
    )
    line_styling = DiffStyling(
        same             = Style(),
        add              = Style(color="green"),
        add_highlight    = Style(color="black", bgcolor="green"),
        remove           = Style(color="red"),
        remove_highlight = Style(color="black", bgcolor="red"),
    )

    for change in diffs:
        if change.kind == DiffType.SAME:
            for line in change.left.split("\n"):
                console.print(Text("  ", style=margin_styling.same) +
                              Text(line, style=line_styling.same))

        elif change.kind == DiffType.ADD:
            for line in change.left.split("\n"):
                console.print(Text("+ ", style=margin_styling.add) +
                              Text(line, style=line_styling.add))

        elif change.kind == DiffType.REMOVE:
            for line in change.left.split("\n"):
                console.print(Text("- ", style=margin_styling.remove) +
                              Text(line, style=line_styling.remove))

        elif change.kind == DiffType.REPLACE:
            lines_b = change.left.split("\n")
            lines_a = change.right.split("\n")
            alignment = align(lines_b, lines_a)
            text_b = Text()
            text_a = Text()
            for before, after in alignment:
                if before is None and after is not None:
                    text_a.append("+ ",          style=margin_styling.add_highlight)
                    text_a.append(after + "\n",  style=line_styling.add_highlight)
                elif before is not None and after is None:
                    text_b.append("- ",          style=margin_styling.remove_highlight)
                    text_b.append(before + "\n", style=line_styling.remove_highlight)
                elif before is not None and after is not None:
                    text_b.append("- ",          style=margin_styling.remove_highlight)
                    text_a.append("+ ",          style=margin_styling.add_highlight)
                    _style_diff_line(before + "\n", after + "\n", line_styling, text_b, text_a)
            console.print(text_b, end="")
            console.print(text_a, end="")


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

def print_diffs_side_by_side(diffs: List[Diff], max_line_count: int):
    # Define styling constants.
    lineno_styling = DiffStyling(
        same             = Style(color="black", bold=True),
        add              = Style(color="green", bold=True),
        add_highlight    = Style(color="green", bold=True),
        remove           = Style(color="red",   bold=True),
        remove_highlight = Style(color="red",   bold=True),
    )
    line_styling = DiffStyling(
        same             = Style(color="black"),
        add              = Style(color="color(157)"),
        add_highlight    = Style(color="color(157)", reverse=True),
        remove           = Style(color="color(217)"),
        remove_highlight = Style(color="color(217)", reverse=True),
    )

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
        if debug: print(f"Diff: {change}", file=sys.stderr)
        if change.kind == DiffType.SAME:
            for line in change.left.split("\n"):
                lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                _print_side_by_side_line(
                    Text(lineno_l_fmt, style=lineno_styling.same),
                    Text(lineno_r_fmt, style=lineno_styling.same),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(empty_lineno, style=lineno_styling.same),
                    Text(line,         style=line_styling.same),
                    Text(line,         style=line_styling.same),
                    line_width, sep,
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
                    Text("",           style=line_styling.same),
                    Text(line,         style=line_styling.add_highlight),
                    line_width, sep,
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
                    Text(line,         style=line_styling.remove_highlight),
                    Text("",           style=line_styling.same),
                    line_width, sep,
                )
                lineno_l += 1

        elif change.kind == DiffType.REPLACE:
            lines_b = change.left.split("\n")
            lines_a = change.right.split("\n")
            alignment = align(lines_b, lines_a)
            for line_l, line_r in alignment:
                if debug: print(f"  Aligned: {line_l!r}, {line_r!r}", file=sys.stderr)
                if line_l is None and line_r is not None:
                    lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                    _print_side_by_side_line(
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(lineno_r_fmt, style=lineno_styling.add_highlight),
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(empty_lineno, style=lineno_styling.add_highlight),
                        Text("",           style=line_styling.same),
                        Text(line_r,       style=line_styling.add_highlight),
                        line_width, sep,
                    )
                    lineno_r += 1
                elif line_l is not None and line_r is None:
                    lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                    _print_side_by_side_line(
                        Text(lineno_l_fmt, style=lineno_styling.remove_highlight),
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(empty_lineno, style=lineno_styling.remove_highlight),
                        Text(empty_lineno, style=lineno_styling.same),
                        Text(line_l, style=line_styling.remove_highlight),
                        Text("", style=line_styling.same),
                        line_width, sep,
                    )
                    lineno_l += 1
                elif line_l is not None and line_r is not None:
                    lineno_l_fmt = f"{lineno_l:>{lineno_width}}:"
                    lineno_r_fmt = f"{lineno_r:>{lineno_width}}:"
                    line_l_text = Text()
                    line_r_text = Text()
                    _style_diff_line(line_l, line_r, line_styling, line_l_text, line_r_text)
                    # line_l_text = Text(line_l, style=line_styling.remove)
                    # line_r_text = Text(line_r, style=line_styling.add)
                    _print_side_by_side_line(
                        Text(lineno_l_fmt, style=lineno_styling.remove),
                        Text(lineno_r_fmt, style=lineno_styling.add),
                        Text(empty_lineno, style=lineno_styling.remove),
                        Text(empty_lineno, style=lineno_styling.add),
                        line_l_text,
                        line_r_text,
                        line_width, sep,
                    )
                    lineno_l += 1
                    lineno_r += 1

def _print_side_by_side_line(lineno_l: Text, lineno_r: Text,
                             wrapno_l: Text, wrapno_r: Text,
                             line_l:   Text, line_r:   Text,
                             line_width: int,
                             separator: str):
    margin_l = lineno_l
    margin_r = lineno_r
    lines_l = line_l.wrap(None, line_width, tab_size=4)
    lines_r = line_r.wrap(None, line_width, tab_size=4)
    first_iteration = True
    for wrapped_l, wrapped_r in itertools.zip_longest(lines_l, lines_r):
        if wrapped_l is None:
            wrapped_l = ""
        if wrapped_r is None:
            wrapped_r = ""
        console.print(margin_l, " ",
                      wrapped_l, " " * (line_width - len(wrapped_l)),
                      separator,
                      margin_r, " ",
                      wrapped_r,
                      sep="")
        if first_iteration:
            margin_l = wrapno_l
            margin_r = wrapno_r
            first_iteration = False
