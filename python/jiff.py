from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import directory_diff
import syntax_highlighting
from jiff_config import ColorScheme, ConfigError, load_color_scheme
from rich.cells import cell_len
from rich.text import Text

import diff

DEFAULT_TERMINAL_SIZE = (80, 24)
TAB_WIDTH = 4


def file_contents(content: bytes) -> str | bytes:
    """Decodes text input while retaining binary content as bytes."""
    if b"\0" in content:
        return content
    try:
        return content.decode("utf-8").removesuffix("\n")
    except UnicodeDecodeError:
        return content


def read_file(path: str | Path) -> str | bytes:
    with open(path, "rb") as file:
        content = file.read()

    # A NUL is the conventional cheap binary-file check. Invalid UTF-8 is
    # binary too because the diff algorithms operate on Unicode text.
    return file_contents(content)


def line_count(content: str) -> int:
    if not content:
        return 0
    return content.count("\n") + 1


def file_labels(repository_path: str | None, lpath: str, rpath: str) -> tuple[str, str]:
    if repository_path is not None:
        return f"a/{repository_path}", f"b/{repository_path}"
    return lpath, rpath


def render_output(
    left: str | bytes,
    right: str | bytes,
    lpath: str,
    rpath: str,
    repository_path: str | None,
    inline: bool,
    color: bool,
    colors: ColorScheme,
    context_lines: int | None = None,
    syntax: str | None = None,
    syntax_enabled: bool = True,
    terminal_width: int | None = None,
) -> str:
    left_label, right_label = file_labels(repository_path, lpath, rpath)

    if isinstance(left, bytes) or isinstance(right, bytes):
        relationship = (
            "are identical"
            if isinstance(left, bytes) and isinstance(right, bytes) and left == right
            else "differ"
        )
        return f"Binary files {left_label} and {right_label} {relationship}\n"

    output = ""
    if repository_path is not None:
        output += diff.render_file_header(repository_path, color, colors)

    highlighting = syntax_highlighting.HighlightedFiles()
    if color and syntax_enabled:
        highlighting = syntax_highlighting.highlight_files(
            left, right, lpath, rpath, repository_path, syntax, colors
        )

    diffs = diff.calculate_line_diff(left, right)
    if context_lines is not None:
        diffs = diff.limit_context(diffs, context_lines)
    if inline:
        output += diff.render_diffs(diffs, color, colors, highlighting)
    else:
        max_line_count = max(line_count(left), line_count(right))
        output += diff.render_diffs_side_by_side(
            diffs, max_line_count, color, colors, highlighting, terminal_width
        )
    return output


def render_directory_output(
    left_root: Path,
    right_root: Path,
    inline: bool,
    color: bool,
    colors: ColorScheme,
    context_lines: int | None = None,
    syntax: str | None = None,
    syntax_enabled: bool = True,
) -> str:
    """Renders all changed files from two directory trees as one diff."""
    output = []
    for directory_entry in directory_diff.directory_diffs(left_root, right_root):
        relative_path = directory_entry.relative_path.as_posix()
        left_path = left_root / directory_entry.relative_path
        right_path = right_root / directory_entry.relative_path
        output.append(
            render_output(
                file_contents(directory_entry.left or b""),
                file_contents(directory_entry.right or b""),
                str(left_path),
                str(right_path),
                relative_path,
                inline,
                color,
                colors,
                context_lines,
                syntax,
                syntax_enabled,
            )
        )
    return "".join(output)


def _display_width(line: str) -> int:
    width = 0
    parts = line.split("\t")
    for index, part in enumerate(parts):
        width += cell_len(part)
        if index < len(parts) - 1:
            width += TAB_WIDTH - width % TAB_WIDTH
    return width


