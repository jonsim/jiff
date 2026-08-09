mod align;
mod wrap;

use crate::config::ColorScheme;
use align::align;
use ansi_term::Style;
use ansi_term::{ANSIString, ANSIStrings};
use itertools::EitherOrBoth;
use itertools::Itertools;
use similar::{capture_diff_slices, Algorithm, DiffTag, TextDiff};
use std::fmt::Write;
use std::sync::LazyLock;
use unicode_width::UnicodeWidthStr;
use wrap::wrap_ansistrings;

static DEBUG: LazyLock<bool> =
    LazyLock::new(|| matches!(std::env::var("JIFF_DEBUG").as_deref(), Ok("1")));

/// One contiguous region in a text diff.
#[derive(Debug, Eq, PartialEq)]
pub(super) enum Diff {
    Same(String),
    Add(String),
    Remove(String),
    Replace(String, String),
    Omitted(usize),
}

#[derive(Default)]
struct DiffStyling {
    same: Style,
    add: Style,
    add_highlight: Style,
    remove: Style,
    remove_highlight: Style,
}

fn indicator_style(mut style: Style) -> Style {
    if style.is_plain() {
        return style;
    }
    style.is_bold = true;
    style
}

fn indicator_styling(colors: &ColorScheme) -> DiffStyling {
    // Bold change indicators remain legible beside highlighted text without
    // introducing a second colour scheme for margins and line numbers.
    DiffStyling {
        same: indicator_style(colors.same),
        add: indicator_style(colors.add),
        add_highlight: indicator_style(colors.add),
        remove: indicator_style(colors.remove),
        remove_highlight: indicator_style(colors.remove),
    }
}

/// Calculates changes between newline-separated line contents.
///
/// The heuristic Myers algorithm avoids the previous quadratic LCS matrix. It
/// can choose a non-minimal script when an exact search grows expensive; that
/// is a deliberate latency trade-off for a command-line tool.
pub(super) fn calculate_line_diff(left: &str, right: &str) -> Vec<Diff> {
    // Rust's `split` represents an empty string as one empty item. Jiff treats
    // empty input as having no lines, consistent with `read_file_or_die`.
    let old_lines: Vec<&str> = if left.is_empty() {
        Vec::new()
    } else {
        left.split('\n').collect()
    };
    let new_lines: Vec<&str> = if right.is_empty() {
        Vec::new()
    } else {
        right.split('\n').collect()
    };

    // Work from operations rather than individual changes so adjacent removed
    // and added ranges remain one `Replace` for the line-pairing stage.
    capture_diff_slices(Algorithm::Myers, &old_lines, &new_lines)
        .iter()
        .map(|operation| {
            let old = old_lines[operation.old_range()].join("\n");
            let new = new_lines[operation.new_range()].join("\n");
            make_diff(operation.tag(), old, new)
        })
        .collect()
}

/// Calculates Unicode-scalar changes within a pair of lines.
pub(super) fn calculate_char_diff(left: &str, right: &str) -> Vec<Diff> {
    let diff = TextDiff::configure()
        .algorithm(Algorithm::Myers)
        .diff_chars(left, right);

    diff.ops()
        .iter()
        .map(|operation| {
            // Operation ranges index the character tokens held by `TextDiff`,
            // not byte offsets into the inputs. Reassemble those source slices
            // to keep every returned string on a valid UTF-8 boundary.
            let old = operation
                .old_range()
                .fold(String::new(), |mut text, index| {
                    text.push_str(diff.old_slice(index).expect("diff old range is valid"));
                    text
                });
            let new = operation
                .new_range()
                .fold(String::new(), |mut text, index| {
                    text.push_str(diff.new_slice(index).expect("diff new range is valid"));
                    text
                });

            make_diff(operation.tag(), old, new)
        })
        .collect()
}

/// Limits unchanged regions to the requested lines around each change.
///
/// Omitted regions retain their line count so the side-by-side renderer can
/// continue with the real source line numbers after each gap.
pub(super) fn limit_context(diffs: Vec<Diff>, context_lines: usize) -> Vec<Diff> {
    let diff_count = diffs.len();
    let mut limited = Vec::new();

    for (index, change) in diffs.into_iter().enumerate() {
        let Diff::Same(same) = change else {
            limited.push(change);
            continue;
        };

        let lines: Vec<&str> = same.split('\n').collect();
        // A leading unchanged region only contributes lines before the first
        // change; a trailing region only contributes lines after the last.
        let prefix_count = if index > 0 {
            context_lines.min(lines.len())
        } else {
            0
        };
        let suffix_count = if index + 1 < diff_count {
            context_lines.min(lines.len() - prefix_count)
        } else {
            0
        };
        let omitted_count = lines.len() - prefix_count - suffix_count;

        if omitted_count == 0 {
            limited.push(Diff::Same(same));
            continue;
        }
        if prefix_count > 0 {
            limited.push(Diff::Same(lines[..prefix_count].join("\n")));
        }
        limited.push(Diff::Omitted(omitted_count));
        if suffix_count > 0 {
            limited.push(Diff::Same(lines[lines.len() - suffix_count..].join("\n")));
        }
    }

    limited
}

