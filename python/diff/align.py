from __future__ import annotations

import enum
import os
import sys

debug = os.environ.get("JIFF_DEBUG", "0") == "1"


def _edit_distance(before: str, after: str) -> int:
    # Matching ends can always be retained by an optimal edit script. Trimming
    # them avoids the quadratic work for the common case of a small change in
    # an otherwise stable line.
    common_prefix = 0
    for before_char, after_char in zip(before, after, strict=False):
        if before_char != after_char:
            break
        common_prefix += 1

    common_suffix = 0
    remaining_before = len(before) - common_prefix
    remaining_after = len(after) - common_prefix
    while (
        common_suffix < remaining_before
        and common_suffix < remaining_after
        and before[-common_suffix - 1] == after[-common_suffix - 1]
    ):
        common_suffix += 1

    before_end = len(before) - common_suffix if common_suffix else len(before)
    after_end = len(after) - common_suffix if common_suffix else len(after)
    before = before[common_prefix:before_end]
    after = after[common_prefix:after_end]
    rows, columns = (before, after) if len(before) >= len(after) else (after, before)

    distances = list(range(len(columns) + 1))
    for row_index, row in enumerate(rows, start=1):
        diagonal = distances[0]
        distances[0] = row_index
        for column_index, column in enumerate(columns):
            # Keep the previous row's value before overwriting it so the next
            # cell still has its diagonal and deletion costs available.
            previous_row = distances[column_index + 1]
            deletion = previous_row + 1
            insertion = distances[column_index] + 1
            substitution = diagonal + (row != column)
            distances[column_index + 1] = min(deletion, insertion, substitution)
            diagonal = previous_row

    return distances[-1]


def _pair_cost(before: str, after: str) -> int:
    if before == after:
        return 0

    unpaired_cost = len(before) + len(after)
    # One more than remove-plus-add makes a dissimilar pair strictly worse
    # without needing a separate "not a candidate" value in the alignment.
    dissimilar_cost = unpaired_cost + 1
    length_difference = abs(len(before) - len(after))

    # A line at least three times longer than the other has too little shared
    # context to make a useful pair, even when it contains the shorter line.
    if 2 * length_difference >= unpaired_cost:
        return dissimilar_cost

    distance = _edit_distance(before, after)
    # A common subsequence can be made from isolated spaces and letters in two
    # unrelated sentences. Levenshtein distance requires those matches to be
    # locally coherent. Keep contiguous extensions as a useful special case
    # for indentation and text added at either end of a line.
    contiguous_extension = before in after or after in before
    if not contiguous_extension and 2 * distance >= max(len(before), len(after)):
        return dissimilar_cost
    return distance


class AlignmentOperation(enum.IntEnum):
    START = 0
    REMOVE = 1
    ADD = 2
    PAIR = 3


def _choose_operation(
    pair: int, remove: int, add: int
) -> tuple[int, AlignmentOperation]:
    if pair <= remove and pair <= add:
        # A tied pairing gives the renderer useful sub-line highlighting rather
        # than two unrelated rows.
        return pair, AlignmentOperation.PAIR
    if add <= remove:
        # Walking this choice backwards puts removals before additions in the
        # final output, matching ordinary diff output.
        return add, AlignmentOperation.ADD
    return remove, AlignmentOperation.REMOVE


def align(
    lines_b: list[str], lines_a: list[str]
) -> list[tuple[str | None, str | None]]:
    """Pairs similar lines while preserving both input orders.

    Unpaired lines cost their character length. Pairing costs their edit
    distance, unless the lines are too dissimilar to make sub-line highlighting
    useful. The dynamic programme keeps two cost rows and one byte of traceback
    state per pair of input lines.
    """
    width = len(lines_a) + 1
    operations = bytearray((len(lines_b) + 1) * width)
    previous_costs = [0] * width
    current_costs = [0] * width

    # The first row and column can only add or remove lines.
    for after_index, after in enumerate(lines_a):
        previous_costs[after_index + 1] = previous_costs[after_index] + len(after)
        operations[after_index + 1] = AlignmentOperation.ADD

    for before_index, before in enumerate(lines_b):
        current_costs[0] = previous_costs[0] + len(before)
        operations[(before_index + 1) * width] = AlignmentOperation.REMOVE

        for after_index, after in enumerate(lines_a):
            column = after_index + 1
            score = _pair_cost(before, after)
            pair = previous_costs[column - 1] + score
            remove = previous_costs[column] + len(before)
            add = current_costs[column - 1] + len(after)
            cost, operation = _choose_operation(pair, remove, add)

            if debug:
                print(
                    f"  Pair score for {before!r} -> {after!r}: {score}",
                    file=sys.stderr,
                )

            current_costs[column] = cost
            operations[(before_index + 1) * width + column] = operation

        previous_costs, current_costs = current_costs, previous_costs

    # Costs only need the previous row. One byte per cell retains enough of the
    # chosen path to reconstruct the alignment backwards.
    before_index = len(lines_b)
    after_index = len(lines_a)
    alignment: list[tuple[str | None, str | None]] = []
    while before_index > 0 or after_index > 0:
        operation = AlignmentOperation(operations[before_index * width + after_index])
        if operation == AlignmentOperation.REMOVE:
            alignment.append((lines_b[before_index - 1], None))
            before_index -= 1
        elif operation == AlignmentOperation.ADD:
            alignment.append((None, lines_a[after_index - 1]))
            after_index -= 1
        elif operation == AlignmentOperation.PAIR:
            alignment.append((lines_b[before_index - 1], lines_a[after_index - 1]))
            before_index -= 1
            after_index -= 1
        else:
            raise AssertionError("alignment path ended before both inputs")

    alignment.reverse()
    return alignment
