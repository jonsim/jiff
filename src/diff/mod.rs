mod align;
mod wrap;

use align::align;
use ansi_term::Color::{Black, Fixed, Green, Red};
use ansi_term::Style;
use ansi_term::{ANSIString, ANSIStrings};
use difference::{Changeset, Difference};
use itertools::EitherOrBoth;
use itertools::Itertools;
use std::sync::LazyLock;
use wrap::wrap_ansistrings;

pub static DEBUG: LazyLock<bool> =
    LazyLock::new(|| matches!(std::env::var("JIFF_DEBUG").as_deref(), Ok("1")));

#[derive(Debug, Eq, PartialEq)]
pub enum Diff {
    Same(String),
    Add(String),
    Remove(String),
    Replace(String, String),
}

struct DiffStyling {
    same: Style,
    add: Style,
    add_highlight: Style,
    remove: Style,
    remove_highlight: Style,
}

pub fn calculate_line_diff(left: &str, right: &str) -> Vec<Diff> {
    calculate_diff(left, right, "\n")
}

pub fn calculate_char_diff(left: &str, right: &str) -> Vec<Diff> {
    calculate_diff(left, right, "")
}

fn calculate_diff(left: &str, right: &str, split: &str) -> Vec<Diff> {
    let mut changeset = Changeset::new(left, right, split);
    let mut diffs = Vec::new();
    let mut previous: Option<Difference> = None;

    for change in changeset.diffs.drain(..) {
        match change {
            Difference::Same(same) => {
                if let Some(last_change) = previous {
                    diffs.push(match last_change {
                        Difference::Same(_) => panic!("Invalid state"),
                        Difference::Add(add) => Diff::Add(add),
                        Difference::Rem(rem) => Diff::Remove(rem),
                    });
                    previous = None;
                }
                diffs.push(Diff::Same(same));
            }
            Difference::Add(add) => match previous {
                Some(last_change) => {
                    diffs.push(match last_change {
                        Difference::Same(_) => panic!("Invalid state"),
                        Difference::Add(_) => panic!("Invalid state"),
                        Difference::Rem(rem) => Diff::Replace(rem, add),
                    });
                    previous = None;
                }
                None => {
                    previous = Some(Difference::Add(add));
                }
            },
            Difference::Rem(rem) => match previous {
                Some(last_change) => {
                    diffs.push(match last_change {
                        Difference::Same(_) => panic!("Invalid state"),
                        Difference::Add(add) => Diff::Replace(rem, add),
                        Difference::Rem(_) => panic!("Invalid state"),
                    });
                    previous = None;
                }
                None => {
                    previous = Some(Difference::Rem(rem));
                }
            },
        }
    }
    if let Some(uncommitted) = previous {
        diffs.push(match uncommitted {
            Difference::Same(_) => panic!("Invalid state"),
            Difference::Add(add) => Diff::Add(add),
            Difference::Rem(rem) => Diff::Remove(rem),
        });
    }
    diffs
}

pub fn print_diffs(diffs: &[Diff], _context: usize, color: bool) {
    let line_styling = if color {
        DiffStyling {
            same: Style::default(),
            add: Green.normal(),
            add_highlight: Black.on(Green),
            remove: Red.normal(),
            remove_highlight: Black.on(Red),
        }
    } else {
        DiffStyling {
            same: Style::default(),
            add: Style::default(),
            add_highlight: Style::default(),
            remove: Style::default(),
            remove_highlight: Style::default(),
        }
    };
    let margin_styling = DiffStyling {
        same: Style::default(),
        add: Style::default(),
        add_highlight: Style::default(),
        remove: Style::default(),
        remove_highlight: Style::default(),
    };

    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let margin = margin_styling.same.paint("  ");
                    let fmt = line_styling.same.paint(line);
                    println!("{}{}", margin, fmt);
                }
            }
            Diff::Add(add) => {
                for line in add.split('\n') {
                    let margin = margin_styling.add.paint("+ ");
                    let fmt = line_styling.add.paint(line);
                    println!("{}{}", margin, fmt);
                }
            }
            Diff::Remove(rem) => {
                for line in rem.split('\n') {
                    let margin = margin_styling.remove.paint("- ");
                    let fmt = line_styling.remove.paint(line);
                    println!("{}{}", margin, fmt);
                }
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
                            _style_diff_line(
                                before,
                                after,
                                &line_styling,
                                &mut fmts_b,
                                &mut fmts_a,
                            );
                            fmts_b.push(Style::default().paint("\n"));
                            fmts_a.push(Style::default().paint("\n"));
                        }
                        (None, None) => {}
                    }
                }
                print!("{}", ANSIStrings(&fmts_b));
                print!("{}", ANSIStrings(&fmts_a));
            }
        }
    }
}

