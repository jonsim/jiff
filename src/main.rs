mod config;
mod diff;
mod directory;
mod pager;
mod syntax;

use clap::{App, Arg};
use std::cmp::max;
use std::fs;
use std::io::IsTerminal;
use std::path::Path;
use std::process::{self, Command};
use termprofile::{DetectorSettings, TermProfile, TermVars};

#[derive(Debug, Eq, PartialEq)]
enum FileContents {
    Text(String),
    Binary(Vec<u8>),
}

#[derive(Debug, Eq, PartialEq)]
enum InputPaths<'a> {
    Comparison {
        left: &'a str,
        right: &'a str,
        repository_paths: Option<[&'a str; 2]>,
    },
    ThreeWay {
        left: &'a str,
        middle: &'a str,
        right: &'a str,
    },
    Unmerged {
        repository_path: &'a str,
    },
}

struct OutputOptions<'a> {
    repository_paths: Option<[&'a str; 2]>,
    inline: bool,
    context_lines: Option<usize>,
}

#[derive(Clone, Copy)]
struct RenderInput<'a> {
    contents: &'a FileContents,
    path: &'a str,
}

#[derive(Debug, Eq, PartialEq)]
struct GitIndexStage {
    // Most index stages are blobs. Mode 160000 is different: it names the
    // checked-out commit of a submodule.
    mode: String,
    object_id: String,
}

#[derive(Clone, Copy)]
struct HighlightOptions<'a> {
    color: bool,
    enabled: bool,
    syntax_name: Option<&'a str>,
}

