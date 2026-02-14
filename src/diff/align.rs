use difference::Changeset;
use std::fmt;
use std::sync::LazyLock;
use std::vec::Vec;

pub static DEBUG: LazyLock<bool> = LazyLock::new(|| {
    matches!(std::env::var("JIFF_DEBUG").as_deref(), Ok("1"))
});


#[derive(Clone)]
struct Point {
    x: usize,
    y: usize,
}

impl fmt::Display for Point {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "({},{})", self.x, self.y)
    }
}
impl fmt::Debug for Point {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "({},{})", self.x, self.y)
    }
}

struct AlignmentNode {
    id: Point,
    weight: i32,
    relax_weight: i32,
    relax_parent: Point,
}

impl AlignmentNode {
    fn new(x: usize, y: usize, weight: i32) -> AlignmentNode {
        AlignmentNode {
            id: Point { x, y },
            weight: weight,
            relax_weight: std::i32::MAX,
            relax_parent: Point { x: 0, y: 0 },
        }
    }

    fn relax(&mut self, predecessor_id: &Point, predecessor_weight: i32) {
        let candidate_weight = predecessor_weight + self.weight;
        if self.relax_weight > candidate_weight {
            self.relax_weight = candidate_weight;
            self.relax_parent = predecessor_id.clone();
        }
    }
}

impl fmt::Display for AlignmentNode {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{}: {}", self.id, self.weight)
    }
}
impl fmt::Debug for AlignmentNode {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "Alignment Node {}: \u{1D464}={:3}, \u{1D451}={:3}, \u{1D70B}={}", self.id,
               self.weight, self.relax_weight, self.relax_parent)
    }
}

struct AlignmentMatrix {
    line_matrix: Vec<Vec<AlignmentNode>>,
    line_matrix_x_len: usize,
    line_matrix_y_len: usize,
}

impl AlignmentMatrix {
    fn new(lines_b: &Vec<&str>, lines_a: &Vec<&str>) -> AlignmentMatrix {
        let lines_b_len = lines_b.len();
        let lines_a_len = lines_a.len();
        let line_matrix_x_len = lines_b_len * 2 + 1;
        let line_matrix_y_len = lines_a_len * 2 + 1;
        // Compute the baseline or benchmark 'unalignment' scores - i.e. the
        // scores if the lines were unaligned. We must do no worse than
        // unalignment.
        // First for all the 'before' lines.
        let mut unalign_b_weights = Vec::with_capacity(lines_b_len);
        for line_b in lines_b {
            unalign_b_weights.push(line_b.len() as i32);
        }
        // Then for all the 'after' lines.
        let mut unalign_a_weights = Vec::with_capacity(lines_a_len);
        for line_a in lines_a {
            unalign_a_weights.push(line_a.len() as i32);
        }
        // Next, compute the edit distance for all lines to one another - i.e.
        // if every line were aligned with one another.
        let mut line_matrix = Vec::with_capacity(line_matrix_x_len);
        for x in 0..line_matrix_x_len {
            let aligned_x = x & 1 != 0;
            let mut row = Vec::with_capacity(line_matrix_y_len);
            for y in 0..line_matrix_y_len {
                let aligned_y = y & 1 != 0;
                let weight: i32 = match (aligned_x, aligned_y) {
                    (false, false) => -1,
                    (true, false) => unalign_b_weights[x/2],
                    (false, true) => unalign_a_weights[y/2],
                    (true, true) => {
                        let line_b = lines_b[x/2];
                        let line_a = lines_a[y/2];
                        let changeset = Changeset::new(line_b, line_a, "");
                        let edit_dist = changeset.distance;
                        let operations = changeset.diffs.len() as i32;
                        if *DEBUG { eprintln!("  Changeset for {} -> {}: {}", line_b, line_a, changeset) };
                        if *DEBUG { eprintln!("    Edit distance: {}, operations: {}", edit_dist, operations) };
                        edit_dist * ((operations+1) / 2)
                    },
                };
                row.push(AlignmentNode::new(x, y, weight));
                if *DEBUG { eprintln!("  Initialized: {:?}", row.last().unwrap()) };
            }
            line_matrix.push(row);
        }
        // Chuck it in a struct and ship it.
        AlignmentMatrix { line_matrix,
                          line_matrix_x_len, line_matrix_y_len }
    }

    fn root_adjacency(&self) -> Vec<Point> {
        let mut adjacency = Vec::with_capacity(3);
        adjacency.push(Point { x: 0, y: 1 });
        adjacency.push(Point { x: 1, y: 0 });
        adjacency.push(Point { x: 1, y: 1 });
        // The nodes in the output are guaranteed to be in topological order.
        return adjacency;
    }

