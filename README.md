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

### Configuration

Jiff uses the first configuration file it finds in this order:

1. The path in `$JIFF_CONFIG`, when set.
2. `$XDG_CONFIG_HOME/jiff/config.toml`, or `~/.config/jiff/config.toml` when
   `$XDG_CONFIG_HOME` is not set.
3. `~/.jiffconfig`.

The file is optional. If it exists, it must contain valid TOML. Colour styles
are configured under `[color]`; every style and field is optional, and omitted
values keep the built-in default. For example, this changes additions to a
blue and yellow palette:

```toml
[color]
add = { color = "blue", bold = true }
add_highlight = { color = "yellow", bgcolor = "blue" }
```

The supported styles are `same`, `add`, `add_highlight`, `remove` and
`remove_highlight`. Each accepts `color`, `bgcolor` and `bold`. Line numbers and
change markers inherit the corresponding `same`, `add` or `remove` colours and
are shown in bold. The built-in palette uses the terminal default for unchanged
text, green for additions, red for removals, and black on green or red for
highlights.

Supported colour names are `default`, `black`, `red`, `green`, `yellow`,
`blue`, `magenta`, `purple`, `cyan` and `white`. `purple` is an alias for
`magenta`; `default` clears that foreground or background and lets the terminal
choose it.

The repository includes ready-made palettes for
[light terminals](examples/jiffconfig-light.toml) and
[dark terminals](examples/jiffconfig-dark.toml). Copy one to the standard XDG
location to use it:

```sh
mkdir -p ~/.config/jiff
cp examples/jiffconfig-dark.toml ~/.config/jiff/config.toml
```

Use the light variant in the command above when your terminal has a light
background. Both examples are complete configs, so they are also useful as a
starting point for your own palette.

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
