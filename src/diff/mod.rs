mod align;
mod wrap;

use align::align;
use ansi_term::{ANSIString, ANSIStrings};
use ansi_term::Color::{Red, Green, Black, Fixed};
use ansi_term::Style;
use difference::{Changeset, Difference};
use itertools::EitherOrBoth;
use itertools::Itertools;
use wrap::{wrap_str, wrap_ansistrings};

#[derive(Debug)]
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
                match previous {
                    Some(last_change) => {
                        diffs.push(match last_change {
                            Difference::Same(_) => panic!("Invalid state"),
                            Difference::Add(add) => Diff::Add(add),
                            Difference::Rem(rem) => Diff::Remove(rem),
                        });
                        previous = None;
                    },
                    None => {},
                }
                diffs.push(Diff::Same(same));
            },
            Difference::Add(add) => {
                match previous {
                    Some(last_change) => {
                        diffs.push(match last_change {
                            Difference::Same(_) => panic!("Invalid state"),
                            Difference::Add(_) => panic!("Invalid state"),
                            Difference::Rem(rem) => Diff::Replace(rem, add),
                        });
                        previous = None;
                    },
                    None => {
                        previous = Some(Difference::Add(add));
                    },
                }
            },
            Difference::Rem(rem) => {
                match previous {
                    Some(last_change) => {
                        diffs.push(match last_change {
                            Difference::Same(_) => panic!("Invalid state"),
                            Difference::Add(add) => Diff::Replace(rem, add),
                            Difference::Rem(_) => panic!("Invalid state"),
                        });
                        previous = None;
                    },
                    None => {
                        previous = Some(Difference::Rem(rem));
                    },
                }
            }
        }
    }
    match previous {
        Some(uncommitted) => {
            diffs.push(match uncommitted {
                Difference::Same(_) => panic!("Invalid state"),
                Difference::Add(add) => Diff::Add(add),
                Difference::Rem(rem) => Diff::Remove(rem),
            });
        },
        None => {},
    }
    diffs
}

pub fn print_diffs(diffs: &Vec<Diff>, context: usize, color: bool) {
    let margin_styling = DiffStyling {
        same:             Style::default(),
        add:              Style::default(),
        add_highlight:    Style::default(),
        remove:           Style::default(),
        remove_highlight: Style::default(),
    };
    let line_styling = DiffStyling {
        same:             Style::default(),
        add:              Green.normal(),
        add_highlight:    Black.on(Green),
        remove:           Red.normal(),
        remove_highlight: Black.on(Red),
    };

    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let margin = margin_styling.same.paint("  ");
                    let fmt = line_styling.same.paint(line);
                    println!("{}{}", margin, fmt);
                }
            },
            Diff::Add(add) => {
                for line in add.split('\n') {
                    let margin = margin_styling.add.paint("+ ");
                    let fmt = line_styling.add.paint(line);
                    println!("{}{}", margin, fmt);
                }
            },
            Diff::Remove(rem) => {
                for line in rem.split('\n') {
                    let margin = margin_styling.remove.paint("- ");
                    let fmt = line_styling.remove.paint(line);
                    println!("{}{}", margin, fmt);
                }
            },
            Diff::Replace(before, after) => {
                let lines_b = before.split('\n').collect();
                let lines_a = after.split('\n').collect();
                let alignment = align(&lines_b, &lines_a);
                let mut fmts_b = Vec::new();
                let mut fmts_a = Vec::new();
                for aligned in alignment {
                    match aligned {
                        (Some(before), None) => {
                            fmts_b.push(margin_styling.remove_highlight.paint("- "));
                            fmts_b.push(line_styling.remove_highlight.paint(before));
                            fmts_b.push(Style::default().paint("\n"));
                        },
                        (None, Some(after)) => {
                            fmts_a.push(margin_styling.add_highlight.paint("+ "));
                            fmts_a.push(line_styling.add_highlight.paint(after));
                            fmts_a.push(Style::default().paint("\n"));
                        },
                        (Some(before), Some(after)) => {
                            fmts_b.push(margin_styling.remove.paint("- "));
                            fmts_a.push(margin_styling.add.paint("+ "));
                            _style_diff_line(before, after, &line_styling,
                                             &mut fmts_b, &mut fmts_a);
                            fmts_b.push(Style::default().paint("\n"));
                            fmts_a.push(Style::default().paint("\n"));
                        },
                        (None, None) => {},
                    }
                }
                print!("{}", ANSIStrings(&fmts_b));
                print!("{}", ANSIStrings(&fmts_a));
            },
        }
    }
}

