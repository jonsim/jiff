use ansi_term::{Color, Style};
use std::env;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const SUPPORTED_COLORS: &str = concat!(
    "default, black, bright_black, red, bright_red, green, bright_green, ",
    "yellow, bright_yellow, blue, bright_blue, magenta, bright_magenta, ",
    "cyan, bright_cyan, white, bright_white, gray, grey, or purple",
);

#[derive(Clone, Copy)]
pub(crate) struct ColorScheme {
    pub(crate) same: Style,
    pub(crate) omitted: Style,
    pub(crate) add: Style,
    pub(crate) add_highlight: Style,
    pub(crate) remove: Style,
    pub(crate) remove_highlight: Style,
    pub(crate) syntax_comment: Style,
    pub(crate) syntax_keyword: Style,
    pub(crate) syntax_string: Style,
    pub(crate) syntax_number: Style,
    pub(crate) syntax_definition: Style,
}

impl ColorScheme {
    pub(crate) fn plain() -> Self {
        Self {
            same: Style::default(),
            omitted: Style::default(),
            add: Style::default(),
            add_highlight: Style::default(),
            remove: Style::default(),
            remove_highlight: Style::default(),
            syntax_comment: Style::default(),
            syntax_keyword: Style::default(),
            syntax_string: Style::default(),
            syntax_number: Style::default(),
            syntax_definition: Style::default(),
        }
    }

    pub(crate) fn without_additions(mut self) -> Self {
        self.add = Style::default();
        self.add_highlight = Style::default();
        self
    }

    pub(crate) fn without_removals(mut self) -> Self {
        self.remove = Style::default();
        self.remove_highlight = Style::default();
        self
    }
}

impl Default for ColorScheme {
    fn default() -> Self {
        Self {
            same: Style::default(),
            omitted: Color::Fixed(8).normal(),
            add: Color::Green.normal(),
            add_highlight: Color::Black.on(Color::Green),
            remove: Color::Red.normal(),
            remove_highlight: Color::Black.on(Color::Red),
            syntax_comment: Color::Fixed(8).normal(),
            syntax_keyword: Color::Purple.normal(),
            syntax_string: Color::Cyan.normal(),
            syntax_number: Color::Blue.normal(),
            syntax_definition: Color::Yellow.normal(),
        }
    }
}

#[derive(Debug)]
pub(crate) struct ConfigError {
    path: PathBuf,
    message: String,
}

impl ConfigError {
    fn new(path: &Path, message: impl Into<String>) -> Self {
        Self {
            path: path.to_path_buf(),
            message: message.into(),
        }
    }
}

impl fmt::Display for ConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.path.display(), self.message)
    }
}

impl std::error::Error for ConfigError {}

pub(crate) fn load_color_scheme() -> Result<ColorScheme, ConfigError> {
    let Some(path) = find_config_file()? else {
        return Ok(ColorScheme::default());
    };
    let contents = fs::read_to_string(&path)
        .map_err(|error| ConfigError::new(&path, format!("could not read file: {error}")))?;

    parse_config(&contents, &path)
}

fn find_config_file() -> Result<Option<PathBuf>, ConfigError> {
    if let Some(path) = env::var_os("JIFF_CONFIG").filter(|path| !path.is_empty()) {
        return Ok(Some(PathBuf::from(path)));
    }

    let candidates = config_candidates(
        env::var_os("HOME").map(PathBuf::from),
        env::var_os("XDG_CONFIG_HOME").map(PathBuf::from),
    );

    for path in candidates {
        match fs::metadata(&path) {
            Ok(_) => return Ok(Some(path)),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(ConfigError::new(
                    &path,
                    format!("could not inspect file: {error}"),
                ));
            }
        }
    }
    Ok(None)
}

fn config_candidates(home: Option<PathBuf>, xdg_home: Option<PathBuf>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    match xdg_home {
        Some(xdg_home) if xdg_home.is_absolute() => {
            candidates.push(xdg_home.join("jiff/config.toml"));
        }
        _ => {
            if let Some(home) = &home {
                candidates.push(home.join(".config/jiff/config.toml"));
            }
        }
    }
    if let Some(home) = home {
        candidates.push(home.join(".jiffconfig"));
    }
    candidates
}