// These arguments deliberately mirror the left and right output columns.
#[allow(clippy::too_many_arguments)]
fn _print_side_by_side_line(
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
            println!("{} {}{}", margin_l, wrapped_l, separator);
        } else {
            println!(
                "{} {}{}{} {}",
                margin_l, wrapped_l, separator, margin_r, wrapped_r
            );
        }
        if first_iteration {
            margin_l = &wrapno_l;
            margin_r = &wrapno_r;
            first_iteration = true;
        }
    }
}

fn _style_diff_line<'u>(
    before: &'u str,
    after: &'u str,
    styling: &DiffStyling,
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
        }
    }
}

fn side_by_side_line_width(term_width: usize, lineno_width: usize, separator: &str) -> usize {
    let separator_width = separator.chars().count();
    let fixed_width = separator_width + 2 * (lineno_width + 2);

    // Some terminals briefly report tiny dimensions while being resized. A
    // one-column line still lets the wrapping iterator make progress.
    term_width.saturating_sub(fixed_width).div_euclid(2).max(1)
}

pub fn print_diffs_side_by_side(
    diffs: &[Diff],
    max_line_count: usize,
    _context: usize,
    color: bool,
) {
    // Define styling constants.
    let lineno_styling = if color {
        DiffStyling {
            same: Black.bold(),
            add: Green.bold(),
            add_highlight: Green.bold(),
            remove: Red.bold(),
            remove_highlight: Red.bold(),
        }
    } else {
        DiffStyling {
            same: Style::default(),
            add: Style::default(),
            add_highlight: Style::default(),
            remove: Style::default(),
            remove_highlight: Style::default(),
        }
    };
    let line_styling = if color {
        DiffStyling {
            same: Style::default(),
            // add:              Fixed(10).normal(),
            // remove:           Fixed( 9).normal(),
            // add_highlight:    Style::default().on(Fixed(22)),
            // remove_highlight: Style::default().on(Fixed(88)),

            // add:              Black.on(Fixed(114)),
            // remove:           Black.on(Fixed(203)),
            // add_highlight:    Black.on(Fixed( 40)),
            // remove_highlight: Black.on(Fixed(160)),
            add: Fixed(157).normal(),    // 194
            remove: Fixed(217).normal(), // 224
            // add_highlight:    Fixed( 40).on(Fixed(235)),
            // remove_highlight: Fixed(160).on(Fixed(235)),
            add_highlight: Fixed(157).reverse(),
            remove_highlight: Fixed(217).reverse(),
        }
    } else {
        DiffStyling {
            same: Style::default(),
            add: Style::default(),
            add_highlight: Style::default(),
            remove: Style::default(),
            remove_highlight: Style::default(),
        }
    };

    // Define separation characters.
    let sep = "\u{2502}";
    // Calculate widths to draw to.
    let lineno_width = (max_line_count as f32).log(10.0).floor() as usize + 1;
    let term_width = term_size::dimensions_stdout()
        .map(|(term_width, _)| term_width)
        .unwrap_or(120);
    let line_width = side_by_side_line_width(term_width, lineno_width, sep);
    let line_width = (line_width, line_width);

    // Print all diffs.
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
                    _print_side_by_side_line(
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
                    _print_side_by_side_line(
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
                    _print_side_by_side_line(
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
                            _print_side_by_side_line(
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
                            _print_side_by_side_line(
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
                            _style_diff_line(line_l, line_r, &line_styling, &mut fmt_l, &mut fmt_r);
                            _print_side_by_side_line(
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
                        (None, None) => {}
                    }
                }
            }
        }
    }
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
