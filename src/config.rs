use nu_ansi_term::{Color, Style};
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

const STYLE_NAMES: &[&str] = &[
    "same",
    "line_number",
    "line_number_add",
    "line_number_remove",
    "omitted",
    "add",
    "add_highlight",
    "remove",
    "remove_highlight",
    "overlap_highlight",
    "syntax_comment",
    "syntax_comment_highlight",
    "syntax_keyword",
    "syntax_keyword_highlight",
    "syntax_string",
    "syntax_string_highlight",
    "syntax_number",
    "syntax_number_highlight",
    "syntax_definition",
    "syntax_definition_highlight",
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ColorDepth {
    Ansi16,
    Ansi256,
    TrueColor,
}

#[derive(Clone, Copy)]
pub(crate) struct ColorConfig {
    pub(crate) depth: ColorDepth,
    pub(crate) ansi16: ColorScheme,
    pub(crate) ansi256: ColorScheme,
    pub(crate) truecolor: ColorScheme,
}

impl Default for ColorConfig {
    fn default() -> Self {
        let ansi16 = ColorScheme::default();
        let ansi256 = ansi256_scheme(ansi16);
        Self {
            depth: ColorDepth::TrueColor,
            ansi16,
            ansi256,
            truecolor: truecolor_scheme(ansi256),
        }
    }
}

impl ColorConfig {
    pub(crate) fn scheme(self, terminal_depth: ColorDepth) -> ColorScheme {
        match self.scheme_depth(terminal_depth) {
            ColorDepth::Ansi16 => self.ansi16,
            ColorDepth::Ansi256 => self.ansi256,
            ColorDepth::TrueColor => self.truecolor,
        }
    }

    fn scheme_depth(self, terminal_depth: ColorDepth) -> ColorDepth {
        match (self.depth, terminal_depth) {
            (ColorDepth::TrueColor, ColorDepth::TrueColor) => ColorDepth::TrueColor,
            (
                ColorDepth::TrueColor | ColorDepth::Ansi256,
                ColorDepth::TrueColor | ColorDepth::Ansi256,
            ) => ColorDepth::Ansi256,
            _ => ColorDepth::Ansi16,
        }
    }
}

#[derive(Clone, Copy)]
pub(crate) struct ColorScheme {
    pub(crate) same: Style,
    pub(crate) line_number: Style,
    pub(crate) line_number_add: Style,
    pub(crate) line_number_remove: Style,
    pub(crate) omitted: Style,
    pub(crate) add: Style,
    pub(crate) add_highlight: Style,
    pub(crate) remove: Style,
    pub(crate) remove_highlight: Style,
    pub(crate) overlap_highlight: Style,
    pub(crate) syntax_comment: Style,
    pub(crate) syntax_comment_highlight: Style,
    pub(crate) syntax_keyword: Style,
    pub(crate) syntax_keyword_highlight: Style,
    pub(crate) syntax_string: Style,
    pub(crate) syntax_string_highlight: Style,
    pub(crate) syntax_number: Style,
    pub(crate) syntax_number_highlight: Style,
    pub(crate) syntax_definition: Style,
    pub(crate) syntax_definition_highlight: Style,
}

impl ColorScheme {
    pub(crate) fn plain() -> Self {
        Self {
            same: Style::default(),
            line_number: Style::default(),
            line_number_add: Style::default(),
            line_number_remove: Style::default(),
            omitted: Style::default(),
            add: Style::default(),
            add_highlight: Style::default(),
            remove: Style::default(),
            remove_highlight: Style::default(),
            overlap_highlight: Style::default(),
            syntax_comment: Style::default(),
            syntax_comment_highlight: Style::default(),
            syntax_keyword: Style::default(),
            syntax_keyword_highlight: Style::default(),
            syntax_string: Style::default(),
            syntax_string_highlight: Style::default(),
            syntax_number: Style::default(),
            syntax_number_highlight: Style::default(),
            syntax_definition: Style::default(),
            syntax_definition_highlight: Style::default(),
        }
    }

    pub(crate) fn without_additions(mut self) -> Self {
        self.line_number_add = Style::default();
        self.add = Style::default();
        self.add_highlight = Style::default();
        self
    }

    pub(crate) fn without_removals(mut self) -> Self {
        self.line_number_remove = Style::default();
        self.remove = Style::default();
        self.remove_highlight = Style::default();
        self
    }
}

impl Default for ColorScheme {
    fn default() -> Self {
        Self {
            same: Style::default(),
            line_number: Style::default(),
            line_number_add: Style::default(),
            line_number_remove: Style::default(),
            omitted: Color::DarkGray.normal(),
            add: Color::Green.normal(),
            add_highlight: Color::Black.on(Color::Green),
            remove: Color::Red.normal(),
            remove_highlight: Color::Black.on(Color::Red),
            overlap_highlight: Color::Black.on(Color::Yellow),
            syntax_comment: Color::DarkGray.normal(),
            syntax_comment_highlight: Color::DarkGray.normal(),
            syntax_keyword: Color::Purple.normal(),
            syntax_keyword_highlight: Color::Purple.normal(),
            syntax_string: Color::Cyan.normal(),
            syntax_string_highlight: Color::Cyan.normal(),
            syntax_number: Color::Blue.normal(),
            syntax_number_highlight: Color::Blue.normal(),
            syntax_definition: Color::Yellow.normal(),
            syntax_definition_highlight: Color::Yellow.normal(),
        }
    }
}

fn ansi256_scheme(scheme: ColorScheme) -> ColorScheme {
    fn indexed_style(mut style: Style) -> Style {
        style.foreground = style.foreground.map(indexed_color);
        style.background = style.background.map(indexed_color);
        style
    }

    ColorScheme {
        same: indexed_style(scheme.same),
        line_number: indexed_style(scheme.line_number),
        line_number_add: indexed_style(scheme.line_number_add),
        line_number_remove: indexed_style(scheme.line_number_remove),
        omitted: indexed_style(scheme.omitted),
        add: indexed_style(scheme.add),
        add_highlight: indexed_style(scheme.add_highlight),
        remove: indexed_style(scheme.remove),
        remove_highlight: indexed_style(scheme.remove_highlight),
        overlap_highlight: indexed_style(scheme.overlap_highlight),
        syntax_comment: indexed_style(scheme.syntax_comment),
        syntax_comment_highlight: indexed_style(scheme.syntax_comment_highlight),
        syntax_keyword: indexed_style(scheme.syntax_keyword),
        syntax_keyword_highlight: indexed_style(scheme.syntax_keyword_highlight),
        syntax_string: indexed_style(scheme.syntax_string),
        syntax_string_highlight: indexed_style(scheme.syntax_string_highlight),
        syntax_number: indexed_style(scheme.syntax_number),
        syntax_number_highlight: indexed_style(scheme.syntax_number_highlight),
        syntax_definition: indexed_style(scheme.syntax_definition),
        syntax_definition_highlight: indexed_style(scheme.syntax_definition_highlight),
    }
}

fn indexed_color(color: Color) -> Color {
    match color {
        Color::Black => Color::Fixed(0),
        Color::Red => Color::Fixed(1),
        Color::Green => Color::Fixed(2),
        Color::Yellow => Color::Fixed(3),
        Color::Blue => Color::Fixed(4),
        Color::Purple => Color::Fixed(5),
        Color::Cyan => Color::Fixed(6),
        Color::White => Color::Fixed(7),
        Color::DarkGray => Color::Fixed(8),
        Color::LightRed => Color::Fixed(9),
        Color::LightGreen => Color::Fixed(10),
        Color::LightYellow => Color::Fixed(11),
        Color::LightBlue => Color::Fixed(12),
        Color::LightPurple => Color::Fixed(13),
        Color::LightCyan => Color::Fixed(14),
        Color::LightGray => Color::Fixed(15),
        Color::Fixed(index) => Color::Fixed(index),
        Color::Rgb(red, green, blue) => Color::Rgb(red, green, blue),
        _ => color,
    }
}

fn truecolor_scheme(scheme: ColorScheme) -> ColorScheme {
    fn rgb_style(mut style: Style) -> Style {
        style.foreground = style.foreground.map(rgb_color);
        style.background = style.background.map(rgb_color);
        style
    }

    ColorScheme {
        same: rgb_style(scheme.same),
        line_number: rgb_style(scheme.line_number),
        line_number_add: rgb_style(scheme.line_number_add),
        line_number_remove: rgb_style(scheme.line_number_remove),
        omitted: rgb_style(scheme.omitted),
        add: rgb_style(scheme.add),
        add_highlight: rgb_style(scheme.add_highlight),
        remove: rgb_style(scheme.remove),
        remove_highlight: rgb_style(scheme.remove_highlight),
        overlap_highlight: rgb_style(scheme.overlap_highlight),
        syntax_comment: rgb_style(scheme.syntax_comment),
        syntax_comment_highlight: rgb_style(scheme.syntax_comment_highlight),
        syntax_keyword: rgb_style(scheme.syntax_keyword),
        syntax_keyword_highlight: rgb_style(scheme.syntax_keyword_highlight),
        syntax_string: rgb_style(scheme.syntax_string),
        syntax_string_highlight: rgb_style(scheme.syntax_string_highlight),
        syntax_number: rgb_style(scheme.syntax_number),
        syntax_number_highlight: rgb_style(scheme.syntax_number_highlight),
        syntax_definition: rgb_style(scheme.syntax_definition),
        syntax_definition_highlight: rgb_style(scheme.syntax_definition_highlight),
    }
}

fn rgb_color(color: Color) -> Color {
    let Color::Fixed(index) = color else {
        return color;
    };
    let (red, green, blue) = match index {
        0 => (0, 0, 0),
        1 => (128, 0, 0),
        2 => (0, 128, 0),
        3 => (128, 128, 0),
        4 => (0, 0, 128),
        5 => (128, 0, 128),
        6 => (0, 128, 128),
        7 => (192, 192, 192),
        8 => (128, 128, 128),
        9 => (255, 0, 0),
        10 => (0, 255, 0),
        11 => (255, 255, 0),
        12 => (0, 0, 255),
        13 => (255, 0, 255),
        14 => (0, 255, 255),
        15 => (255, 255, 255),
        16..=231 => {
            let cube = index - 16;
            let level = |value| [0, 95, 135, 175, 215, 255][value as usize];
            (level(cube / 36), level(cube / 6 % 6), level(cube % 6))
        }
        232..=255 => {
            let level = 8 + (index - 232) * 10;
            (level, level, level)
        }
    };
    Color::Rgb(red, green, blue)
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

pub(crate) fn load_color_config() -> Result<ColorConfig, ConfigError> {
    let Some(path) = find_config_file()? else {
        return Ok(ColorConfig::default());
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

fn parse_config(contents: &str, path: &Path) -> Result<ColorConfig, ConfigError> {
    let document = contents
        .parse::<toml::Table>()
        .map_err(|error| ConfigError::new(path, format!("invalid TOML: {error}")))?;
    reject_unknown_fields(&document, &["color"], "root", path)?;

    let Some(color_value) = document.get("color") else {
        return Ok(ColorConfig::default());
    };
    let color = color_value
        .as_table()
        .ok_or_else(|| ConfigError::new(path, "color must be a table"))?;
    reject_unknown_fields(
        color,
        &["depth", "ansi16", "ansi256", "truecolor"],
        "color",
        path,
    )?;

    let depth = match color.get("depth") {
        None | Some(toml::Value::Integer(24)) => ColorDepth::TrueColor,
        Some(toml::Value::Integer(16)) => ColorDepth::Ansi16,
        Some(toml::Value::Integer(256)) => ColorDepth::Ansi256,
        Some(toml::Value::Integer(value)) => {
            return Err(ConfigError::new(
                path,
                format!("color.depth must be 16, 24 or 256, not {value}"),
            ));
        }
        Some(_) => {
            return Err(ConfigError::new(path, "color.depth must be 16, 24 or 256"));
        }
    };

    let ansi16 = parse_scheme(
        color.get("ansi16"),
        ColorScheme::default(),
        "color.ansi16",
        path,
        ColorDepth::Ansi16,
    )?;
    let ansi256 = parse_scheme(
        color.get("ansi256"),
        ansi256_scheme(ansi16),
        "color.ansi256",
        path,
        ColorDepth::Ansi256,
    )?;
    let truecolor = parse_scheme(
        color.get("truecolor"),
        truecolor_scheme(ansi256),
        "color.truecolor",
        path,
        ColorDepth::TrueColor,
    )?;
    Ok(ColorConfig {
        depth,
        ansi16,
        ansi256,
        truecolor,
    })
}

fn parse_scheme(
    value: Option<&toml::Value>,
    mut scheme: ColorScheme,
    field: &str,
    path: &Path,
    depth: ColorDepth,
) -> Result<ColorScheme, ConfigError> {
    let Some(value) = value else {
        return Ok(scheme);
    };
    let table = value
        .as_table()
        .ok_or_else(|| ConfigError::new(path, format!("{field} must be a table")))?;
    reject_unknown_fields(table, STYLE_NAMES, field, path)?;

    macro_rules! parse {
        ($name:ident, $background:expr) => {
            scheme.$name = parse_style(
                table.get(stringify!($name)),
                scheme.$name,
                &format!("{field}.{}", stringify!($name)),
                path,
                $background,
                depth,
            )?;
        };
    }
    parse!(same, true);
    parse!(line_number, true);
    if table.contains_key("line_number") {
        if !table.contains_key("line_number_add") {
            scheme.line_number_add = scheme.line_number;
        }
        if !table.contains_key("line_number_remove") {
            scheme.line_number_remove = scheme.line_number;
        }
    }
    parse!(line_number_add, true);
    parse!(line_number_remove, true);
    parse!(omitted, true);
    parse!(add, true);
    parse!(add_highlight, true);
    parse!(remove, true);
    parse!(remove_highlight, true);
    parse!(overlap_highlight, true);
    parse!(syntax_comment, false);
    parse!(syntax_comment_highlight, false);
    parse!(syntax_keyword, false);
    parse!(syntax_keyword_highlight, false);
    parse!(syntax_string, false);
    parse!(syntax_string_highlight, false);
    parse!(syntax_number, false);
    parse!(syntax_number_highlight, false);
    parse!(syntax_definition, false);
    parse!(syntax_definition_highlight, false);
    Ok(scheme)
}

fn parse_style(
    value: Option<&toml::Value>,
    mut style: Style,
    field: &str,
    path: &Path,
    allow_background: bool,
    depth: ColorDepth,
) -> Result<Style, ConfigError> {
    let Some(value) = value else {
        return Ok(style);
    };
    let table = value
        .as_table()
        .ok_or_else(|| ConfigError::new(path, format!("{field} must be a table")))?;
    let expected = if allow_background {
        &["color", "bgcolor", "bold", "italic"][..]
    } else {
        &["color", "bold", "italic"][..]
    };
    reject_unknown_fields(table, expected, field, path)?;

    if let Some(color) = color_field(table, "color", field, path, depth)? {
        style.foreground = color;
    }
    if allow_background {
        if let Some(color) = color_field(table, "bgcolor", field, path, depth)? {
            style.background = color;
        }
    }
    if let Some(bold) = boolean_field(table, "bold", field, path)? {
        style.is_bold = bold;
    }
    if let Some(italic) = boolean_field(table, "italic", field, path)? {
        style.is_italic = italic;
    }
    Ok(style)
}

fn color_field(
    table: &toml::Table,
    name: &str,
    parent: &str,
    path: &Path,
    depth: ColorDepth,
) -> Result<Option<Option<Color>>, ConfigError> {
    let Some(value) = table.get(name) else {
        return Ok(None);
    };
    let field = format!("{parent}.{name}");
    if depth == ColorDepth::Ansi256 {
        return match value {
            toml::Value::Integer(index) if (0..=255).contains(index) => {
                Ok(Some(Some(Color::Fixed(*index as u8))))
            }
            toml::Value::Integer(index) => Err(ConfigError::new(
                path,
                format!("{field} must be between 0 and 255, not {index}"),
            )),
            toml::Value::String(value) if value.trim().eq_ignore_ascii_case("default") => {
                Ok(Some(None))
            }
            _ => Err(ConfigError::new(
                path,
                format!("{field} must be an index from 0 to 255 or \"default\""),
            )),
        };
    }

    if depth == ColorDepth::TrueColor {
        return match value {
            toml::Value::String(value) if value.trim().eq_ignore_ascii_case("default") => {
                Ok(Some(None))
            }
            toml::Value::String(value) => parse_rgb(value)
                .map(|color| Some(Some(color)))
                .ok_or_else(|| {
                    ConfigError::new(path, format!("{field} must be #RRGGBB or \"default\""))
                }),
            _ => Err(ConfigError::new(
                path,
                format!("{field} must be #RRGGBB or \"default\""),
            )),
        };
    }

    match value {
        toml::Value::String(value) => Ok(Some(parse_color(value, &field, path)?)),
        _ => Err(ConfigError::new(path, format!("{field} must be a string"))),
    }
}

fn parse_rgb(value: &str) -> Option<Color> {
    let value = value.trim();
    if value.len() != 7 || !value.starts_with('#') {
        return None;
    }
    let red = u8::from_str_radix(&value[1..3], 16).ok()?;
    let green = u8::from_str_radix(&value[3..5], 16).ok()?;
    let blue = u8::from_str_radix(&value[5..7], 16).ok()?;
    Some(Color::Rgb(red, green, blue))
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
        "bright_black" | "gray" | "grey" => Some(Color::DarkGray),
        "red" => Some(Color::Red),
        "bright_red" => Some(Color::LightRed),
        "green" => Some(Color::Green),
        "bright_green" => Some(Color::LightGreen),
        "yellow" => Some(Color::Yellow),
        "bright_yellow" => Some(Color::LightYellow),
        "blue" => Some(Color::Blue),
        "bright_blue" => Some(Color::LightBlue),
        "magenta" | "purple" => Some(Color::Purple),
        "bright_magenta" => Some(Color::LightPurple),
        "cyan" => Some(Color::Cyan),
        "bright_cyan" => Some(Color::LightCyan),
        "white" => Some(Color::White),
        "bright_white" => Some(Color::LightGray),
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
        parse_config(contents, Path::new("/tmp/.jiffconfig")).map(|config| config.ansi16)
    }

    #[test]
    fn partial_styles_merge_with_the_default_palette() {
        let scheme = parse(
            r#"
            [color.ansi16]
            add = { color = "blue", bold = true, italic = true }
            omitted = { color = "cyan" }
            "#,
        )
        .unwrap();

        assert_eq!(Some(Color::Blue), scheme.add.foreground);
        assert!(scheme.add.is_bold);
        assert!(scheme.add.is_italic);
        assert_eq!(Some(Color::Cyan), scheme.omitted.foreground);
        assert_eq!(Some(Color::Red), scheme.remove.foreground);
    }

    #[test]
    fn default_clears_an_existing_colour() {
        let scheme = parse(
            r#"
            [color.ansi16.add_highlight]
            bgcolor = "default"
            "#,
        )
        .unwrap();

        assert_eq!(None, scheme.add_highlight.background);
        assert_eq!(Some(Color::Black), scheme.add_highlight.foreground);
    }

    #[test]
    fn invalid_italic_value_is_rejected() {
        let error = parse(
            r#"
            [color.ansi16.add]
            italic = "yes"
            "#,
        )
        .err()
        .expect("non-boolean italics should be rejected");

        assert!(error
            .to_string()
            .contains("color.ansi16.add.italic must be true or false"));
    }

    #[test]
    fn line_number_style_accepts_a_background() {
        let config = parse_config(
            r#"
            [color.ansi16.line_number]
            color = "white"
            bgcolor = "blue"
            bold = true
            "#,
            Path::new("/tmp/.jiffconfig"),
        )
        .unwrap();

        assert_eq!(Some(Color::White), config.ansi16.line_number.foreground);
        assert_eq!(Some(Color::Blue), config.ansi16.line_number.background);
        assert!(config.ansi16.line_number.is_bold);
        assert_eq!(Some(Color::Fixed(7)), config.ansi256.line_number.foreground);
        assert_eq!(Some(Color::Fixed(4)), config.ansi256.line_number.background);
    }

    #[test]
    fn changed_line_numbers_inherit_the_general_gutter_style() {
        // Existing configs should keep styling every gutter as they did before.
        let config = parse_config(
            r#"
            [color.ansi16.line_number]
            color = "white"
            bgcolor = "blue"
            bold = true
            "#,
            Path::new("/tmp/.jiffconfig"),
        )
        .unwrap();

        assert_eq!(config.ansi16.line_number, config.ansi16.line_number_add);
        assert_eq!(config.ansi16.line_number, config.ansi16.line_number_remove);
        assert_eq!(config.ansi256.line_number, config.ansi256.line_number_add);
        assert_eq!(
            config.ansi256.line_number,
            config.ansi256.line_number_remove
        );
    }

    #[test]
    fn changed_line_number_styles_are_configurable() {
        let scheme = parse(
            r#"
            [color.ansi16.line_number_add]
            color = "green"
            bgcolor = "blue"

            [color.ansi16.line_number_remove]
            color = "red"
            bgcolor = "yellow"
            "#,
        )
        .unwrap();

        assert_eq!(Some(Color::Green), scheme.line_number_add.foreground);
        assert_eq!(Some(Color::Blue), scheme.line_number_add.background);
        assert_eq!(Some(Color::Red), scheme.line_number_remove.foreground);
        assert_eq!(Some(Color::Yellow), scheme.line_number_remove.background);
    }

    #[test]
    fn all_ansi_colours_are_configurable() {
        // Keep the TOML names aligned with the terminal's standard 16 colours.
        let colours = [
            ("default", None),
            ("black", Some(Color::Black)),
            ("bright_black", Some(Color::DarkGray)),
            ("red", Some(Color::Red)),
            ("bright_red", Some(Color::LightRed)),
            ("green", Some(Color::Green)),
            ("bright_green", Some(Color::LightGreen)),
            ("yellow", Some(Color::Yellow)),
            ("bright_yellow", Some(Color::LightYellow)),
            ("blue", Some(Color::Blue)),
            ("bright_blue", Some(Color::LightBlue)),
            ("magenta", Some(Color::Purple)),
            ("bright_magenta", Some(Color::LightPurple)),
            ("cyan", Some(Color::Cyan)),
            ("bright_cyan", Some(Color::LightCyan)),
            ("white", Some(Color::White)),
            ("bright_white", Some(Color::LightGray)),
        ];

        for (name, expected) in colours {
            let scheme = parse(&format!("[color.ansi16]\nadd = {{ color = {name:?} }}\n")).unwrap();

            assert_eq!(expected, scheme.add.foreground, "{name}");
        }
    }

    #[test]
    fn unsupported_colours_report_the_field() {
        let error = parse(
            r#"
            [color.ansi16]
            add = { color = "orange" }
            "#,
        )
        .err()
        .expect("orange should be rejected");

        assert!(error.to_string().contains("color.ansi16.add.color"));
        assert!(error.to_string().contains("orange"));
    }

    #[test]
    fn unknown_options_are_rejected() {
        let error = parse(
            r#"
            [color.ansi16]
            kermit = { color = "green" }
            "#,
        )
        .err()
        .expect("unknown styles should be rejected");

        assert!(error
            .to_string()
            .contains("unknown option color.ansi16.kermit"));
    }

    #[test]
    fn syntax_colours_are_configurable() {
        let scheme = parse(
            r#"
            [color.ansi16.syntax_comment]
            color = "grey"
            bold = true

            [color.ansi16.syntax_keyword_highlight]
            color = "black"
            bold = true
            "#,
        )
        .unwrap();

        assert_eq!(Some(Color::DarkGray), scheme.syntax_comment.foreground);
        assert!(scheme.syntax_comment.is_bold);
        assert_eq!(
            Some(Color::Black),
            scheme.syntax_keyword_highlight.foreground
        );
        assert!(scheme.syntax_keyword_highlight.is_bold);
    }

    #[test]
    fn three_way_overlap_highlight_is_configurable() {
        let scheme = parse(
            r#"
            [color.ansi16.overlap_highlight]
            color = "white"
            bgcolor = "blue"
            "#,
        )
        .unwrap();

        assert_eq!(Some(Color::White), scheme.overlap_highlight.foreground);
        assert_eq!(Some(Color::Blue), scheme.overlap_highlight.background);
    }

    #[test]
    fn syntax_colours_cannot_hide_the_diff_background() {
        // Diff highlighting is the bit users came to see, so syntax must not
        // overwrite its background.
        let error = parse(
            r#"
            [color.ansi16.syntax_keyword]
            bgcolor = "cyan"
            "#,
        )
        .err()
        .expect("syntax backgrounds should be rejected");

        assert!(error
            .to_string()
            .contains("unknown option color.ansi16.syntax_keyword.bgcolor"));

        let error = parse(
            r#"
            [color.ansi16.syntax_keyword_highlight]
            bgcolor = "cyan"
            "#,
        )
        .err()
        .expect("syntax highlight backgrounds should be rejected");

        assert!(error
            .to_string()
            .contains("unknown option color.ansi16.syntax_keyword_highlight.bgcolor"));
    }

    #[test]
    fn ansi256_styles_inherit_the_resolved_ansi16_palette() {
        let config = parse_config(
            r#"
            [color.ansi16]
            add = { color = "bright_green", bold = true, italic = true }

            [color.ansi256]
            add = { color = 114 }
            "#,
            Path::new("/tmp/.jiffconfig"),
        )
        .unwrap();

        assert_eq!(Some(Color::Fixed(114)), config.ansi256.add.foreground);
        assert!(config.ansi256.add.is_bold);
        assert!(config.ansi256.add.is_italic);
        assert_eq!(Some(Color::Fixed(1)), config.ansi256.remove.foreground);
    }

    #[test]
    fn ansi256_default_clears_an_inherited_colour() {
        let config = parse_config(
            r#"
            [color.ansi256]
            add = { color = "default" }
            "#,
            Path::new("/tmp/.jiffconfig"),
        )
        .unwrap();

        assert_eq!(None, config.ansi256.add.foreground);
    }

    #[test]
    fn truecolor_styles_inherit_the_resolved_ansi256_palette() {
        let config = parse_config(
            r##"
            [color.ansi256]
            add = { color = 114, bold = true, italic = true }

            [color.truecolor]
            add = { color = "#89B4FA" }
            "##,
            Path::new("/tmp/.jiffconfig"),
        )
        .unwrap();

        assert_eq!(
            Some(Color::Rgb(137, 180, 250)),
            config.truecolor.add.foreground
        );
        assert!(config.truecolor.add.is_bold);
        assert!(config.truecolor.add.is_italic);
        assert_eq!(
            Some(Color::Rgb(128, 0, 0)),
            config.truecolor.remove.foreground
        );
    }

    #[test]
    fn truecolor_preference_falls_back_through_each_palette() {
        let config = ColorConfig::default();

        assert_eq!(
            config.truecolor.add,
            config.scheme(ColorDepth::TrueColor).add
        );
        assert_eq!(config.ansi256.add, config.scheme(ColorDepth::Ansi256).add);
        assert_eq!(config.ansi16.add, config.scheme(ColorDepth::Ansi16).add);
    }

    #[test]
    fn invalid_truecolor_values_are_rejected() {
        for value in ["12ab34", "#abc", "#12zz34", "green"] {
            let contents = format!("[color.truecolor]\nadd = {{ color = {value:?} }}\n");
            let error = parse_config(&contents, Path::new("/tmp/.jiffconfig"))
                .err()
                .expect("invalid RGB should be rejected");

            assert!(error.to_string().contains("#RRGGBB"), "{}", value);
        }
    }

    #[test]
    fn invalid_depth_and_indexes_are_rejected() {
        for contents in [
            "[color]\ndepth = 23\n",
            "[color.ansi256]\nadd = { color = -1 }\n",
            "[color.ansi256]\nadd = { color = 256 }\n",
        ] {
            assert!(parse_config(contents, Path::new("/tmp/.jiffconfig")).is_err());
        }
    }

    #[test]
    fn old_palette_layout_is_rejected() {
        let error = parse_config(
            "[color]\nadd = { color = \"green\" }\n",
            Path::new("/tmp/.jiffconfig"),
        )
        .err()
        .expect("the old layout should be rejected");

        assert!(error.to_string().contains("unknown option color.add"));
    }

    #[test]
    fn xdg_config_precedes_the_home_dotfile() {
        let root = env::temp_dir();
        let home = root.join("home").join("kermit");
        let xdg_home = root.join("configs");
        let paths = config_candidates(Some(home.clone()), Some(xdg_home.clone()));

        assert_eq!(
            vec![
                xdg_home.join("jiff").join("config.toml"),
                home.join(".jiffconfig"),
            ],
            paths
        );
    }

    #[test]
    fn home_config_is_used_when_xdg_home_is_relative() {
        let home = env::temp_dir().join("home").join("fozzie");
        let paths = config_candidates(Some(home.clone()), Some(PathBuf::from("relative")));

        assert_eq!(
            vec![
                home.join(".config").join("jiff").join("config.toml"),
                home.join(".jiffconfig"),
            ],
            paths
        );
    }
}
