use super::align::align;
use super::wrap::wrap_ansistrings;
use super::{
    calculate_line_diff, line_diff_overrides, line_number_margin, omission_text, terminal_width,
    three_way_line_width, Diff, StyleOverride,
};
use crate::config::ColorScheme;
use crate::syntax::HighlightedFile;
use itertools::Itertools;
use nu_ansi_term::{AnsiString as ANSIString, Style};
use std::fmt::Write;

/// A zero-based line number in one of the three original files.
type LineIndex = usize;

#[derive(Debug, Eq, PartialEq)]
struct LinePair {
    // This is either Local -> Base or Base -> Remote. A missing index means an
    // outer-file insertion or removal beside the next base line.
    left: Option<LineIndex>,
    right: Option<LineIndex>,
}

#[derive(Debug, Eq, PartialEq)]
struct ThreeWayLine {
    // A middle index ties the row to that base-file line. Without one, the row
    // holds outer-file insertions beside the next base line.
    left: Option<LineIndex>,
    middle: Option<LineIndex>,
    right: Option<LineIndex>,
}

impl ThreeWayLine {
    fn is_unchanged(&self, source_lines: [&[&str]; 3]) -> bool {
        match (self.left, self.middle, self.right) {
            (Some(left), Some(middle), Some(right)) => {
                source_lines[0][left] == source_lines[1][middle]
                    && source_lines[1][middle] == source_lines[2][right]
            }
            _ => false,
        }
    }
}

enum ThreeWayRow {
    Line(ThreeWayLine),
    Omitted(usize),
}

fn append_line_pairs<'a>(
    pairs: &mut Vec<LinePair>,
    left_index: &mut usize,
    right_index: &mut usize,
    alignment: impl IntoIterator<Item = (Option<&'a str>, Option<&'a str>)>,
) {
    for (left, right) in alignment {
        let left = left.map(|_| {
            let index = *left_index;
            *left_index += 1;
            index
        });
        let right = right.map(|_| {
            let index = *right_index;
            *right_index += 1;
            index
        });
        pairs.push(LinePair { left, right });
    }
}

fn aligned_lines(left: &str, right: &str) -> Vec<LinePair> {
    let mut pairs = Vec::new();
    let mut left_index = 0;
    let mut right_index = 0;

    for change in calculate_line_diff(left, right) {
        match change {
            Diff::Same(same) => append_line_pairs(
                &mut pairs,
                &mut left_index,
                &mut right_index,
                same.split('\n').map(|line| (Some(line), Some(line))),
            ),
            Diff::Add(add) => append_line_pairs(
                &mut pairs,
                &mut left_index,
                &mut right_index,
                add.split('\n').map(|line| (None, Some(line))),
            ),
            Diff::Remove(remove) => append_line_pairs(
                &mut pairs,
                &mut left_index,
                &mut right_index,
                remove.split('\n').map(|line| (Some(line), None)),
            ),
            Diff::Replace(before, after) => {
                let before_lines: Vec<_> = before.split('\n').collect();
                let after_lines: Vec<_> = after.split('\n').collect();
                append_line_pairs(
                    &mut pairs,
                    &mut left_index,
                    &mut right_index,
                    align(&before_lines, &after_lines),
                );
            }
            Diff::Omitted(_) => unreachable!("unlimited line diffs contain no omissions"),
        }
    }
    pairs
}

fn append_outer_lines(rows: &mut Vec<ThreeWayLine>, left: Vec<LineIndex>, right: Vec<LineIndex>) {
    // Put insertions at the same base-file boundary on one row. That doesn't
    // mean the outer lines match; it just keeps the three panes compact.
    let line_count = left.len().max(right.len());
    let mut left = left.into_iter();
    let mut right = right.into_iter();
    for _ in 0..line_count {
        rows.push(ThreeWayLine {
            left: left.next(),
            middle: None,
            right: right.next(),
        });
    }
}

fn take_left_only(pairs: &[LinePair], cursor: &mut usize) -> Vec<LineIndex> {
    let mut lines = Vec::new();
    while let Some(pair) = pairs.get(*cursor).filter(|pair| pair.right.is_none()) {
        lines.push(pair.left.expect("an aligned row cannot omit both sides"));
        *cursor += 1;
    }
    lines
}

