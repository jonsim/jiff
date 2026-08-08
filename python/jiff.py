import argparse
import os
import shutil
import subprocess
import sys

from rich.cells import cell_len
from rich.text import Text

import diff

DEFAULT_TERMINAL_SIZE = (80, 24)
TAB_WIDTH = 4


def read_file_or_die(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
            content = content.removesuffix("\n")
            return content
    except (OSError, UnicodeError) as error:
        print(f"Could not read {path}: {error}", file=sys.stderr)
        sys.exit(1)


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
        sys.stdout.write(output)


def main():
    parser = argparse.ArgumentParser(description="Colored diff tool")
    parser.add_argument(
        "-g", "--git-diff", action="store_true", help="Enable git diff mode"
    )
    parser.add_argument(
        "-i", "--inline", action="store_true", help="Display the diff inline"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disables colorization of the output"
    )
    parser.add_argument(
        "--no-pager", action="store_true", help="Disables paging of long output"
    )
    parser.add_argument("file1", help="Left file")
    parser.add_argument("file2", help="Right file")
    args = parser.parse_args()

    lpath = args.file1
    rpath = args.file2
    lfile = read_file_or_die(lpath)
    rfile = read_file_or_die(rpath)

    max_line_count = max(lfile.count("\n"), rfile.count("\n"))

    diffs = diff.calculate_line_diff(lfile, rfile)

    color = not args.no_color
    if args.inline:
        output = diff.render_diffs(diffs, color)
    else:
        output = diff.render_diffs_side_by_side(diffs, max_line_count, color)

    try:
        _display(output, args.no_pager)
    except (OSError, RuntimeError) as error:
        print(f"Could not display diff: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