fn parse_config(contents: &str, path: &Path) -> Result<ColorScheme, ConfigError> {
    let document = contents
        .parse::<toml::Table>()
        .map_err(|error| ConfigError::new(path, format!("invalid TOML: {error}")))?;
    reject_unknown_fields(&document, &["color"], "root", path)?;

    let Some(color_value) = document.get("color") else {
        return Ok(ColorScheme::default());
    };
    let color = color_value
        .as_table()
        .ok_or_else(|| ConfigError::new(path, "color must be a table"))?;
    reject_unknown_fields(
        color,
        &[
            "same",
            "omitted",
            "add",
            "add_highlight",
            "remove",
            "remove_highlight",
            "syntax_comment",
            "syntax_keyword",
            "syntax_string",
            "syntax_number",
            "syntax_definition",
        ],
        "color",
        path,
    )?;

    let mut scheme = ColorScheme::default();
    scheme.same = parse_style(color.get("same"), scheme.same, "color.same", path, true)?;
    scheme.omitted = parse_style(
        color.get("omitted"),
        scheme.omitted,
        "color.omitted",
        path,
        true,
    )?;
    scheme.add = parse_style(color.get("add"), scheme.add, "color.add", path, true)?;
    scheme.add_highlight = parse_style(
        color.get("add_highlight"),
        scheme.add_highlight,
        "color.add_highlight",
        path,
        true,
    )?;
    scheme.remove = parse_style(
        color.get("remove"),
        scheme.remove,
        "color.remove",
        path,
        true,
    )?;
    scheme.remove_highlight = parse_style(
        color.get("remove_highlight"),
        scheme.remove_highlight,
        "color.remove_highlight",
        path,
        true,
    )?;
    scheme.syntax_comment = parse_style(
        color.get("syntax_comment"),
        scheme.syntax_comment,
        "color.syntax_comment",
        path,
        false,
    )?;
    scheme.syntax_keyword = parse_style(
        color.get("syntax_keyword"),
        scheme.syntax_keyword,
        "color.syntax_keyword",
        path,
        false,
    )?;
    scheme.syntax_string = parse_style(
        color.get("syntax_string"),
        scheme.syntax_string,
        "color.syntax_string",
        path,
        false,
    )?;
    scheme.syntax_number = parse_style(
        color.get("syntax_number"),
        scheme.syntax_number,
        "color.syntax_number",
        path,
        false,
    )?;
    scheme.syntax_definition = parse_style(
        color.get("syntax_definition"),
        scheme.syntax_definition,
        "color.syntax_definition",
        path,
        false,
    )?;
    Ok(scheme)
}

fn parse_style(
    value: Option<&toml::Value>,
    mut style: Style,
    field: &str,
    path: &Path,
    allow_background: bool,
) -> Result<Style, ConfigError> {
    let Some(value) = value else {
        return Ok(style);
    };
    let table = value
        .as_table()
        .ok_or_else(|| ConfigError::new(path, format!("{field} must be a table")))?;
    let expected = if allow_background {
        &["color", "bgcolor", "bold"][..]
    } else {
        &["color", "bold"][..]
    };
    reject_unknown_fields(table, expected, field, path)?;

    if let Some(color) = string_field(table, "color", field, path)? {
        style.foreground = parse_color(color, &format!("{field}.color"), path)?;
    }
    if allow_background {
        if let Some(color) = string_field(table, "bgcolor", field, path)? {
            style.background = parse_color(color, &format!("{field}.bgcolor"), path)?;
        }
    }
    if let Some(bold) = boolean_field(table, "bold", field, path)? {
        style.is_bold = bold;
    }
    Ok(style)
}

fn string_field<'a>(
    table: &'a toml::Table,
    name: &str,
    parent: &str,
    path: &Path,
) -> Result<Option<&'a str>, ConfigError> {
    match table.get(name) {
        Some(toml::Value::String(value)) => Ok(Some(value)),
        Some(_) => Err(ConfigError::new(
            path,
            format!("{parent}.{name} must be a string"),
        )),
        None => Ok(None),
    }
}

fn boolean_field(
    table: &toml::Table,
    name: &str,
    parent: &str,
    path: &Path,
) -> Result<Option<bool>, ConfigError> {
    match table.get(name) {
        Some(toml::Value::Boolean(value)) => Ok(Some(*value)),
        Some(_) => Err(ConfigError::new(
            path,
            format!("{parent}.{name} must be true or false"),
        )),
        None => Ok(None),
    }
}

fn parse_color(name: &str, field: &str, path: &Path) -> Result<Option<Color>, ConfigError> {
    let color = match name.trim().to_ascii_lowercase().as_str() {
        "default" => None,
        "black" => Some(Color::Black),
        "bright_black" | "gray" | "grey" => Some(Color::Fixed(8)),
        "red" => Some(Color::Red),
        "bright_red" => Some(Color::Fixed(9)),
        "green" => Some(Color::Green),
        "bright_green" => Some(Color::Fixed(10)),
        "yellow" => Some(Color::Yellow),
        "bright_yellow" => Some(Color::Fixed(11)),
        "blue" => Some(Color::Blue),
        "bright_blue" => Some(Color::Fixed(12)),
        "magenta" | "purple" => Some(Color::Purple),
        "bright_magenta" => Some(Color::Fixed(13)),
        "cyan" => Some(Color::Cyan),
        "bright_cyan" => Some(Color::Fixed(14)),
        "white" => Some(Color::White),
        "bright_white" => Some(Color::Fixed(15)),
        _ => {
            return Err(ConfigError::new(
                path,
                format!("{field} has unsupported colour {name:?}; expected {SUPPORTED_COLORS}"),
            ));
        }
    };
    Ok(color)
}

