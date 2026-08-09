# jiff

[![Build Status](https://travis-ci.org/jonsim/jiff.svg?branch=master)](https://travis-ci.org/jonsim/jiff)
[![codecov](https://codecov.io/gh/jonsim/jiff/branch/master/graph/badge.svg)](https://codecov.io/gh/jonsim/jiff)

A terminal diff tool supporting sub-line diffs and side-by-side output display

## Implementations

This repo has two separate, fully featured implementations: one written in Rust,
the other in Python. The Rust version is expected to be faster, but the Python
version is more portable. The core diff behaviour is kept identical. Syntax
highlighting can differ slightly because the implementations use different
language engines.

### Installing

Install the Rust implementation with Cargo:

```sh
cargo install --path .
```

Or install the Python implementation as a standalone uv tool:

```sh
uv tool install ./python
```

Both commands install a `jiff` executable. Only install one implementation at a
time unless you deliberately arrange their order in `$PATH`.

Long output from either implementation is sent to `$PAGER`, using `less` by
default. Output which fits in the terminal, or is redirected to another
command, is printed directly. Pass `--no-pager` to always print directly.

By default Jiff shows every unchanged line. Pass `-U<n>` or `--unified=<n>` to
show at most `<n>` lines of context on either side of each change. For example,
this shows three context lines:

```sh
jiff -U3 FILE1 FILE2
```

Omitted regions are marked with their number of unchanged lines in either
output layout. `-U0` shows only changed lines and those markers.

### Syntax highlighting

Jiff automatically detects source languages from the input filenames. Git
difftool comparisons use the repository path supplied through `--path`, rather
than trying to identify Git's temporary filenames.

Use `--syntax=LANGUAGE` when the filename is ambiguous or has no useful
extension:

```sh
jiff --syntax=python FILE1 FILE2
```

Common language names and extensions are accepted. The Python implementation
uses Pygments, while Rust uses syntect, so their complete language lists and a
few token boundaries differ. An unknown automatically detected language falls
back to plain text. An unknown explicit language is reported as an error.

Pass `--no-syntax` to retain Jiff's diff colours without token highlighting.
`--no-color` disables both. The built-in syntax palette is deliberately muted:

- comments are grey;
- keywords are magenta;
- strings are cyan;
- numbers are blue;
- function and type names are yellow.

Syntax highlighting only changes foreground colour and optional bold text.
Diff backgrounds remain in control, and intraline changes take priority where
the two overlap.

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

The diff styles are `same`, `omitted`, `add`, `add_highlight`, `remove` and
`remove_highlight`. Each accepts `color`, `bgcolor` and `bold`. `omitted`
controls the muted markers for unchanged regions hidden by `--unified`.
Syntax styles are `syntax_comment`, `syntax_keyword`, `syntax_string`,
`syntax_number` and `syntax_definition`; these accept `color` and `bold`.
Syntax backgrounds are rejected so they cannot hide the diff.

Line numbers and change markers inherit the corresponding `same`, `add` or
`remove` colours and are shown in bold. The built-in diff palette uses the
terminal default for unchanged text, green for additions, red for removals,
and black on green or red for highlights.

Supported colour names are `default`, `black`, `bright_black`, `gray`, `grey`,
`red`, `green`, `yellow`, `blue`, `magenta`, `purple`, `cyan` and `white`.
`gray` and `grey` are aliases for `bright_black`; `purple` is an alias for
`magenta`. `default` clears that foreground or background and lets the terminal
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

### Git difftool

Once `jiff` is installed and available in `$PATH`, configure it as a custom Git
difftool with:

```sh
git config --global diff.tool jiff
git config --global difftool.jiff.cmd 'jiff --path "$MERGED" "$LOCAL" "$REMOTE"'
git config --global difftool.prompt false
git config --global difftool.trustExitCode true
```

`$LOCAL` and `$REMOTE` are Git's temporary before and after files. `$MERGED`
holds the repository path, which Jiff displays as `a/PATH` and `b/PATH` above
the diff. Git supplies the source path for a detected rename. Remove `--global`
from the commands if the configuration should only apply to the current
repository.

The usual Git forms work as expected. For changes spanning more than one file,
use Git's directory mode:

```sh
git difftool
git difftool --cached
git difftool HEAD~1 HEAD
git difftool --dir-diff HEAD~1 HEAD
```

`--dir-diff` makes Git prepare two temporary directory trees and launch Jiff
once. Jiff compares their files recursively and sends the complete result to
one pager, so `q` stops the whole review rather than opening the next file.
Added and removed files, empty files, nested paths and binary files are all
handled. The same behaviour is available directly with `jiff DIR1 DIR2`.

For a one-off comparison without changing the Git configuration, use
`--extcmd`. Git appends the two temporary files to this command and exposes the
repository path as `$BASE`:

```sh
git difftool --no-prompt --extcmd='jiff --no-pager --path "$BASE"'
```

The `--no-pager` in this example avoids opening a pager for each changed file.
For a multi-file comparison with automatic paging, use the configured
`--dir-diff` form above instead. Jiff returns zero after displaying a text or
binary comparison and non-zero when it cannot read, configure or display the
diff. `difftool.trustExitCode` makes Git report those failures rather than
silently continuing.

### Git diff and Git show

Git's ordinary `diff` command uses a different interface from `git difftool`.
It calls an external diff once per changed path using its own seven-argument
protocol. `--git-external-diff` tells Jiff to parse those arguments, retain its
colours and leave Git in charge of the pager.

Configure Jiff globally, or omit `--global` to use it in one repository:

```sh
git config --global diff.external 'jiff --git-external-diff'
```

Ordinary diff commands will now use Jiff:

```sh
git diff
git diff --cached
git diff HEAD~
```

`git show` and `git log` do not enable external diff programs by default. Pass
`--ext-diff`, or add shorter aliases:

```sh
git show --ext-diff HEAD
git log -p --ext-diff

git config --global alias.jshow 'show --ext-diff'
git config --global alias.jlog 'log -p --ext-diff'
```

The aliases are then available as `git jshow` and `git jlog`. Git aliases
cannot replace built-in commands, so a Git configuration cannot make the exact
command `git show` imply `--ext-diff`.

External diff output is intended for people to read; it is not a patch. Use
`git diff --no-ext-diff` for scripts or anything which needs Git's normal patch
format. Git only supplies the path for an unmerged file, so Jiff currently
prints `Unmerged file: PATH` rather than attempting a three-way diff.

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
