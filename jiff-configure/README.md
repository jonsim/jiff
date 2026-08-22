# jiff-configure

`jiff-configure` is Jiff's interactive colour configuration editor. It uses
Textual to show side-by-side, inline and TOML previews while you adjust the
palette.

Run it from the root of the Jiff repository:

```sh
uv run jiff-configure
```

The built-in example exercises every two-file diff and syntax style. The
three-way overlap style is available in the controls and generated TOML, but
does not appear in this two-file preview. You can use a real pair of UTF-8 text
files instead:

```sh
uv run jiff-configure OLD NEW
```

Choose a packaged theme as a starting point, adjust the individual styles and
press `Ctrl+S` to save a complete Jiff configuration. The save dialog suggests
the standard XDG configuration path and asks before overwriting a file.

The [main Jiff README](../README.md#building-a-theme-interactively) describes
the controls and the configuration format in more detail.
