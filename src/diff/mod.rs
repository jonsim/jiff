mod align;
mod three_way;
mod wrap;

pub(super) use three_way::render_three_way_side_by_side;

use crate::config::ColorScheme;
use crate::syntax::{HighlightedFile, HighlightedFiles};
use align::align;
use ansi_term::{ANSIString, ANSIStrings, Style};
use itertools::EitherOrBoth;
use itertools::Itertools;
use similar::{capture_diff_slices, Algorithm, DiffTag, TextDiff};
use std::env;
use std::fmt::Write;
use std::ops::Range;
use std::sync::LazyLock;
use unicode_width::UnicodeWidthStr;
use wrap::wrap_ansistrings;

static DEBUG: LazyLock<bool> =
    LazyLock::new(|| matches!(std::env::var("JIFF_DEBUG").as_deref(), Ok("1")));
const DEFAULT_TERMINAL_WIDTH: usize = 120;

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
/// The heuristic Myers algorithm bounds work on difficult inputs by accepting
/// a potentially non-minimal script. That latency trade-off matters more than
/// a theoretically perfect edit script in an interactive command-line tool.
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

    let changes = diff
        .ops()
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
        .collect();

    coalesce_dissimilar_middle(changes)
}

fn coalesce_dissimilar_middle(mut changes: Vec<Diff>) -> Vec<Diff> {
    if changes.len() < 2 {
        return changes;
    }

    // The ends are reliable anchors. Similarity inside the changed middle is
    // judged separately so a long common prefix cannot legitimise accidental
    // one-character matches across otherwise unrelated text.
    let suffix = if matches!(changes.last(), Some(Diff::Same(_))) {
        changes.pop()
    } else {
        None
    };
    let prefix = if matches!(changes.first(), Some(Diff::Same(_))) {
        Some(changes.remove(0))
    } else {
        None
    };

    if let Some(replacement) = dissimilar_replacement(&changes, false) {
        changes = vec![replacement];
    } else {
        // A genuinely common phrase can make the whole line look similar while
        // a smaller replacement inside it is still full of accidental matches.
        // Longer common runs are reliable anchors for judging those regions.
        let mut refined = Vec::new();
        let mut region = Vec::new();
        for change in changes {
            if matches!(&change, Diff::Same(same) if same.chars().count() >= 3) {
                refined.extend(coalesce_dissimilar_region(region));
                refined.push(change);
                region = Vec::new();
            } else {
                region.push(change);
            }
        }
        refined.extend(coalesce_dissimilar_region(region));
        changes = refined;
    }

    prefix.into_iter().chain(changes).chain(suffix).collect()
}

fn coalesce_dissimilar_region(changes: Vec<Diff>) -> Vec<Diff> {
    match dissimilar_replacement(&changes, true) {
        Some(replacement) => vec![replacement],
        None => changes,
    }
}

