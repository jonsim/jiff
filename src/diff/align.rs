
use difference::Changeset;
use std::fmt;
use std::vec::Vec;

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
        write!(f, "{}: \u{1D464}={},\u{1D451}={},\u{1D70B}={}", self.id,
               self.weight, self.relax_weight, self.relax_parent)
    }
}

pub struct AlignmentMatrix {
    line_matrix: Vec<Vec<AlignmentNode>>,
    line_matrix_x_len: usize,
    line_matrix_y_len: usize,
}

impl AlignmentMatrix {
    pub fn new(lines_b: &Vec<&str>, lines_a: &Vec<&str>) -> AlignmentMatrix {
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
                        edit_dist * ((operations+1) / 2)
                    },
                };
                row.push(AlignmentNode::new(x, y, weight));
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
        return adjacency;
    }

    fn walk_path<'a>(&'a self, exit: &'a AlignmentNode) -> Vec<&'a AlignmentNode> {
        let mut path = Vec::with_capacity(self.line_matrix_x_len / 2 + self.line_matrix_y_len / 2);
        let mut pos = exit;
        while pos.id.x > 0 || pos.id.y > 0 {
            path.push(pos);
            let next = &self.line_matrix[pos.id.x][pos.id.y].relax_parent;
            pos = &self.line_matrix[next.x][next.y];
        }
        return path;
    }

    pub fn shortest_path(&mut self) {
        // Generate all nodes, sorted topologically.
        let mut topo = self.root_adjacency();
        for adj in &topo {
            let vertex = &mut self.line_matrix[adj.x][adj.y];
            vertex.relax_weight = 0;
        }
        let mut i = 0usize;
        println!("enumerating all nodes...");
        while i < topo.len() {
            let vertex = &self.line_matrix[topo[i].x][topo[i].y];
            let vertex_id = vertex.id.clone();
            assert!((vertex_id.x | vertex_id.y) & 1 == 1, "vertex is an invalid node");
            let vertex_weight = vertex.relax_weight;
            let adjacency = self.adjacency(vertex);
            for adj in adjacency {
                let child = &mut self.line_matrix[adj.x][adj.y];
                child.relax(&vertex_id, vertex_weight);
                topo.push(adj);
            }
            i += 1;
        }
        println!("enumerated all {} nodes", topo.len());
        println!("exits:");
        println!("  {:?}", self.walk_path(&self.line_matrix[self.line_matrix_x_len-2][self.line_matrix_y_len-2]));
        println!("  {:?}", self.walk_path(&self.line_matrix[self.line_matrix_x_len-1][self.line_matrix_y_len-2]));
        println!("  {:?}", self.walk_path(&self.line_matrix[self.line_matrix_x_len-2][self.line_matrix_y_len-1]));
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