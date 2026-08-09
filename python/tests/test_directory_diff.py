import tempfile
import unittest
from pathlib import Path

import directory_diff


class DirectoryDiffTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="jiff-directory-test-"
        )
        self.left = Path(self.temporary_directory.name) / "left"
        self.right = Path(self.temporary_directory.name) / "right"
        self.left.mkdir()
        self.right.mkdir()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write(self, root: Path, relative_path: str, contents: bytes):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def test_reports_changed_files_in_repository_path_order(self):
        self.write(self.left, "same.txt", b"Kermit")
        self.write(self.right, "same.txt", b"Kermit")
        self.write(self.left, "changed.txt", b"Kermit")
        self.write(self.right, "changed.txt", b"Fozzie")
        self.write(self.left, "empty.txt", b"")
        self.write(self.right, "nested/new.txt", b"Gonzo")

        diffs = directory_diff.directory_diffs(self.left, self.right)

        self.assertEqual(
            [Path("changed.txt"), Path("empty.txt"), Path("nested/new.txt")],
            [diff.relative_path for diff in diffs],
        )
        self.assertEqual(b"", diffs[1].left)
        self.assertIsNone(diffs[1].right)
        self.assertIsNone(diffs[2].left)
        self.assertEqual(b"Gonzo", diffs[2].right)

    def test_handles_a_file_becoming_a_directory(self):
        self.write(self.left, "stage", b"Kermit")
        self.write(self.right, "stage/kermit.txt", b"Green")

        diffs = directory_diff.directory_diffs(self.left, self.right)

        self.assertEqual(Path("stage"), diffs[0].relative_path)
        self.assertEqual(b"Kermit", diffs[0].left)
        self.assertIsNone(diffs[0].right)
        self.assertEqual(Path("stage/kermit.txt"), diffs[1].relative_path)
        self.assertIsNone(diffs[1].left)
        self.assertEqual(b"Green", diffs[1].right)


if __name__ == "__main__":
    unittest.main()
