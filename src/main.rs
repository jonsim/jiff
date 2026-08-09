mod config;
mod diff;
mod pager;
mod syntax;

use clap::{App, Arg};
use std::cmp::max;
use std::fs;
use std::io::IsTerminal;
use std::process;

#[derive(Debug, Eq, PartialEq)]
enum FileContents {
    Text(String),
    Binary(Vec<u8>),
}

struct OutputOptions<'a> {
    repository_path: Option<&'a str>,
    inline: bool,
    context_lines: Option<usize>,
}

impl FileContents {
    fn from_bytes(bytes: Vec<u8>) -> Self {
        // A NUL is the conventional cheap binary-file check. Invalid UTF-8 is
        // binary too because Jiff's line and character algorithms operate on
        // Unicode text rather than arbitrary bytes.
        if bytes.contains(&0) {
            return Self::Binary(bytes);
        }

        match String::from_utf8(bytes) {
            Ok(mut text) => {
                // Renderers add their own newline. Remove one file terminator
                // so it does not become a spurious empty line in the diff.
                if text.ends_with('\n') {
                    text.pop();
                }
                Self::Text(text)
            }
            Err(error) => Self::Binary(error.into_bytes()),
        }
    }
}

fn line_count(content: &str) -> usize {
    // `FileContents` has already removed a terminal newline, so every
    // remaining separator introduces another displayed line.
    if content.is_empty() {
        0
    } else {
        content.matches('\n').count() + 1
    }
}

fn file_labels(repository_path: Option<&str>, lpath: &str, rpath: &str) -> (String, String) {
    match repository_path {
        Some(path) => (format!("a/{path}"), format!("b/{path}")),
        None => (lpath.to_string(), rpath.to_string()),
    }
}

fn render_output(
    left: &FileContents,
    right: &FileContents,
    lpath: &str,
    rpath: &str,
    options: &OutputOptions,
    colors: &config::ColorScheme,
    highlighting: &syntax::HighlightedFiles,
) -> String {
    let (left_label, right_label) = file_labels(options.repository_path, lpath, rpath);

    match (left, right) {
        (FileContents::Text(left), FileContents::Text(right)) => {
            let mut output = String::new();
            if options.repository_path.is_some() {
                output.push_str(&format!(
                    "{}\n{}\n",
                    colors.remove.paint(format!("--- {left_label}")),
                    colors.add.paint(format!("+++ {right_label}")),
                ));
            }

            let mut diffs = diff::calculate_line_diff(left, right);
            if let Some(context_lines) = options.context_lines {
                diffs = diff::limit_context(diffs, context_lines);
            }
            if options.inline {
                output.push_str(&diff::render_diffs(&diffs, colors, highlighting));
            } else {
                let max_line_count = max(line_count(left), line_count(right));
                output.push_str(&diff::render_diffs_side_by_side(
                    &diffs,
                    max_line_count,
                    colors,
                    highlighting,
                ));
            }
            output
        }
        (FileContents::Binary(left), FileContents::Binary(right)) if left == right => {
            format!("Binary files {left_label} and {right_label} are identical\n")
        }
        _ => format!("Binary files {left_label} and {right_label} differ\n"),
    }
}