fn dissimilar_replacement(changes: &[Diff], coalesce_phrases: bool) -> Option<Diff> {
    let mut before = String::new();
    let mut after = String::new();
    let mut matched_characters = 0;
    for change in changes {
        match change {
            Diff::Same(same) => {
                matched_characters += same.chars().count();
                before.push_str(same);
                after.push_str(same);
            }
            Diff::Add(add) => after.push_str(add),
            Diff::Remove(remove) => before.push_str(remove),
            Diff::Replace(remove, add) => {
                before.push_str(remove);
                after.push_str(add);
            }
            Diff::Omitted(_) => unreachable!("character diffs are never context-limited"),
        }
    }

    let middle_length = before.chars().count().max(after.chars().count());
    let fragmented_phrase = coalesce_phrases
        && before.chars().any(char::is_whitespace)
        && after.chars().any(char::is_whitespace);
    if !before.is_empty()
        && !after.is_empty()
        && (matched_characters.saturating_mul(3) < middle_length || fragmented_phrase)
    {
        return Some(Diff::Replace(before, after));
    }
    None
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
pub(super) fn render_diffs(
    diffs: &[Diff],
    colors: &ColorScheme,
    highlighting: &HighlightedFiles,
) -> String {
    let line_styling = colors;
    let margin_styling = indicator_styling(colors);
    let mut output = String::new();
    let mut left_index = 0;
    let mut right_index = 0;

    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let margin = margin_styling.same.paint("  ");
                    let fmt =
                        highlighting
                            .right
                            .render_line(right_index, line, line_styling.same, &[]);
                    writeln!(&mut output, "{}{}", margin, ANSIStrings(&fmt))
                        .expect("writing to a String cannot fail");
                    left_index += 1;
                    right_index += 1;
                }
            }
            Diff::Add(add) => {
                for line in add.split('\n') {
                    let margin = margin_styling.add.paint("+ ");
                    let fmt =
                        highlighting
                            .right
                            .render_line(right_index, line, line_styling.add, &[]);
                    writeln!(&mut output, "{}{}", margin, ANSIStrings(&fmt))
                        .expect("writing to a String cannot fail");
                    right_index += 1;
                }
            }
            Diff::Remove(rem) => {
                for line in rem.split('\n') {
                    let margin = margin_styling.remove.paint("- ");
                    let fmt =
                        highlighting
                            .left
                            .render_line(left_index, line, line_styling.remove, &[]);
                    writeln!(&mut output, "{}{}", margin, ANSIStrings(&fmt))
                        .expect("writing to a String cannot fail");
                    left_index += 1;
                }
            }
            Diff::Omitted(line_count) => {
                let margin = margin_styling.same.paint("  ");
                let message = omission_text(*line_count);
                let fmt = line_styling.omitted.paint(message);
                writeln!(&mut output, "{}{}", margin, fmt)
                    .expect("writing to a String cannot fail");
                left_index += line_count;
                right_index += line_count;
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
                            fmts_b.extend(highlighting.left.render_line(
                                left_index,
                                before,
                                line_styling.remove_highlight,
                                &[],
                            ));
                            fmts_b.push(Style::default().paint("\n"));
                            left_index += 1;
                        }
                        (None, Some(after)) => {
                            fmts_a.push(margin_styling.add_highlight.paint("+ "));
                            fmts_a.extend(highlighting.right.render_line(
                                right_index,
                                after,
                                line_styling.add_highlight,
                                &[],
                            ));
                            fmts_a.push(Style::default().paint("\n"));
                            right_index += 1;
                        }
                        (Some(before), Some(after)) => {
                            fmts_b.push(margin_styling.remove.paint("- "));
                            fmts_a.push(margin_styling.add.paint("+ "));
                            _style_diff_line(
                                before,
                                after,
                                line_styling,
                                &mut fmts_b,
                                &mut fmts_a,
                                (&highlighting.left, left_index),
                                (&highlighting.right, right_index),
                            );
                            fmts_b.push(Style::default().paint("\n"));
                            fmts_a.push(Style::default().paint("\n"));
                            left_index += 1;
                            right_index += 1;
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
        if margin_r.trim().is_empty() && wrapped_r.trim().is_empty() {
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

type StyleOverride = (Range<usize>, Style);

fn line_diff_overrides(
    before: &str,
    after: &str,
    styling: &ColorScheme,
) -> (Vec<StyleOverride>, Vec<StyleOverride>) {
    let mut before_overrides = Vec::new();
    let mut after_overrides = Vec::new();
    let mut before_offset = 0;
    let mut after_offset = 0;

    for char_change in calculate_char_diff(before, after) {
        match char_change {
            Diff::Same(same) => {
                before_offset += same.len();
                after_offset += same.len();
            }
            Diff::Add(add) => {
                let end = after_offset + add.len();
                after_overrides.push((after_offset..end, styling.add_highlight));
                after_offset = end;
            }
            Diff::Remove(rem) => {
                let end = before_offset + rem.len();
                before_overrides.push((before_offset..end, styling.remove_highlight));
                before_offset = end;
            }
            Diff::Replace(rem, add) => {
                let before_end = before_offset + rem.len();
                let after_end = after_offset + add.len();
                before_overrides.push((before_offset..before_end, styling.remove_highlight));
                after_overrides.push((after_offset..after_end, styling.add_highlight));
                before_offset = before_end;
                after_offset = after_end;
            }
            Diff::Omitted(_) => unreachable!("character diffs are never context-limited"),
        }
    }

    (before_overrides, after_overrides)
}

fn _style_diff_line<'u>(
    before: &'u str,
    after: &'u str,
    styling: &ColorScheme,
    before_fmts: &mut Vec<ANSIString<'u>>,
    after_fmts: &mut Vec<ANSIString<'u>>,
    before_syntax: (&HighlightedFile, usize),
    after_syntax: (&HighlightedFile, usize),
) {
    let (before_highlighting, before_index) = before_syntax;
    let (after_highlighting, after_index) = after_syntax;
    let (before_overrides, after_overrides) = line_diff_overrides(before, after, styling);

    before_fmts.extend(before_highlighting.render_line(
        before_index,
        before,
        styling.remove,
        &before_overrides,
    ));
    after_fmts.extend(after_highlighting.render_line(
        after_index,
        after,
        styling.add,
        &after_overrides,
    ));
}

fn side_by_side_line_width(term_width: usize, lineno_width: usize, separator: &str) -> usize {
    let separator_width = separator.width();
    let fixed_width = separator_width + 2 * (lineno_width + 2);

    // Some terminals briefly report tiny dimensions while being resized. A
    // one-column line still lets the wrapping iterator make progress.
    term_width.saturating_sub(fixed_width).div_euclid(2).max(1)
}

fn three_way_line_width(term_width: usize, lineno_width: usize, separator: &str) -> usize {
    let separator_width = separator.width();
    let fixed_width = 2 * separator_width + 3 * (lineno_width + 2);

    term_width.saturating_sub(fixed_width).div_euclid(3).max(1)
}

fn terminal_width() -> usize {
    // `COLUMNS` is how Git, CI and terminal wrappers pass a useful width when
    // none of Jiff's standard streams is itself attached to the terminal.
    env::var("COLUMNS")
        .ok()
        .and_then(|columns| columns.parse().ok())
        .filter(|columns| *columns > 0)
        .or_else(|| term_size::dimensions().map(|(columns, _)| columns))
        .unwrap_or(DEFAULT_TERMINAL_WIDTH)
}

/// Renders a two-column diff sized to the current terminal.
pub(super) fn render_diffs_side_by_side(
    diffs: &[Diff],
    max_line_count: usize,
    colors: &ColorScheme,
    highlighting: &HighlightedFiles,
) -> String {
    let lineno_styling = indicator_styling(colors);
    let line_styling = colors;
    let mut output = String::new();

    let sep = "\u{2502}";
    let lineno_width = max_line_count.max(1).to_string().len();
    let term_width = terminal_width();
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
                        &highlighting
                            .left
                            .render_line(lineno_l - 1, line, line_styling.same, &[]),
                        &highlighting
                            .right
                            .render_line(lineno_r - 1, line, line_styling.same, &[]),
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
                        &highlighting.right.render_line(
                            lineno_r - 1,
                            line_r,
                            line_styling.add_highlight,
                            &[],
                        ),
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
                        &highlighting.left.render_line(
                            lineno_l - 1,
                            line_l,
                            line_styling.remove_highlight,
                            &[],
                        ),
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
                    &[line_styling.omitted.paint(&message)],
                    &[line_styling.omitted.paint(&message)],
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
                                &highlighting.left.render_line(
                                    lineno_l - 1,
                                    line_l,
                                    line_styling.remove_highlight,
                                    &[],
                                ),
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
                                &highlighting.right.render_line(
                                    lineno_r - 1,
                                    line_r,
                                    line_styling.add_highlight,
                                    &[],
                                ),
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
                            _style_diff_line(
                                line_l,
                                line_r,
                                line_styling,
                                &mut fmt_l,
                                &mut fmt_r,
                                (&highlighting.left, lineno_l - 1),
                                (&highlighting.right, lineno_r - 1),
                            );
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
    fn char_diff_coalesces_accidental_matches_in_an_unrelated_suffix() {
        let before = "version is more portable. Tests assert that the two versions are";
        let after = "version is more portable. The core diff behaviour is identical";

        let diffs = calculate_char_diff(before, after);

        assert_eq!(
            vec![
                Diff::Same("version is more portable. T".to_string()),
                Diff::Replace(
                    "ests assert that the two versions are".to_string(),
                    "he core diff behaviour is identical".to_string(),
                ),
            ],
            diffs
        );
    }

    #[test]
    fn char_diff_retains_dense_fragmented_matches() {
        let diffs = calculate_char_diff("aXaXaXa", "aYaYaYa");

        assert_eq!(
            vec![
                Diff::Same("a".to_string()),
                Diff::Replace("X".to_string(), "Y".to_string()),
                Diff::Same("a".to_string()),
                Diff::Replace("X".to_string(), "Y".to_string()),
                Diff::Same("a".to_string()),
                Diff::Replace("X".to_string(), "Y".to_string()),
                Diff::Same("a".to_string()),
            ],
            diffs
        );
    }

    #[test]
    fn char_diff_coalesces_a_noisy_phrase_between_stable_anchors() {
        // Shared surrounding clauses should not legitimise scattered letters.
        let before = "Sam keeps one dependable act ready in the wings.";
        let after = "Scooter keeps two unpredictable acts ready in the wings.";

        let diffs = calculate_char_diff(before, after);

        assert_eq!(
            vec![
                Diff::Same("S".to_string()),
                Diff::Replace("am".to_string(), "cooter".to_string()),
                Diff::Same(" keeps ".to_string()),
                Diff::Replace("one depend".to_string(), "two unpredict".to_string()),
                Diff::Same("able act".to_string()),
                Diff::Add("s".to_string()),
                Diff::Same(" ready in the wings.".to_string()),
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

        let output = render_diffs_side_by_side(
            &diffs,
            10,
            &ColorScheme::plain(),
            &HighlightedFiles::default(),
        );

        assert!(output.contains("10: Kermit"));
    }

    #[test]
    fn side_by_side_unpaired_wrapped_lines_have_no_trailing_whitespace() {
        // Padding for an absent right pane must stop at the separator on every wrap.
        let diffs = vec![Diff::Replace("Kermit ".repeat(100), "Gonzo".to_string())];

        let output = render_diffs_side_by_side(
            &diffs,
            1,
            &ColorScheme::plain(),
            &HighlightedFiles::default(),
        );

        assert!(output.lines().all(|line| !line.ends_with(' ')));
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
