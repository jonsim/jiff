use crate::config::ColorScheme;
use nu_ansi_term::{AnsiString as ANSIString, Style};
use std::borrow::Cow;
use std::fmt;
use std::ops::Range;
use std::path::Path;
use std::str::FromStr;
use std::sync::LazyLock;
use syntect::easy::ScopeRangeIterator;
use syntect::highlighting::ScopeSelector;
use syntect::parsing::{ParseState, Scope, ScopeStack, SyntaxReference, SyntaxSet};
use syntect::util::LinesWithEndings;
use unicode_width::UnicodeWidthStr;

static SYNTAX_SET: LazyLock<SyntaxSet> = LazyLock::new(SyntaxSet::load_defaults_newlines);
static SELECTORS: LazyLock<SyntaxSelectors> = LazyLock::new(SyntaxSelectors::new);
const TAB_WIDTH: usize = 4;

fn expand_tabs<'a>(content: &'a str, column: &mut usize) -> Cow<'a, str> {
    if !content.contains('\t') {
        *column += content.width();
        return Cow::Borrowed(content);
    }

    let mut expanded = String::with_capacity(content.len());
    let mut parts = content.split('\t').peekable();
    while let Some(part) = parts.next() {
        expanded.push_str(part);
        *column += part.width();
        if parts.peek().is_some() {
            let spaces = TAB_WIDTH - *column % TAB_WIDTH;
            expanded.extend(std::iter::repeat_n(' ', spaces));
            *column += spaces;
        }
    }
    Cow::Owned(expanded)
}

#[derive(Debug)]
pub(crate) struct HighlightError {
    message: String,
}

impl HighlightError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for HighlightError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for HighlightError {}

#[derive(Clone, Copy, Debug, PartialEq)]
struct SyntaxSpan {
    start: usize,
    end: usize,
    style: Style,
    highlight_style: Style,
}

#[derive(Debug, Default, PartialEq)]
struct HighlightedLine {
    spans: Vec<SyntaxSpan>,
}

/// Syntax spans for a source file, retained in source-line order.
#[derive(Debug, Default, PartialEq)]
pub(crate) struct HighlightedFile {
    lines: Vec<HighlightedLine>,
    highlight_styles: Vec<Style>,
}

impl HighlightedFile {
    /// Combines syntax foregrounds with the diff styling for one source line.
    pub(crate) fn render_line<'a>(
        &self,
        index: usize,
        content: &'a str,
        base_style: Style,
        overrides: &[(Range<usize>, Style)],
    ) -> Vec<ANSIString<'a>> {
        if content.is_empty() {
            return vec![base_style.paint(content)];
        }

        let empty = HighlightedLine::default();
        let line = self.lines.get(index).unwrap_or(&empty);
        let mut boundaries = vec![0, content.len()];
        for span in &line.spans {
            boundaries.push(span.start.min(content.len()));
            boundaries.push(span.end.min(content.len()));
        }
        for (range, _) in overrides {
            boundaries.push(range.start.min(content.len()));
            boundaries.push(range.end.min(content.len()));
        }
        boundaries.sort_unstable();
        boundaries.dedup();
        let mut syntax_spans = line.spans.iter().peekable();
        let mut diff_overrides = overrides.iter().peekable();
        let mut column = 0;

        boundaries
            .windows(2)
            .filter_map(|window| {
                let start = window[0];
                let end = window[1];
                if start == end {
                    return None;
                }

                let mut style = base_style;
                let mut is_highlight = self.highlight_styles.contains(&base_style);
                while diff_overrides
                    .peek()
                    .is_some_and(|(range, _)| range.end <= start)
                {
                    diff_overrides.next();
                }
                if let Some((_, override_style)) = diff_overrides
                    .peek()
                    .filter(|(range, _)| range.start <= start && start < range.end)
                {
                    style = *override_style;
                    is_highlight = true;
                }
                while syntax_spans.peek().is_some_and(|span| span.end <= start) {
                    syntax_spans.next();
                }
                if let Some(span) = syntax_spans
                    .peek()
                    .filter(|span| span.start <= start && start < span.end)
                {
                    // Syntax only supplies the foreground. Leave the background
                    // alone so the diff still shows across the whole line.
                    let syntax = if is_highlight {
                        span.highlight_style
                    } else {
                        span.style
                    };
                    style.foreground = syntax.foreground;
                    style.is_bold |= syntax.is_bold;
                    style.is_italic |= syntax.is_italic;
                }
                Some(style.paint(expand_tabs(&content[start..end], &mut column)))
            })
            .collect()
    }
}

