extern crate difference;

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
            Difference::Same(same_lines) => {
                diffs.push(Diff::Same(same_lines))
            },
            Difference::Add(add_lines) => {
                match diffs.last_mut() {
                    Some(ref mut last_change) => {
                        match last_change {
                            Diff::Same(_) => {
                                diffs.push(Diff::Replace(Option::None, Option::Some(add_lines)));
                            }
                            Diff::Replace(before, ref mut after) => {
                                assert!(before.is_some());
                                assert!(after.is_none());
                                *after = Option::Some(add_lines);
                            }
                        }
                    }
                    None => {
                        diffs.push(Diff::Replace(Option::None, Option::Some(add_lines)));
                    }
                }
            },
            Difference::Rem(rem_lines) => {
                match diffs.last_mut() {
                    Some(ref mut last_change) => {
                        match last_change {
                            Diff::Same(_) => {
                                diffs.push(Diff::Replace(Option::Some(rem_lines), Option::None));
                            }
                            Diff::Replace(ref mut before, after) => {
                                assert!(before.is_none());
                                assert!(after.is_some());
                                *before = Option::Some(rem_lines);
                            }
                        }
                    }
                    None => {
                        diffs.push(Diff::Replace(Option::Some(rem_lines), Option::None));
                    }
                }
            }
        }
    }
    diffs
}

pub fn print_diffs(diffs: &Vec<Diff>) {
    for change in diffs {
        match change {
            Diff::Same(lines) => {
                println!("SAME");
                for line in lines.split('\n') {
                    println!("  {}", line);
                }
            },
            Diff::Replace(before, after) => {
                println!("REPLACE");
                match before {
                    Some(lines) => {
                        for line in lines.split('\n') {
                            println!("- {}", line);
                        }
                    },
                    None => {}
                }
                match after {
                    Some(lines) => {
                        for line in lines.split('\n') {
                            println!("+ {}", line);
                        }
                    },
                    None => {}
                }
            },
        }
    }
}