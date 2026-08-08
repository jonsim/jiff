mod config;
mod diff;
mod pager;

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
    // Renderers add their own newline. Remove one file terminator so it does
    // not become a spurious empty line in the diff.
    if content.ends_with('\n') {
        content.pop();
    }
    content
}

fn line_count(content: &str) -> usize {
    // `read_file_or_die` has already removed a terminal newline, so every
    // remaining separator introduces another displayed line.
    if content.is_empty() {
        0
    } else {
        content.matches('\n').count() + 1
    }
}

fn main() {
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
            Arg::with_name("inline")
                .short("i")
                .long("inline")
                .help("Display the diff inline"),
        )
        .arg(
            Arg::with_name("no-color")
                .long("no-color")
                .help("Disables colorization of the output"),
        )
        .arg(
            Arg::with_name("no-pager")
                .long("no-pager")
                .help("Disables paging of long output"),
        )
        .arg(Arg::with_name("file1").required(true).help("Left file"))
        .arg(Arg::with_name("file2").required(true).help("Right file"))
        .get_matches();
    let lpath = matches.value_of("file1").expect("file1 is required");
    let rpath = matches.value_of("file2").expect("file2 is required");
    let mut color = !matches.is_present("no-color");
    let no_pager = matches.is_present("no-pager");
    let inline = matches.is_present("inline");
    let mut colors = match config::load_color_scheme() {
        Ok(colors) => colors,
        Err(error) => {
            eprintln!("Could not load config: {error}");
            process::exit(1);
        }
    };
    let lfile = read_file_or_die(lpath);
    let rfile = read_file_or_die(rpath);
    let max_line_count = max(line_count(&lfile), line_count(&rfile));

    // Match the Python implementation: explicit no-colour wins, otherwise a
    // non-terminal disables colour unless Rich's force flag is present.
    if color {
        let force_color = std::env::var("RICH_FORCE_TERMINAL").is_ok();
        let is_tty = std::io::stdout().is_terminal();
        color = force_color || is_tty;
    }
    if !color {
        colors = config::ColorScheme::plain();
    }

    let diffs = diff::calculate_line_diff(&lfile, &rfile);

    let output = if inline {
        diff::render_diffs(&diffs, &colors)
    } else {
        diff::render_diffs_side_by_side(&diffs, max_line_count, &colors)
    };

    if let Err(error) = pager::display(&output, no_pager) {
        eprintln!("Could not display diff: {error}");
        process::exit(1);
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
