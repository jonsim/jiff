use std::cmp::min;
use std::iter::Iterator;
use ansi_term::{ANSIString, ANSIStrings};
use std::fmt;

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

pub struct WrappedANSIStringsIter<'u, 's> where 'u: 's  {
    s: &'s Vec<ANSIString<'u>>,
    s_ansi: ANSIStrings<'u>,
    unstyled_len: usize,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
}

impl<'s, 'u> Iterator for WrappedANSIStringsIter<'s, 'u> where 'u: 's  {
    type Item = String;

    fn next(&mut self) -> Option<String> {
        if self.output_once && self.cur_pos >= self.unstyled_len {
            return None;
        }
        self.output_once = true;
        let start_pos = self.cur_pos;
        if self.unstyled_len <= self.wrap_at {
            self.cur_pos = self.unstyled_len;
            let padding_required = self.wrap_at - self.unstyled_len;
            let fmt = format!("{}{:w$}", self.s_ansi, "", w=padding_required);
            return Some(fmt);
        } else {
            self.cur_pos = min(self.cur_pos + self.wrap_at, self.unstyled_len);
            let split = ansi_term::sub_string(start_pos, self.cur_pos, &self.s_ansi);
            let ansi = ANSIStrings(split.as_slice());
            let padding_required = self.wrap_at - ansi_term::unstyled_len(&ansi);
            let fmt = format!("{}{:w$}", ansi, "", w=padding_required);
            return Some(fmt);
        }
    }
}

pub fn wrap_ansistrings<'s, 'u>(s: &'s Vec<ANSIString<'u>>, width: usize)
        -> WrappedANSIStringsIter<'s, 'u> where 'u: 's {
    WrappedANSIStringsIter {
        s: s,
        s_ansi: ANSIStrings(s.as_slice()),
        unstyled_len: ansi_term::unstyled_len(&ANSIStrings(s.as_slice())),
        wrap_at: width,
        cur_pos: 0,
        output_once: false,
    }
}
