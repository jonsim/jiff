from __future__ import annotations

import math
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


class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"({self.x},{self.y})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Point):
            return self.x == other.x and self.y == other.y
        return False

    def __hash__(self) -> int:
        return hash((self.x, self.y))


class AlignmentNode:
    def __init__(self, x: int, y: int, weight: int) -> None:
        self.id = Point(x, y)
        self.weight = weight
        self.relax_weight = math.inf
        self.relax_parent = Point(0, 0)

    def __repr__(self) -> str:
        if debug:
            return (
                f"Alignment Node {self.id}: "
                f"\U0001d464={self.weight:3}, "
                f"\U0001d451={self.relax_weight:3}, "
                f"\U0001d70b={self.relax_parent}"
            )
        else:
            return f"{self.id}: {self.weight}"

    def relax(self, predecessor_id: Point, predecessor_weight: int) -> None:
        candidate_weight = predecessor_weight + self.weight
        if self.relax_weight > candidate_weight:
            self.relax_weight = candidate_weight
            self.relax_parent = predecessor_id


class AlignmentMatrix:
    def __init__(self, lines_b: list[str], lines_a: list[str]) -> None:
        lines_b_len = len(lines_b)
        lines_a_len = len(lines_a)
        self.line_matrix_x_len = lines_b_len * 2 + 1
        self.line_matrix_y_len = lines_a_len * 2 + 1

        # Compute the baseline or benchmark 'unalignment' scores - i.e. the
        # scores if the lines were unaligned. We must do no worse than
        # unalignment.
        # First for all the 'before' lines.
        unalign_b_weights = [len(line) for line in lines_b]
        # Then for all the 'after' lines.
        unalign_a_weights = [len(line) for line in lines_a]

        # Next, compute the edit distance for all lines to one another - i.e.
        # if every line were aligned with one another.
        self.line_matrix = []
        for x in range(self.line_matrix_x_len):
            aligned_x = x % 2 != 0
            row = []
            for y in range(self.line_matrix_y_len):
                aligned_y = y % 2 != 0
                weight: int | None = None
                if not aligned_x and not aligned_y:
                    weight = -1
                elif aligned_x and not aligned_y:
                    weight = unalign_b_weights[x // 2]
                elif not aligned_x and aligned_y:
                    weight = unalign_a_weights[y // 2]
                elif aligned_x and aligned_y:
                    line_b = lines_b[x // 2]
                    line_a = lines_a[y // 2]
                    weight = _pair_cost(line_b, line_a)
                    if debug:
                        print(
                            f"  Pair score for {line_b!r} -> {line_a!r}: {weight}",
                            file=sys.stderr,
                        )
                row.append(AlignmentNode(x, y, weight))
                if debug:
                    print(f"  Initialised: {row[-1]}", file=sys.stderr)
            self.line_matrix.append(row)

    def __repr__(self) -> str:
        s = f"Alignment matrix ({self.line_matrix_x_len} x {self.line_matrix_y_len}):\n"
        for x in range(self.line_matrix_x_len):
            for y in range(self.line_matrix_y_len):
                s += f" {self.line_matrix[x][y].weight:4}"
            s += "\n"
        return s

    def root_adjacency(self) -> list[Point]:
        # The nodes in the output are guaranteed to be in topological order.
        return [Point(0, 1), Point(1, 0), Point(1, 1)]

    def adjacency(self, node: AlignmentNode) -> list[Point]:
        # If I just paired node.id.x and node.id.y, what are the remaining
        # valid alignments?
        adjacency: list[Point] = []
        next_x = node.id.x + (node.id.x % 2)  # will exist
        next_y = node.id.y + (node.id.y % 2)  # will exist
        next_x_aligned = next_x + 1  # might not exist
        next_y_aligned = next_y + 1  # might not exist
        if next_x_aligned < self.line_matrix_x_len:
            adjacency.append(Point(next_x_aligned, next_y))
        if next_y_aligned < self.line_matrix_y_len:
            adjacency.append(Point(next_x, next_y_aligned))
        if (
            next_x_aligned < self.line_matrix_x_len
            and next_y_aligned < self.line_matrix_y_len
        ):
            adjacency.append(Point(next_x_aligned, next_y_aligned))
        # The nodes in the output are guaranteed to be in topological order.
        return adjacency

    def walk_path(self, exit: AlignmentNode) -> list[Point]:
        path: list[Point] = []
        pos = exit
        while pos.id.x > 0 or pos.id.y > 0:
            path.append(pos.id)
            next_pos = self.line_matrix[pos.id.x][pos.id.y].relax_parent
            pos = self.line_matrix[next_pos.x][next_pos.y]
        path.reverse()
        return path

    def shortest_path(self) -> list[Point]:
        # Each root neighbour represents the first real operation. Starting
        # it at zero would make the first insertion, removal or pairing free.
        for adj in self.root_adjacency():
            vertex = self.line_matrix[adj.x][adj.y]
            vertex.relax_weight = vertex.weight

        # Walk all nodes.
        # The line matrix is iterated in topological order, line by line, since
        # the adjacency for a given node may never go backwards (decrease x or
        # y). The iteration order is not the most obvious topological ordering
        # of the matrix, but it is the most cache friendly.
        # Iterating in topological order permits a single pass through the line
        # matrix (a weighted DAG) to relax all edges and compute the shortest
        # path. This is significantly better than conventional shortest-path
        # finding algorithms both in terms of time and memory complexity, by
        # exploiting the structure of the data. The walk will visit
        # 3|A||B| + |A| + |B| nodes, relaxing at most 3 nodes from each (i.e.
        # O(|A||B|) or linear complexity).
        for x in range(self.line_matrix_x_len):
            for y in range(self.line_matrix_y_len):
                if (x | y) % 2 == 0:
                    continue
                vertex = self.line_matrix[x][y]
                vertex_id = vertex.id
                vertex_weight = vertex.relax_weight
                adjacency = self.adjacency(vertex)
                for adj in adjacency:
                    child = self.line_matrix[adj.x][adj.y]
                    child.relax(vertex_id, vertex_weight)

        # Derive the shortest path from the walk.
        # There are three legal exit points, so choose the best of these and
        # walk its parents backwards.
        exit_xy = self.line_matrix[self.line_matrix_x_len - 2][
            self.line_matrix_y_len - 2
        ]
        exit_x = self.line_matrix[self.line_matrix_x_len - 2][
            self.line_matrix_y_len - 1
        ]
        exit_y = self.line_matrix[self.line_matrix_x_len - 1][
            self.line_matrix_y_len - 2
        ]
        if (
            exit_x.relax_weight < exit_y.relax_weight
            and exit_x.relax_weight < exit_xy.relax_weight
        ):
            return self.walk_path(exit_x)
        elif exit_y.relax_weight < exit_xy.relax_weight:
            return self.walk_path(exit_y)
        else:
            return self.walk_path(exit_xy)


def align(
    lines_b: list[str], lines_a: list[str]
) -> list[tuple[str | None, str | None]]:
    matrix = AlignmentMatrix(lines_b, lines_a)
    if debug:
        print(f"  Initialised: {matrix}", file=sys.stderr)
    path = matrix.shortest_path()
    if debug:
        print(f"  Shortest path: {path}", file=sys.stderr)
    alignment: list[tuple[str | None, str | None]] = []
    for point in path:
        before = lines_b[point.x // 2] if point.x % 2 else None
        after = lines_a[point.y // 2] if point.y % 2 else None
        alignment.append((before, after))
    return alignment