/// Syntax highlighting for the before and after sides of a diff.
#[derive(Debug, Default, PartialEq)]
pub(crate) struct HighlightedFiles {
    pub(crate) left: HighlightedFile,
    pub(crate) right: HighlightedFile,
}

/// Checks an explicit syntax name even when colour output is disabled.
pub(crate) fn validate_syntax(syntax_name: Option<&str>) -> Result<(), HighlightError> {
    let Some(name) = syntax_name.filter(|name| !name.eq_ignore_ascii_case("auto")) else {
        return Ok(());
    };
    if SYNTAX_SET.find_syntax_by_token(name).is_none() {
        return Err(HighlightError::new(format!("unknown syntax {name:?}")));
    }
    Ok(())
}

/// Highlights both files using an explicitly requested or detected syntax.
pub(crate) fn highlight_files(
    left: &str,
    right: &str,
    left_path: &str,
    right_path: &str,
    repository_path: Option<&str>,
    syntax_name: Option<&str>,
    colors: &ColorScheme,
) -> Result<HighlightedFiles, HighlightError> {
    let left_path = repository_path.unwrap_or(left_path);
    let right_path = repository_path.unwrap_or(right_path);

    Ok(HighlightedFiles {
        left: highlight_file(left, left_path, syntax_name, colors)?,
        right: highlight_file(right, right_path, syntax_name, colors)?,
    })
}

/// Highlights one source file using an explicit or detected syntax.
pub(crate) fn highlight_file(
    content: &str,
    path: &str,
    syntax_name: Option<&str>,
    colors: &ColorScheme,
) -> Result<HighlightedFile, HighlightError> {
    let explicit_syntax = syntax_name.filter(|name| !name.eq_ignore_ascii_case("auto"));
    let syntax = if let Some(name) = explicit_syntax {
        SYNTAX_SET
            .find_syntax_by_token(name)
            .ok_or_else(|| HighlightError::new(format!("unknown syntax {name:?}")))?
    } else {
        let Some(syntax) = detect_syntax(path, content) else {
            return Ok(HighlightedFile::default());
        };
        syntax
    };

    parse_highlights(content, path, syntax, colors)
}

fn detect_syntax(path: &str, content: &str) -> Option<&'static SyntaxReference> {
    let path = Path::new(path);
    let extension_match = path
        .extension()
        .and_then(|extension| extension.to_str())
        .and_then(|extension| SYNTAX_SET.find_syntax_by_extension(extension));
    let filename_match = path
        .file_name()
        .and_then(|name| name.to_str())
        .and_then(|name| SYNTAX_SET.find_syntax_by_token(name.trim_start_matches('.')));
    let first_line_match = content
        .lines()
        .next()
        .and_then(|line| SYNTAX_SET.find_syntax_by_first_line(line));

    extension_match.or(filename_match).or(first_line_match)
}

fn parse_highlights(
    content: &str,
    path: &str,
    syntax: &SyntaxReference,
    colors: &ColorScheme,
) -> Result<HighlightedFile, HighlightError> {
    let mut parser = ParseState::new(syntax);
    let mut stack = ScopeStack::new();
    let mut lines = Vec::new();

    for line_with_ending in LinesWithEndings::from(content) {
        let visible_length = line_with_ending
            .strip_suffix('\n')
            .unwrap_or(line_with_ending)
            .len();
        let operations = parser
            .parse_line(line_with_ending, &SYNTAX_SET)
            .map_err(|error| HighlightError::new(format!("could not parse {path:?}: {error}")))?;
        let mut spans: Vec<SyntaxSpan> = Vec::new();

        for (range, operation) in ScopeRangeIterator::new(&operations, line_with_ending) {
            stack.apply(operation).map_err(|error| {
                HighlightError::new(format!("could not parse {path:?}: {error}"))
            })?;
            let start = range.start.min(visible_length);
            let end = range.end.min(visible_length);
            let Some((style, highlight_style)) = syntax_style(stack.as_slice(), colors) else {
                continue;
            };
            if start == end {
                continue;
            }

            if let Some(previous) = spans.last_mut() {
                if previous.end == start
                    && previous.style == style
                    && previous.highlight_style == highlight_style
                {
                    previous.end = end;
                    continue;
                }
            }
            spans.push(SyntaxSpan {
                start,
                end,
                style,
                highlight_style,
            });
        }
        lines.push(HighlightedLine { spans });
    }

    // `LinesWithEndings` keeps the final newline on the previous line (fair
    // enough). Jiff stripped the file terminator earlier, so any newline left
    // here represents a real final blank line.
    if content.ends_with('\n') {
        lines.push(HighlightedLine::default());
    }

    Ok(HighlightedFile {
        lines,
        highlight_styles: vec![
            colors.add_highlight,
            colors.remove_highlight,
            colors.overlap_highlight,
        ],
    })
}

