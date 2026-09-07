# jiff-configure

`jiff-configure` is Jiff's interactive colour configuration editor. It uses
Textual to show side-by-side, inline, three-way and TOML previews while you
adjust the palette.

Run it from the root of the Jiff repository:

```sh
uv run jiff-configure
```

The built-in examples exercise every diff and syntax style. Side-by-side and
Inline show the larger two-file example. Three-way uses a separate compact
example so all three panes remain readable beside the controls.

You can use a real pair of UTF-8 text files instead:

```sh
uv run jiff-configure OLD NEW
```

Those files replace the Side-by-side and Inline examples. The Three-way tab
keeps its compact built-in example.

Choose a packaged theme as a starting point, then set `Preferred output` to
ANSI16 or ANSI256. `Palette to edit` switches between that indexed palette and
the named ANSI16 fallback. ANSI256 colour fields open a 16 by 16 grid; use the
mouse or arrow keys to choose an index from 0 to 255, or select terminal
default.

The previews use the preferred palette when the terminal can display it. On an
ANSI16 terminal they show the fallback and a short notice instead. Bold,
italic and colour settings remain independent between the two palettes. The
Line-number gutters control styles the complete padded number cell, leaving
its vertical divider alone.

Press `Ctrl+S` to save both complete palette sections. The save dialog suggests
the standard XDG configuration path and asks before overwriting a file. Jiff
silently uses the saved ANSI16 fallback whenever a preferred ANSI256 palette is
not supported by the output terminal.

The [main Jiff README](../README.md#building-a-theme-interactively) describes
the controls and the configuration format in more detail.