def _output_height(output: str, terminal_width: int) -> int:
    plain = Text.from_ansi(output).plain
    return sum(
        max(1, (_display_width(line) - 1) // terminal_width + 1)
        for line in plain.splitlines()
    )


def _should_page(
    output: str,
    no_pager: bool,
    is_terminal: bool,
    terminal_size: tuple[int, int],
) -> bool:
    if no_pager or not is_terminal:
        return False

    width, height = terminal_size
    return _output_height(output, max(width, 1)) > max(height, 1)


def _run_pager(output: str) -> None:
    pager = os.environ.get("PAGER", "").strip() or "less"
    environment = os.environ.copy()
    environment.setdefault("LESS", "FRX")

    # PAGER is conventionally a shell command rather than a single executable,
    # so values such as "less -S" need shell parsing here.
    result = subprocess.run(
        pager,
        input=output,
        text=True,
        shell=True,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pager exited with status {result.returncode}")


def _display(output: str, no_pager: bool) -> None:
    terminal_size = shutil.get_terminal_size(DEFAULT_TERMINAL_SIZE)
    if _should_page(
        output,
        no_pager,
        sys.stdout.isatty(),
        (terminal_size.columns, terminal_size.lines),
    ):
        _run_pager(output)
    else:
        try:
            sys.stdout.write(output)
            sys.stdout.flush()
        except BrokenPipeError:
            # A downstream command such as `head` may deliberately stop
            # reading early. Redirect the final interpreter flush too.
            # This deliberately stays open until interpreter shutdown.
            sys.stdout = open(os.devnull, "w")  # noqa: SIM115


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "context must be a non-negative integer"
        ) from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("context must be a non-negative integer")
    return parsed


def run():
    parser = argparse.ArgumentParser(description="Colored diff tool")
    parser.add_argument(
        "--path",
        metavar="PATH",
        help="Display Git-style headings for a repository path",
    )
    parser.add_argument(
        "--git-external-diff",
        action="store_true",
        help="Parse arguments supplied by Git's external diff protocol",
    )
    parser.add_argument(
        "-i", "--inline", action="store_true", help="Display the diff inline"
    )
    parser.add_argument(
        "-U",
        "--unified",
        metavar="n",
        type=_non_negative_int,
        help="Show n lines of context around each change",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disables colorization of the output"
    )
    parser.add_argument(
        "--no-pager", action="store_true", help="Disables paging of long output"
    )
    syntax = parser.add_mutually_exclusive_group()
    syntax.add_argument(
        "--syntax",
        metavar="LANGUAGE",
        help="Use LANGUAGE for syntax highlighting instead of detecting it",
    )
    syntax.add_argument(
        "--no-syntax",
        action="store_true",
        help="Disables syntax highlighting",
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="Files to compare, or arguments supplied by Git",
    )
    args = parser.parse_args()

    if args.git_external_diff and args.path is not None:
        parser.error("--git-external-diff cannot be used with --path")
    if args.git_external_diff and len(args.files) == 1:
        print(f"Unmerged file: {args.files[0]}")
        return
    if args.git_external_diff:
        if len(args.files) != 7:
            parser.error("--git-external-diff expects one or seven arguments")
        repository_path = args.files[0]
        lpath = args.files[1]
        rpath = args.files[4]
    else:
        if len(args.files) != 2:
            parser.error("jiff expects two files or directories")
        lpath, rpath = args.files
        repository_path = args.path or None

    try:
        syntax_highlighting.validate_syntax(args.syntax)
    except syntax_highlighting.UnknownSyntaxError as error:
        print(f"Could not highlight diff: {error}", file=sys.stderr)
        sys.exit(1)

    try:
        colors = load_color_scheme()
    except ConfigError as error:
        print(f"Could not load config: {error}", file=sys.stderr)
        sys.exit(1)

    color = not args.no_color
    if args.git_external_diff and color:
        diff.force_terminal_colors()
    left_is_directory = Path(lpath).is_dir()
    right_is_directory = Path(rpath).is_dir()
    if left_is_directory != right_is_directory:
        print(
            f"Could not compare {lpath} and {rpath}: both inputs must be files "
            "or both directories",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        if left_is_directory:
            output = render_directory_output(
                Path(lpath),
                Path(rpath),
                args.inline,
                color,
                colors,
                args.unified,
                args.syntax,
                not args.no_syntax,
            )
        else:
            output = render_output(
                read_file(lpath),
                read_file(rpath),
                lpath,
                rpath,
                repository_path,
                args.inline,
                color,
                colors,
                args.unified,
                args.syntax,
                not args.no_syntax,
            )
    except OSError as error:
        print(f"Could not read input: {error}", file=sys.stderr)
        sys.exit(1)
    except syntax_highlighting.UnknownSyntaxError as error:
        print(f"Could not highlight diff: {error}", file=sys.stderr)
        sys.exit(1)

    try:
        _display(output, args.no_pager or args.git_external_diff)
    except (OSError, RuntimeError) as error:
        print(f"Could not display diff: {error}", file=sys.stderr)
        sys.exit(1)


def main():
    try:
        run()
    except KeyboardInterrupt:
        # Match ordinary Unix command behaviour without printing a traceback.
        sys.exit(130)


if __name__ == "__main__":
    main()