fn syntax_style(scopes: &[Scope], colors: &ColorScheme) -> Option<(Style, Style)> {
    if SELECTORS
        .comment
        .iter()
        .any(|selector| selector.does_match(scopes).is_some())
    {
        return Some((colors.syntax_comment, colors.syntax_comment_highlight));
    }
    if SELECTORS
        .string
        .iter()
        .any(|selector| selector.does_match(scopes).is_some())
    {
        return Some((colors.syntax_string, colors.syntax_string_highlight));
    }
    if SELECTORS
        .keyword
        .iter()
        .any(|selector| selector.does_match(scopes).is_some())
    {
        return Some((colors.syntax_keyword, colors.syntax_keyword_highlight));
    }
    if SELECTORS
        .number
        .iter()
        .any(|selector| selector.does_match(scopes).is_some())
    {
        return Some((colors.syntax_number, colors.syntax_number_highlight));
    }
    if SELECTORS
        .name
        .iter()
        .any(|selector| selector.does_match(scopes).is_some())
    {
        return Some((colors.syntax_definition, colors.syntax_definition_highlight));
    }
    None
}

struct SyntaxSelectors {
    comment: Vec<ScopeSelector>,
    string: Vec<ScopeSelector>,
    keyword: Vec<ScopeSelector>,
    number: Vec<ScopeSelector>,
    name: Vec<ScopeSelector>,
}

impl SyntaxSelectors {
    fn new() -> Self {
        Self {
            comment: parse_selectors(&["comment"]),
            string: parse_selectors(&["string"]),
            keyword: parse_selectors(&["keyword", "storage"]),
            number: parse_selectors(&["constant.numeric"]),
            name: parse_selectors(&[
                "entity.name.function",
                "entity.name.type",
                "support.type",
                "variable.function",
            ]),
        }
    }
}