fn take_right_only(pairs: &[LinePair], cursor: &mut usize) -> Vec<LineIndex> {
    let mut lines = Vec::new();
    while let Some(pair) = pairs.get(*cursor).filter(|pair| pair.left.is_none()) {
        lines.push(pair.right.expect("an aligned row cannot omit both sides"));
        *cursor += 1;
    }
    lines
}

fn three_way_lines(left: &str, middle: &str, right: &str) -> Vec<ThreeWayLine> {
    let left_pairs = aligned_lines(left, middle);
    let right_pairs = aligned_lines(middle, right);
    let middle_line_count = if middle.is_empty() {
        0
    } else {
        middle.split('\n').count()
    };
    let mut left_cursor = 0;
    let mut right_cursor = 0;
    let mut rows = Vec::new();

    for middle_index in 0..middle_line_count {
        // Each pairwise diff puts outer-only rows just before the next base
        // line. Bring both sides together before adding that base line.
        append_outer_lines(
            &mut rows,
            take_left_only(&left_pairs, &mut left_cursor),
            take_right_only(&right_pairs, &mut right_cursor),
        );

        let left_pair = &left_pairs[left_cursor];
        let right_pair = &right_pairs[right_cursor];
        let middle_line = left_pair
            .right
            .expect("every middle line appears in the left alignment");
        debug_assert_eq!(middle_index, middle_line);
        debug_assert_eq!(right_pair.left, Some(middle_line));
        rows.push(ThreeWayLine {
            left: left_pair.left,
            middle: Some(middle_line),
            right: right_pair.right,
        });
        left_cursor += 1;
        right_cursor += 1;
    }

    append_outer_lines(
        &mut rows,
        take_left_only(&left_pairs, &mut left_cursor),
        take_right_only(&right_pairs, &mut right_cursor),
    );
    debug_assert_eq!(left_pairs.len(), left_cursor);
    debug_assert_eq!(right_pairs.len(), right_cursor);
    rows
}

fn limit_three_way_context(
    lines: Vec<ThreeWayLine>,
    source_lines: [&[&str]; 3],
    context_lines: usize,
) -> Vec<ThreeWayRow> {
    let mut keep = vec![false; lines.len()];
    // Make one pass in each direction so a change on either outer side keeps
    // nearby context. A single pairwise pass would miss the other side.
    let mut distance = usize::MAX;
    for (index, line) in lines.iter().enumerate() {
        distance = if line.is_unchanged(source_lines) {
            distance.saturating_add(1)
        } else {
            0
        };
        keep[index] = distance <= context_lines;
    }
    distance = usize::MAX;
    for (index, line) in lines.iter().enumerate().rev() {
        distance = if line.is_unchanged(source_lines) {
            distance.saturating_add(1)
        } else {
            0
        };
        keep[index] |= distance <= context_lines;
    }

    let mut rows = Vec::new();
    let mut omitted = 0;
    for (line, keep) in lines.into_iter().zip(keep) {
        if keep {
            if omitted > 0 {
                rows.push(ThreeWayRow::Omitted(omitted));
                omitted = 0;
            }
            rows.push(ThreeWayRow::Line(line));
        } else {
            omitted += 1;
        }
    }
    if omitted > 0 {
        rows.push(ThreeWayRow::Omitted(omitted));
    }
    rows
}

struct ThreeWayHighlighting<'a> {
    left: &'a HighlightedFile,
    middle: &'a HighlightedFile,
    right: &'a HighlightedFile,
}

struct PaneLine<'a> {
    lineno: ANSIString<'a>,
    wrapno: ANSIString<'a>,
    text: &'a [ANSIString<'a>],
    present: bool,
}

