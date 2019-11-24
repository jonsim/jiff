use std::cmp::min;
use std::iter::Iterator;

pub struct WrappedStrIter<'a> {
    s: &'a str,
    s_len: usize,
    wrap_at: usize,
    cur_pos: usize,
    output_once: bool,
}

impl<'a> Iterator for WrappedStrIter<'a> {
    type Item = &'a str;

    fn next(&mut self) -> Option<&'a str> {
        if self.output_once && self.cur_pos >= self.s_len {
            return None;
        }
        self.output_once = true;
        let start_pos = self.cur_pos;
        self.cur_pos = min(self.cur_pos + self.wrap_at, self.s_len);
        return Some(&self.s[start_pos..self.cur_pos]);
    }
}

pub fn wrap_str<'a>(s: &'a str, width: usize) -> WrappedStrIter<'a> {
    WrappedStrIter {
        s: s,
        s_len: s.len(),
        wrap_at: width,
        cur_pos: 0,
        output_once: false,
    }
}