fn calc_max_line_width(diffs: &Vec<Diff>) -> (usize, usize){
    let mut max_width = (0, 0);
    for change in diffs {
        match change {
            Diff::Same(same) => {
                let len = same.split('\n').map(|l| l.chars().count()).max().unwrap_or(0);
                if len > max_width.0 {
                    max_width.0 = len;
                }
                if len > max_width.1 {
                    max_width.1 = len;
                }
            }
            Diff::Add(add) => {
                let len = add.split('\n').map(|l| l.chars().count()).max().unwrap_or(0);
                if len > max_width.0 {
                    max_width.0 = len;
                }
            }
            Diff::Remove(rem) => {
                let len = rem.split('\n').map(|l| l.chars().count()).max().unwrap_or(0);
                if len > max_width.1 {
                    max_width.1 = len;
                }
            }
            Diff::Replace(before, after) => {
                let len = before.split('\n').map(|l| l.chars().count()).max().unwrap_or(0);
                if len > max_width.0 {
                    max_width.0 = len;
                }
                let len =  after.split('\n').map(|l| l.chars().count()).max().unwrap_or(0);
                if len > max_width.1 {
                    max_width.1 = len;
                }
            }
        }
    }
    return max_width;
}

fn _print_side_by_side_line(lineno_l: ANSIString,
                            lineno_r: ANSIString,
                            wrapno_l: ANSIString,
                            wrapno_r: ANSIString,
                            line_l:   &Vec<ANSIString>,
                            line_r:   &Vec<ANSIString>,
                            line_width: (usize, usize),
                            separator: &str) {
    let mut margin_l = &lineno_l;
    let mut margin_r = &lineno_r;
    let line_l_iter = wrap_ansistrings(line_l, line_width.0);
    let line_r_iter = wrap_ansistrings(line_r, line_width.1);
    let mut first_iteration = true;
    for zipped in line_l_iter.zip_longest(line_r_iter) {
        let (wrapped_l, wrapped_r) = match zipped {
            EitherOrBoth::Both(l, r) => (l, r),
            EitherOrBoth::Left(l)    => (l, " ".repeat(line_width.1)),
            EitherOrBoth::Right(r)   => (" ".repeat(line_width.0), r),
        };

        // TODO: optimize to expoit ANSIStrings
        println!("{} {}{}{} {}",
                 margin_l, wrapped_l, separator, margin_r, wrapped_r);
        if first_iteration {
            margin_l = &wrapno_l;
            margin_r = &wrapno_r;
            first_iteration = true;
        }
    }
}

fn _style_diff_line<'u>(before: &'u str, after: &'u str, styling: &DiffStyling,
        before_fmts: &mut Vec<ANSIString<'u>>,
        after_fmts: &mut Vec<ANSIString<'u>>) {
    for char_change in calculate_char_diff(before, after) {
        match char_change {
            Diff::Same(same) => {
                before_fmts.push(styling.remove.paint(same.clone()));
                after_fmts.push( styling.add.paint(same));
            },
            Diff::Add(add) => {
                after_fmts.push( styling.add_highlight.paint(add));
            },
            Diff::Remove(rem) => {
                before_fmts.push(styling.remove_highlight.paint(rem));
            },
            Diff::Replace(rem, add) => {
                before_fmts.push(styling.remove_highlight.paint(rem));
                after_fmts.push( styling.add_highlight.paint(add));
            }
        }
    }
}