fn render_three_way_line(
    output: &mut String,
    panes: &[PaneLine; 3],
    line_width: usize,
    separator: &str,
) {
    let wrapped: Vec<Vec<String>> = panes
        .iter()
        .enumerate()
        .map(|(index, pane)| wrap_ansistrings(pane.text, line_width, index < 2).collect())
        .collect();
    let height = wrapped.iter().map(Vec::len).max().unwrap_or(1);
    let padded_empty = " ".repeat(line_width);

    for index in 0..height {
        let margins: Vec<_> = panes
            .iter()
            .map(|pane| {
                if index == 0 {
                    &pane.lineno
                } else {
                    &pane.wrapno
                }
            })
            .collect();
        let left = wrapped[0]
            .get(index)
            .map(String::as_str)
            .unwrap_or(&padded_empty);
        let middle = wrapped[1]
            .get(index)
            .map(String::as_str)
            .unwrap_or(&padded_empty);
        let right = wrapped[2].get(index).map(String::as_str).unwrap_or("");

        write!(
            output,
            "{} {}{}{} {}{}",
            margins[0], left, separator, margins[1], middle, separator
        )
        .expect("writing to a String cannot fail");
        write!(output, "{}", margins[2]).expect("writing to a String cannot fail");
        if panes[2].present && index < wrapped[2].len() && !right.is_empty() {
            write!(output, " {right}").expect("writing to a String cannot fail");
        }
        output.push('\n');
    }
}

fn merge_middle_overrides(
    from_left: &[StyleOverride],
    from_right: &[StyleOverride],
    overlap: Style,
) -> Vec<StyleOverride> {
    // Both span lists are sorted and don't overlap. Merge their boundaries and
    // walk each list once; rescanning every tiny region gets painfully slow on
    // minified text.
    let boundaries: Vec<_> = from_left
        .iter()
        .flat_map(|(range, _)| [range.start, range.end])
        .merge(
            from_right
                .iter()
                .flat_map(|(range, _)| [range.start, range.end]),
        )
        .dedup()
        .collect();

    let mut merged: Vec<StyleOverride> = Vec::new();
    let mut left_index = 0;
    let mut right_index = 0;
    for boundary in boundaries.windows(2) {
        let start = boundary[0];
        let end = boundary[1];
        while from_left
            .get(left_index)
            .is_some_and(|(range, _)| range.end <= start)
        {
            left_index += 1;
        }
        while from_right
            .get(right_index)
            .is_some_and(|(range, _)| range.end <= start)
        {
            right_index += 1;
        }
        let left_style = from_left
            .get(left_index)
            .filter(|(range, _)| range.start <= start && start < range.end)
            .map(|(_, style)| *style);
        let right_style = from_right
            .get(right_index)
            .filter(|(range, _)| range.start <= start && start < range.end)
            .map(|(_, style)| *style);
        let style = match (left_style, right_style) {
            (Some(_), Some(_)) => overlap,
            (Some(style), None) | (None, Some(style)) => style,
            (None, None) => continue,
        };

        if let Some((previous_range, previous_style)) = merged.last_mut() {
            if previous_range.end == start && *previous_style == style {
                previous_range.end = end;
                continue;
            }
        }
        merged.push((start..end, style));
    }
    merged
}

fn full_line_override(line: &str, style: Style) -> Vec<StyleOverride> {
    if line.is_empty() {
        Vec::new()
    } else {
        vec![(0..line.len(), style)]
    }
}

