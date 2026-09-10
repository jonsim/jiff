# jiff

[![Build Status](https://travis-ci.org/jonsim/jiff.svg?branch=master)](https://travis-ci.org/jonsim/jiff)

A terminal diff tool supporting sub-line diffs and side-by-side output display

## Implementations

This repo has two separate, fully featured implementations: one written in Rust,
the other in Python. The Rust version is expected to be faster, but the Python
version is more portable. The core diff behaviour is identical, though syntax
highlighting may differ slightly because the implementations use different
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

Invoke Jiff with two files or directories to see the difference between them:
```sh
jiff FILE1 FILE2
jiff DIR1 DIR2
```

By default, Jiff renders diffs in side-by-side mode. To render diffs in the more
conventional inline mode, pass `--inline`.

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

Jiff also supports three-way merge diffs. Pass three files to compare two
versions against a common base. The second file is the base, so the order is:

```sh
jiff LOCAL BASE REMOTE
```

Side-by-side mode draws one pane per file. Changes are highlighted in the two
outer panes, relative to base, while the central (base) pane highlights the
text changed by the local side, the remote side or both. `--inline` falls back
to two labelled diffs, `LOCAL` against `BASE` followed by `BASE` against
`REMOTE`.

### Syntax highlighting

Jiff automatically detects source languages from the input filenames. Git
difftool comparisons use the repository path supplied through `--path`, rather
than trying to identify Git's temporary filenames.

Use `--syntax=LANGUAGE` to override automatic detection:

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

Syntax highlighting only changes foreground colour and optional bold or italic
text - diff highlights control the background colour.

### Configuration

Jiff supports an optional XDG-style config file for persisting configuration.

#### File location

Jiff uses the first configuration file it finds in this order:

1. The path in `$JIFF_CONFIG`, when set. If no other paths are searched.
2. `$XDG_CONFIG_HOME/jiff/config.toml`, or `~/.config/jiff/config.toml` when
   `$XDG_CONFIG_HOME` is not set.
3. `~/.jiffconfig`.

The XDG path is recommended for normal use. Create it with:

```sh
mkdir -p ~/.config/jiff
touch ~/.config/jiff/config.toml
```

`JIFF_CONFIG` is useful for trying another theme temporarily:

```sh
JIFF_CONFIG=jiff-configure/themes/high-contrast-light.toml jiff OLD NEW
```

#### TOML structure

The config file must contain valid TOML and supports one top-level table:
`[color]`. Set `color.depth` to `16` or `256` to choose the preferred output;
it defaults to `16`. The palettes live in `[color.ansi16]` and
`[color.ansi256]`. Unknown tables, styles and fields are reported as errors.

The two palette tables use the same style names and fields:

| Field | Value | Meaning |
|---|---|---|
| `color` | Colour name or index | Foreground colour |
| `bgcolor` | Colour name or index | Background colour; diff styles only |
| `bold` | `true` or `false` | Enable or disable bold text |
| `italic` | `true` or `false` | Enable or disable italic text |

Inline tables keep short styles compact:

```toml
[color]
depth = 256

[color.ansi16]
add = { color = "green", bold = true }

[color.ansi256]
add = { color = 114, bold = true }
add_highlight = { color = 231, bgcolor = 22 }
```

Alternatively you may use the longer, equivalent, TOML table form:

```toml
[color.ansi256.add_highlight]
color = 231
bgcolor = 22
bold = true
italic = true
```

All styles and fields are optional. Missing ANSI16 values use Jiff's built-in
defaults. Missing ANSI256 values inherit the corresponding resolved ANSI16
values. Use `"default"` to select the terminal's normal foreground or
background explicitly:

```toml
[color.ansi16]
add = { color = "default" }

[color.ansi256]
add = { color = "default" }
```

The old layout, where styles appeared directly below `[color]`, is no longer
accepted.

Jiff uses ANSI256 only when the config asks for it and the terminal reports
ANSI256 or true-colour support. Otherwise it silently renders the ANSI16
fallback. `--no-color` continues to disable both palettes.

#### Diff styles

These styles control the diff itself:

| Style | Used for | Default foreground | Default background |
|---|---|---|---|
| `same` | Unchanged text | Terminal default | Terminal default |
| `line_number` | Side-by-side line-number gutters | Terminal default | Terminal default |
| `omitted` | `... N unchanged lines ...` markers | `bright_black` | Terminal default |
| `add` | Normal added text and unchanged characters in paired lines | `green` | Terminal default |
| `add_highlight` | Changed characters and unpaired side-by-side additions | `black` | `green` |
| `remove` | Normal removed text and unchanged characters in paired lines | `red` | Terminal default |
| `remove_highlight` | Changed characters and unpaired side-by-side removals | `black` | `red` |
| `overlap_highlight` | Middle-pane characters changed by both outer files in a three-way | `black` | `yellow` |

All eight accept `color`, `bgcolor`, `bold` and `italic`. Their built-in text
attributes are both `false`. `line_number` applies to the complete padded
line-number cell, but not the vertical rule beside it, so a background colour
fills the number cleanly without catching the divider. The `+`/`-` markers
inherit the corresponding diff colour and italics, and are deliberately bold.
`overlap_highlight` is only used in three-way side-by-side output.

#### Syntax highlighting styles

Syntax configuration only changes how token categories are drawn.

| Style | Used for | Default foreground |
|---|---|---|
| `syntax_comment` | Comments and documentation | `bright_black` |
| `syntax_comment_highlight` | Comments within highlighted text | `bright_black` |
| `syntax_keyword` | Language keywords | `magenta` |
| `syntax_keyword_highlight` | Language keywords within highlighted text | `magenta` |
| `syntax_string` | String literals | `cyan` |
| `syntax_string_highlight` | String literals within highlighted text | `cyan` |
| `syntax_number` | Numeric literals | `blue` |
| `syntax_number_highlight` | Numeric literals within highlighted text | `blue` |
| `syntax_definition` | Function, type and other definition names | `yellow` |
| `syntax_definition_highlight` | Function, type and other definition names within highlighted text | `yellow` |

These ten styles accept `color`, `bold` and `italic`; both text attributes
default to `false`. They do not accept `bgcolor`. Diff backgrounds must remain
in control, and syntax highlighting renders on top of diff highlights.

Use `--no-syntax` to ignore the syntax styles while retaining the diff colours.
Use `--no-color` to disable both diff and syntax styling.

#### Supported palette values

ANSI16 foregrounds and backgrounds use these case-insensitive names:

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
`magenta`. `default` means the terminal's normal foreground or background (not
Jiff's built-in value).

ANSI256 foregrounds and backgrounds use integer indexes from `0` to `255`, or
the string `"default"`. Hex and RGB values are not accepted. A true-colour
terminal can display the indexed palette but Jiff still emits ANSI256 colours.

#### Complete themes

The repository includes seven complete themes which you can use as-is or extend:

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
five borrow the colour relationships of popular editor themes. Every theme has
an indexed palette for closer shades and a named ANSI16 fallback. Terminals can
customise their first 16 colours, so the fallback's exact appearance still
depends on the terminal theme.

Copy any theme to the standard XDG location to use it:

```sh
mkdir -p ~/.config/jiff
cp jiff-configure/themes/high-contrast-dark.toml ~/.config/jiff/config.toml
```

#### Building a theme interactively

You can build a theme interactively using the separate `jiff-configure` tool.
Run it from the repository with:

```sh
uv run jiff-configure
```

This starts with a small built-in Python diff which exercises all supported diff
functionality. If Jiff already has a configuration file, the tool loads it as
`Current configuration` using the same path lookup as Jiff. To preview a pair
of your own files:

```sh
uv run jiff-configure OLD NEW
```

Use the picker to switch between the current configuration, the default colours
and the packaged themes. `Preferred output` chooses the depth used by Jiff and
the previews; `Palette to edit` switches between the indexed palette and its
named fallback. ANSI16 fields use named selectors. ANSI256 fields open a 16 by
16 colour grid which works with the mouse or arrow keys, plus a separate
terminal-default choice.

The Side-by-side, Inline, and Three-way tabs use Jiff's real Python renderer, so
they update as either palette changes. If the current terminal cannot display
ANSI256, the previews use ANSI16 and say so above the tabs. The saved TOML still
contains both complete palettes, including separate bold and italic settings.

Press `Ctrl+S` or use the Save button to save your theme.

### Git difftool

Once `jiff` is installed and available in `$PATH`, configure it as a custom Git
difftool with:

```sh
git config --global diff.tool jiff
git config --global difftool.jiff.cmd 'jiff --path "$MERGED" "$LOCAL" "$REMOTE"'
git config --global difftool.prompt false
git config --global difftool.trustExitCode true
```
Remove `--global` if the configuration should only apply to the current
repository.

For a one-off comparison without changing your Git configuration, use
`--extcmd`:

```sh
git difftool --no-prompt --extcmd='jiff --no-pager --path "$BASE"'
```

The `--no-pager` in this example avoids opening a pager for each changed file.
For a multi-file comparison with automatic paging, use the `--dir-diff` form
instead. Side-by-side Git diffs put each path above its pane when both fit.
Wider paths and inline output keep the Git-style `---` and `+++` headings.
Jiff returns zero after displaying a text or binary comparison and non-zero
when it cannot read, configure or display the diff.
`difftool.trustExitCode` makes Git report those failures rather than silently
continuing.

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
format.

Jiff automatically renders merge conflicts using the same three-way diff
functionality described above. This deliberately represents the index, not the
working-tree file. Any conflict markers or edits made since the merge are
therefore not included. Some Git commands render unresolved paths with Git's
built-in combined diff instead of calling an external helper; Jiff cannot replace
output when it is not invoked.

### Rust

#### Building

```sh
cargo build
```

#### Running

```sh
cargo run -- <options>
```

#### Testing

Unit tests:
```sh
cargo test
```

System tests:
```sh
uv run robot tests
```

Optionally, the Python tests can be skipped with:
```sh
uv run robot -v SKIP_PYTHON_TESTS:True tests
```


### Python

#### Running

```sh
uv run jiff FILE1 FILE2
```

#### Testing

Unit tests:
```sh
uv run python -m unittest discover -s python/tests
uv run python -m unittest discover -s jiff-configure/tests
```

System tests:
```sh
uv run robot tests
```

Optionally, the Rust tests can be skipped with:
```sh
uv run robot -v SKIP_RUST_TESTS:True tests
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
