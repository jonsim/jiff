from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import directory_diff
import syntax_highlighting
from jiff_config import ColorScheme, ConfigError, load_color_scheme
from rich.cells import cell_len
from rich.text import Text

import diff

DEFAULT_TERMINAL_SIZE = (80, 24)
TAB_WIDTH = 4


@dataclass(frozen=True)
class ComparisonPaths:
    """Two inputs and their optional repository-relative display path."""

    left: str
    right: str
    repository_path: str | None


@dataclass(frozen=True)
class ThreeWayPaths:
    """Three explicit inputs ordered as local, common base and remote."""

    left: str
    middle: str
    right: str


@dataclass(frozen=True)
class UnmergedPath:
    """One unresolved repository path supplied by Git."""

    repository_path: str


@dataclass(frozen=True)
class GitIndexStage:
    """An object and mode from one stage of Git's unmerged index."""

    mode: str
    object_id: str


class GitError(Exception):
    """Git could not provide a usable unmerged index entry."""


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


def _parse_input_paths(
    files: list[str], git_external_diff: bool, repository_path: str | None
) -> ComparisonPaths | ThreeWayPaths | UnmergedPath:
    if not git_external_diff:
        if len(files) == 2:
            return ComparisonPaths(files[0], files[1], repository_path)
        if len(files) == 3 and repository_path is None:
            return ThreeWayPaths(*files)
        if len(files) == 3:
            raise ValueError("--path cannot be used with a three-way comparison")
        raise ValueError("jiff expects two or three files, or two directories")

    # Keep Git's unusual positional protocol behind its explicit mode. The
    # seven-argument form supplies temporary files; the one-argument form
    # identifies an unresolved index entry which Jiff must read from Git.
    if len(files) == 1:
        return UnmergedPath(files[0])
    if len(files) == 7:
        return ComparisonPaths(files[1], files[4], files[0])
    raise ValueError("--git-external-diff expects one or seven arguments")


def _parse_unmerged_stages(
    output: bytes, repository_path: str
) -> tuple[GitIndexStage | None, GitIndexStage | None, GitIndexStage | None]:
    stages: list[GitIndexStage | None] = [None, None, None]
    for record in filter(None, output.split(b"\0")):
        metadata, separator, path = record.partition(b"\t")
        if not separator:
            raise GitError(
                f"Git returned a malformed unmerged entry for {repository_path}"
            )
        if path != os.fsencode(repository_path):
            raise GitError(
                f"Git returned an unexpected path while reading {repository_path}"
            )

        fields = metadata.split()
        if len(fields) != 3:
            raise GitError(
                f"Git returned a malformed unmerged entry for {repository_path}"
            )
        mode_bytes, object_id_bytes, stage_bytes = fields
        try:
            mode = mode_bytes.decode("ascii")
            object_id = object_id_bytes.decode("ascii")
            stage = int(stage_bytes)
        except (UnicodeDecodeError, ValueError) as error:
            raise GitError(
                f"Git returned an invalid mode, stage or object ID for {repository_path}"
            ) from error
        if stage not in (1, 2, 3):
            raise GitError(
                f"Git returned an invalid stage while reading {repository_path}"
            )
        if stages[stage - 1] is not None:
            raise GitError(
                f"Git returned stage {stage} more than once for {repository_path}"
            )
        stages[stage - 1] = GitIndexStage(mode, object_id)

    return stages[0], stages[1], stages[2]


