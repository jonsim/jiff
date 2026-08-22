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

Pass three files to compare two versions against a common base. The second
file is the base, so the order is `LOCAL BASE REMOTE`:

```sh
jiff LOCAL BASE REMOTE
```

Side-by-side mode draws one pane per file. Changes are highlighted in the two
outer panes, while the base pane shows the exact text changed by the local
side, the remote side or both. `--inline` falls back to two labelled diffs,
`LOCAL` against `BASE` followed by `BASE` against `REMOTE`.

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

The configuration file is optional. Jiff uses the first file it finds and does
not merge settings from several files.

#### File location

Jiff uses the first configuration file it finds in this order:

1. The path in `$JIFF_CONFIG`, when set.
2. `$XDG_CONFIG_HOME/jiff/config.toml`, or `~/.config/jiff/config.toml` when
   `$XDG_CONFIG_HOME` is not set.
3. `~/.jiffconfig`.

The XDG path is recommended for normal use. Create it with:

```sh
mkdir -p ~/.config/jiff
touch ~/.config/jiff/config.toml
```

`JIFF_CONFIG` is useful for trying another palette without replacing the usual
one:

```sh
JIFF_CONFIG=jiff-configure/themes/high-contrast-light.toml jiff OLD NEW
```

If `$JIFF_CONFIG` is set, Jiff uses that exact path. It does not fall back to
the other locations when the file is missing or invalid.

#### TOML structure

The file must contain valid TOML and currently supports one top-level table:
`[color]`. Unknown tables, styles and fields are reported as errors so a typo
cannot silently change the result.

Each entry below `[color]` names a style. A style has up to three fields:

| Field | Value | Meaning |
|---|---|---|
| `color` | Colour name | Foreground colour |
| `bgcolor` | Colour name | Background colour; diff styles only |
| `bold` | `true` or `false` | Enable or disable bold text |

Inline tables keep short styles compact:

```toml
[color]
add = { color = "blue", bold = true }
add_highlight = { color = "yellow", bgcolor = "blue" }
```

The normal TOML table form is clearer for a longer style and means exactly the
same thing:

```toml
[color.add_highlight]
color = "yellow"
bgcolor = "blue"
bold = true
```

Every style and field is optional. An omitted value keeps its built-in default.
Use the colour name `default` when you want to clear a built-in foreground or
background instead:

```toml
[color]
add = { color = "default" }
```

That example makes added text use the terminal's normal foreground colour.

#### Diff styles

These styles control the diff itself:

| Style | Used for | Default foreground | Default background |
|---|---|---|---|
| `same` | Unchanged text | Terminal default | Terminal default |
| `omitted` | `... N unchanged lines ...` markers | `bright_black` | Terminal default |
| `add` | Normal added text and unchanged characters in paired lines | `green` | Terminal default |
| `add_highlight` | Changed characters and unpaired side-by-side additions | `black` | `green` |
| `remove` | Normal removed text and unchanged characters in paired lines | `red` | Terminal default |
| `remove_highlight` | Changed characters and unpaired side-by-side removals | `black` | `red` |
| `overlap_highlight` | Middle-pane characters changed by both outer files in a three-way diff | `black` | `yellow` |

All seven accept `color`, `bgcolor` and `bold`. Their built-in `bold` value is
`false`. Line numbers and the `+`/`-` markers inherit the corresponding diff
colour and are deliberately bold so they remain visible beside highlighted
text. `overlap_highlight` is only used in three-way side-by-side output.

#### Syntax highlighting styles

Syntax configuration only changes how token categories are drawn. It does not
select a language: Jiff still detects that from the filename, or uses the
language passed to `--syntax=LANGUAGE`.

| Style | Used for | Default foreground |
|---|---|---|
| `syntax_comment` | Comments and documentation | `bright_black` |
| `syntax_keyword` | Language keywords | `magenta` |
| `syntax_string` | String literals | `cyan` |
| `syntax_number` | Numeric literals | `blue` |
| `syntax_definition` | Function, type and other definition names | `yellow` |

