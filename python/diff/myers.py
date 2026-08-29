from __future__ import annotations

import enum
from dataclasses import dataclass

MAX_SEARCH_STATES = 500_000


class EditKind(enum.Enum):
    SAME = enum.auto()
    ADD = enum.auto()
    REMOVE = enum.auto()


@dataclass(frozen=True)
class Edit:
    kind: EditKind
    value: str


def calculate_edits(old: list[str], new: list[str]) -> list[Edit]:
    """Calculates a deterministic, bounded Myers edit script."""
    prefix_count = 0
    for old_value, new_value in zip(old, new, strict=False):
        if old_value != new_value:
            break
        prefix_count += 1

    suffix_count = 0
    while (
        suffix_count < len(old) - prefix_count
        and suffix_count < len(new) - prefix_count
        and old[-suffix_count - 1] == new[-suffix_count - 1]
    ):
        suffix_count += 1

    old_end = len(old) - suffix_count if suffix_count else len(old)
    new_end = len(new) - suffix_count if suffix_count else len(new)
    edits = [Edit(EditKind.SAME, value) for value in old[:prefix_count]]
    edits.extend(
        _calculate_middle(old[prefix_count:old_end], new[prefix_count:new_end])
    )
    if suffix_count:
        edits.extend(Edit(EditKind.SAME, value) for value in old[-suffix_count:])
    return edits


def _calculate_middle(old: list[str], new: list[str]) -> list[Edit]:
    if not old:
        return [Edit(EditKind.ADD, value) for value in new]
    if not new:
        return [Edit(EditKind.REMOVE, value) for value in old]

    # Each row records how far we got along every diagonal. Keep the old rows
    # so backtracking makes the same choice as the search: delete on a tie.
    frontiers: list[dict[int, int]] = []
    previous = {1: 0}
    visited_states = 0
    for distance in range(len(old) + len(new) + 1):
        visited_states += distance + 1
        if visited_states > MAX_SEARCH_STATES:
            # Myers can wander through a quadratic number of states when the
            # inputs barely match. At that point one replacement is faster and
            # usually clearer anyway.
            return [
                *(Edit(EditKind.REMOVE, value) for value in old),
                *(Edit(EditKind.ADD, value) for value in new),
            ]

        frontiers.append(previous)
        current: dict[int, int] = {}
        for diagonal in range(-distance, distance + 1, 2):
            if diagonal == -distance or (
                diagonal != distance and previous[diagonal - 1] < previous[diagonal + 1]
            ):
                old_index = previous[diagonal + 1]
            else:
                old_index = previous[diagonal - 1] + 1
            new_index = old_index - diagonal
            while (
                old_index < len(old)
                and new_index < len(new)
                and old[old_index] == new[new_index]
            ):
                old_index += 1
                new_index += 1
            current[diagonal] = old_index
            if old_index == len(old) and new_index == len(new):
                return _backtrack(old, new, frontiers, distance)
        previous = current

    raise AssertionError("Myers search must reach the end of both inputs")


def _backtrack(
    old: list[str],
    new: list[str],
    frontiers: list[dict[int, int]],
    edit_distance: int,
) -> list[Edit]:
    old_index = len(old)
    new_index = len(new)
    edits: list[Edit] = []

    for distance in range(edit_distance, 0, -1):
        previous = frontiers[distance]
        diagonal = old_index - new_index
        if diagonal == -distance or (
            diagonal != distance and previous[diagonal - 1] < previous[diagonal + 1]
        ):
            previous_diagonal = diagonal + 1
            previous_old = previous[previous_diagonal]
            inserted = True
        else:
            previous_diagonal = diagonal - 1
            previous_old = previous[previous_diagonal]
            inserted = False
        previous_new = previous_old - previous_diagonal

        while old_index > previous_old and new_index > previous_new:
            old_index -= 1
            new_index -= 1
            edits.append(Edit(EditKind.SAME, old[old_index]))

        if inserted:
            new_index -= 1
            edits.append(Edit(EditKind.ADD, new[new_index]))
        else:
            old_index -= 1
            edits.append(Edit(EditKind.REMOVE, old[old_index]))

    while old_index and new_index:
        old_index -= 1
        new_index -= 1
        edits.append(Edit(EditKind.SAME, old[old_index]))

    edits.reverse()
    return edits