fn parse_selectors(names: &[&str]) -> Vec<ScopeSelector> {
    names
        .iter()
        .map(|name| ScopeSelector::from_str(name).expect("built-in scope selector is valid"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use nu_ansi_term::Color;

    #[test]
    fn filename_selects_the_python_syntax() {
        // A normal Python filename should be enough to pick the syntax.
        let highlighted = highlight_file(
            "def kermit():\n    return 3",
            "muppets.py",
            None,
            &ColorScheme::default(),
        )
        .expect("Python source should highlight");

        assert_eq!(
            Some(Color::Purple),
            highlighted.lines[0].spans[0].style.foreground
        );
    }

    #[test]
    fn explicit_syntax_overrides_a_plain_filename() {
        // Git and process-substitution paths often have no useful extension.
        let highlighted = highlight_file(
            "def kermit():",
            "temporary.txt",
            Some("python"),
            &ColorScheme::default(),
        )
        .expect("explicit Python source should highlight");

        assert_eq!(
            Some(Color::Purple),
            highlighted.lines[0].spans[0].style.foreground
        );
    }

    #[test]
    fn unknown_detected_syntax_falls_back_to_plain_text() {
        let highlighted = highlight_file(
            "Kermit and Fozzie",
            "muppets.unknown",
            None,
            &ColorScheme::default(),
        )
        .expect("unknown files should remain plain");

        assert_eq!(HighlightedFile::default(), highlighted);
    }

    #[test]
    fn unknown_explicit_syntax_is_reported() {
        let error = highlight_file(
            "Kermit",
            "muppets.txt",
            Some("great-gonzo"),
            &ColorScheme::default(),
        )
        .expect_err("an unknown explicit syntax should fail");

        assert!(error.to_string().contains("great-gonzo"));
    }

    #[test]
    fn explicit_syntax_is_validated_without_highlighting() {
        // `--no-color` must not make a misspelled explicit language valid.
        let error = validate_syntax(Some("great-gonzo"))
            .expect_err("an unknown explicit syntax should fail");

        assert!(error.to_string().contains("great-gonzo"));
    }

    #[test]
    fn repository_path_identifies_git_temporary_files() {
        // Both Git sides should use the real path supplied through `--path`.
        let highlighted = highlight_files(
            "def kermit(): pass",
            "def fozzie(): pass",
            "/tmp/old",
            "/tmp/new",
            Some("muppets.py"),
            None,
            &ColorScheme::default(),
        )
        .expect("repository path should select Python");

        assert!(!highlighted.left.lines[0].spans.is_empty());
        assert!(!highlighted.right.lines[0].spans.is_empty());
    }

    #[test]
    fn syntax_foreground_keeps_the_diff_background() {
        // Diff background matters more than token colour.
        let highlighted =
            highlight_file("def kermit():", "muppets.py", None, &ColorScheme::default())
                .expect("Python source should highlight");

        let rendered =
            highlighted.render_line(0, "def kermit():", Color::Green.on(Color::Red), &[]);

        assert_eq!(
            Color::Purple.on(Color::Red).paint("def").to_string(),
            rendered[0].to_string()
        );
    }

    #[test]
    fn syntax_and_diff_italics_are_combined() {
        let colors = ColorScheme {
            syntax_keyword: Color::Purple.italic(),
            ..ColorScheme::default()
        };
        let highlighted = highlight_file("def kermit():", "muppets.py", None, &colors)
            .expect("Python source should highlight");
        let syntax_italic = highlighted.render_line(0, "def kermit():", Style::default(), &[]);

        let default_highlighting =
            highlight_file("def kermit():", "muppets.py", None, &ColorScheme::default())
                .expect("Python source should highlight");
        let diff_italic =
            default_highlighting.render_line(0, "def kermit():", Style::default().italic(), &[]);

        assert_eq!(
            Color::Purple.italic().paint("def").to_string(),
            syntax_italic[0].to_string()
        );
        assert_eq!(
            Color::Purple.italic().paint("def").to_string(),
            diff_italic[0].to_string()
        );
    }

    #[test]
    fn tabs_expand_relative_to_the_source_line() {
        // Margins differ between output modes, but source tab stops must not.
        let rendered = HighlightedFile::default().render_line(0, "a\tb", Style::default(), &[]);

        assert_eq!(
            "a   b",
            nu_ansi_term::unstyle(&nu_ansi_term::AnsiStrings(&rendered))
        );
    }

    #[test]
    fn syntax_foreground_renders_on_top_of_intraline_diff() {
        let highlighted =
            highlight_file("def kermit():", "muppets.py", None, &ColorScheme::default())
                .expect("Python source should highlight");
        let changed = vec![(0..3, Color::Black.on(Color::Green))];

        let rendered = highlighted.render_line(0, "def kermit():", Style::default(), &changed);

        assert_eq!(
            Color::Purple.on(Color::Green).paint("def").to_string(),
            rendered[0].to_string()
        );
    }

    #[test]
    fn highlight_syntax_colors_are_used_on_diff_highlights() {
        let colors = ColorScheme {
            syntax_keyword: Color::Purple.normal(),
            syntax_keyword_highlight: Color::Black.normal(),
            ..ColorScheme::default()
        };

        let highlighted = highlight_file("def kermit():", "muppets.py", None, &colors)
            .expect("Python source should highlight");
        let changed = vec![(0..3, colors.add_highlight)];

        // On an unhighlighted line:
        let normal_rendered = highlighted.render_line(0, "def kermit():", Style::default(), &[]);
        assert_eq!(
            Color::Purple.paint("def").to_string(),
            normal_rendered[0].to_string()
        );

        // On an intraline highlight:
        let intraline_rendered =
            highlighted.render_line(0, "def kermit():", Style::default(), &changed);
        assert_eq!(
            Color::Black.on(Color::Green).paint("def").to_string(),
            intraline_rendered[0].to_string()
        );

        // On a whole-line highlight:
        let line_rendered = highlighted.render_line(0, "def kermit():", colors.add_highlight, &[]);
        assert_eq!(
            Color::Black.on(Color::Green).paint("def").to_string(),
            line_rendered[0].to_string()
        );
    }

    #[test]
    fn multiline_parser_state_is_kept() {
        // The second line stays a string because we parse the whole file at once.
        let highlighted = highlight_file(
            "muppet = \"\"\"Kermit\nthe Frog\"\"\"",
            "muppets.py",
            None,
            &ColorScheme::default(),
        )
        .expect("multiline Python should highlight");

        assert_eq!(
            Some(Color::Cyan),
            highlighted.lines[1].spans[0].style.foreground
        );
    }
}
