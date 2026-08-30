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
class HighlightedLine:
    """Syntax spans for one source line, using character offsets."""

    spans: tuple[Span, ...] = ()

    def render(
        self,
        content: str,
        base_style: Style,
        overrides: Sequence[Span] = (),
    ) -> Text:
        """Combines syntax foregrounds with the diff style for this line."""
        rendered = Text(content, style=base_style)
        for span in overrides:
            rendered.stylize(span.style, span.start, span.end)
        for span in self.spans:
            rendered.stylize(span.style, span.start, span.end)
        return rendered


@dataclass(frozen=True)
class HighlightedFile:
    """Syntax spans for a source file, retained in source-line order."""

    lines: tuple[HighlightedLine, ...] = ()

    def render_line(
        self,
        index: int,
        content: str,
        base_style: Style,
        overrides: Sequence[Span] = (),
    ) -> Text:
        """Styles a source line, falling back to its diff style when absent."""
        if index >= len(self.lines):
            rendered = Text(content, style=base_style)
            for span in overrides:
                rendered.stylize(span.style, span.start, span.end)
        else:
            rendered = self.lines[index].render(content, base_style, overrides)
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
    repository_path: str | None,
    syntax: str | None,
    colors: ColorScheme,
) -> HighlightedFiles:
    """Highlights both source files using an explicit or detected lexer.

    Args:
        left: Source text from the before side of the diff.
        right: Source text from the after side of the diff.
        left_path: Filename used to detect the left language.
        right_path: Filename used to detect the right language.
        repository_path: Original Git path, when comparing temporary files.
        syntax: Explicit Pygments lexer name, or ``None`` for detection.
        colors: Configured styles for each syntax token category.

    Raises:
        UnknownSyntaxError: The explicitly requested lexer is unknown.
    """
    if repository_path is not None:
        left_path = repository_path
        right_path = repository_path

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

    lines: list[list[Span]] = [[]]
    column = 0
    for _, token_type, value in lexer.get_tokens_unprocessed(content):
        style = _style_for_token(token_type, colors)
        parts = value.split("\n")
        for index, part in enumerate(parts):
            if part and style is not None:
                lines[-1].append(Span(column, column + len(part), style))
            column += len(part)
            if index + 1 < len(parts):
                lines.append([])
                column = 0

    if not content:
        return HighlightedFile()
    return HighlightedFile(tuple(HighlightedLine(tuple(spans)) for spans in lines))


def _style_for_token(token_type, colors: ColorScheme) -> Style | None:
    if token_type in Comment:
        return _syntax_style(colors.syntax_comment)
    if token_type in Keyword:
        return _syntax_style(colors.syntax_keyword)
    if token_type in String:
        return _syntax_style(colors.syntax_string)
    if token_type in Number:
        return _syntax_style(colors.syntax_number)
    if (
        token_type in Name.Class
        or token_type in Name.Function
        or token_type in Name.Decorator
    ):
        return _syntax_style(colors.syntax_definition)
    return None


def _syntax_style(style: ColorStyle) -> Style:
    # A missing bold flag should leave the diff style alone. Rich treats that
    # differently from explicitly turning bold off for every token.
    return Style(color=style.color or "default", bold=True if style.bold else None)
