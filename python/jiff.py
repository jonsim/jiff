import argparse
import sys

import diff


def read_file_or_die(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
            content = content.removesuffix("\n")
            return content
    except (OSError, UnicodeError) as error:
        print(f"Could not read {path}: {error}", file=sys.stderr)
        sys.exit(1)


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
    parser.add_argument("file1", help="Left file")
    parser.add_argument("file2", help="Right file")
    args = parser.parse_args()

    lpath = args.file1
    rpath = args.file2
    lfile = read_file_or_die(lpath)
    rfile = read_file_or_die(rpath)

    max_line_count = max(lfile.count("\n"), rfile.count("\n"))

    diffs = diff.calculate_line_diff(lfile, rfile)

    if args.inline:
        diff.print_diffs(diffs)
    else:
        diff.print_diffs_side_by_side(diffs, max_line_count)


if __name__ == "__main__":
    main()
