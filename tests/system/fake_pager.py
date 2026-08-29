from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    mode, destination = sys.argv[1:]
    if mode == "close":
        # A real pager closes this pipe when the user quits before reading the
        # complete diff. One byte makes that behaviour deterministic here.
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
