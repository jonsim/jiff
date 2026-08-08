use std::sync::LazyLock;

static DEBUG: LazyLock<bool> =
    LazyLock::new(|| matches!(std::env::var("JIFF_DEBUG").as_deref(), Ok("1")));

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
enum AlignmentOperation {
    Start,
    Remove,
    Add,
    Pair,
}

fn lcs_distance(before: &[char], after: &[char], lengths: &mut Vec<usize>) -> usize {
    // Shared ends can always participate in an optimal subsequence. Removing
    // them leaves the same edit distance and keeps the quadratic part small for
    // the common case of a local change in an otherwise stable line.
    let common_prefix = before
        .iter()
        .zip(after)
        .take_while(|(before, after)| before == after)
        .count();
    let mut common_suffix = 0;
    while common_suffix < before.len() - common_prefix
        && common_suffix < after.len() - common_prefix
        && before[before.len() - common_suffix - 1] == after[after.len() - common_suffix - 1]
    {
        common_suffix += 1;
    }

    let before = &before[common_prefix..before.len() - common_suffix];
    let after = &after[common_prefix..after.len() - common_suffix];
    let (rows, columns) = if before.len() >= after.len() {
        (before, after)
    } else {
        (after, before)
    };

    lengths.clear();
    lengths.resize(columns.len() + 1, 0);
    for row in rows {
        let mut diagonal = 0;
        for (column_index, column) in columns.iter().enumerate() {
            // `lengths[j]` is the LCS length for the rows processed so far and
            // the first `j` columns. Keep the overwritten value and diagonal
            // so this row can be calculated in place.
            let previous_row = lengths[column_index + 1];
            lengths[column_index + 1] = if row == column {
                diagonal + 1
            } else {
                lengths[column_index].max(previous_row)
            };
            diagonal = previous_row;
        }
    }

    before.len() + after.len() - 2 * lengths[columns.len()]
}

fn pair_cost(before: &[char], after: &[char], lengths: &mut Vec<usize>) -> usize {
    if before == after {
        return 0;
    }

    let unpaired_cost = before.len() + after.len();
    // One more than remove-plus-add makes a dissimilar pair strictly worse
    // without introducing a separate "not a candidate" value in the main DP.
    let dissimilar_cost = unpaired_cost + 1;
    let length_difference = before.len().abs_diff(after.len());

    // A sufficiently large length difference cannot pass the similarity
    // cutoff, regardless of how the shorter line is arranged.
    if 2 * length_difference >= unpaired_cost {
        return dissimilar_cost;
    }

    let distance = lcs_distance(before, after, lengths);
    if 2 * distance >= unpaired_cost {
        dissimilar_cost
    } else {
        distance
    }
}

fn choose_operation(pair: usize, remove: usize, add: usize) -> (usize, AlignmentOperation) {
    if pair <= remove && pair <= add {
        // Prefer a useful side-by-side pairing when it costs exactly the same
        // as leaving both lines unmatched.
        (pair, AlignmentOperation::Pair)
    } else if add <= remove {
        // Ending with an addition puts removals before additions when two gap
        // orderings have the same cost, matching normal diff output.
        (add, AlignmentOperation::Add)
    } else {
        (remove, AlignmentOperation::Remove)
    }
}

