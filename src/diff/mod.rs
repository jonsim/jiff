mod align;
mod wrap;

use align::align;
use ansi_term::ANSIStrings;
use ansi_term::Color::{Red, Green, Black};
use ansi_term::Style;
use difference::{Changeset, Difference};
use itertools::EitherOrBoth;
use itertools::Itertools;
use wrap::wrap_str;

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
                            for char_change in calculate_char_diff(before, after) {
                                match char_change {
                                    Diff::Same(same) => {
                                        fmts_b.push(line_styling.remove.paint(same.clone()));
                                        fmts_a.push(line_styling.add.paint(same));
                                    },
                                    Diff::Add(add) => {
                                        fmts_a.push(line_styling.add.paint(add));
                                    },
                                    Diff::Remove(rem) => {
                                        fmts_b.push(line_styling.remove.paint(rem));
                                    },
                                    Diff::Replace(rem, add) => {
                                        fmts_b.push(line_styling.remove.paint(rem));
                                        fmts_a.push(line_styling.remove.paint(add));
                                    }
                                }
                            }
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

fn _print_side_by_side_line(lineno_l: Option<(usize, Style)>,
                            line_l: Option<(&str, Style)>,
                            lineno_r: Option<(usize, Style)>,
                            line_r: Option<(&str, Style)>,
                            lineno_width: usize,
                            line_width: (usize, usize),
                            separator: &str) {
    let mut lineno_l_fmt = match lineno_l {
        Some((i, _)) => format!("{:w$}:", i, w=lineno_width),
        None =>         format!("{:w$} ", "", w=lineno_width),
    };
    let mut lineno_r_fmt = match lineno_r {
        Some((i, _)) => format!("{:w$}:", i, w=lineno_width),
        None =>         format!("{:w$} ", "", w=lineno_width),
    };
    let line_l_iter = match line_l {
        Some((s, _)) => wrap_str(s, line_width.0),
        None => wrap_str("", 1),
    };
    let line_r_iter = match line_r {
        Some((s, _)) => wrap_str(s, line_width.1),
        None => wrap_str("", 1),
    };
    let lineno_l_style = match lineno_l {
        Some((_, style)) => style,
        None => Black.bold(),
    };
    let lineno_r_style = match lineno_r {
        Some((_, style)) => style,
        None => Black.bold(),
    };
    let line_l_style = match line_l {
        Some((_, style)) => style,
        None => Style::default(),
    };
    let line_r_style = match line_r {
        Some((_, style)) => style,
        None => Style::default(),
    };
    let mut first_line = true;
    for zipped in line_l_iter.zip_longest(line_r_iter) {
        let (wrap_l_fmt, wrap_r_fmt) = match zipped {
            EitherOrBoth::Both(l, r) => {
                (format!("{:w$}", l, w=line_width.0),
                 format!("{:w$}", r, w=line_width.1))
            },
            EitherOrBoth::Left(l) => {
                (format!("{:w$}", l,  w=line_width.0),
                 format!("{:w$}", "", w=line_width.1))
            },
            EitherOrBoth::Right(r) => {
                (format!("{:w$}", "", w=line_width.0),
                 format!("{:w$}", r,  w=line_width.1))
            },
        };

        println!("{} {}{}{} {}",
                 lineno_l_style.paint(&lineno_l_fmt),
                 line_l_style.paint(&wrap_l_fmt),
                 separator,
                 lineno_r_style.paint(&lineno_r_fmt),
                 line_r_style.paint(&wrap_r_fmt));
        if first_line {
            lineno_l_fmt = format!("{:w$} ", "", w=lineno_width);
            lineno_r_fmt = format!("{:w$} ", "", w=lineno_width);
            first_line = false;
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
        add:              Green.normal(),
        remove:           Red.normal(),
        add_highlight:    Green.on(Black),
        remove_highlight: Red.on(Black),
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
    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    _print_side_by_side_line(
                            Some((lineno_l, lineno_styling.same)),
                            Some((line, line_styling.same)),
                            Some((lineno_r, lineno_styling.same)),
                            Some((line, line_styling.same)),
                            lineno_width, line_width, sep);
                    lineno_l += 1;
                    lineno_r += 1;
                }
            },
            Diff::Add(add) => {
                for line_r in add.split('\n') {
                    _print_side_by_side_line(
                            None,
                            None,
                            Some((lineno_r, lineno_styling.add)),
                            Some((line_r, line_styling.add)),
                            lineno_width, line_width, sep);
                    lineno_r += 1;
                }
            },
            Diff::Remove(rem) => {
                for line_l in rem.split('\n') {
                    _print_side_by_side_line(
                            Some((lineno_l, lineno_styling.remove)),
                            Some((line_l, line_styling.remove)),
                            None,
                            None,
                            lineno_width, line_width, sep);
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
                            _print_side_by_side_line(
                                    Some((lineno_l, lineno_styling.remove_highlight)),
                                    Some((line_l, line_styling.remove_highlight)),
                                    None,
                                    None,
                                    lineno_width, line_width, sep);
                            lineno_l += 1;
                        },
                        (None, Some(line_r)) => {
                            _print_side_by_side_line(
                                    None,
                                    None,
                                    Some((lineno_r, lineno_styling.add_highlight)),
                                    Some((line_r, line_styling.add_highlight)),
                                    lineno_width, line_width, sep);
                            lineno_r += 1;
                        },
                        (Some(line_l), Some(line_r)) => {
                            _print_side_by_side_line(
                                    Some((lineno_l, lineno_styling.remove)),
                                    Some((line_l, line_styling.remove)),
                                    Some((lineno_r, lineno_styling.add)),
                                    Some((line_r, line_styling.add)),
                                    lineno_width, line_width, sep);
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
