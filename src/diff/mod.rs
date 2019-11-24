use ansi_term::Color::{Red, Green};
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

pub fn print_diffs(diffs: &Vec<Diff>, color: bool) {
    for change in diffs {
        match change {
            Diff::Same(same) => {
                //println!("SAME");
                for line in same.split('\n') {
                    println!("  {}", line);
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