/// Pairs similar lines while preserving the order of both inputs.
///
/// Each output entry consumes a line from `lines_b`, `lines_a`, or both. The
/// dynamic programme chooses the lowest-cost path, where an unpaired line costs
/// its character length. Lines are paired only when their insertion/deletion
/// distance is less than half their combined length.
///
/// Scoring is `O(C_b * C_a)` in the worst case, where `C_b` and `C_a` are the
/// total character counts on each side. Traceback uses `O(L_b * L_a)` bytes for
/// `L_b` before lines and `L_a` after lines. Alignment costs keep two line rows,
/// while every candidate pair reuses one LCS row.
pub(super) fn align<'a>(
    lines_b: &[&'a str],
    lines_a: &[&'a str],
) -> Vec<(Option<&'a str>, Option<&'a str>)> {
    let width = lines_a.len() + 1;
    // Cell `(i, j)` is the cheapest alignment of the first `i` before lines
    // and first `j` after lines. Costs need only two rows; `operations` retains
    // the final transition at every cell so the path can be reconstructed.
    let mut operations = vec![AlignmentOperation::Start; (lines_b.len() + 1) * width];
    let mut previous_costs = vec![0; width];
    let mut current_costs = vec![0; width];
    let before_chars: Vec<Vec<char>> = lines_b.iter().map(|line| line.chars().collect()).collect();
    let after_chars: Vec<Vec<char>> = lines_a.iter().map(|line| line.chars().collect()).collect();
    let mut lcs_lengths = Vec::new();

    // The first row and column describe paths which can only add or remove.
    for (after_index, after) in after_chars.iter().enumerate() {
        previous_costs[after_index + 1] = previous_costs[after_index] + after.len();
        operations[after_index + 1] = AlignmentOperation::Add;
    }

    for (before_index, before) in before_chars.iter().enumerate() {
        current_costs[0] = previous_costs[0] + before.len();
        operations[(before_index + 1) * width] = AlignmentOperation::Remove;

        for (after_index, after) in after_chars.iter().enumerate() {
            let column = after_index + 1;
            let score = pair_cost(before, after, &mut lcs_lengths);
            let pair = previous_costs[column - 1] + score;
            let remove = previous_costs[column] + before.len();
            let add = current_costs[column - 1] + after.len();
            let (cost, operation) = choose_operation(pair, remove, add);

            if *DEBUG {
                eprintln!(
                    "  Pair score for {} -> {}: {}",
                    lines_b[before_index], lines_a[after_index], score
                );
            }

            current_costs[column] = cost;
            operations[(before_index + 1) * width + column] = operation;
        }

        std::mem::swap(&mut previous_costs, &mut current_costs);
    }

    // Costs need only the previous row, but one byte-sized operation per cell
    // is retained so the chosen path can be reconstructed backwards.
    let mut before_index = lines_b.len();
    let mut after_index = lines_a.len();
    let mut alignment = Vec::with_capacity(before_index + after_index);
    while before_index > 0 || after_index > 0 {
        match operations[before_index * width + after_index] {
            AlignmentOperation::Remove => {
                alignment.push((Some(lines_b[before_index - 1]), None));
                before_index -= 1;
            }
            AlignmentOperation::Add => {
                alignment.push((None, Some(lines_a[after_index - 1])));
                after_index -= 1;
            }
            AlignmentOperation::Pair => {
                alignment.push((
                    Some(lines_b[before_index - 1]),
                    Some(lines_a[after_index - 1]),
                ));
                before_index -= 1;
                after_index -= 1;
            }
            AlignmentOperation::Start => unreachable!("alignment path ended before both inputs"),
        }
    }

    alignment.reverse();
    alignment
}

#[cfg(test)]
mod tests {
    use super::*;

    fn characters(s: &str) -> Vec<char> {
        s.chars().collect()
    }

    #[test]
    fn lcs_distance_ignores_a_common_prefix_and_suffix() {
        // Trimming anchors must leave the same distance as diffing the full line.
        let before = characters("abcXYZdef");
        let after = characters("abcX123YZdef");

        let distance = lcs_distance(&before, &after, &mut Vec::new());

        assert_eq!(3, distance);
    }

    #[test]
    fn pair_cost_rejects_lines_at_the_similarity_boundary() {
        // One changed character in a two-character line is too little context.
        let before = characters("ab");
        let after = characters("ac");

        let cost = pair_cost(&before, &after, &mut Vec::new());

        assert!(cost > before.len() + after.len());
    }

    #[test]
    fn equal_total_cost_prefers_pairing() {
        // A tied pairing keeps the side-by-side result compact and useful.
        assert_eq!((5, AlignmentOperation::Pair), choose_operation(5, 5, 7));
    }

    #[test]
    fn aligns_identical_lines() {
        // Exact matches should keep their input order and pair every line.
        let before = ["Kermit", "Fozzie"];
        let after = ["Kermit", "Fozzie"];

        let alignment = align(&before, &after);

        assert_eq!(
            vec![
                (Some("Kermit"), Some("Kermit")),
                (Some("Fozzie"), Some("Fozzie"))
            ],
            alignment
        );
    }

    #[test]
    fn aligns_insertions_around_an_exact_match() {
        // A stable line is a better anchor than pairing it with either neighbour.
        let before = ["Kermit"];
        let after = ["Statler", "Kermit", "Waldorf"];

        let alignment = align(&before, &after);

        assert_eq!(
            vec![
                (None, Some("Statler")),
                (Some("Kermit"), Some("Kermit")),
                (None, Some("Waldorf")),
            ],
            alignment
        );
    }

    #[test]
    fn aligns_removals_around_an_exact_match() {
        // The same anchoring rule applies when the extra lines are on the left.
        let before = ["Statler", "Kermit", "Waldorf"];
        let after = ["Kermit"];

        let alignment = align(&before, &after);

        assert_eq!(
            vec![
                (Some("Statler"), None),
                (Some("Kermit"), Some("Kermit")),
                (Some("Waldorf"), None),
            ],
            alignment
        );
    }

    #[test]
    fn pairs_a_small_change_between_exact_matches() {
        // Similar changed lines should stay together so their character diff is useful.
        let before = ["Kermit", "Fozzie Bear", "Gonzo"];
        let after = ["Kermit", "Fozzie Brown Bear", "Gonzo"];

        let alignment = align(&before, &after);

        assert_eq!(
            vec![
                (Some("Kermit"), Some("Kermit")),
                (Some("Fozzie Bear"), Some("Fozzie Brown Bear")),
                (Some("Gonzo"), Some("Gonzo")),
            ],
            alignment
        );
    }

    #[test]
    fn keeps_dissimilar_lines_unpaired_between_exact_matches() {
        // Pairing unrelated lines produces noisy character highlighting.
        let before = ["Kermit", "Fozzie", "Gonzo"];
        let after = ["Kermit", "Swedish Chef", "Gonzo"];

        let alignment = align(&before, &after);

        assert_eq!(
            vec![
                (Some("Kermit"), Some("Kermit")),
                (Some("Fozzie"), None),
                (None, Some("Swedish Chef")),
                (Some("Gonzo"), Some("Gonzo")),
            ],
            alignment
        );
    }

    #[test]
    fn charges_for_the_first_alignment_operation() {
        // Unrelated first lines cost more to pair than to remove and add.
        let before = ["Kermit"];
        let after = ["Gonzo"];

        let alignment = align(&before, &after);

        assert_eq!(
            vec![(Some("Kermit"), None), (None, Some("Gonzo"))],
            alignment
        );
    }

    #[test]
    fn pairs_fragmented_changes_when_the_line_is_still_similar() {
        // Several small edits should not outweigh the characters which still match.
        let before = ["aXaXaXa"];
        let after = ["aYaYaYa"];

        let alignment = align(&before, &after);

        assert_eq!(vec![(Some("aXaXaXa"), Some("aYaYaYa"))], alignment);
    }

    #[test]
    fn uses_character_lengths_for_unicode_lines() {
        // UTF-8 byte length must not make unrelated non-ASCII lines cheaper to pair.
        let before = ["éé"];
        let after = ["zz"];

        let alignment = align(&before, &after);

        assert_eq!(vec![(Some("éé"), None), (None, Some("zz"))], alignment);
    }

    #[test]
    fn aligns_two_empty_inputs() {
        // No input lines means there are no alignment operations to report.
        assert_eq!(Vec::<(Option<&str>, Option<&str>)>::new(), align(&[], &[]));
    }

    #[test]
    fn aligns_an_empty_before_input() {
        // With no left lines, every right line is an insertion in input order.
        let after = ["Kermit", "Gonzo"];

        let alignment = align(&[], &after);

        assert_eq!(
            vec![(None, Some("Kermit")), (None, Some("Gonzo"))],
            alignment
        );
    }

    #[test]
    fn aligns_an_empty_after_input() {
        // With no right lines, every left line is a removal in input order.
        let before = ["Kermit", "Gonzo"];

        let alignment = align(&before, &[]);

        assert_eq!(
            vec![(Some("Kermit"), None), (Some("Gonzo"), None)],
            alignment
        );
    }
}