fn omission_text(line_count: usize) -> String {
    let noun = if line_count == 1 { "line" } else { "lines" };
    format!("... {line_count} unchanged {noun} ...")
}

fn make_diff(tag: DiffTag, old: String, new: String) -> Diff {
    match tag {
        DiffTag::Equal => Diff::Same(old),
        DiffTag::Delete => Diff::Remove(old),
        DiffTag::Insert => Diff::Add(new),
        DiffTag::Replace => Diff::Replace(old, new),
    }
}

/// Renders a unified diff, including character highlighting for paired lines.
pub(super) fn render_diffs(diffs: &[Diff], colors: &ColorScheme) -> String {
    let line_styling = colors;
    let margin_styling = indicator_styling(colors);
    let mut output = String::new();

    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let margin = margin_styling.same.paint("  ");
                    let fmt = line_styling.same.paint(line);
                    writeln!(&mut output, "{}{}", margin, fmt)
                        .expect("writing to a String cannot fail");
                }
            }
            Diff::Add(add) => {
                for line in add.split('\n') {
                    let margin = margin_styling.add.paint("+ ");
                    let fmt = line_styling.add.paint(line);
                    writeln!(&mut output, "{}{}", margin, fmt)
                        .expect("writing to a String cannot fail");
                }
            }
            Diff::Remove(rem) => {
                for line in rem.split('\n') {
                    let margin = margin_styling.remove.paint("- ");
                    let fmt = line_styling.remove.paint(line);
                    writeln!(&mut output, "{}{}", margin, fmt)
                        .expect("writing to a String cannot fail");
                }
            }
            Diff::Omitted(line_count) => {
                let margin = margin_styling.same.paint("  ");
                let message = omission_text(*line_count);
                let fmt = line_styling.same.paint(message);
                writeln!(&mut output, "{}{}", margin, fmt)
                    .expect("writing to a String cannot fail");
            }
            Diff::Replace(before, after) => {
                let lines_b: Vec<&str> = before.split('\n').collect();
                let lines_a: Vec<&str> = after.split('\n').collect();
                let alignment = align(&lines_b, &lines_a);
                let mut fmts_b = Vec::new();
                let mut fmts_a = Vec::new();
                for aligned in alignment {
                    match aligned {
                        (Some(before), None) => {
                            fmts_b.push(margin_styling.remove_highlight.paint("- "));
                            fmts_b.push(line_styling.remove_highlight.paint(before));
                            fmts_b.push(Style::default().paint("\n"));
                        }
                        (None, Some(after)) => {
                            fmts_a.push(margin_styling.add_highlight.paint("+ "));
                            fmts_a.push(line_styling.add_highlight.paint(after));
                            fmts_a.push(Style::default().paint("\n"));
                        }
                        (Some(before), Some(after)) => {
                            fmts_b.push(margin_styling.remove.paint("- "));
                            fmts_a.push(margin_styling.add.paint("+ "));
                            _style_diff_line(before, after, line_styling, &mut fmts_b, &mut fmts_a);
                            fmts_b.push(Style::default().paint("\n"));
                            fmts_a.push(Style::default().paint("\n"));
                        }
                        (None, None) => unreachable!("alignment cannot omit both lines"),
                    }
                }
                write!(&mut output, "{}", ANSIStrings(&fmts_b))
                    .expect("writing to a String cannot fail");
                write!(&mut output, "{}", ANSIStrings(&fmts_a))
                    .expect("writing to a String cannot fail");
            }
        }
    }

    output
}