fn reject_unknown_fields(
    table: &toml::Table,
    expected: &[&str],
    parent: &str,
    path: &Path,
) -> Result<(), ConfigError> {
    if let Some(field) = table
        .keys()
        .find(|field| !expected.contains(&field.as_str()))
    {
        return Err(ConfigError::new(
            path,
            format!("unknown option {parent}.{field}"),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(contents: &str) -> Result<ColorScheme, ConfigError> {
        parse_config(contents, Path::new("/tmp/.jiffconfig"))
    }

    #[test]
    fn partial_styles_merge_with_the_default_palette() {
        let scheme = parse(
            r#"
            [color]
            add = { color = "blue", bold = true }
            omitted = { color = "cyan" }
            "#,
        )
        .unwrap();

        assert_eq!(Some(Color::Blue), scheme.add.foreground);
        assert!(scheme.add.is_bold);
        assert_eq!(Some(Color::Cyan), scheme.omitted.foreground);
        assert_eq!(Some(Color::Red), scheme.remove.foreground);
    }

    #[test]
    fn default_clears_an_existing_colour() {
        let scheme = parse(
            r#"
            [color.add_highlight]
            bgcolor = "default"
            "#,
        )
        .unwrap();

        assert_eq!(None, scheme.add_highlight.background);
        assert_eq!(Some(Color::Black), scheme.add_highlight.foreground);
    }

    #[test]
    fn all_ansi_colours_are_configurable() {
        // Keep the TOML names aligned with the terminal's standard 16 colours.
        let colours = [
            ("default", None),
            ("black", Some(Color::Black)),
            ("bright_black", Some(Color::Fixed(8))),
            ("red", Some(Color::Red)),
            ("bright_red", Some(Color::Fixed(9))),
            ("green", Some(Color::Green)),
            ("bright_green", Some(Color::Fixed(10))),
            ("yellow", Some(Color::Yellow)),
            ("bright_yellow", Some(Color::Fixed(11))),
            ("blue", Some(Color::Blue)),
            ("bright_blue", Some(Color::Fixed(12))),
            ("magenta", Some(Color::Purple)),
            ("bright_magenta", Some(Color::Fixed(13))),
            ("cyan", Some(Color::Cyan)),
            ("bright_cyan", Some(Color::Fixed(14))),
            ("white", Some(Color::White)),
            ("bright_white", Some(Color::Fixed(15))),
        ];

        for (name, expected) in colours {
            let scheme = parse(&format!("[color]\nadd = {{ color = {name:?} }}\n")).unwrap();

            assert_eq!(expected, scheme.add.foreground, "{name}");
        }
    }

    #[test]
    fn unsupported_colours_report_the_field() {
        let error = parse(
            r#"
            [color]
            add = { color = "orange" }
            "#,
        )
        .err()
        .expect("orange should be rejected");

        assert!(error.to_string().contains("color.add.color"));
        assert!(error.to_string().contains("orange"));
    }

    #[test]
    fn unknown_options_are_rejected() {
        let error = parse(
            r#"
            [color]
            kermit = { color = "green" }
            "#,
        )
        .err()
        .expect("unknown styles should be rejected");

        assert!(error.to_string().contains("unknown option color.kermit"));
    }

    #[test]
    fn syntax_colours_are_configurable() {
        let scheme = parse(
            r#"
            [color.syntax_comment]
            color = "grey"
            bold = true
            "#,
        )
        .unwrap();

        assert_eq!(Some(Color::Fixed(8)), scheme.syntax_comment.foreground);
        assert!(scheme.syntax_comment.is_bold);
    }

    #[test]
    fn syntax_colours_cannot_hide_the_diff_background() {
        // Backgrounds belong to the diff, which is the primary signal in Jiff.
        let error = parse(
            r#"
            [color.syntax_keyword]
            bgcolor = "cyan"
            "#,
        )
        .err()
        .expect("syntax backgrounds should be rejected");

        assert!(error
            .to_string()
            .contains("unknown option color.syntax_keyword.bgcolor"));
    }

    #[test]
    fn xdg_config_precedes_the_home_dotfile() {
        let paths = config_candidates(
            Some(PathBuf::from("/home/kermit")),
            Some(PathBuf::from("/configs")),
        );

        assert_eq!(
            vec![
                PathBuf::from("/configs/jiff/config.toml"),
                PathBuf::from("/home/kermit/.jiffconfig"),
            ],
            paths
        );
    }

    #[test]
    fn home_config_is_used_when_xdg_home_is_relative() {
        let paths = config_candidates(
            Some(PathBuf::from("/home/fozzie")),
            Some(PathBuf::from("relative")),
        );

        assert_eq!(
            vec![
                PathBuf::from("/home/fozzie/.config/jiff/config.toml"),
                PathBuf::from("/home/fozzie/.jiffconfig"),
            ],
            paths
        );
    }
}