pub fn print_diffs_side_by_side(diffs: &Vec<Diff>, max_line_count: usize,
                                context: usize, color: bool) {
    // Define styling constants.
    let lineno_styling = DiffStyling {
        same:             Black.bold(),
        add:              Green.bold(),
        add_highlight:    Green.bold(),
        remove:           Red.bold(),
        remove_highlight: Red.bold(),
    };
    let line_styling = DiffStyling {
        same:             Style::default(),
        // add:              Fixed(10).normal(),
        // remove:           Fixed( 9).normal(),
        // add_highlight:    Style::default().on(Fixed(22)),
        // remove_highlight: Style::default().on(Fixed(88)),

        // add:              Black.on(Fixed(114)),
        // remove:           Black.on(Fixed(203)),
        // add_highlight:    Black.on(Fixed( 40)),
        // remove_highlight: Black.on(Fixed(160)),

        add:              Fixed(157).normal(), // 194
        remove:           Fixed(217).normal(), // 224
        // add_highlight:    Fixed( 40).on(Fixed(235)),
        // remove_highlight: Fixed(160).on(Fixed(235)),
        add_highlight:    Fixed(157).reverse(),
        remove_highlight: Fixed(217).reverse(),
    };

    // Define separation characters.
    let sep = "\u{2502}";
    let sep_width = sep.len();

    // Caclulcate widths to draw to.
    let lineno_width = (max_line_count as f32).log(10.0).ceil() as usize;
    let line_width = match term_size::dimensions_stdout() {
        Some((term_width, _)) => {
            let line_width = ((term_width - sep_width) / 2) - (lineno_width + 2);
            (line_width, line_width)
        },
        None => {
            calc_max_line_width(diffs)
        },
    };

    // Print all diffs.
    let mut lineno_l = 1;
    let mut lineno_r = 1;
    let empty_lineno = " ".repeat(lineno_width + 1);
    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let lineno_l_fmt = format!("{:w$}:", lineno_l, w=lineno_width);
                    let lineno_r_fmt = format!("{:w$}:", lineno_r, w=lineno_width);
                    _print_side_by_side_line(
                            lineno_styling.same.paint(&lineno_l_fmt),
                            lineno_styling.same.paint(&lineno_r_fmt),
                            lineno_styling.same.paint(&empty_lineno),
                            lineno_styling.same.paint(&empty_lineno),
                            &vec![line_styling.same.paint(line)],
                            &vec![line_styling.same.paint(line)],
                            line_width, sep);
                    lineno_l += 1;
                    lineno_r += 1;
                }
            },
            Diff::Add(add) => {
                for line_r in add.split('\n') {
                    let lineno_r_fmt = format!("{:w$}:", lineno_r, w=lineno_width);
                    _print_side_by_side_line(
                            lineno_styling.same.paint(&empty_lineno),
                            lineno_styling.add_highlight.paint(&lineno_r_fmt),
                            lineno_styling.same.paint(&empty_lineno),
                            lineno_styling.add_highlight.paint(&empty_lineno),
                            &vec![line_styling.same.paint("")],
                            &vec![line_styling.add_highlight.paint(line_r)],
                            line_width, sep);
                    lineno_r += 1;
                }
            },
            Diff::Remove(rem) => {
                for line_l in rem.split('\n') {
                    let lineno_l_fmt = format!("{:w$}:", lineno_l, w=lineno_width);
                    _print_side_by_side_line(
                            lineno_styling.remove_highlight.paint(&lineno_l_fmt),
                            lineno_styling.same.paint(&empty_lineno),
                            lineno_styling.remove_highlight.paint(&empty_lineno),
                            lineno_styling.same.paint(&empty_lineno),
                            &vec![line_styling.remove_highlight.paint(line_l)],
                            &vec![line_styling.same.paint("")],
                            line_width, sep);
                    lineno_l += 1;
                }
            },
            Diff::Replace(before, after) => {
                let lines_b = before.split('\n').collect();
                let lines_a = after.split('\n').collect();
                let alignment = align(&lines_b, &lines_a);
                for aligned in alignment {
                    match aligned {
                        (Some(line_l), None) => {
                            let lineno_l_fmt = format!("{:w$}:", lineno_l, w=lineno_width);
                            _print_side_by_side_line(
                                    lineno_styling.remove_highlight.paint(&lineno_l_fmt),
                                    lineno_styling.same.paint(&empty_lineno),
                                    lineno_styling.remove_highlight.paint(&empty_lineno),
                                    lineno_styling.same.paint(&empty_lineno),
                                    &vec![line_styling.remove_highlight.paint(line_l)],
                                    &vec![line_styling.same.paint("")],
                                    line_width, sep);
                            lineno_l += 1;
                        },
                        (None, Some(line_r)) => {
                            let lineno_r_fmt = format!("{:w$}:", lineno_r, w=lineno_width);
                            _print_side_by_side_line(
                                    lineno_styling.same.paint(&empty_lineno),
                                    lineno_styling.add_highlight.paint(&lineno_r_fmt),
                                    lineno_styling.same.paint(&empty_lineno),
                                    lineno_styling.add_highlight.paint(&empty_lineno),
                                    &vec![line_styling.same.paint("")],
                                    &vec![line_styling.add_highlight.paint(line_r)],
                                    line_width, sep);
                            lineno_r += 1;
                        },
                        (Some(line_l), Some(line_r)) => {
                            let lineno_l_fmt = format!("{:w$}:", lineno_l, w=lineno_width);
                            let lineno_r_fmt = format!("{:w$}:", lineno_r, w=lineno_width);
                            let mut fmt_l = Vec::new();
                            let mut fmt_r = Vec::new();
                            _style_diff_line(line_l, line_r, &line_styling,
                                             &mut fmt_l, &mut fmt_r);
                            _print_side_by_side_line(
                                    lineno_styling.remove.paint(&lineno_l_fmt),
                                    lineno_styling.add.paint(&lineno_r_fmt),
                                    lineno_styling.remove.paint(&empty_lineno),
                                    lineno_styling.add.paint(&empty_lineno),
                                    &fmt_l,
                                    &fmt_r,
                                    line_width, sep);
                            lineno_l += 1;
                            lineno_r += 1;
                        },
                        (None, None) => {},
                    }
                }
            },
        }
    }
}
