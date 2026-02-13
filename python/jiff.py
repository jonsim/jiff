import argparse
import sys
import diff

def read_file_or_die(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as error:
        print(f"Could not read {path}: {error}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Colored diff tool")
    parser.add_argument("-g", "--git-diff", action="store_true", help="Enable git diff mode")
    parser.add_argument("-s", "--side-by-side", action="store_true", help="Enable side-by-side diffing")
    parser.add_argument("--no-color", action="store_true", help="Disables colorization of the output")
    parser.add_argument("file1", help="Left file")
    parser.add_argument("file2", help="Right file")
    args = parser.parse_args()

    lpath = args.file1
    rpath = args.file2
    color = not args.no_color
    side_by_side = args.side_by_side

    lfile = read_file_or_die(lpath)
    rfile = read_file_or_die(rpath)

    max_line_count = max(lfile.count('\n'), rfile.count('\n'))

    diffs = diff.calculate_line_diff(lfile, rfile)


    if side_by_side:
        diff.print_diffs_side_by_side(diffs, max_line_count)
    else:
        diff.print_diffs(diffs)


if __name__ == "__main__":
    main()
