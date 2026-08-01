# jiff

[![Build Status](https://travis-ci.org/jonsim/jiff.svg?branch=master)](https://travis-ci.org/jonsim/jiff)
[![codecov](https://codecov.io/gh/jonsim/jiff/branch/master/graph/badge.svg)](https://codecov.io/gh/jonsim/jiff)

A terminal diff tool supporting sub-line diffs and side-by-side output display

## Implementations

This repo has two separate, fully featured implementations: one written in Rust,
the other in Python. The Rust version is expected to be faster, but the Python
version is more portable. Tests assert that the two versions are functionally
identical.

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

#### Testing

Unit tests:
- Currently no unit tests for the Python code - TBD.

System tests:
```sh
robot tests
```

Optionally, the Rust tests can be skipped with:
```sh
robot -v SKIP_RUST_TESTS:True tests
```