These five styles accept `color` and `bold`; their built-in `bold` value is
`false`. They do not accept `bgcolor`. Diff backgrounds must remain in control,
and the stronger `add_highlight` and `remove_highlight` styles win when syntax
and intraline highlighting overlap.

Use `--no-syntax` to ignore the syntax styles while retaining the diff colours.
Use `--no-color` to disable both diff and syntax styling.

#### Supported colour names

Colour names are case-insensitive and surrounding whitespace is ignored. The
supported canonical names are:

```text
default
black
bright_black
red
bright_red
green
bright_green
yellow
bright_yellow
blue
bright_blue
magenta
bright_magenta
cyan
bright_cyan
white
bright_white
```

`gray` and `grey` are aliases for `bright_black`; `purple` is an alias for
`magenta`. `default` means the terminal's normal foreground or background—it
does not mean Jiff's built-in value. Hex colours, RGB values, ANSI colour
numbers and colours outside the standard 16-colour ANSI palette are not
currently supported.

#### Complete themes

The repository includes seven complete themes:

| Theme | Best suited to | Character |
|---|---|---|
| [High contrast light](jiff-configure/themes/high-contrast-light.toml) | Light terminals | Crisp blue and magenta diff colours |
| [High contrast dark](jiff-configure/themes/high-contrast-dark.toml) | Dark terminals | Bright cyan and yellow diff colours |
| [Catppuccin Mocha](jiff-configure/themes/catppuccin-mocha.toml) | Dark terminals | Soft green, magenta and cyan |
| [Dracula](jiff-configure/themes/dracula.toml) | Dark terminals | Green and red diffs with purple syntax |
| [Gruvbox Dark](jiff-configure/themes/gruvbox-dark.toml) | Dark terminals | Warm, bright foregrounds on restrained backgrounds |
| [Nord](jiff-configure/themes/nord.toml) | Dark terminals | Cool cyan, red and blue |
| [Tokyo Night](jiff-configure/themes/tokyo-night.toml) | Dark terminals | Cyan and magenta with blue syntax |

The first two prioritise contrast and colour-blind accessibility. The other
five borrow the colour relationships of popular editor themes. Jiff's config
uses ANSI colour names, so your terminal theme still chooses the exact shades.
This generally makes the palettes sit naturally alongside a matching terminal
theme, but they are not exact RGB reproductions.

Gruvbox Dark and High Contrast Dark use bright foregrounds for the main diff
signal, but retain standard colours for highlight backgrounds. This keeps
changed spans clear without turning them into high-intensity blocks. The light
theme and the other editor-inspired themes deliberately keep their standard
ANSI colours.

Copy any theme to the standard XDG location to use it:

```sh
mkdir -p ~/.config/jiff
cp jiff-configure/themes/high-contrast-dark.toml ~/.config/jiff/config.toml
```

Replace `high-contrast-dark.toml` with another filename from the table to use
that theme. Every example is a complete config, so they are also useful as
starting points for your own palette.

#### Building a theme interactively

`jiff-configure` is a separate Textual application in the uv workspace. Run it
from the repository with:

```sh
uv run jiff-configure
```

It starts with a small built-in Python diff which exercises the normal diff,
intraline and syntax colours. To preview a pair of your own UTF-8 text files
instead, pass both paths:

```sh
uv run jiff-configure OLD NEW
```

Pick one of the packaged themes as a starting point, then adjust the text
colour, background colour and bold setting for each style. The Side-by-side,
Inline and Three-way tabs use Jiff's real Python renderer, so they update as
the palette changes. The TOML tab shows the complete configuration which will
be written.

Press `Ctrl+S` or use the Save button to save it. The application asks for a
path every time, initially suggesting `$XDG_CONFIG_HOME/jiff/config.toml` or
`~/.config/jiff/config.toml`. It creates missing parent directories and asks
before replacing an existing file. Changing the starting theme or quitting
with unsaved edits also requires confirmation.

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
uv run python -m unittest discover -s jiff-configure/tests
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
