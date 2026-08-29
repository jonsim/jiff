from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    mode, destination = sys.argv[1:]
    if mode == "close":
        # Quitting a pager closes this pipe before the diff is consumed. Read
        # one byte so the test always reaches that case.
        sys.stdin.buffer.read(1)
        return 0
    if mode == "fail":
        return 7

    Path(destination).write_text(
        json.dumps(
            {
                "input": sys.stdin.read(),
                "less": os.environ.get("LESS"),
            }
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
