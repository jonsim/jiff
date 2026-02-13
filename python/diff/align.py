import difflib
import math
from typing import List, Optional, Tuple

debug = False

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
            return f"{self.id}: "\
                f"\U0001D464={self.weight}, "\
                f"\U0001D451={self.relax_weight}, "\
                f"\U0001D70B={self.relax_parent}"
        else:
            return f"{self.id}: {self.weight}"

    def relax(self, predecessor_id: Point, predecessor_weight: int) -> None:
        candidate_weight = predecessor_weight + self.weight
        if self.relax_weight > candidate_weight:
            self.relax_weight = candidate_weight
            self.relax_parent = predecessor_id


class AlignmentMatrix:
    def __init__(self, lines_b: List[str], lines_a: List[str]) -> None:
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
                weight: Optional[int] = None
                if not aligned_x and not aligned_y:
                    weight = -1
                elif aligned_x and not aligned_y:
                    weight = unalign_b_weights[x // 2]
                elif not aligned_x and aligned_y:
                    weight = unalign_a_weights[y // 2]
                elif aligned_x and aligned_y:
                    line_b = lines_b[x // 2]
                    line_a = lines_a[y // 2]
                    changeset = difflib.ndiff(line_b, line_a)
                    edit_dist = sum(1 for _ in changeset if _[0] != ' ')
                    operations = sum(1 for _ in changeset if _[0] in ['+', '-'])
                    weight = edit_dist * ((operations + 1) // 2)
                row.append(AlignmentNode(x, y, weight))
            self.line_matrix.append(row)

    def __repr__(self) -> str:
        s = f"Alignment matrix ({self.line_matrix_x_len} x {self.line_matrix_y_len}):\n"
        for x in range(self.line_matrix_x_len):
            for y in range(self.line_matrix_y_len):
                s += f" {self.line_matrix[x][y].weight:4}"
            s += "\n"
        return s

    def root_adjacency(self) -> List[Point]:
        # The nodes in the output are guaranteed to be in topological order.
        return [Point(0, 1), Point(1, 0), Point(1, 1)]

    def adjacency(self, node: AlignmentNode) -> List[Point]:
        # If I just paired node.id.x and node.id.y, what are the remaining
        # valid alignments?
        adjacency: List[Point] = []
        next_x = node.id.x + (node.id.x % 2) # will exist
        next_y = node.id.y + (node.id.y % 2) # will exist
        next_x_aligned = next_x + 1 # might not exist
        next_y_aligned = next_y + 1 # might not exist
        if next_x_aligned < self.line_matrix_x_len:
            adjacency.append(Point(next_x_aligned, next_y))
        if next_y_aligned < self.line_matrix_y_len:
            adjacency.append(Point(next_x, next_y_aligned))
        if next_x_aligned < self.line_matrix_x_len and next_y_aligned < self.line_matrix_y_len:
            adjacency.append(Point(next_x_aligned, next_y_aligned))
        # The nodes in the output are guaranteed to be in topological order.
        return adjacency

    def walk_path(self, exit: AlignmentNode) -> List[Point]:
        path: List[Point] = []
        pos = exit
        while pos.id.x > 0 or pos.id.y > 0:
            path.append(pos.id)
            next_pos = self.line_matrix[pos.id.x][pos.id.y].relax_parent
            pos = self.line_matrix[next_pos.x][next_pos.y]
        path.reverse()
        return path

    def shortest_path(self) -> List[Point]:
        # Initialize the root adjacency nodes (i.e. those accessible from
        # the single source node).
        for adj in self.root_adjacency():
            vertex = self.line_matrix[adj.x][adj.y]
            vertex.relax_weight = 0

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
        exit_xy = self.line_matrix[self.line_matrix_x_len - 2][self.line_matrix_y_len - 2]
        exit_x  = self.line_matrix[self.line_matrix_x_len - 2][self.line_matrix_y_len - 1]
        exit_y  = self.line_matrix[self.line_matrix_x_len - 1][self.line_matrix_y_len - 2]
        if exit_x.relax_weight < exit_y.relax_weight and exit_x.relax_weight < exit_xy.relax_weight:
            return self.walk_path(exit_x)
        elif exit_y.relax_weight < exit_xy.relax_weight:
            return self.walk_path(exit_y)
        else:
            return self.walk_path(exit_xy)


def align(lines_b: List[str], lines_a: List[str]) -> List[Tuple[Optional[str], Optional[str]]]:
    matrix = AlignmentMatrix(lines_b, lines_a)
    path = matrix.shortest_path()
    alignment: List[Tuple[Optional[str], Optional[str]]] = []
    for point in path:
        before = lines_b[point.x // 2] if point.x % 2 else None
        after  = lines_a[point.y // 2] if point.y % 2 else None
        alignment.append((before, after))
    return alignment
