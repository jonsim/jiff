use ansi_term::{ANSIString, ANSIStrings};
use std::iter::Iterator;
use unicode_width::UnicodeWidthChar;

fn split_at_width(s: &str, width: usize) -> (usize, usize) {
    let mut byte_len = 0;
    let mut display_width = 0;
    for character in s.chars() {
        let character_width = character.width().unwrap_or(0);
        if byte_len > 0 && display_width + character_width > width {
            break;
        }

        // A double-width character still has to be consumed in a one-column
        // terminal, otherwise the iterator can never make progress.
        byte_len += character.len_utf8();
        display_width += character_width;
        if display_width > width {
            break;
        }
    }

    (byte_len, display_width)
}

#[cfg(test)]
pub struct WrappedStrIter<'a> {
    s: &'a str,
    len: usize,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
}

#[cfg(test)]
impl<'a> Iterator for WrappedStrIter<'a> {
    type Item = &'a str;

    fn next(&mut self) -> Option<&'a str> {
        if self.output_once && self.cur_pos >= self.len {
            return None;
        }
        self.output_once = true;
        let start_pos = self.cur_pos;
        let (byte_len, _) = split_at_width(&self.s[start_pos..], self.wrap_at);
        self.cur_pos += byte_len;
        Some(&self.s[start_pos..self.cur_pos])
    }
}

#[cfg(test)]
pub fn wrap_str(s: &str, width: usize) -> WrappedStrIter<'_> {
    WrappedStrIter {
        s,
        len: s.len(),
        wrap_at: if s.is_empty() { width } else { width.max(1) },
        cur_pos: 0,
        output_once: false,
    }
}

pub struct WrappedANSIStringsIter<'u> {
    s_ansi: ANSIStrings<'u>,
    unstyled: String,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
    pad: bool,
}

impl<'u> Iterator for WrappedANSIStringsIter<'u> {
    type Item = String;

    fn next(&mut self) -> Option<String> {
        if self.output_once && self.cur_pos >= self.unstyled.len() {
            return None;
        }
        self.output_once = true;

        if self.unstyled.is_empty() {
            let padding_required = if self.pad { self.wrap_at } else { 0 };
            return Some(format!("{}{:w$}", self.s_ansi, "", w = padding_required));
        }

        let start_pos = self.cur_pos;
        let (byte_len, display_width) = split_at_width(&self.unstyled[start_pos..], self.wrap_at);
        self.cur_pos += byte_len;

        let split = ansi_term::sub_string(start_pos, byte_len, &self.s_ansi);
        let split_fmt = ANSIStrings(split.as_slice());
        let padding_required = if self.pad {
            self.wrap_at.saturating_sub(display_width)
        } else {
            0
        };
        Some(format!("{}{:w$}", split_fmt, "", w = padding_required))
    }
}

pub fn wrap_ansistrings<'s, 'u>(
    s: &'s [ANSIString<'u>],
    width: usize,
    pad: bool,
) -> WrappedANSIStringsIter<'s>
where
    'u: 's,
{
    let unstyled = ansi_term::unstyle(&ANSIStrings(s));
    let wrap_at = if unstyled.is_empty() {
        width
    } else {
        width.max(1)
    };
    WrappedANSIStringsIter {
        s_ansi: ANSIStrings(s),
        unstyled,
        // A zero-width terminal is not useful, but it can be reported while a
        // terminal is being resized. Advancing one column avoids looping forever.
        wrap_at,
        cur_pos: 0,
        output_once: false,
        pad,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ansi_term::Color::{Green, Red};

    #[test]
    fn wrap_str_empty() {
        let s = "";
        let wrapped: Vec<&str> = wrap_str(s, 0).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!("", wrapped[0]);
    }

    #[test]
    fn wrap_str_nonempty_at_zero_width() {
        // A transient zero-width terminal must still make forward progress.
        let wrapped: Vec<&str> = wrap_str("hi", 0).collect();

        assert_eq!(vec!["h", "i"], wrapped);
    }

    #[test]
    fn wrap_str_single_line_under() {
        let s = "hello";
        let wrapped: Vec<&str> = wrap_str(s, 10).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!("hello", wrapped[0]);
    }

    #[test]
    fn wrap_str_single_line_exact() {
        let s = "hello";
        let wrapped: Vec<&str> = wrap_str(s, 5).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!("hello", wrapped[0]);
    }

    #[test]
    fn wrap_str_multi_line_under() {
        let s = "hello world";
        let wrapped: Vec<&str> = wrap_str(s, 6).collect();
        assert_eq!(2, wrapped.len());
        assert_eq!("hello ", wrapped[0]);
        assert_eq!("world", wrapped[1]);
    }

    #[test]
    fn wrap_str_multi_line_exact() {
        let s = "hello";
        let wrapped: Vec<&str> = wrap_str(s, 1).collect();
        assert_eq!(5, wrapped.len());
        assert_eq!("h", wrapped[0]);
        assert_eq!("e", wrapped[1]);
        assert_eq!("l", wrapped[2]);
        assert_eq!("l", wrapped[3]);
        assert_eq!("o", wrapped[4]);
    }

    #[test]
    fn wrap_str_uses_unicode_display_width() {
        // The accent is one column and the emoji is two, despite their UTF-8 sizes.
        let wrapped: Vec<&str> = wrap_str("é🙂a", 2).collect();

        assert_eq!(vec!["é", "🙂", "a"], wrapped);
    }

    #[test]
    fn wrap_ansi_empty() {
        let s = vec![Red.paint("")];
        let s_fmt = vec![format!("{}", ANSIStrings(&s))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 0, true).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_nonempty_at_zero_width() {
        // ANSI wrapping uses the same one-column fallback as plain text.
        let s = vec![Red.paint("hi")];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 0, false).collect();

        assert_eq!(
            vec![format!("{}", Red.paint("h")), format!("{}", Red.paint("i"))],
            wrapped
        );
    }

    #[test]
    fn wrap_ansi_single_line_under() {
        let s = vec![Red.paint("hel"), Red.paint("lo")];
        let s_fmt = vec![format!("{}     ", ANSIStrings(&s))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 10, true).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_single_line_exact() {
        let s = vec![Red.paint("hel"), Green.paint("lo")];
        let s_fmt = vec![format!("{}", ANSIStrings(&s))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 5, true).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_multi_line_under() {
        let s = vec![Red.paint("hello "), Green.paint("world")];
        let s_fmt = vec![format!("{}", s[0]), format!("{} ", s[1])];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 6, true).collect();
        assert_eq!(2, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_multi_line_exact() {
        let s = vec![Red.paint("hello")];
        let s_fmt = vec![
            format!("{}", Red.paint("h")),
            format!("{}", Red.paint("e")),
            format!("{}", Red.paint("l")),
            format!("{}", Red.paint("l")),
            format!("{}", Red.paint("o")),
        ];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 1, true).collect();
        assert_eq!(5, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_uses_unicode_display_width() {
        // Wrapping must preserve styles while splitting at UTF-8 boundaries.
        let s = vec![Red.paint("é"), Green.paint("🙂a")];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 2, true).collect();

        assert_eq!(
            vec![
                format!("{} ", Red.paint("é")),
                format!("{}", Green.paint("🙂")),
                format!("{} ", Green.paint("a")),
            ],
            wrapped
        );
    }
}
