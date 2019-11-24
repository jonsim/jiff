
use std::borrow::Cow;

use ansi_term::Color::{Red, Green, Black};
use difference::{Changeset, Difference};

pub enum Diff {
    Same(String),
    Replace(Option<String>, Option<String>),
}

pub fn calculate_diff(left: &str, right: &str) -> Vec<Diff> {
    let mut changeset = Changeset::new(left, right, "\n");
    let mut diffs = Vec::new();

    for change in changeset.diffs.drain(..) {
        match change {
            Difference::Same(same) => {
                diffs.push(Diff::Same(same))
            },
            Difference::Add(add) => {
                match diffs.last_mut() {
                    Some(ref mut last_change) => {
                        match last_change {
                            Diff::Same(_) => {
                                diffs.push(Diff::Replace(Option::None, Option::Some(add)));
                            }
                            Diff::Replace(before, ref mut after) => {
                                assert!(before.is_some(), "Invalid changeset");
                                assert!(after.is_none(),  "Invalid changeset");
                                *after = Option::Some(add);
                            }
                        }
                    }
                    None => {
                        diffs.push(Diff::Replace(Option::None, Option::Some(add)));
                    }
                }
            },
            Difference::Rem(rem) => {
                match diffs.last_mut() {
                    Some(ref mut last_change) => {
                        match last_change {
                            Diff::Same(_) => {
                                diffs.push(Diff::Replace(Option::Some(rem), Option::None));
                            }
                            Diff::Replace(ref mut before, after) => {
                                assert!(before.is_none(), "Invalid changeset");
                                assert!(after.is_some(), "Invalid changeset");
                                *before = Option::Some(rem);
                            }
                        }
                    }
                    None => {
                        diffs.push(Diff::Replace(Option::Some(rem), Option::None));
                    }
                }
            }
        }
    }
    diffs
}

pub fn print_diffs(diffs: &Vec<Diff>, context: usize, color: bool) {
    for change in diffs {
        match change {
            Diff::Same(same) => {
                //println!("SAME");
                let lines: Vec<&str> = same.split('\n').collect();
                if context > 0 && lines.len() > (context*2) {
                    for line in lines.iter().take(context) {
                        println!("  {}", line);
                    }
                    println!("  ...");
                    for line in lines.iter().skip(lines.len() - context) {
                        println!("  {}", line);
                    }
                } else {
                    for line in lines {
                        println!("  {}", line);
                    }
                }
            },
            Diff::Replace(before, after) => {
                //println!("REPLACE");
                match (before, after) {
                    (Some(before_lines), Some(after_lines)) => {
                        // Replacement.
                        for line in before_lines.split('\n') {
                            let formatted = format!("- {}", line);
                            println!("{}", Red.paint(formatted));
                        }
                        for line in after_lines.split('\n') {
                            let formatted = format!("+ {}", line);
                            println!("{}", Green.paint(formatted));
                        }
                    },
                    (Some(before_lines), None) => {
                        // Removal.
                        for line in before_lines.split('\n') {
                            let formatted = format!("- {}", line);
                            println!("{}", Red.paint(formatted));
                        }
                    },
                    (None, Some(after_lines)) => {
                        // Addition.
                        for line in after_lines.split('\n') {
                            let formatted = format!("+ {}", line);
                            println!("{}", Green.paint(formatted));
                        }
                    },
                    (None, None) => {}
                }
            },
        }
    }
}

pub fn print_diffs_side_by_side(diffs: &Vec<Diff>, max_line_count: usize,
                                context: usize, color: bool) {
    let sep = "\u{2502} ";
    let sep_width = sep.len();
    let lineno_width = (max_line_count as f32).log(10.0).ceil() as usize;
    let (term_width, term_height) = match term_size::dimensions_stdout() {
        Some(dim) => dim,
        None => (80, 80), // TODO: should really disable all wrapping.
    };
    let line_width = ((term_width - sep_width) / 2) - (lineno_width + 2);

    let mut lineno_l = 1;
    let mut lineno_r = 1;
    for change in diffs {
        match change {
            Diff::Same(same) => {
                for line in same.split('\n') {
                    let mut lineno_l_fmt = Black.bold().paint(format!("{:w$}:", lineno_l, w=lineno_width));
                    let mut lineno_r_fmt = Black.bold().paint(format!("{:w$}:", lineno_r, w=lineno_width));
                    for wrapped in textwrap::wrap_iter(&line, line_width) {
                        println!("{} {:w$}{}{} {:w$}",
                                 lineno_l_fmt,
                                 wrapped, sep,
                                 lineno_r_fmt,
                                 wrapped, w=line_width);
                        lineno_l_fmt = Black.bold().paint(format!("{:w$} ", "", w=lineno_width));
                        lineno_r_fmt = Black.bold().paint(format!("{:w$} ", "", w=lineno_width));
                    }
                    lineno_l += 1;
                    lineno_r += 1;
                }
            },
            Diff::Replace(before, after) => {
                match (before, after) {
                    (Some(before_lines), Some(after_lines)) => {
                        // Replacement.
                        for line in before_lines.split('\n') {
                            let formatted = format!("- {}", line);
                            println!("{}", Red.paint(formatted));
                        }
                        for line in after_lines.split('\n') {
                            let formatted = format!("+ {}", line);
                            println!("{}", Green.paint(formatted));
                        }
                    },
                    (Some(before_lines), None) => {
                        // Removal.
                        for line in before_lines.split('\n') {
                            let formatted = format!("- {}", line);
                            println!("{}", Red.paint(formatted));
                        }
                    },
                    (None, Some(after_lines)) => {
                        // Addition.
                        for line in after_lines.split('\n') {
                            let formatted = format!("+ {}", line);
                            println!("{}", Green.paint(formatted));
                        }
                    },
                    (None, None) => {}
                }
            },
        }
    }
}
