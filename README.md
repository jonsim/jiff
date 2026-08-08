# jiff

[![Build Status](https://travis-ci.org/jonsim/jiff.svg?branch=master)](https://travis-ci.org/jonsim/jiff)
[![codecov](https://codecov.io/gh/jonsim/jiff/branch/master/graph/badge.svg)](https://codecov.io/gh/jonsim/jiff)

A terminal diff tool supporting sub-line diffs and side-by-side output display

## Implementations

This repo has two separate, fully featured implementations: one written in Rust,
the other in Python. The Rust version is expected to be faster, but the Python
version is more portable. Tests assert that the two versions are functionally
identical.

Long output from either implementation is sent to `$PAGER`, using `less` by
default. Output which fits in the terminal, or is redirected to another
command, is printed directly. Pass `--no-pager` to always print directly.

### Rust

#### Building

```sh
cargo build
```

#### Testing

Unit tests:
```sh
cargo test
```

System tests:
```sh
robot tests
```

Optionally, the Python tests can be skipped with:
```sh
robot -v SKIP_PYTHON_TESTS:True tests
```


### Python

#### Running

Jiff displays a side-by-side diff by default:

```sh
uv run jiff FILE1 FILE2
```

Use `-i` or `--inline` for inline output:

```sh
uv run jiff --inline FILE1 FILE2
```

#### Testing

Unit tests:
```sh
uv run python -m unittest discover -s python/tests
```

System tests:
```sh
robot tests
```

Optionally, the Rust tests can be skipped with:
```sh
robot -v SKIP_RUST_TESTS:True tests
```

## Developing

### Setting up a development environment

Create the development environment and install the git hooks with:
```sh
uv sync
uv run pre-commit install
```

Once the hooks are installed they will run automatically on commit. You can run
pre-commit manually with:
```sh
uv run pre-commit run --all-files
```