// These arguments deliberately mirror the left and right output columns.
#[allow(clippy::too_many_arguments)]
fn _render_side_by_side_line(
    output: &mut String,
    lineno_l: ANSIString,
    lineno_r: ANSIString,
    wrapno_l: ANSIString,
    wrapno_r: ANSIString,
    line_l: &[ANSIString],
    line_r: &[ANSIString],
    line_width: (usize, usize),
    separator: &str,
) {
    let mut margin_l = &lineno_l;
    let mut margin_r = &lineno_r;
    let line_l_iter = wrap_ansistrings(line_l, line_width.0, true);
    let line_r_iter = wrap_ansistrings(line_r, line_width.1, false);
    let mut first_iteration = true;
    for zipped in line_l_iter.zip_longest(line_r_iter) {
        let (wrapped_l, wrapped_r) = match zipped {
            EitherOrBoth::Both(l, r) => (l, r),
            EitherOrBoth::Left(l) => (l, " ".repeat(line_width.1)),
            EitherOrBoth::Right(r) => (" ".repeat(line_width.0), r),
        };

        // A missing right line has no line number or text worth padding. Stop
        // at the separator so redirected output does not contain whitespace.
        if margin_r.trim().is_empty() && wrapped_r.is_empty() {
            writeln!(output, "{} {}{}", margin_l, wrapped_l, separator)
                .expect("writing to a String cannot fail");
        } else {
            writeln!(
                output,
                "{} {}{}{} {}",
                margin_l, wrapped_l, separator, margin_r, wrapped_r
            )
            .expect("writing to a String cannot fail");
        }
        if first_iteration {
            margin_l = &wrapno_l;
            margin_r = &wrapno_r;
            first_iteration = false;
        }
    }
}

fn _style_diff_line<'u>(
    before: &'u str,
    after: &'u str,
    styling: &ColorScheme,
    before_fmts: &mut Vec<ANSIString<'u>>,
    after_fmts: &mut Vec<ANSIString<'u>>,
) {
    for char_change in calculate_char_diff(before, after) {
        match char_change {
            Diff::Same(same) => {
                before_fmts.push(styling.remove.paint(same.clone()));
                after_fmts.push(styling.add.paint(same));
            }
            Diff::Add(add) => {
                after_fmts.push(styling.add_highlight.paint(add));
            }
            Diff::Remove(rem) => {
                before_fmts.push(styling.remove_highlight.paint(rem));
            }
            Diff::Replace(rem, add) => {
                before_fmts.push(styling.remove_highlight.paint(rem));
                after_fmts.push(styling.add_highlight.paint(add));
            }
            Diff::Omitted(_) => unreachable!("character diffs are never context-limited"),
        }
    }
}

fn side_by_side_line_width(term_width: usize, lineno_width: usize, separator: &str) -> usize {
    let separator_width = separator.width();
    let fixed_width = separator_width + 2 * (lineno_width + 2);

    // Some terminals briefly report tiny dimensions while being resized. A
    // one-column line still lets the wrapping iterator make progress.
    term_width.saturating_sub(fixed_width).div_euclid(2).max(1)
}