def _run_git(arguments: list[str], action: str, repository_path: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        if not detail:
            detail = f"Git exited with status {result.returncode}"
        raise GitError(f"Could not {action} for {repository_path}: {detail}")
    return result.stdout


def _read_git_stage(stage: GitIndexStage | None, repository_path: str) -> str | bytes:
    if stage is None:
        # Add/add and modify/delete conflicts omit one or more index stages.
        # An empty input lets the ordinary three-way renderer show that side.
        return file_contents(b"")
    if stage.mode == "160000":
        return f"Subproject commit {stage.object_id}"
    return file_contents(
        _run_git(
            ["cat-file", "blob", stage.object_id],
            "read Git object",
            repository_path,
        )
    )


def _read_unmerged_inputs(repository_path: str) -> tuple[str | bytes, ...]:
    output = _run_git(
        [
            "--literal-pathspecs",
            "ls-files",
            "--unmerged",
            "--full-name",
            "-z",
            "--",
            repository_path,
        ],
        "read Git stages",
        repository_path,
    )
    stages = _parse_unmerged_stages(output, repository_path)
    if not any(stages):
        raise GitError(f"Git has no unmerged entries for {repository_path}")

    # Git names the common ancestor stage 1, ours stage 2 and theirs stage 3.
    # Jiff's three panes are Local, Base, Remote, hence the deliberate reorder.
    return tuple(_read_git_stage(stages[index], repository_path) for index in (1, 0, 2))


def file_labels(
    repository_path: str | None, left_path: str, right_path: str
) -> tuple[str, str]:
    if repository_path is not None:
        return f"a/{repository_path}", f"b/{repository_path}"
    return left_path, right_path


def render_output(
    left: str | bytes,
    right: str | bytes,
    left_path: str,
    right_path: str,
    *,
    repository_path: str | None,
    inline: bool,
    color: bool,
    colors: ColorScheme,
    context_lines: int | None = None,
    syntax: str | None = None,
    syntax_enabled: bool = True,
    terminal_width: int | None = None,
) -> str:
    """Renders one file comparison.

    Binary input produces a single status line because the text renderer cannot
    show useful line changes. ``repository_path`` adds Git-style headings and
    takes precedence over temporary filenames when detecting syntax.

    Args:
        left: Before-side text or undecoded binary content.
        right: After-side text or undecoded binary content.
        left_path: Filename used for labels and syntax detection.
        right_path: Filename used for labels and syntax detection.
        repository_path: Original Git path, or ``None`` for ordinary files.
        inline: Use unified output instead of the default two panes.
        color: Include ANSI colours in the output.
        colors: Styles used for diff and syntax highlighting.
        context_lines: Unchanged lines to retain around each change.
        syntax: Explicit lexer name, or ``None`` for detection.
        syntax_enabled: Whether to apply syntax highlighting.
        terminal_width: Explicit width for an embedded side-by-side preview.
    """
    left_label, right_label = file_labels(repository_path, left_path, right_path)

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
            left,
            right,
            left_path,
            right_path,
            repository_path,
            syntax,
            colors,
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


def render_three_way_output(
    left: str | bytes,
    middle: str | bytes,
    right: str | bytes,
    left_path: str,
    middle_path: str,
    right_path: str,
    *,
    inline: bool,
    color: bool,
    colors: ColorScheme,
    context_lines: int | None = None,
    syntax: str | None = None,
    syntax_enabled: bool = True,
    terminal_width: int | None = None,
    labels: tuple[str, str, str] | None = None,
) -> str:
    """Renders a comparison whose second input is the common base.

    Text uses three panes unless ``inline`` is selected. Inline and binary
    inputs fall back to labelled Local-to-Base and Base-to-Remote comparisons.

    Args:
        left: Local text or undecoded binary content.
        middle: Common-base text or undecoded binary content.
        right: Remote text or undecoded binary content.
        left_path: Local filename used for labels and syntax detection.
        middle_path: Base filename used for labels and syntax detection.
        right_path: Remote filename used for labels and syntax detection.
        inline: Use two labelled unified comparisons instead of three panes.
        color: Include ANSI colours in the output.
        colors: Styles used for diff and syntax highlighting.
        context_lines: Unchanged lines to retain around each change.
        syntax: Explicit lexer name, or ``None`` for detection.
        syntax_enabled: Whether to apply syntax highlighting.
        terminal_width: Explicit width for an embedded three-pane preview.
        labels: Explicit pane names, or ``None`` to use the filenames.
    """
    labels = labels or tuple(
        Path(path).name or path for path in (left_path, middle_path, right_path)
    )
    if (
        not inline
        and isinstance(left, str)
        and isinstance(middle, str)
        and isinstance(right, str)
    ):
        highlighting = (
            syntax_highlighting.HighlightedFile(),
            syntax_highlighting.HighlightedFile(),
            syntax_highlighting.HighlightedFile(),
        )
        if color and syntax_enabled:
            highlighting = tuple(
                syntax_highlighting.highlight_file(content, path, syntax, colors)
                for content, path in zip(
                    (left, middle, right),
                    (left_path, middle_path, right_path),
                    strict=True,
                )
            )
        return diff.render_three_way_side_by_side(
            (left, middle, right),
            labels,
            color,
            colors,
            highlighting,
            context_lines,
            terminal_width,
        )

    # Inline output and binary inputs remain two ordinary comparisons. There
    # is no useful three-pane representation for a binary-file status line.
    first = render_output(
        left,
        middle,
        left_path,
        middle_path,
        repository_path=None,
        inline=inline,
        color=color,
        colors=colors.without_additions(),
        context_lines=context_lines,
        syntax=syntax,
        syntax_enabled=syntax_enabled,
        terminal_width=terminal_width,
    )
    second = render_output(
        middle,
        right,
        middle_path,
        right_path,
        repository_path=None,
        inline=inline,
        color=color,
        colors=colors.without_removals(),
        context_lines=context_lines,
        syntax=syntax,
        syntax_enabled=syntax_enabled,
        terminal_width=terminal_width,
    )
    return (
        f"=== 1: {labels[0]} vs 2: {labels[1]} ===\n"
        f"{first}\n"
        f"=== 2: {labels[1]} vs 3: {labels[2]} ===\n"
        f"{second}"
    )


def render_directory_output(
    left_root: Path,
    right_root: Path,
    *,
    inline: bool,
    color: bool,
    colors: ColorScheme,
    context_lines: int | None = None,
    syntax: str | None = None,
    syntax_enabled: bool = True,
) -> str:
    """Renders all changed files from two directory trees as one diff.

    Directory entries retain repository-relative headings and are emitted in
    deterministic path order. Binary files use the same status-line fallback
    as an ordinary file comparison.
    """
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
                repository_path=relative_path,
                inline=inline,
                color=color,
                colors=colors,
                context_lines=context_lines,
                syntax=syntax,
                syntax_enabled=syntax_enabled,
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
        help="Files to compare",
    )
    args = parser.parse_args()

    if args.git_external_diff and args.path is not None:
        parser.error("--git-external-diff cannot be used with --path")
    try:
        input_paths = _parse_input_paths(
            args.files, args.git_external_diff, args.path or None
        )
    except ValueError as error:
        parser.error(str(error))
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

    # Git owns the terminal pager in external-diff mode. Otherwise decide at
    # the CLI boundary, before the explicit render API sees the final policy.
    color = not args.no_color and (
        args.git_external_diff
        or sys.stdout.isatty()
        or os.environ.get("RICH_FORCE_TERMINAL") is not None
    )
    try:
        if isinstance(input_paths, UnmergedPath):
            repository_path = input_paths.repository_path
            output = f"=== Unmerged: {repository_path} ===\n"
            output += render_three_way_output(
                *_read_unmerged_inputs(repository_path),
                repository_path,
                repository_path,
                repository_path,
                inline=args.inline,
                color=color,
                colors=colors,
                context_lines=args.unified,
                syntax=args.syntax,
                syntax_enabled=not args.no_syntax,
                labels=("Local", "Base", "Remote"),
            )
        elif isinstance(input_paths, ThreeWayPaths):
            paths = (input_paths.left, input_paths.middle, input_paths.right)
            if any(Path(path).is_dir() for path in paths):
                joined_paths = ", ".join(paths[:-1]) + f", and {paths[-1]}"
                print(
                    f"Could not compare {joined_paths}: three-way inputs must be files",
                    file=sys.stderr,
                )
                sys.exit(1)
            output = render_three_way_output(
                *(read_file(path) for path in paths),
                *paths,
                inline=args.inline,
                color=color,
                colors=colors,
                context_lines=args.unified,
                syntax=args.syntax,
                syntax_enabled=not args.no_syntax,
            )
        else:
            left_path = input_paths.left
            right_path = input_paths.right
            left_is_directory = Path(left_path).is_dir()
            right_is_directory = Path(right_path).is_dir()
            if left_is_directory != right_is_directory:
                print(
                    f"Could not compare {left_path} and {right_path}: both inputs must be "
                    "files or both directories",
                    file=sys.stderr,
                )
                sys.exit(1)
            if left_is_directory:
                output = render_directory_output(
                    Path(left_path),
                    Path(right_path),
                    inline=args.inline,
                    color=color,
                    colors=colors,
                    context_lines=args.unified,
                    syntax=args.syntax,
                    syntax_enabled=not args.no_syntax,
                )
            else:
                output = render_output(
                    read_file(left_path),
                    read_file(right_path),
                    left_path,
                    right_path,
                    repository_path=input_paths.repository_path,
                    inline=args.inline,
                    color=color,
                    colors=colors,
                    context_lines=args.unified,
                    syntax=args.syntax,
                    syntax_enabled=not args.no_syntax,
                )
    except GitError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
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