    fn adjacency(&self, node: &AlignmentNode) -> Vec<Point> {
        // If I just paired node.id.x and node.id.y, what are the remaining
        // valid alignments?
        let mut adjacency = Vec::with_capacity(3);
        let next_x = node.id.x + (node.id.x & 1); // will exist
        let next_y = node.id.y + (node.id.y & 1); // will exist
        let next_x_aligned = next_x + 1; // might not exist
        let next_y_aligned = next_y + 1; // might not exist
        if next_x_aligned < self.line_matrix_x_len {
            adjacency.push(Point { x: next_x_aligned, y: next_y });
        }
        if next_y_aligned < self.line_matrix_y_len {
            adjacency.push(Point { x: next_x, y: next_y_aligned });
        }
        if next_x_aligned < self.line_matrix_x_len && next_y_aligned < self.line_matrix_y_len {
            adjacency.push(Point { x: next_x_aligned, y: next_y_aligned });
        }
        // The nodes in the output are guaranteed to be in topological order.
        return adjacency;
    }

    fn walk_path(&self, exit: &AlignmentNode) -> Vec<Point> {
        let mut path = Vec::with_capacity(self.line_matrix_x_len / 2 + self.line_matrix_y_len / 2);
        let mut pos = exit;
        while pos.id.x > 0 || pos.id.y > 0 {
            path.push(pos.id.clone());
            let next = &self.line_matrix[pos.id.x][pos.id.y].relax_parent;
            pos = &self.line_matrix[next.x][next.y];
        }
        path.reverse();
        return path;
    }

    fn shortest_path(&mut self) -> Vec<Point> {
        // Initialize the root adjacency nodes (i.e. those accessible from
        // the single source node).
        for adj in self.root_adjacency() {
            let vertex = &mut self.line_matrix[adj.x][adj.y];
            vertex.relax_weight = 0;
        }
        // Walk all nodes.
        // The line matrix is iterated in topological order, line by line, since
        // the adjacency for a given node may never go backwards (decrease x or
        // y). The iteration order is not the most obvious topological ordering
        // of the matrix, but it is the most cache friendly.
        // Iterating in topological order permits a single pass through the line
        // matrix (a weighted DAG) to relax all edges and compute the shortest
        // path. This is significantly better than conventional shortest-path
        // finding algorithms both in terms of time and memory complexity, by
        // exploiting the structure of the data. The walk will visit
        // 3|A||B| + |A| + |B| nodes, relaxing at most 3 nodes from each (i.e.
        // O(|A||B|) or linear complexity).
        for x in 0..self.line_matrix_x_len {
            for y in 0..self.line_matrix_y_len {
                if (x | y) & 1 == 0 {
                    continue;
                }
                let vertex = &self.line_matrix[x][y];
                let vertex_id = vertex.id.clone();
                let vertex_weight = vertex.relax_weight;
                let adjacency = self.adjacency(vertex);
                for adj in adjacency {
                    let child = &mut self.line_matrix[adj.x][adj.y];
                    child.relax(&vertex_id, vertex_weight);
                }
            }
        }
        // Derive the shortest path from the walk.
        // There are three legal exit points, so choose the best of these and
        // walk its parents backwards.
        let exit_xy = &self.line_matrix[self.line_matrix_x_len-2][self.line_matrix_y_len-2];
        let exit_x  = &self.line_matrix[self.line_matrix_x_len-2][self.line_matrix_y_len-1];
        let exit_y  = &self.line_matrix[self.line_matrix_x_len-1][self.line_matrix_y_len-2];
        if exit_x.relax_weight < exit_y.relax_weight && exit_x.relax_weight < exit_xy.relax_weight {
            return self.walk_path(exit_x);
        } else if exit_y.relax_weight < exit_xy.relax_weight {
            return self.walk_path(exit_y);
        } else {
            return self.walk_path(exit_xy);
        }
    }
}

impl fmt::Display for AlignmentMatrix {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "Alignment matrix ({} x {}):\n", self.line_matrix_x_len, self.line_matrix_y_len)?;
        for x in 0..self.line_matrix_x_len {
            for y in 0..self.line_matrix_y_len {
                write!(f, " {:4}", self.line_matrix[x][y].weight)?;
            }
            write!(f, "\n")?;
        }
        Ok(())
    }
}

pub fn align<'a>(lines_b: &Vec<&'a str>, lines_a: &Vec<&'a str>) ->
        Vec<(Option<&'a str>, Option<&'a str>)> {
    let mut matrix = AlignmentMatrix::new(lines_b, lines_a);
    if *DEBUG { eprintln!("  Initialised: {}", matrix) };
    let path = matrix.shortest_path();
    if *DEBUG { eprintln!("  Shortest path: {:?}", path) };
    let mut alignment = Vec::with_capacity(lines_b.len() + lines_a.len());
    for point in path {
        let before;
        let after;
        if point.x & 1 > 0 {
            before = Some(lines_b[point.x / 2]);
        } else {
            before = None;
        }
        if point.y & 1 > 0 {
            after = Some(lines_a[point.y / 2]);
        } else {
            after = None;
        }
        alignment.push((before, after));
    }
    return alignment;
}
