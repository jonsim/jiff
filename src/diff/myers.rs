const MAX_SEARCH_STATES: usize = 500_000;

#[derive(Debug, Eq, PartialEq)]
pub(super) enum Edit<T> {
    Same(T),
    Add(T),
    Remove(T),
}

pub(super) fn calculate_edits<T: Clone + Eq>(old: &[T], new: &[T]) -> Vec<Edit<T>> {
    let prefix_count = old
        .iter()
        .zip(new)
        .take_while(|(old_value, new_value)| old_value == new_value)
        .count();
    let suffix_count = old[prefix_count..]
        .iter()
        .rev()
        .zip(new[prefix_count..].iter().rev())
        .take_while(|(old_value, new_value)| old_value == new_value)
        .count();
    let old_end = old.len() - suffix_count;
    let new_end = new.len() - suffix_count;

    let mut edits = old[..prefix_count]
        .iter()
        .cloned()
        .map(Edit::Same)
        .collect::<Vec<_>>();
    edits.extend(calculate_middle(
        &old[prefix_count..old_end],
        &new[prefix_count..new_end],
    ));
    edits.extend(old[old_end..].iter().cloned().map(Edit::Same));
    edits
}

fn calculate_middle<T: Clone + Eq>(old: &[T], new: &[T]) -> Vec<Edit<T>> {
    if old.is_empty() {
        return new.iter().cloned().map(Edit::Add).collect();
    }
    if new.is_empty() {
        return old.iter().cloned().map(Edit::Remove).collect();
    }

    // Each row holds the furthest old-side position reached on one diagonal.
    // Keeping the rows also gives backtracking the exact same tie-break as the
    // forward search: delete when two paths have equal length.
    let mut frontiers: Vec<Vec<usize>> = Vec::new();
    let mut visited_states = 0;
    for distance in 0..=old.len() + new.len() {
        visited_states += distance + 1;
        if visited_states > MAX_SEARCH_STATES {
            // A very different pair can make Myers explore a quadratic number
            // of states. One replacement is both quicker and easier to read.
            return old
                .iter()
                .cloned()
                .map(Edit::Remove)
                .chain(new.iter().cloned().map(Edit::Add))
                .collect();
        }

        let mut current = Vec::with_capacity(distance + 1);
        for index in 0..=distance {
            let diagonal = -(distance as isize) + 2 * index as isize;
            let mut old_index = if distance == 0 {
                0
            } else {
                let previous = &frontiers[distance - 1];
                if index == 0 || (index != distance && previous[index - 1] < previous[index]) {
                    previous[index]
                } else {
                    previous[index - 1] + 1
                }
            };
            let mut new_index = (old_index as isize - diagonal) as usize;
            while old_index < old.len() && new_index < new.len() && old[old_index] == new[new_index]
            {
                old_index += 1;
                new_index += 1;
            }
            current.push(old_index);
            if old_index == old.len() && new_index == new.len() {
                frontiers.push(current);
                return backtrack(old, new, &frontiers, distance);
            }
        }
        frontiers.push(current);
    }

    unreachable!("Myers search must reach the end of both inputs")
}

fn backtrack<T: Clone + Eq>(
    old: &[T],
    new: &[T],
    frontiers: &[Vec<usize>],
    edit_distance: usize,
) -> Vec<Edit<T>> {
    let mut old_index = old.len();
    let mut new_index = new.len();
    let mut edits = Vec::with_capacity(old.len() + new.len());

    for distance in (1..=edit_distance).rev() {
        let previous = &frontiers[distance - 1];
        let diagonal = old_index as isize - new_index as isize;
        let index = ((diagonal + distance as isize) / 2) as usize;
        let (previous_diagonal, previous_old, inserted) =
            if index == 0 || (index != distance && previous[index - 1] < previous[index]) {
                (diagonal + 1, previous[index], true)
            } else {
                (diagonal - 1, previous[index - 1], false)
            };
        let previous_new = (previous_old as isize - previous_diagonal) as usize;

        while old_index > previous_old && new_index > previous_new {
            old_index -= 1;
            new_index -= 1;
            edits.push(Edit::Same(old[old_index].clone()));
        }
        if inserted {
            new_index -= 1;
            edits.push(Edit::Add(new[new_index].clone()));
        } else {
            old_index -= 1;
            edits.push(Edit::Remove(old[old_index].clone()));
        }
    }

    while old_index > 0 && new_index > 0 {
        old_index -= 1;
        new_index -= 1;
        edits.push(Edit::Same(old[old_index].clone()));
    }
    edits.reverse();
    edits
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ambiguous_internal_matches_have_a_stable_anchor() {
        assert_eq!(
            vec![
                Edit::Remove("A"),
                Edit::Same("B"),
                Edit::Add("C"),
                Edit::Add("A"),
            ],
            calculate_edits(&["A", "B"], &["B", "C", "A"])
        );
    }
}
