from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DirectoryDiff:
    """One changed path from a pair of directory trees."""

    relative_path: Path
    left: bytes | None
    right: bytes | None


def directory_diffs(left_root: Path, right_root: Path) -> list[DirectoryDiff]:
    """Reads changed files from two directory trees in repository-path order."""
    left_paths = _collect_files(left_root)
    right_paths = _collect_files(right_root)
    diffs = []

    for relative_path in sorted(left_paths | right_paths, key=Path.as_posix):
        left = _read_side(left_root, relative_path, left_paths)
        right = _read_side(right_root, relative_path, right_paths)

        # Keep presence separate from content so adding or removing an empty
        # file still produces its file header.
        if left != right:
            diffs.append(DirectoryDiff(relative_path, left, right))

    return diffs


def _collect_files(root: Path) -> set[Path]:
    files: set[Path] = set()

    def visit(directory: Path, relative_directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                relative_path = relative_directory / entry.name
                if entry.is_dir(follow_symlinks=False):
                    visit(Path(entry.path), relative_path)
                else:
                    # Git commonly represents the working-tree side with
                    # symlinks. Reading the entry later follows it as intended.
                    files.add(relative_path)

    visit(root, Path())
    return files


def _read_side(root: Path, relative_path: Path, paths: set[Path]) -> bytes | None:
    if relative_path not in paths:
        return None
    return (root / relative_path).read_bytes()