impl FileContents {
    fn from_bytes(bytes: Vec<u8>) -> Self {
        // A NUL is a cheap, conventional binary-file check. Invalid UTF-8
        // counts as binary too because the diff code works on Unicode text.
        if bytes.contains(&0) {
            return Self::Binary(bytes);
        }

        match String::from_utf8(bytes) {
            Ok(mut text) => {
                // Renderers add their own newline. Drop one file terminator so
                // it doesn't turn into an extra blank line in the diff.
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

fn parse_input_paths<'a>(
    files: &'a [&'a str],
    git_external_diff: bool,
    repository_path: Option<&'a str>,
) -> Result<InputPaths<'a>, &'static str> {
    if !git_external_diff {
        return match files {
            [left, right] => Ok(InputPaths::Comparison {
                left,
                right,
                repository_paths: repository_path.map(|path| [path, path]),
            }),
            [left, middle, right] if repository_path.is_none() => Ok(InputPaths::ThreeWay {
                left,
                middle,
                right,
            }),
            [_, _, _] => Err("--path cannot be used with a three-way comparison"),
            _ => Err("jiff expects two or three files, or two directories"),
        };
    }

    // Git's positional protocol is a bit odd, so only recognise it when the
    // flag is set. Seven arguments compare temporary files; one names an
    // unresolved path which Jiff has to read from the index.
    match files {
        [repository_path] => Ok(InputPaths::Unmerged { repository_path }),
        [repository_path, left, _, _, right, _, _] => Ok(InputPaths::Comparison {
            left,
            right,
            repository_paths: Some([repository_path, repository_path]),
        }),
        [repository_path, left, _, _, right, _, _, right_repository_path]
        | [repository_path, left, _, _, right, _, _, right_repository_path, _] => {
            Ok(InputPaths::Comparison {
                left,
                right,
                repository_paths: Some([repository_path, right_repository_path]),
            })
        }
        _ => Err("--git-external-diff expects one, seven, eight or nine arguments"),
    }
}

fn file_labels(
    repository_paths: Option<[&str; 2]>,
    left_path: &str,
    right_path: &str,
) -> (String, String) {
    match repository_paths {
        Some([left_repository_path, right_repository_path]) => (
            if left_path == "/dev/null" {
                left_path.to_string()
            } else {
                format!("a/{left_repository_path}")
            },
            if right_path == "/dev/null" {
                right_path.to_string()
            } else {
                format!("b/{right_repository_path}")
            },
        ),
        None => (left_path.to_string(), right_path.to_string()),
    }
}

fn display_name(path: &str) -> &str {
    Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or(path)
}

fn render_output(
    left: &FileContents,
    right: &FileContents,
    left_path: &str,
    right_path: &str,
    options: &OutputOptions,
    colors: &config::ColorScheme,
    highlighting: &syntax::HighlightedFiles,
) -> String {
    let (left_label, right_label) = file_labels(options.repository_paths, left_path, right_path);

    match (left, right) {
        (FileContents::Text(left), FileContents::Text(right)) => {
            let mut output = String::new();
            if options.repository_paths.is_some() && options.inline {
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
                    options
                        .repository_paths
                        .map(|_| [left_label.as_str(), right_label.as_str()]),
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

fn render_comparison(
    left: &FileContents,
    right: &FileContents,
    left_path: &str,
    right_path: &str,
    output_options: &OutputOptions,
    highlight_options: HighlightOptions,
    colors: &config::ColorScheme,
) -> Result<String, syntax::HighlightError> {
    let highlighting = match (left, right) {
        (FileContents::Text(left), FileContents::Text(right))
            if highlight_options.color && highlight_options.enabled =>
        {
            syntax::highlight_files(
                left,
                right,
                left_path,
                right_path,
                output_options.repository_paths,
                highlight_options.syntax_name,
                colors,
            )?
        }
        _ => syntax::HighlightedFiles::default(),
    };

    Ok(render_output(
        left,
        right,
        left_path,
        right_path,
        output_options,
        colors,
        &highlighting,
    ))
}

fn render_three_way_output(
    left: RenderInput,
    middle: RenderInput,
    right: RenderInput,
    labels: [&str; 3],
    output_options: &OutputOptions,
    highlight_options: HighlightOptions,
    colors: &config::ColorScheme,
) -> Result<String, syntax::HighlightError> {
    if !output_options.inline {
        if let (
            FileContents::Text(left_contents),
            FileContents::Text(middle_contents),
            FileContents::Text(right_contents),
        ) = (left.contents, middle.contents, right.contents)
        {
            let highlighting = if highlight_options.color && highlight_options.enabled {
                [
                    syntax::highlight_file(
                        left_contents,
                        left.path,
                        highlight_options.syntax_name,
                        colors,
                    )?,
                    syntax::highlight_file(
                        middle_contents,
                        middle.path,
                        highlight_options.syntax_name,
                        colors,
                    )?,
                    syntax::highlight_file(
                        right_contents,
                        right.path,
                        highlight_options.syntax_name,
                        colors,
                    )?,
                ]
            } else {
                std::array::from_fn(|_| syntax::HighlightedFile::default())
            };
            return Ok(diff::render_three_way_side_by_side(
                [left_contents, middle_contents, right_contents],
                labels,
                colors,
                [&highlighting[0], &highlighting[1], &highlighting[2]],
                output_options.context_lines,
            ));
        }
    }

    // Binary files don't have useful three-pane output. Use the same pair of
    // comparisons as inline mode.
    let mut output = format!("=== 1: {} vs 2: {} ===\n", labels[0], labels[1]);
    output.push_str(&render_comparison(
        left.contents,
        middle.contents,
        left.path,
        middle.path,
        output_options,
        highlight_options,
        &colors.without_additions(),
    )?);
    output.push('\n');
    output.push_str(&format!("=== 2: {} vs 3: {} ===\n", labels[1], labels[2]));
    output.push_str(&render_comparison(
        middle.contents,
        right.contents,
        middle.path,
        right.path,
        output_options,
        highlight_options,
        &colors.without_removals(),
    )?);
    Ok(output)
}

fn render_directory_output(
    left_root: &Path,
    right_root: &Path,
    output_options: &OutputOptions,
    highlight_options: HighlightOptions,
    colors: &config::ColorScheme,
) -> Result<String, String> {
    let directory_diffs = directory::directory_diffs(left_root, right_root)
        .map_err(|error| format!("Could not read {error}"))?;
    let mut output = String::new();

    for directory_diff in directory_diffs {
        let relative_path = directory_diff
            .relative_path
            .iter()
            .map(|component| component.to_string_lossy())
            .collect::<Vec<_>>()
            .join("/");
        let left_path = left_root.join(&directory_diff.relative_path);
        let right_path = right_root.join(&directory_diff.relative_path);
        let left = FileContents::from_bytes(directory_diff.left.unwrap_or_default());
        let right = FileContents::from_bytes(directory_diff.right.unwrap_or_default());
        let file_options = OutputOptions {
            repository_paths: Some([&relative_path, &relative_path]),
            inline: output_options.inline,
            context_lines: output_options.context_lines,
        };

        output.push_str(
            &render_comparison(
                &left,
                &right,
                &left_path.to_string_lossy(),
                &right_path.to_string_lossy(),
                &file_options,
                highlight_options,
                colors,
            )
            .map_err(|error| format!("Could not highlight diff: {error}"))?,
        );
    }

    Ok(output)
}

fn is_directory(path: &str) -> Result<bool, String> {
    fs::metadata(path)
        .map(|metadata| metadata.is_dir())
        .map_err(|error| format!("Could not read {path}: {error}"))
}

fn read_input(path: &str) -> Result<FileContents, String> {
    fs::read(path)
        .map(FileContents::from_bytes)
        .map_err(|error| format!("Could not read {path}: {error}"))
}

fn parse_unmerged_stages(
    output: &[u8],
    repository_path: &str,
) -> Result<[Option<GitIndexStage>; 3], String> {
    let mut stages = [None, None, None];

    for record in output
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
    {
        let Some(separator) = record.iter().position(|byte| *byte == b'\t') else {
            return Err(format!(
                "Git returned a malformed unmerged entry for {repository_path}"
            ));
        };
        let (metadata, path_with_separator) = record.split_at(separator);
        let path = &path_with_separator[1..];
        if path != repository_path.as_bytes() {
            return Err(format!(
                "Git returned an unexpected path while reading {repository_path}"
            ));
        }

        let fields: Vec<_> = metadata
            .split(|byte| byte.is_ascii_whitespace())
            .filter(|field| !field.is_empty())
            .collect();
        let [mode, object_id, stage] = fields.as_slice() else {
            return Err(format!(
                "Git returned a malformed unmerged entry for {repository_path}"
            ));
        };
        let stage = std::str::from_utf8(stage)
            .ok()
            .and_then(|stage| stage.parse::<usize>().ok())
            .filter(|stage| (1..=3).contains(stage))
            .ok_or_else(|| {
                format!("Git returned an invalid stage while reading {repository_path}")
            })?;
        let object_id = std::str::from_utf8(object_id)
            .map_err(|_| format!("Git returned an invalid object ID for {repository_path}"))?;
        let mode = std::str::from_utf8(mode)
            .map_err(|_| format!("Git returned an invalid mode for {repository_path}"))?;
        let slot = &mut stages[stage - 1];
        if slot.is_some() {
            return Err(format!(
                "Git returned stage {stage} more than once for {repository_path}"
            ));
        }
        *slot = Some(GitIndexStage {
            mode: mode.to_string(),
            object_id: object_id.to_string(),
        });
    }

    Ok(stages)
}

fn git_error(action: &str, repository_path: &str, output: &process::Output) -> String {
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if detail.is_empty() {
        format!(
            "Could not {action} for {repository_path}: {}",
            output.status
        )
    } else {
        format!("Could not {action} for {repository_path}: {detail}")
    }
}

fn run_git(arguments: &[&str], action: &str, repository_path: &str) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .args(arguments)
        .output()
        .map_err(|error| format!("Could not {action} for {repository_path}: {error}"))?;
    if !output.status.success() {
        return Err(git_error(action, repository_path, &output));
    }
    Ok(output.stdout)
}

fn read_git_stage(
    stage: Option<&GitIndexStage>,
    repository_path: &str,
) -> Result<FileContents, String> {
    let Some(stage) = stage else {
        // Git leaves out stages which don't exist in add/add or modify/delete
        // conflicts. An empty input makes the missing side visible in the
        // three-way diff.
        return Ok(FileContents::from_bytes(Vec::new()));
    };
    if stage.mode == "160000" {
        return Ok(FileContents::Text(format!(
            "Subproject commit {}",
            stage.object_id
        )));
    }
    run_git(
        &["cat-file", "blob", &stage.object_id],
        "read Git object",
        repository_path,
    )
    .map(FileContents::from_bytes)
}

fn read_unmerged_inputs(repository_path: &str) -> Result<[FileContents; 3], String> {
    let output = run_git(
        &[
            "--literal-pathspecs",
            "ls-files",
            "--unmerged",
            "--full-name",
            "-z",
            "--",
            repository_path,
        ],
        "read Git stages",
        repository_path,
    )?;

    let stages = parse_unmerged_stages(&output, repository_path)?;
    if stages.iter().all(Option::is_none) {
        return Err(format!("Git has no unmerged entries for {repository_path}"));
    }

    // Git orders these as Base, Local, Remote. Jiff shows Local, Base, Remote,
    // so swap the first two here.
    Ok([
        read_git_stage(stages[1].as_ref(), repository_path)?,
        read_git_stage(stages[0].as_ref(), repository_path)?,
        read_git_stage(stages[2].as_ref(), repository_path)?,
    ])
}

fn render_unmerged_path(
    repository_path: &str,
    output_options: &OutputOptions,
    highlight_options: HighlightOptions,
    colors: &config::ColorScheme,
) -> Result<String, String> {
    let [local, base, remote] = read_unmerged_inputs(repository_path)?;
    let output = render_three_way_output(
        RenderInput {
            contents: &local,
            path: repository_path,
        },
        RenderInput {
            contents: &base,
            path: repository_path,
        },
        RenderInput {
            contents: &remote,
            path: repository_path,
        },
        ["Local", "Base", "Remote"],
        output_options,
        highlight_options,
        colors,
    )
    .map_err(|error| format!("Could not highlight diff: {error}"))?;
    Ok(format!("=== Unmerged: {repository_path} ===\n{output}"))
}

fn render_path_comparison(
    left_path: &str,
    right_path: &str,
    output_options: &OutputOptions,
    highlight_options: HighlightOptions,
    colors: &config::ColorScheme,
) -> Result<String, String> {
    let left_is_directory = is_directory(left_path)?;
    let right_is_directory = is_directory(right_path)?;
    if left_is_directory != right_is_directory {
        return Err(format!(
            "Could not compare {left_path} and {right_path}: both inputs must be files or both directories"
        ));
    }
    if left_is_directory {
        return render_directory_output(
            Path::new(left_path),
            Path::new(right_path),
            output_options,
            highlight_options,
            colors,
        );
    }

    render_comparison(
        &read_input(left_path)?,
        &read_input(right_path)?,
        left_path,
        right_path,
        output_options,
        highlight_options,
        colors,
    )
    .map_err(|error| format!("Could not highlight diff: {error}"))
}

fn render_three_paths(
    left_path: &str,
    middle_path: &str,
    right_path: &str,
    output_options: &OutputOptions,
    highlight_options: HighlightOptions,
    colors: &config::ColorScheme,
) -> Result<String, String> {
    let contains_directory =
        is_directory(left_path)? || is_directory(middle_path)? || is_directory(right_path)?;
    if contains_directory {
        return Err(format!(
            "Could not compare {left_path}, {middle_path}, and {right_path}: three-way inputs must be files"
        ));
    }

    let left = read_input(left_path)?;
    let middle = read_input(middle_path)?;
    let right = read_input(right_path)?;

    render_three_way_output(
        RenderInput {
            contents: &left,
            path: left_path,
        },
        RenderInput {
            contents: &middle,
            path: middle_path,
        },
        RenderInput {
            contents: &right,
            path: right_path,
        },
        [
            display_name(left_path),
            display_name(middle_path),
            display_name(right_path),
        ],
        output_options,
        highlight_options,
        colors,
    )
    .map_err(|error| format!("Could not highlight diff: {error}"))
}

fn main() {
    let matches = App::new("jiff")
        .version(env!("CARGO_PKG_VERSION"))
        .about("Colored diff tool")
        .arg(
            Arg::with_name("path")
                .long("path")
                .takes_value(true)
                .value_name("PATH")
                .help("Display Git-style headings for a repository path"),
        )
        .arg(
            Arg::with_name("git-external-diff")
                .long("git-external-diff")
                .conflicts_with("path")
                .help("Parse arguments supplied by Git's external diff protocol"),
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
        .arg(
            Arg::with_name("files")
                .required(true)
                .multiple(true)
                .value_name("FILE")
                .help("Files to compare"),
        )
        .get_matches();
    let files: Vec<_> = matches
        .values_of("files")
        .expect("at least one file is required")
        .collect();
    let git_external_diff = matches.is_present("git-external-diff");
    let input_paths = match parse_input_paths(
        &files,
        git_external_diff,
        matches.value_of("path").filter(|path| !path.is_empty()),
    ) {
        Ok(input_paths) => input_paths,
        Err(error) => {
            eprintln!("{error}");
            process::exit(2);
        }
    };
    let context_lines = matches
        .value_of("unified")
        .map(|value| value.parse().expect("unified was validated"));
    let mut color = !matches.is_present("no-color");
    let no_pager = matches.is_present("no-pager") || git_external_diff;
    let inline = matches.is_present("inline");
    if let Err(error) = syntax::validate_syntax(matches.value_of("syntax")) {
        eprintln!("Could not highlight diff: {error}");
        process::exit(1);
    }
    let color_config = match config::load_color_config() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("Could not load config: {error}");
            process::exit(1);
        }
    };
    // Git sends an external diff to its own pager, even though stdout looks
    // like a pipe to Jiff.
    if color && !git_external_diff {
        let force_color = std::env::var("RICH_FORCE_TERMINAL").is_ok();
        let is_tty = std::io::stdout().is_terminal();
        color = force_color || is_tty;
    }
    let terminal_depth = if color {
        let stdout = std::io::stdout();
        let mut vars = TermVars::from_env(&stdout, DetectorSettings::default());
        // Git sends output to its own pager, so stdout isn't the terminal Jiff
        // is really targeting. RICH_FORCE_TERMINAL has the same implication.
        if git_external_diff || std::env::var("RICH_FORCE_TERMINAL").is_ok() {
            vars.meta.is_terminal = true;
        }
        match TermProfile::detect_with_vars(vars) {
            TermProfile::TrueColor => config::ColorDepth::TrueColor,
            TermProfile::Ansi256 => config::ColorDepth::Ansi256,
            _ => config::ColorDepth::Ansi16,
        }
    } else {
        config::ColorDepth::Ansi16
    };
    let colors = if color {
        color_config.scheme(terminal_depth)
    } else {
        config::ColorScheme::plain()
    };

    let highlight_options = HighlightOptions {
        color,
        enabled: !matches.is_present("no-syntax"),
        syntax_name: matches.value_of("syntax"),
    };
    let output = match input_paths {
        InputPaths::Comparison {
            left,
            right,
            repository_paths,
        } => render_path_comparison(
            left,
            right,
            &OutputOptions {
                repository_paths,
                inline,
                context_lines,
            },
            highlight_options,
            &colors,
        ),
        InputPaths::ThreeWay {
            left,
            middle,
            right,
        } => render_three_paths(
            left,
            middle,
            right,
            &OutputOptions {
                repository_paths: None,
                inline,
                context_lines,
            },
            highlight_options,
            &colors,
        ),
        InputPaths::Unmerged { repository_path } => render_unmerged_path(
            repository_path,
            &OutputOptions {
                repository_paths: None,
                inline,
                context_lines,
            },
            highlight_options,
            &colors,
        ),
    };
    let output = match output {
        Ok(output) => output,
        Err(error) => {
            eprintln!("{error}");
            process::exit(1);
        }
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

    #[test]
    fn ordinary_inputs_are_exactly_two_paths() {
        assert_eq!(
            Ok(InputPaths::Comparison {
                left: "local.txt",
                right: "remote.txt",
                repository_paths: Some(["muppet.txt", "muppet.txt"]),
            }),
            parse_input_paths(&["local.txt", "remote.txt"], false, Some("muppet.txt"))
        );
        assert_eq!(
            Err("jiff expects two or three files, or two directories"),
            parse_input_paths(&["local.txt"], false, None)
        );
        assert_eq!(
            Err("jiff expects two or three files, or two directories"),
            parse_input_paths(
                &["local.txt", "base.txt", "remote.txt", "fourth.txt"],
                false,
                None
            )
        );
    }

    #[test]
    fn ordinary_inputs_accept_three_way_file_paths() {
        assert_eq!(
            Ok(InputPaths::ThreeWay {
                left: "local.txt",
                middle: "base.txt",
                right: "remote.txt",
            }),
            parse_input_paths(&["local.txt", "base.txt", "remote.txt"], false, None)
        );
    }

    #[test]
    fn repository_headings_are_rejected_for_three_way_input() {
        assert_eq!(
            Err("--path cannot be used with a three-way comparison"),
            parse_input_paths(
                &["local.txt", "base.txt", "remote.txt"],
                false,
                Some("muppet.txt")
            )
        );
    }

    #[test]
    fn git_external_diff_extracts_only_the_paths_jiff_uses() {
        assert_eq!(
            Ok(InputPaths::Comparison {
                left: "/tmp/old",
                right: "/tmp/new",
                repository_paths: Some(["muppet.txt", "muppet.txt"]),
            }),
            parse_input_paths(
                &[
                    "muppet.txt",
                    "/tmp/old",
                    "old-object",
                    "100644",
                    "/tmp/new",
                    "new-object",
                    "100644",
                ],
                true,
                None,
            )
        );
    }

    #[test]
    fn git_external_diff_retains_both_paths_for_a_rename() {
        assert_eq!(
            Ok(InputPaths::Comparison {
                left: "/tmp/old",
                right: "/tmp/new",
                repository_paths: Some(["old.txt", "new.txt"]),
            }),
            parse_input_paths(
                &[
                    "old.txt",
                    "/tmp/old",
                    "old-object",
                    "100644",
                    "/tmp/new",
                    "new-object",
                    "100644",
                    "new.txt",
                    "similarity index 100%",
                ],
                true,
                None,
            )
        );
    }

    #[test]
    fn git_external_diff_accepts_an_unmerged_path() {
        assert_eq!(
            Ok(InputPaths::Unmerged {
                repository_path: "muppet.txt"
            }),
            parse_input_paths(&["muppet.txt"], true, None)
        );
    }

    #[test]
    fn git_labels_use_dev_null_for_a_missing_side() {
        assert_eq!(
            ("/dev/null".to_string(), "b/new.txt".to_string()),
            file_labels(Some(["new.txt", "new.txt"]), "/dev/null", "/tmp/new")
        );
        assert_eq!(
            ("a/old.txt".to_string(), "/dev/null".to_string()),
            file_labels(Some(["old.txt", "old.txt"]), "/tmp/old", "/dev/null")
        );
    }

    #[test]
    fn unmerged_index_entries_are_collected_by_stage() {
        let output = concat!(
            "100644 base-object 1\tmuppet cast.txt\0",
            "100644 local-object 2\tmuppet cast.txt\0",
            "100644 remote-object 3\tmuppet cast.txt\0",
        );

        assert_eq!(
            [
                Some(GitIndexStage {
                    mode: "100644".to_string(),
                    object_id: "base-object".to_string(),
                }),
                Some(GitIndexStage {
                    mode: "100644".to_string(),
                    object_id: "local-object".to_string(),
                }),
                Some(GitIndexStage {
                    mode: "100644".to_string(),
                    object_id: "remote-object".to_string(),
                }),
            ],
            parse_unmerged_stages(output.as_bytes(), "muppet cast.txt")
                .expect("valid index entries should parse")
        );
    }

    #[test]
    fn unmerged_index_entries_may_omit_the_base() {
        let output = concat!(
            "100644 local-object 2\tnew.txt\0",
            "100644 remote-object 3\tnew.txt\0",
        );

        let stages = parse_unmerged_stages(output.as_bytes(), "new.txt")
            .expect("an add/add conflict has no base stage");

        assert_eq!(None, stages[0]);
        assert_eq!("local-object", stages[1].as_ref().unwrap().object_id);
        assert_eq!("remote-object", stages[2].as_ref().unwrap().object_id);
    }

    #[test]
    fn gitlink_stage_is_rendered_as_a_subproject_commit() {
        let stage = GitIndexStage {
            mode: "160000".to_string(),
            object_id: "deadbeef".to_string(),
        };

        assert_eq!(
            FileContents::Text("Subproject commit deadbeef".to_string()),
            read_git_stage(Some(&stage), "muppets").expect("gitlinks do not need object lookup")
        );
    }

    #[test]
    fn unmerged_gitlinks_are_read_from_the_index_entries() {
        let output = concat!(
            "160000 base-object 1\tmuppets\0",
            "160000 local-object 2\tmuppets\0",
            "160000 remote-object 3\tmuppets\0",
        );
        let stages = parse_unmerged_stages(output.as_bytes(), "muppets")
            .expect("valid gitlink stages should parse");
        let contents = [1, 0, 2].map(|index| {
            read_git_stage(stages[index].as_ref(), "muppets")
                .expect("gitlinks do not need object lookup")
        });

        assert_eq!(
            [
                FileContents::Text("Subproject commit local-object".to_string()),
                FileContents::Text("Subproject commit base-object".to_string()),
                FileContents::Text("Subproject commit remote-object".to_string()),
            ],
            contents
        );
    }

    #[test]
    fn malformed_unmerged_index_entries_are_rejected() {
        let error = parse_unmerged_stages(
            b"100644 repeated 2\tkermit.txt\0\
              100644 repeated-again 2\tkermit.txt\0",
            "kermit.txt",
        )
        .expect_err("duplicate stages are ambiguous");

        assert_eq!("Git returned stage 2 more than once for kermit.txt", error);
    }

    #[test]
    fn git_arguments_are_rejected_without_git_external_diff_mode() {
        let git_arguments = [
            "muppet.txt",
            "/tmp/old",
            "old-object",
            "100644",
            "/tmp/new",
            "new-object",
            "100644",
        ];

        assert_eq!(
            Err("jiff expects two or three files, or two directories"),
            parse_input_paths(&git_arguments, false, None)
        );
    }

    #[test]
    fn three_way_output_highlights_only_the_outer_files() {
        let output = render_three_way_output(
            RenderInput {
                contents: &FileContents::Text("AAAAA".to_string()),
                path: "local.txt",
            },
            RenderInput {
                contents: &FileContents::Text("MMMMM".to_string()),
                path: "base.txt",
            },
            RenderInput {
                contents: &FileContents::Text("ZZZZZ".to_string()),
                path: "remote.txt",
            },
            ["local.txt", "base.txt", "remote.txt"],
            &OutputOptions {
                repository_paths: None,
                inline: true,
                context_lines: None,
            },
            HighlightOptions {
                color: true,
                enabled: false,
                syntax_name: None,
            },
            &config::ColorScheme::default(),
        )
        .expect("plain text highlighting cannot fail");

        assert!(output.contains("=== 1: local.txt vs 2: base.txt ===\n"));
        assert!(output.contains("=== 2: base.txt vs 3: remote.txt ===\n"));
        assert!(output.contains(
            &config::ColorScheme::default()
                .remove_highlight
                .paint("AAAAA")
                .to_string()
        ));
        assert!(output.contains("+ MMMMM\n"));
        assert!(output.contains("- MMMMM\n"));
        assert!(output.contains(
            &config::ColorScheme::default()
                .add_highlight
                .paint("ZZZZZ")
                .to_string()
        ));
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
    fn git_inline_keeps_git_style_headings() {
        let left = FileContents::Text("Kermit".to_string());
        let right = FileContents::Text("Fozzie".to_string());

        let output = render_output(
            &left,
            &right,
            "/tmp/local",
            "/tmp/remote",
            &OutputOptions {
                repository_paths: Some(["muppet cast.txt", "muppet cast.txt"]),
                inline: true,
                context_lines: None,
            },
            &config::ColorScheme::plain(),
            &syntax::HighlightedFiles::default(),
        );

        assert!(output.starts_with("--- a/muppet cast.txt\n+++ b/muppet cast.txt\n"));
    }

    #[test]
    fn git_inline_labels_a_deleted_file_as_dev_null() {
        let left = FileContents::Text("Kermit".to_string());
        let right = FileContents::Text(String::new());

        let output = render_output(
            &left,
            &right,
            "/tmp/local",
            "/dev/null",
            &OutputOptions {
                repository_paths: Some(["muppet.txt", "muppet.txt"]),
                inline: true,
                context_lines: None,
            },
            &config::ColorScheme::plain(),
            &syntax::HighlightedFiles::default(),
        );

        assert!(output.starts_with("--- a/muppet.txt\n+++ /dev/null\n"));
    }

    #[test]
    fn git_side_by_side_uses_pane_headings() {
        let left = FileContents::Text("Kermit".to_string());
        let right = FileContents::Text("Fozzie".to_string());

        let output = render_output(
            &left,
            &right,
            "/tmp/left.py",
            "/tmp/right.py",
            &OutputOptions {
                repository_paths: Some(["muppet.py", "muppet.py"]),
                inline: false,
                context_lines: None,
            },
            &config::ColorScheme::plain(),
            &syntax::HighlightedFiles::default(),
        );

        let lines = output.lines().take(3).collect::<Vec<_>>();
        assert!(lines[0].contains('┬'));
        assert!(lines[1].starts_with(" muppet.py"));
        assert!(lines[1].contains("│ muppet.py"));
        assert!(lines[2].contains('┼'));
        assert!(!output.contains("--- a/muppet.py"));
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
                repository_paths: Some(["animal.dat", "animal.dat"]),
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
                repository_paths: None,
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
