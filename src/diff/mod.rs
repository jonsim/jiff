use std::borrow::Cow;

use ansi_term::Color::{Red, Green, Black};
use difference::{Changeset, Difference};

pub enum Diff {
    Same(String),
    Add(String),
    Remove(String),
    Replace(String, String),
}

pub fn calculate_diff(left: &str, right: &str) -> Vec<Diff> {
    let mut changeset = Changeset::new(left, right, "\n");
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
    for change in diffs {
        match change {
            Diff::Same(same) => {
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
            Diff::Add(add) => {
                for line in add.split('\n') {
                    let formatted = format!("+ {}", line);
                    println!("{}", Green.paint(formatted));
                }
            },
            Diff::Remove(rem) => {
                for line in rem.split('\n') {
                    let formatted = format!("- {}", line);
                    println!("{}", Red.paint(formatted));
                }
            },
            Diff::Replace(before, after) => {
                for line in before.split('\n') {
                    let formatted = format!("- {}", line);
                    println!("{}", Red.paint(formatted));
                }
                for line in after.split('\n') {
                    let formatted = format!("+ {}", line);
                    println!("{}", Green.paint(formatted));
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
            Diff::Add(add) => {
                for line in add.split('\n') {
                    let formatted = format!("+ {}", line);
                    println!("{}", Green.paint(formatted));
                }
            },
            Diff::Remove(rem) => {
                for line in rem.split('\n') {
                    let formatted = format!("- {}", line);
                    println!("{}", Red.paint(formatted));
                }
            },
            Diff::Replace(before, after) => {
                for line in before.split('\n') {
                    let formatted = format!("- {}", line);
                    println!("{}", Red.paint(formatted));
                }
                for line in after.split('\n') {
                    let formatted = format!("+ {}", line);
                    println!("{}", Green.paint(formatted));
                }
            },
        }
    }
}
