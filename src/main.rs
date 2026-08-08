mod diff;

use clap::{App, Arg};
use std::cmp::max;
use std::fs;
use std::io::IsTerminal;
use std::process;

fn read_file_or_die(path: &str) -> String {
    let mut content = match fs::read_to_string(path) {
        Ok(content) => content,
        Err(ref error) => {
            eprintln!("Could not read {}: {}", path, error);
            process::exit(1);
        }
    };
    if content.ends_with('\n') {
        content.pop();
    }
    content
}

fn line_count(content: &str) -> usize {
    if content.is_empty() {
        0
    } else {
        content.matches('\n').count() + 1
    }
}

fn main() {
    // Handle command line.
    let matches = App::new("jiff")
        .version("1.0")
        .about("Colored diff tool")
        .arg(
            Arg::with_name("git-diff")
                .short("g")
                .long("git-diff")
                .help("Enable git diff mode"),
        )
        .arg(
            Arg::with_name("side-by-side")
                .short("s")
                .long("side-by-side")
                .help("Enable side-by-side diffing"),
        )
        .arg(
            Arg::with_name("no-color")
                .long("no-color")
                .help("Disables colorization of the output"),
        )
        .arg(Arg::with_name("file1").required(true).help("Left file"))
        .arg(Arg::with_name("file2").required(true).help("Right file"))
        .get_matches();
    let lpath = matches.value_of("file1").expect("file1 is required");
    let rpath = matches.value_of("file2").expect("file2 is required");
    let mut color = !matches.is_present("no-color");
    let side_by_side = matches.is_present("side-by-side");
    let lfile = read_file_or_die(lpath);
    let rfile = read_file_or_die(rpath);
    let max_line_count = max(line_count(&lfile), line_count(&rfile));
    //println!("lpath: {}\n{}\nrpath: {}\n{}\n", lpath, lfile, rpath, rfile);

    // If colorization is enabled, determine whether or not to automatically
    // disable it.
    if color {
        let force_color = std::env::var("RICH_FORCE_TERMINAL").is_ok();
        let is_tty = std::io::stdout().is_terminal();
        color = force_color || is_tty;
    }

    // Calculate the changeset.
    let diffs = diff::calculate_line_diff(&lfile, &rfile);

    // Print the changeset.
    if side_by_side {
        diff::print_diffs_side_by_side(&diffs, max_line_count, 0, color);
    } else {
        diff::print_diffs(&diffs, 0, color);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_content_has_no_lines() {
        // An empty file should not reserve a real line number.
        assert_eq!(0, line_count(""));
    }

    #[test]
    fn content_without_a_separator_has_one_line() {
        // A line exists even when there is no newline separator.
        assert_eq!(1, line_count("Kermit"));
    }

    #[test]
    fn line_count_includes_the_text_after_each_separator() {
        // This boundary decides when side-by-side line numbers gain a digit.
        let content = "1\n2\n3\n4\n5\n6\n7\n8\n9\n10";

        assert_eq!(10, line_count(content));
    }
}