fn main() {
    let matches = App::new("jiff")
        .version("1.0")
        .about("Colored diff tool")
        .arg(
            Arg::with_name("path")
                .long("path")
                .takes_value(true)
                .value_name("PATH")
                .help("Display Git-style headings for a repository path"),
        )
        .arg(
            Arg::with_name("inline")
                .short("i")
                .long("inline")
                .help("Display the diff inline"),
        )
        .arg(
            Arg::with_name("unified")
                .short("U")
                .long("unified")
                .takes_value(true)
                .value_name("n")
                .validator(|value| {
                    value
                        .parse::<usize>()
                        .map(|_| ())
                        .map_err(|_| "context must be a non-negative integer".to_string())
                })
                .help("Show n lines of context around each change"),
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
        .arg(
            Arg::with_name("syntax")
                .long("syntax")
                .takes_value(true)
                .value_name("LANGUAGE")
                .conflicts_with("no-syntax")
                .help("Use LANGUAGE for syntax highlighting instead of detecting it"),
        )
        .arg(
            Arg::with_name("no-syntax")
                .long("no-syntax")
                .conflicts_with("syntax")
                .help("Disables syntax highlighting"),
        )
        .arg(Arg::with_name("file1").required(true).help("Left file"))
        .arg(Arg::with_name("file2").required(true).help("Right file"))
        .get_matches();
    let lpath = matches.value_of("file1").expect("file1 is required");
    let rpath = matches.value_of("file2").expect("file2 is required");
    let repository_path = matches.value_of("path");
    let context_lines = matches
        .value_of("unified")
        .map(|value| value.parse().expect("unified was validated"));
    let mut color = !matches.is_present("no-color");
    let no_pager = matches.is_present("no-pager");
    let inline = matches.is_present("inline");
    if let Err(error) = syntax::validate_syntax(matches.value_of("syntax")) {
        eprintln!("Could not highlight diff: {error}");
        process::exit(1);
    }
    let mut colors = match config::load_color_scheme() {
        Ok(colors) => colors,
        Err(error) => {
            eprintln!("Could not load config: {error}");
            process::exit(1);
        }
    };
    let lfile = match fs::read(lpath) {
        Ok(contents) => FileContents::from_bytes(contents),
        Err(error) => {
            eprintln!("Could not read {lpath}: {error}");
            process::exit(1);
        }
    };
    let rfile = match fs::read(rpath) {
        Ok(contents) => FileContents::from_bytes(contents),
        Err(error) => {
            eprintln!("Could not read {rpath}: {error}");
            process::exit(1);
        }
    };

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

    let highlighting = match (&lfile, &rfile) {
        (FileContents::Text(left), FileContents::Text(right))
            if color && !matches.is_present("no-syntax") =>
        {
            match syntax::highlight_files(
                left,
                right,
                lpath,
                rpath,
                repository_path,
                matches.value_of("syntax"),
                &colors,
            ) {
                Ok(highlighting) => highlighting,
                Err(error) => {
                    eprintln!("Could not highlight diff: {error}");
                    process::exit(1);
                }
            }
        }
        _ => syntax::HighlightedFiles::default(),
    };

    let output = render_output(
        &lfile,
        &rfile,
        lpath,
        rpath,
        &OutputOptions {
            repository_path,
            inline,
            context_lines,
        },
        &colors,
        &highlighting,
    );

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

    #[test]
    fn text_content_loses_one_terminal_newline() {
        // The renderer owns line endings, but meaningful blank lines remain.
        let content = FileContents::from_bytes(b"Kermit\n\n".to_vec());

        assert_eq!(FileContents::Text("Kermit\n".to_string()), content);
    }

    #[test]
    fn nul_bytes_mark_a_file_as_binary() {
        let bytes = b"Kermit\0Fozzie".to_vec();

        assert_eq!(
            FileContents::Binary(bytes.clone()),
            FileContents::from_bytes(bytes)
        );
    }

    #[test]
    fn invalid_utf8_marks_a_file_as_binary() {
        let bytes = vec![0x4b, 0xff, 0x21];

        assert_eq!(
            FileContents::Binary(bytes.clone()),
            FileContents::from_bytes(bytes)
        );
    }

    #[test]
    fn repository_path_adds_git_style_headings() {
        let left = FileContents::Text("Kermit".to_string());
        let right = FileContents::Text("Fozzie".to_string());

        let output = render_output(
            &left,
            &right,
            "/tmp/local",
            "/tmp/remote",
            &OutputOptions {
                repository_path: Some("muppet cast.txt"),
                inline: true,
                context_lines: None,
            },
            &config::ColorScheme::plain(),
            &syntax::HighlightedFiles::default(),
        );

        assert!(output.starts_with("--- a/muppet cast.txt\n+++ b/muppet cast.txt\n"));
    }

    #[test]
    fn differing_binary_files_are_reported_without_decoding_them() {
        let left = FileContents::Binary(vec![0, 1]);
        let right = FileContents::Binary(vec![0, 2]);

        let output = render_output(
            &left,
            &right,
            "/tmp/local",
            "/tmp/remote",
            &OutputOptions {
                repository_path: Some("animal.dat"),
                inline: false,
                context_lines: None,
            },
            &config::ColorScheme::plain(),
            &syntax::HighlightedFiles::default(),
        );

        assert_eq!(
            "Binary files a/animal.dat and b/animal.dat differ\n",
            output
        );
    }

    #[test]
    fn identical_binary_files_are_reported() {
        let left = FileContents::Binary(vec![0, 1]);
        let right = FileContents::Binary(vec![0, 1]);

        let output = render_output(
            &left,
            &right,
            "/tmp/kermit.dat",
            "/tmp/kermit-copy.dat",
            &OutputOptions {
                repository_path: None,
                inline: false,
                context_lines: None,
            },
            &config::ColorScheme::plain(),
            &syntax::HighlightedFiles::default(),
        );

        assert_eq!(
            "Binary files /tmp/kermit.dat and /tmp/kermit-copy.dat are identical\n",
            output
        );
    }
}
