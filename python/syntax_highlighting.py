from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jiff_config import ColorScheme, ColorStyle
from pygments.lexers import get_lexer_by_name, get_lexer_for_filename
from pygments.token import Comment, Keyword, Name, Number, String
from pygments.util import ClassNotFound
from rich.style import Style
from rich.text import Span, Text

TAB_WIDTH = 4


class UnknownSyntaxError(ValueError):
    """The explicitly requested Pygments lexer does not exist."""


@dataclass(frozen=True)
class SyntaxSpan:
    """A range of characters with its normal and highlighted syntax styles."""

    start: int
    end: int
    style: Style
    highlight_style: Style


@dataclass(frozen=True)
class HighlightedLine:
    """Syntax spans for one source line, using character offsets."""

    spans: tuple[SyntaxSpan, ...] = ()

    def render(
        self,
        content: str,
        base_style: Style,
        overrides: Sequence[Span] = (),
        highlight_styles: tuple[Style, ...] = (),
    ) -> Text:
        """Combines syntax foregrounds with the diff style for this line."""
        if not content:
            return Text(content, style=base_style)

        boundaries = [0, len(content)]
        for span in self.spans:
            boundaries.append(min(span.start, len(content)))
            boundaries.append(min(span.end, len(content)))
        for span in overrides:
            boundaries.append(min(span.start, len(content)))
            boundaries.append(min(span.end, len(content)))
        boundaries = sorted(set(boundaries))

        syntax_iter = iter(self.spans)
        current_syntax = next(syntax_iter, None)

        override_iter = iter(overrides)
        current_override = next(override_iter, None)

        rendered = Text()
        for start, end in zip(boundaries, boundaries[1:]):
            if start == end:
                continue

            style = base_style
            is_highlight = base_style in highlight_styles

            while current_override is not None and current_override.end <= start:
                current_override = next(override_iter, None)
            if (
                current_override is not None
                and current_override.start <= start < current_override.end
            ):
                style = current_override.style
                is_highlight = True

            while current_syntax is not None and current_syntax.end <= start:
                current_syntax = next(syntax_iter, None)
            if (
                current_syntax is not None
                and current_syntax.start <= start < current_syntax.end
            ):
                syntax = (
                    current_syntax.highlight_style
                    if is_highlight
                    else current_syntax.style
                )
                bold = (
                    style.bold if syntax.bold is None else (style.bold or syntax.bold)
                )
                italic = (
                    style.italic
                    if syntax.italic is None
                    else (style.italic or syntax.italic)
                )
                style = Style(
                    color=syntax.color,
                    bgcolor=style.bgcolor,
                    bold=bold,
                    italic=italic,
                )

            rendered.append(content[start:end], style)

        return rendered


@dataclass(frozen=True)
class HighlightedFile:
    """Syntax spans for a source file, retained in source-line order."""

    lines: tuple[HighlightedLine, ...] = ()
    highlight_styles: tuple[Style, ...] = ()

    def render_line(
        self,
        index: int,
        content: str,
        base_style: Style,
        overrides: Sequence[Span] = (),
    ) -> Text:
        """Styles a source line, falling back to its diff style when absent."""
        if index >= len(self.lines):
            line = HighlightedLine()
        else:
            line = self.lines[index]
        rendered = line.render(content, base_style, overrides, self.highlight_styles)
        # Expand tabs before margins are added. Otherwise Rich uses eight-column
        # tabs, and the same source line shifts between output modes.
        rendered.expand_tabs(TAB_WIDTH)
        return rendered


@dataclass(frozen=True)
class HighlightedFiles:
    """Syntax highlighting for the before and after sides of a diff."""

    left: HighlightedFile = HighlightedFile()
    right: HighlightedFile = HighlightedFile()


def validate_syntax(syntax: str | None) -> None:
    """Checks an explicit lexer name even when colour output is disabled."""
    if syntax is None or syntax.lower() == "auto":
        return
    try:
        get_lexer_by_name(syntax)
    except ClassNotFound as error:
        raise UnknownSyntaxError(f"unknown syntax {syntax!r}") from error


def highlight_files(
    left: str,
    right: str,
    left_path: str,
    right_path: str,
    repository_paths: tuple[str, str] | None,
    syntax: str | None,
    colors: ColorScheme,
) -> HighlightedFiles:
    """Highlights both source files using an explicit or detected lexer.

    Args:
        left: Source text from the before side of the diff.
        right: Source text from the after side of the diff.
        left_path: Filename used to detect the left language.
        right_path: Filename used to detect the right language.
        repository_paths: Original Git paths, when comparing temporary files.
        syntax: Explicit Pygments lexer name, or ``None`` for detection.
        colors: Configured styles for each syntax token category.

    Raises:
        UnknownSyntaxError: The explicitly requested lexer is unknown.
    """
    if repository_paths is not None:
        left_path, right_path = repository_paths

    return HighlightedFiles(
        left=highlight_file(left, left_path, syntax, colors),
        right=highlight_file(right, right_path, syntax, colors),
    )


def highlight_file(
    content: str,
    path: str,
    syntax: str | None,
    colors: ColorScheme,
) -> HighlightedFile:
    """Highlights one source file using an explicit or detected lexer."""
    try:
        if syntax is None or syntax.lower() == "auto":
            lexer = get_lexer_for_filename(path, content)
        else:
            lexer = get_lexer_by_name(syntax)
    except ClassNotFound as error:
        if syntax is not None and syntax.lower() != "auto":
            raise UnknownSyntaxError(f"unknown syntax {syntax!r}") from error
        return HighlightedFile()

    lines: list[list[SyntaxSpan]] = [[]]
    column = 0
    for _, token_type, value in lexer.get_tokens_unprocessed(content):
        styles = _style_for_token(token_type, colors)
        parts = value.split("\n")
        for index, part in enumerate(parts):
            if part and styles is not None:
                lines[-1].append(
                    SyntaxSpan(column, column + len(part), styles[0], styles[1])
                )
            column += len(part)
            if index + 1 < len(parts):
                lines.append([])
                column = 0

    if not content:
        return HighlightedFile()
    highlight_styles = (
        colors.add_highlight.rich_style(),
        colors.remove_highlight.rich_style(),
        colors.overlap_highlight.rich_style(),
    )
    return HighlightedFile(
        tuple(HighlightedLine(tuple(spans)) for spans in lines),
        highlight_styles,
    )


def _style_for_token(token_type, colors: ColorScheme) -> tuple[Style, Style] | None:
    if token_type in Comment:
        return (
            _syntax_style(colors.syntax_comment),
            _syntax_style(colors.syntax_comment_highlight),
        )
    if token_type in Keyword:
        return (
            _syntax_style(colors.syntax_keyword),
            _syntax_style(colors.syntax_keyword_highlight),
        )
    if token_type in String:
        return (
            _syntax_style(colors.syntax_string),
            _syntax_style(colors.syntax_string_highlight),
        )
    if token_type in Number:
        return (
            _syntax_style(colors.syntax_number),
            _syntax_style(colors.syntax_number_highlight),
        )
    if (
        token_type in Name.Class
        or token_type in Name.Function
        or token_type in Name.Decorator
    ):
        return (
            _syntax_style(colors.syntax_definition),
            _syntax_style(colors.syntax_definition_highlight),
        )
    return None


def _syntax_style(style: ColorStyle) -> Style:
    # Missing attributes should leave the diff style alone. Rich treats that
    # differently from explicitly turning them off for every token.
    color = style.rich_style().color or "default"
    return Style(
        color=color,
        bold=True if style.bold else None,
        italic=True if style.italic else None,
    )
