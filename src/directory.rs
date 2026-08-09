use std::collections::BTreeSet;
use std::error::Error;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// One changed path from a pair of directory trees.
#[derive(Debug, Eq, PartialEq)]
pub(crate) struct DirectoryDiff {
    pub(crate) relative_path: PathBuf,
    pub(crate) left: Option<Vec<u8>>,
    pub(crate) right: Option<Vec<u8>>,
}

/// An I/O failure annotated with the path which caused it.
#[derive(Debug)]
pub(crate) struct DirectoryError {
    path: PathBuf,
    source: io::Error,
}

impl DirectoryError {
    fn new(path: impl Into<PathBuf>, source: io::Error) -> Self {
        Self {
            path: path.into(),
            source,
        }
    }
}

impl fmt::Display for DirectoryError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.path.display(), self.source)
    }
}

impl Error for DirectoryError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        Some(&self.source)
    }
}

/// Reads the changed files from two directory trees in repository-path order.
pub(crate) fn directory_diffs(
    left_root: &Path,
    right_root: &Path,
) -> Result<Vec<DirectoryDiff>, DirectoryError> {
    let left_paths = collect_files(left_root)?;
    let right_paths = collect_files(right_root)?;
    let paths = left_paths
        .union(&right_paths)
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut diffs = Vec::new();

    for relative_path in paths {
        let left = read_side(left_root, &relative_path, &left_paths)?;
        let right = read_side(right_root, &relative_path, &right_paths)?;

        // Presence is significant: adding or removing an empty file still
        // deserves a file header even though both byte strings are empty.
        if left != right {
            diffs.push(DirectoryDiff {
                relative_path,
                left,
                right,
            });
        }
    }

    Ok(diffs)
}

fn collect_files(root: &Path) -> Result<BTreeSet<PathBuf>, DirectoryError> {
    let mut files = BTreeSet::new();
    collect_directory(root, Path::new(""), &mut files)?;
    Ok(files)
}

fn collect_directory(
    root: &Path,
    relative_directory: &Path,
    files: &mut BTreeSet<PathBuf>,
) -> Result<(), DirectoryError> {
    let directory = root.join(relative_directory);
    let entries =
        fs::read_dir(&directory).map_err(|error| DirectoryError::new(&directory, error))?;

    for entry in entries {
        let entry = entry.map_err(|error| DirectoryError::new(&directory, error))?;
        let relative_path = relative_directory.join(entry.file_name());
        let path = entry.path();
        let file_type = entry
            .file_type()
            .map_err(|error| DirectoryError::new(&path, error))?;

        if file_type.is_dir() {
            collect_directory(root, &relative_path, files)?;
        } else {
            // Git may use symlinks for the working-tree side. Treat them as
            // file entries and let `read` follow them to their contents.
            files.insert(relative_path);
        }
    }

    Ok(())
}

fn read_side(
    root: &Path,
    relative_path: &Path,
    paths: &BTreeSet<PathBuf>,
) -> Result<Option<Vec<u8>>, DirectoryError> {
    if !paths.contains(relative_path) {
        return Ok(None);
    }

    let path = root.join(relative_path);
    fs::read(&path)
        .map(Some)
        .map_err(|error| DirectoryError::new(path, error))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

    struct TestDirectories {
        root: PathBuf,
        left: PathBuf,
        right: PathBuf,
    }

    impl TestDirectories {
        fn new() -> Self {
            let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "jiff-directory-test-{}-{sequence}",
                std::process::id()
            ));
            let left = root.join("left");
            let right = root.join("right");
            fs::create_dir_all(&left).expect("left test directory should be created");
            fs::create_dir_all(&right).expect("right test directory should be created");
            Self { root, left, right }
        }

        fn write(&self, side: &Path, relative_path: &str, contents: &[u8]) {
            let path = side.join(relative_path);
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).expect("test parent directory should be created");
            }
            fs::write(path, contents).expect("test file should be written");
        }
    }

    impl Drop for TestDirectories {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.root).expect("test directory should be removed");
        }
    }

    #[test]
    fn reports_changed_files_in_repository_path_order() {
        let directories = TestDirectories::new();
        directories.write(&directories.left, "same.txt", b"Kermit");
        directories.write(&directories.right, "same.txt", b"Kermit");
        directories.write(&directories.left, "changed.txt", b"Kermit");
        directories.write(&directories.right, "changed.txt", b"Fozzie");
        directories.write(&directories.left, "empty.txt", b"");
        directories.write(&directories.right, "nested/new.txt", b"Gonzo");

        let diffs = directory_diffs(&directories.left, &directories.right)
            .expect("test directories should be readable");

        assert_eq!(
            vec![
                PathBuf::from("changed.txt"),
                PathBuf::from("empty.txt"),
                PathBuf::from("nested/new.txt"),
            ],
            diffs
                .iter()
                .map(|diff| diff.relative_path.clone())
                .collect::<Vec<_>>()
        );
        assert_eq!(Some(Vec::new()), diffs[1].left);
        assert_eq!(None, diffs[1].right);
        assert_eq!(None, diffs[2].left);
        assert_eq!(Some(b"Gonzo".to_vec()), diffs[2].right);
    }

    #[test]
    fn handles_a_file_becoming_a_directory() {
        let directories = TestDirectories::new();
        directories.write(&directories.left, "stage", b"Kermit");
        directories.write(&directories.right, "stage/kermit.txt", b"Green");

        let diffs = directory_diffs(&directories.left, &directories.right)
            .expect("test directories should be readable");

        assert_eq!(Path::new("stage"), diffs[0].relative_path);
        assert_eq!(Some(b"Kermit".to_vec()), diffs[0].left);
        assert_eq!(None, diffs[0].right);
        assert_eq!(Path::new("stage/kermit.txt"), diffs[1].relative_path);
        assert_eq!(None, diffs[1].left);
        assert_eq!(Some(b"Green".to_vec()), diffs[1].right);
    }
}