fn style_three_way_line<'a>(
    line: &ThreeWayLine,
    source_lines: [&[&'a str]; 3],
    colors: &ColorScheme,
    highlighting: &ThreeWayHighlighting,
) -> [Vec<ANSIString<'a>>; 3] {
    let left = line.left.map(|index| (index, source_lines[0][index]));
    let middle = line.middle.map(|index| (index, source_lines[1][index]));
    let right = line.right.map(|index| (index, source_lines[2][index]));
    let (left, middle_from_left) = match (left, middle) {
        (Some((left_index, left)), Some((_, middle))) if left != middle => {
            let (left_overrides, middle_overrides) = line_diff_overrides(left, middle, colors);
            (
                highlighting
                    .left
                    .render_line(left_index, left, colors.remove, &left_overrides),
                middle_overrides,
            )
        }
        (Some((left_index, left)), Some(_)) => (
            highlighting
                .left
                .render_line(left_index, left, colors.same, &[]),
            Vec::new(),
        ),
        (Some((left_index, left)), None) => (
            highlighting
                .left
                .render_line(left_index, left, colors.remove_highlight, &[]),
            Vec::new(),
        ),
        (None, Some((_, middle))) => (
            vec![colors.same.paint("")],
            full_line_override(middle, colors.add_highlight),
        ),
        (None, None) => (vec![colors.same.paint("")], Vec::new()),
    };
    let (middle_from_right, right) = match (middle, right) {
        (Some((_, middle)), Some((right_index, right))) if middle != right => {
            let (middle_overrides, right_overrides) = line_diff_overrides(middle, right, colors);
            (
                middle_overrides,
                highlighting
                    .right
                    .render_line(right_index, right, colors.add, &right_overrides),
            )
        }
        (Some(_), Some((right_index, right))) => (
            Vec::new(),
            highlighting
                .right
                .render_line(right_index, right, colors.same, &[]),
        ),
        (Some((_, middle)), None) => (
            full_line_override(middle, colors.remove_highlight),
            vec![colors.same.paint("")],
        ),
        (None, Some((right_index, right))) => (
            Vec::new(),
            highlighting
                .right
                .render_line(right_index, right, colors.add_highlight, &[]),
        ),
        (None, None) => (Vec::new(), vec![colors.same.paint("")]),
    };
    let middle = match middle {
        Some((middle_index, middle)) => {
            let overrides = merge_middle_overrides(
                &middle_from_left,
                &middle_from_right,
                colors.overlap_highlight,
            );
            highlighting
                .middle
                .render_line(middle_index, middle, colors.same, &overrides)
        }
        None => vec![colors.same.paint("")],
    };
    [left, middle, right]
}

/// Renders two pairwise alignments as three panes around their shared input.
pub(crate) fn render_three_way_side_by_side(
    contents: [&str; 3],
    labels: [&str; 3],
    colors: &ColorScheme,
    highlighting: [&HighlightedFile; 3],
    context_lines: Option<usize>,
) -> String {
    let split_lines: [Vec<_>; 3] = contents.map(|content| {
        if content.is_empty() {
            Vec::new()
        } else {
            content.split('\n').collect()
        }
    });
    let source_lines = [
        split_lines[0].as_slice(),
        split_lines[1].as_slice(),
        split_lines[2].as_slice(),
    ];
    let lines = three_way_lines(contents[0], contents[1], contents[2]);
    let rows = match context_lines {
        Some(context_lines) => limit_three_way_context(lines, source_lines, context_lines),
        None => lines.into_iter().map(ThreeWayRow::Line).collect(),
    };
    let max_line_count = contents
        .iter()
        .map(|content| {
            if content.is_empty() {
                0
            } else {
                content.split('\n').count()
            }
        })
        .max()
        .unwrap_or(0);
    let lineno_width = max_line_count.max(1).to_string().len();
    let empty_lineno = " ".repeat(lineno_width);
    let separator = "\u{2502}";
    let term_width = terminal_width();
    let line_width = three_way_line_width(term_width, lineno_width, separator);
    let highlighting = ThreeWayHighlighting {
        left: highlighting[0],
        middle: highlighting[1],
        right: highlighting[2],
    };
    let mut output = String::new();

    let headings = [
        colors.same.paint(format!("1: {}", labels[0])),
        colors.same.paint(format!("2: {}", labels[1])),
        colors.same.paint(format!("3: {}", labels[2])),
    ];
    let heading_margin = colors.same.paint(" ".repeat(lineno_width + 1));
    let heading_margins = [
        heading_margin.clone(),
        heading_margin.clone(),
        heading_margin,
    ];
    render_three_way_line(
        &mut output,
        &[
            PaneLine {
                lineno: heading_margins[0].clone(),
                wrapno: heading_margins[0].clone(),
                text: std::slice::from_ref(&headings[0]),
                present: true,
            },
            PaneLine {
                lineno: heading_margins[1].clone(),
                wrapno: heading_margins[1].clone(),
                text: std::slice::from_ref(&headings[1]),
                present: true,
            },
            PaneLine {
                lineno: heading_margins[2].clone(),
                wrapno: heading_margins[2].clone(),
                text: std::slice::from_ref(&headings[2]),
                present: true,
            },
        ],
        line_width,
        separator,
    );

    for row in rows {
        match row {
            ThreeWayRow::Omitted(line_count) => {
                let message = omission_text(line_count);
                let rendered = colors.omitted.paint(&message);
                let margins = line_number_margin(&empty_lineno, colors);
                render_three_way_line(
                    &mut output,
                    &[
                        PaneLine {
                            lineno: margins.clone(),
                            wrapno: margins.clone(),
                            text: std::slice::from_ref(&rendered),
                            present: true,
                        },
                        PaneLine {
                            lineno: margins.clone(),
                            wrapno: margins.clone(),
                            text: std::slice::from_ref(&rendered),
                            present: true,
                        },
                        PaneLine {
                            lineno: margins.clone(),
                            wrapno: margins.clone(),
                            text: std::slice::from_ref(&rendered),
                            present: true,
                        },
                    ],
                    line_width,
                    separator,
                );
            }
            ThreeWayRow::Line(line) => {
                let rendered = style_three_way_line(&line, source_lines, colors, &highlighting);
                let numbers = [
                    line.left.map(|line| line + 1),
                    line.middle.map(|line| line + 1),
                    line.right.map(|line| line + 1),
                ];
                let number_text: Vec<_> = numbers
                    .iter()
                    .map(|number| match number {
                        Some(number) => format!("{number:>lineno_width$}"),
                        None => empty_lineno.clone(),
                    })
                    .collect();
                let margins = [
                    line_number_margin(&number_text[0], colors),
                    line_number_margin(&number_text[1], colors),
                    line_number_margin(&number_text[2], colors),
                ];
                let wrap_margins = [
                    line_number_margin(&empty_lineno, colors),
                    line_number_margin(&empty_lineno, colors),
                    line_number_margin(&empty_lineno, colors),
                ];
                render_three_way_line(
                    &mut output,
                    &[
                        PaneLine {
                            lineno: margins[0].clone(),
                            wrapno: wrap_margins[0].clone(),
                            text: &rendered[0],
                            present: line.left.is_some(),
                        },
                        PaneLine {
                            lineno: margins[1].clone(),
                            wrapno: wrap_margins[1].clone(),
                            text: &rendered[1],
                            present: line.middle.is_some(),
                        },
                        PaneLine {
                            lineno: margins[2].clone(),
                            wrapno: wrap_margins[2].clone(),
                            text: &rendered[2],
                            present: line.right.is_some(),
                        },
                    ],
                    line_width,
                    separator,
                );
            }
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    use nu_ansi_term::Color;

    #[test]
    fn three_way_alignment_uses_the_middle_file_as_its_anchor() {
        let contents = [
            "start\nLOCAL ONLY\nanchor",
            "start\nanchor",
            "start\nREMOTE ONLY\nanchor",
        ];
        let split_lines: [Vec<_>; 3] = contents.map(|content| content.split('\n').collect());
        let source_lines = [
            split_lines[0].as_slice(),
            split_lines[1].as_slice(),
            split_lines[2].as_slice(),
        ];
        let lines = three_way_lines(contents[0], contents[1], contents[2]);

        assert_eq!(3, lines.len());
        assert!(lines[0].is_unchanged(source_lines));
        assert_eq!(Some(1), lines[1].left);
        assert!(lines[1].middle.is_none());
        assert_eq!(Some(1), lines[1].right);
        assert!(lines[2].is_unchanged(source_lines));
    }

    #[test]
    fn three_way_context_is_measured_from_changes_on_either_side() {
        let contents = [
            "zero\nvalue = 11\ntwo\nthree\nfour",
            "zero\nvalue = 10\ntwo\nthree\nfour",
            "zero\nvalue = 10\ntwo\nthree\nfour",
        ];
        let split_lines: [Vec<_>; 3] = contents.map(|content| content.split('\n').collect());
        let source_lines = [
            split_lines[0].as_slice(),
            split_lines[1].as_slice(),
            split_lines[2].as_slice(),
        ];
        let lines = three_way_lines(contents[0], contents[1], contents[2]);

        let rows = limit_three_way_context(lines, source_lines, 1);

        assert_eq!(4, rows.len());
        assert!(matches!(rows[3], ThreeWayRow::Omitted(2)));
    }

    #[test]
    fn three_way_renderer_draws_three_panes() {
        let highlighting = [
            HighlightedFile::default(),
            HighlightedFile::default(),
            HighlightedFile::default(),
        ];

        let output = render_three_way_side_by_side(
            ["same\nlocal", "same\nbase", "same\nremote"],
            ["local.txt", "base.txt", "remote.txt"],
            &ColorScheme::plain(),
            [&highlighting[0], &highlighting[1], &highlighting[2]],
            None,
        );

        assert!(output.contains("1: local.txt"));
        assert!(output.contains("2: base.txt"));
        assert!(output.contains("3: remote.txt"));
        assert_eq!(2, output.lines().next().unwrap().matches('│').count());
        assert!(output
            .lines()
            .skip(1)
            .all(|line| line.matches('│').count() == 5));
        assert!(output.contains("1│ same"));
        assert!(output.lines().all(|line| !line.ends_with(' ')));
        assert!(!output.contains("\x1b["));
    }

    #[test]
    fn three_way_renderer_marks_middle_text_changed_on_both_sides() {
        let colors = ColorScheme::default();
        let highlighting = [
            HighlightedFile::default(),
            HighlightedFile::default(),
            HighlightedFile::default(),
        ];

        let output = render_three_way_side_by_side(
            ["AAAAA", "MMMMM", "ZZZZZ"],
            ["local", "base", "remote"],
            &colors,
            [&highlighting[0], &highlighting[1], &highlighting[2]],
            None,
        );

        assert!(output.contains(&colors.remove_highlight.paint("AAAAA").to_string()));
        assert!(output.contains(&colors.add_highlight.paint("ZZZZZ").to_string()));
        assert!(output.contains(&colors.overlap_highlight.paint("MMMMM").to_string()));
    }

    #[test]
    fn middle_highlights_split_partially_overlapping_changes() {
        let add = Color::Black.on(Color::Green);
        let remove = Color::Black.on(Color::Red);
        let overlap = Color::Black.on(Color::Yellow);

        let merged = merge_middle_overrides(&[(1..5, add)], &[(3..7, remove)], overlap);

        assert_eq!(vec![(1..3, add), (3..5, overlap), (5..7, remove)], merged);
    }

    #[test]
    fn three_way_renderer_marks_middle_intraline_changes_from_each_side() {
        let colors = ColorScheme::default();
        let highlighting = [
            HighlightedFile::default(),
            HighlightedFile::default(),
            HighlightedFile::default(),
        ];
        let references = [&highlighting[0], &highlighting[1], &highlighting[2]];

        let changed_from_left = render_three_way_side_by_side(
            ["hello world", "hello cruel world", "hello cruel world"],
            ["local", "base", "remote"],
            &colors,
            references,
            None,
        );
        let changed_from_right = render_three_way_side_by_side(
            ["hello cruel world", "hello cruel world", "hello world"],
            ["local", "base", "remote"],
            &colors,
            references,
            None,
        );

        assert!(changed_from_left.contains(&colors.add_highlight.paint("cruel ").to_string()));
        assert!(changed_from_right.contains(&colors.remove_highlight.paint("cruel ").to_string()));
    }

    #[test]
    fn three_way_renderer_marks_whole_middle_lines_missing_from_outer_files() {
        let colors = ColorScheme::default();
        let highlighting = [
            HighlightedFile::default(),
            HighlightedFile::default(),
            HighlightedFile::default(),
        ];

        let missing_from_left = render_three_way_side_by_side(
            [
                "start\nend",
                "start\nbase only\nend",
                "start\nbase only\nend",
            ],
            ["local", "base", "remote"],
            &colors,
            [&highlighting[0], &highlighting[1], &highlighting[2]],
            None,
        );
        let missing_from_right = render_three_way_side_by_side(
            [
                "start\nbase only\nend",
                "start\nbase only\nend",
                "start\nend",
            ],
            ["local", "base", "remote"],
            &colors,
            [&highlighting[0], &highlighting[1], &highlighting[2]],
            None,
        );

        assert!(missing_from_left.contains(&colors.add_highlight.paint("base only").to_string()));
        assert!(
            missing_from_right.contains(&colors.remove_highlight.paint("base only").to_string())
        );
    }

    #[test]
    fn three_way_width_accounts_for_both_separators_and_three_margins() {
        assert_eq!(36, three_way_line_width(120, 1, "│"));
    }
}
