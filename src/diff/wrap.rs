use std::cmp::min;
use std::iter::Iterator;
use ansi_term::{ANSIString, ANSIStrings};

pub struct WrappedStrIter<'a> {
    s: &'a str,
    len: usize,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
}

impl<'a> Iterator for WrappedStrIter<'a> {
    type Item = &'a str;

    fn next(&mut self) -> Option<&'a str> {
        if self.output_once && self.cur_pos >= self.len {
            return None;
        }
        self.output_once = true;
        let start_pos = self.cur_pos;
        self.cur_pos = min(self.cur_pos + self.wrap_at, self.len);
        return Some(&self.s[start_pos..self.cur_pos]);
    }
}

pub fn wrap_str<'a>(s: &'a str, width: usize) -> WrappedStrIter<'a> {
    WrappedStrIter {
        s: s,
        len: s.len(),
        wrap_at: width,
        cur_pos: 0,
        output_once: false,
    }
}

pub struct WrappedANSIStringsIter<'u> {
    s_ansi: ANSIStrings<'u>,
    unstyled_len: usize,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
    pad: bool,
}

impl<'s, 'u> Iterator for WrappedANSIStringsIter<'u> where 'u: 's  {
    type Item = String;

    fn next(&mut self) -> Option<String> {
        if self.output_once && self.cur_pos >= self.unstyled_len {
            return None;
        }
        self.output_once = true;
        let start_pos = self.cur_pos;
        if self.unstyled_len <= self.wrap_at {
            self.cur_pos = self.unstyled_len;
            let padding_required = if self.pad { self.wrap_at - self.unstyled_len } else { 0 };
            let fmt = format!("{}{:w$}", self.s_ansi, "", w=padding_required);
            return Some(fmt);
        } else {
            let split = ansi_term::sub_string(start_pos, self.wrap_at, &self.s_ansi);
            let split_fmt = ANSIStrings(split.as_slice());
            let split_len = ansi_term::unstyled_len(&split_fmt);
            self.cur_pos += split_len;
            let padding_required = if self.pad { self.wrap_at - split_len } else { 0 };
            let fmt = format!("{}{:w$}", split_fmt, "", w=padding_required);
            return Some(fmt);
        }
    }
}

pub fn wrap_ansistrings<'s, 'u>(s: &'s Vec<ANSIString<'u>>, width: usize, pad: bool)
        -> WrappedANSIStringsIter<'s> where 'u: 's {
    WrappedANSIStringsIter {
        s_ansi: ANSIStrings(s.as_slice()),
        unstyled_len: ansi_term::unstyled_len(&ANSIStrings(s.as_slice())),
        wrap_at: width,
        cur_pos: 0,
        output_once: false,
        pad: pad,
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    use ansi_term::Color::{Red, Green};

    #[test]
    fn wrap_str_empty() {
        let s = "";
        let wrapped: Vec<&str> = wrap_str(&s, 0).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!("", wrapped[0]);
    }

    #[test]
    fn wrap_str_single_line_under() {
        let s = "hello";
        let wrapped: Vec<&str> = wrap_str(&s, 10).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!("hello", wrapped[0]);
    }

    #[test]
    fn wrap_str_single_line_exact() {
        let s = "hello";
        let wrapped: Vec<&str> = wrap_str(&s, 5).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!("hello", wrapped[0]);
    }

    #[test]
    fn wrap_str_multi_line_under() {
        let s = "hello world";
        let wrapped: Vec<&str> = wrap_str(&s, 6).collect();
        assert_eq!(2, wrapped.len());
        assert_eq!("hello ", wrapped[0]);
        assert_eq!("world", wrapped[1]);
    }

    #[test]
    fn wrap_str_multi_line_exact() {
        let s = "hello";
        let wrapped: Vec<&str> = wrap_str(&s, 1).collect();
        assert_eq!(5, wrapped.len());
        assert_eq!("h", wrapped[0]);
        assert_eq!("e", wrapped[1]);
        assert_eq!("l", wrapped[2]);
        assert_eq!("l", wrapped[3]);
        assert_eq!("o", wrapped[4]);
    }

    #[test]
    fn wrap_ansi_empty() {
        let s = vec![Red.paint("")];
        let s_fmt = vec![format!("{}", ANSIStrings(&s))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 0).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_single_line_under() {
        let s = vec![Red.paint("hel"), Red.paint("lo")];
        let s_fmt = vec![format!("{}     ", ANSIStrings(&s))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 10).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_single_line_exact() {
        let s = vec![Red.paint("hel"), Green.paint("lo")];
        let s_fmt = vec![format!("{}", ANSIStrings(&s))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 5).collect();
        assert_eq!(1, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_multi_line_under() {
        let s = vec![Red.paint("hello "), Green.paint("world")];
        let s_fmt = vec![format!("{}", s[0]), format!("{} ", s[1])];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 6).collect();
        assert_eq!(2, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }

    #[test]
    fn wrap_ansi_multi_line_exact() {
        let s = vec![Red.paint("hello")];
        let s_fmt = vec![format!("{}", Red.paint("h")),
                         format!("{}", Red.paint("e")),
                         format!("{}", Red.paint("l")),
                         format!("{}", Red.paint("l")),
                         format!("{}", Red.paint("o"))];
        let wrapped: Vec<String> = wrap_ansistrings(&s, 1).collect();
        assert_eq!(5, wrapped.len());
        assert_eq!(s_fmt, wrapped);
    }
}