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
    s: &'s ANSIStrings<'u>,
    unstyled_len: usize,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
}

struct ANSIStringsSplit<'u> {
    split: Vec<ANSIString<'u>>,
}

impl<'u> fmt::Display for ANSIStringsSplit<'u> {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        let s = ANSIStrings(self.split.as_slice());
        return s.fmt(f);
    }
}

impl<'s, 'u> Iterator for WrappedANSIStringsIter<'s, 'u> where 'u: 's  {
    type Item = Box<dyn fmt::Display + 'u>;

    fn next(&mut self) -> Option<Box<dyn fmt::Display + 'u>> {
        if self.output_once && self.cur_pos >= self.unstyled_len {
            return None;
        }
        self.output_once = true;
        let start_pos = self.cur_pos;
        if self.unstyled_len <= self.wrap_at {
            self.cur_pos = self.unstyled_len;
            return Some(Box::new(self.s));
        } else {
            self.cur_pos = min(self.cur_pos + self.wrap_at, self.unstyled_len);
            let split = ansi_term::sub_string(start_pos, self.cur_pos, self.s);
            return Some(Box::new(ANSIStringsSplit{ split }));
        }
    }
}

pub fn wrap_ansistrings<'s, 'u>(s: &'s ANSIStrings<'u>, width: usize)
        -> WrappedANSIStringsIter<'s, 'u> where 'u: 's {
    WrappedANSIStringsIter {
        s: s,
        unstyled_len: ansi_term::unstyled_len(&s),
        wrap_at: width,
        cur_pos: 0,
        output_once: false,
    }
}