/// Renders a two-column diff sized to the current terminal.
pub(super) fn render_diffs_side_by_side(
    diffs: &[Diff],
    max_line_count: usize,
    colors: &ColorScheme,
) -> String {
    let lineno_styling = indicator_styling(colors);
    let line_styling = colors;
    let mut output = String::new();

    let sep = "\u{2502}";
    let lineno_width = max_line_count.max(1).to_string().len();
    let term_width = term_size::dimensions_stdout()
        .map(|(term_width, _)| term_width)
        .unwrap_or(120);
    let line_width = side_by_side_line_width(term_width, lineno_width, sep);
    let line_width = (line_width, line_width);

    let mut lineno_l = 1;
    let mut lineno_r = 1;
    let empty_lineno = " ".repeat(lineno_width + 1);
    for change in diffs {
        if *DEBUG {
            eprintln!("Diff: {:?}", change)
        };
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let lineno_l_fmt = format!("{:w$}:", lineno_l, w = lineno_width);
                    let lineno_r_fmt = format!("{:w$}:", lineno_r, w = lineno_width);
                    _render_side_by_side_line(
                        &mut output,
                        lineno_styling.same.paint(&lineno_l_fmt),
                        lineno_styling.same.paint(&lineno_r_fmt),
                        lineno_styling.same.paint(&empty_lineno),
                        lineno_styling.same.paint(&empty_lineno),
                        &[line_styling.same.paint(line)],
                        &[line_styling.same.paint(line)],
                        line_width,
                        sep,
                    );
                    lineno_l += 1;
                    lineno_r += 1;
                }
            }
            Diff::Add(add) => {
                for line_r in add.split('\n') {
                    let lineno_r_fmt = format!("{:w$}:", lineno_r, w = lineno_width);
                    _render_side_by_side_line(
                        &mut output,
                        lineno_styling.same.paint(&empty_lineno),
                        lineno_styling.add_highlight.paint(&lineno_r_fmt),
                        lineno_styling.same.paint(&empty_lineno),
                        lineno_styling.add_highlight.paint(&empty_lineno),
                        &[line_styling.same.paint("")],
                        &[line_styling.add_highlight.paint(line_r)],
                        line_width,
                        sep,
                    );
                    lineno_r += 1;
                }
            }
            Diff::Remove(rem) => {
                for line_l in rem.split('\n') {
                    let lineno_l_fmt = format!("{:w$}:", lineno_l, w = lineno_width);
                    _render_side_by_side_line(
                        &mut output,
                        lineno_styling.remove_highlight.paint(&lineno_l_fmt),
                        lineno_styling.same.paint(&empty_lineno),
                        lineno_styling.remove_highlight.paint(&empty_lineno),
                        lineno_styling.same.paint(&empty_lineno),
                        &[line_styling.remove_highlight.paint(line_l)],
                        &[line_styling.same.paint("")],
                        line_width,
                        sep,
                    );
                    lineno_l += 1;
                }
            }
            Diff::Omitted(line_count) => {
                let message = omission_text(*line_count);
                _render_side_by_side_line(
                    &mut output,
                    lineno_styling.same.paint(&empty_lineno),
                    lineno_styling.same.paint(&empty_lineno),
                    lineno_styling.same.paint(&empty_lineno),
                    lineno_styling.same.paint(&empty_lineno),
                    &[line_styling.same.paint(&message)],
                    &[line_styling.same.paint(&message)],
                    line_width,
                    sep,
                );
                lineno_l += line_count;
                lineno_r += line_count;
            }
            Diff::Replace(before, after) => {
                let lines_b: Vec<&str> = before.split('\n').collect();
                let lines_a: Vec<&str> = after.split('\n').collect();
                let alignment = align(&lines_b, &lines_a);
                for aligned in alignment {
                    if *DEBUG {
                        eprintln!("  Aligned: {:?}", aligned)
                    };
                    match aligned {
                        (Some(line_l), None) => {
                            let lineno_l_fmt = format!("{:w$}:", lineno_l, w = lineno_width);
                            _render_side_by_side_line(
                                &mut output,
                                lineno_styling.remove_highlight.paint(&lineno_l_fmt),
                                lineno_styling.same.paint(&empty_lineno),
                                lineno_styling.remove_highlight.paint(&empty_lineno),
                                lineno_styling.same.paint(&empty_lineno),
                                &[line_styling.remove_highlight.paint(line_l)],
                                &[line_styling.same.paint("")],
                                line_width,
                                sep,
                            );
                            lineno_l += 1;
                        }
                        (None, Some(line_r)) => {
                            let lineno_r_fmt = format!("{:w$}:", lineno_r, w = lineno_width);
                            _render_side_by_side_line(
                                &mut output,
                                lineno_styling.same.paint(&empty_lineno),
                                lineno_styling.add_highlight.paint(&lineno_r_fmt),
                                lineno_styling.same.paint(&empty_lineno),
                                lineno_styling.add_highlight.paint(&empty_lineno),
                                &[line_styling.same.paint("")],
                                &[line_styling.add_highlight.paint(line_r)],
                                line_width,
                                sep,
                            );
                            lineno_r += 1;
                        }
                        (Some(line_l), Some(line_r)) => {
                            let lineno_l_fmt = format!("{:w$}:", lineno_l, w = lineno_width);
                            let lineno_r_fmt = format!("{:w$}:", lineno_r, w = lineno_width);
                            let mut fmt_l = Vec::new();
                            let mut fmt_r = Vec::new();
                            _style_diff_line(line_l, line_r, line_styling, &mut fmt_l, &mut fmt_r);
                            _render_side_by_side_line(
                                &mut output,
                                lineno_styling.remove.paint(&lineno_l_fmt),
                                lineno_styling.add.paint(&lineno_r_fmt),
                                lineno_styling.remove.paint(&empty_lineno),
                                lineno_styling.add.paint(&empty_lineno),
                                &fmt_l,
                                &fmt_r,
                                line_width,
                                sep,
                            );
                            lineno_l += 1;
                            lineno_r += 1;
                        }
                        (None, None) => unreachable!("alignment cannot omit both lines"),
                    }
                }
            }
        }
    }

    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn line_diff_preserves_unchanged_text() {
        // An unchanged file should remain one chunk rather than disappearing.
        let diffs = calculate_line_diff("Kermit\nFozzie", "Kermit\nFozzie");

        assert_eq!(vec![Diff::Same("Kermit\nFozzie".to_string())], diffs);
    }

    #[test]
    fn line_diff_reports_an_insertion() {
        // A line inserted between two anchors should be one addition.
        let diffs = calculate_line_diff("Kermit\nGonzo", "Kermit\nFozzie\nGonzo");

        assert_eq!(
            vec![
                Diff::Same("Kermit".to_string()),
                Diff::Add("Fozzie".to_string()),
                Diff::Same("Gonzo".to_string()),
            ],
            diffs
        );
    }

    #[test]
    fn line_diff_matches_a_final_line_with_an_interior_line() {
        // Line endings are separators, so they must not prevent this exact match.
        let diffs = calculate_line_diff("first", "before\nfirst\nafter");

        assert_eq!(
            vec![
                Diff::Add("before".to_string()),
                Diff::Same("first".to_string()),
                Diff::Add("after".to_string()),
            ],
            diffs
        );
    }

    #[test]
    fn line_diff_reports_a_removal() {
        // A line removed between two anchors should be one removal.
        let diffs = calculate_line_diff("Kermit\nFozzie\nGonzo", "Kermit\nGonzo");

        assert_eq!(
            vec![
                Diff::Same("Kermit".to_string()),
                Diff::Remove("Fozzie".to_string()),
                Diff::Same("Gonzo".to_string()),
            ],
            diffs
        );
    }

    #[test]
    fn line_diff_combines_adjacent_removal_and_addition() {
        // Changed runs belong in one replacement so line alignment can refine them.
        let diffs = calculate_line_diff("Kermit\nFozzie", "Kermit\nGonzo");

        assert_eq!(
            vec![
                Diff::Same("Kermit".to_string()),
                Diff::Replace("Fozzie".to_string(), "Gonzo".to_string()),
            ],
            diffs
        );
    }

    #[test]
    fn char_diff_handles_unicode_as_characters() {
        // A multi-byte character should be replaced as a whole character.
        let diffs = calculate_char_diff("café", "cafe");

        assert_eq!(
            vec![
                Diff::Same("caf".to_string()),
                Diff::Replace("é".to_string(), "e".to_string()),
            ],
            diffs
        );
    }

    #[test]
    fn context_keeps_lines_on_each_side_of_a_change() {
        // Leading and trailing ranges keep the lines nearest the replacement.
        let diffs = vec![
            Diff::Same("one\ntwo\nthree\nfour".to_string()),
            Diff::Replace("Kermit".to_string(), "Fozzie".to_string()),
            Diff::Same("five\nsix\nseven\neight".to_string()),
        ];

        let limited = limit_context(diffs, 2);

        assert_eq!(
            vec![
                Diff::Omitted(2),
                Diff::Same("three\nfour".to_string()),
                Diff::Replace("Kermit".to_string(), "Fozzie".to_string()),
                Diff::Same("five\nsix".to_string()),
                Diff::Omitted(2),
            ],
            limited
        );
    }

    #[test]
    fn context_joins_nearby_changes_without_an_omission() {
        // Overlapping context belongs to one continuous hunk.
        let diffs = vec![
            Diff::Remove("Kermit".to_string()),
            Diff::Same("one\ntwo\nthree".to_string()),
            Diff::Add("Fozzie".to_string()),
        ];

        let limited = limit_context(diffs, 2);

        assert_eq!(
            vec![
                Diff::Remove("Kermit".to_string()),
                Diff::Same("one\ntwo\nthree".to_string()),
                Diff::Add("Fozzie".to_string()),
            ],
            limited
        );
    }

    #[test]
    fn zero_context_omits_every_unchanged_line() {
        let diffs = vec![
            Diff::Same("one\ntwo".to_string()),
            Diff::Replace("Kermit".to_string(), "Fozzie".to_string()),
            Diff::Same("three\nfour".to_string()),
        ];

        let limited = limit_context(diffs, 0);

        assert_eq!(
            vec![
                Diff::Omitted(2),
                Diff::Replace("Kermit".to_string(), "Fozzie".to_string()),
                Diff::Omitted(2),
            ],
            limited
        );
    }

    #[test]
    fn side_by_side_line_numbers_advance_over_omitted_lines() {
        // The first visible line after a gap keeps its source line number.
        let diffs = vec![Diff::Omitted(9), Diff::Same("Kermit".to_string())];

        let output = render_diffs_side_by_side(&diffs, 10, &ColorScheme::plain());

        assert!(output.contains("10: Kermit"));
    }

    #[test]
    fn side_by_side_width_accounts_for_fixed_columns() {
        // A 120-column terminal leaves 56 text columns on each side.
        assert_eq!(56, side_by_side_line_width(120, 1, "│"));
    }

    #[test]
    fn side_by_side_width_survives_a_tiny_terminal() {
        // Terminal resizing can report less width than the margins require.
        assert_eq!(1, side_by_side_line_width(4, 3, "│"));
    }
}
