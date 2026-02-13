from typing import Iterator, List

class WrappedStrIter(Iterator):
    def __init__(self, s: str, wrap_at: int) -> None:
        self.s = s
        self.len = len(s)
        self.wrap_at = wrap_at
        self.cur_pos = 0
        self.output_once = False

    def __next__(self) -> str:
        if self.output_once and self.cur_pos >= self.len:
            raise StopIteration
        self.output_once = True
        start_pos = self.cur_pos
        self.cur_pos = min(self.cur_pos + self.wrap_at, self.len)
        return self.s[start_pos:self.cur_pos]


def wrap_str(s: str, width: int) -> WrappedStrIter:
    return WrappedStrIter(s, width)


class WrappedANSIStringsIter(Iterator):
    def __init__(self, s_ansi: List[str], wrap_at: int) -> None:
        self.s_ansi = s_ansi
        self.unstyled_len = sum(len(s) for s in s_ansi)  # unstyled length
        self.wrap_at = wrap_at
        self.cur_pos = 0
        self.output_once = False

    def __next__(self) -> str:
        if self.output_once and self.cur_pos >= self.unstyled_len:
            raise StopIteration
        self.output_once = True
        start_pos = self.cur_pos
        if self.unstyled_len <= self.wrap_at:
            self.cur_pos = self.unstyled_len
            padding_required = self.wrap_at - self.unstyled_len
            fmt = f"{''.join(self.s_ansi)}{''.join([' ' for _ in range(padding_required)])}"
            return fmt
        else:
            # For ANSI strings, we need a sublist of strings, and handle their length properly
            split_len = min(self.wrap_at, self.unstyled_len - start_pos)
            split = self.s_ansi[start_pos:start_pos + split_len]
            self.cur_pos += split_len
            padding_required = self.wrap_at - split_len
            fmt = f"{''.join(split)}{''.join([' ' for _ in range(padding_required)])}"
            return fmt


def wrap_ansistrings(s: List[str], width: int) -> WrappedANSIStringsIter:
    return WrappedANSIStringsIter(s, width)
