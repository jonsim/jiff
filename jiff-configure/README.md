# jiff-configure

`jiff-configure` is Jiff's interactive colour configuration editor. It uses
Textual to show side-by-side, inline, three-way and TOML previews while you
adjust the palette.

Run it from the root of the Jiff repository:

```sh
uv run jiff-configure
```

If Jiff already has a configuration file, `jiff-configure` loads it as
`Current configuration`. This uses the same `JIFF_CONFIG`, XDG and legacy
path lookup as Jiff itself. The picker still includes `Default` and every
packaged theme, so you can try another theme and switch back.

The built-in examples exercise every diff and syntax style. Side-by-side and
Inline show the larger two-file example. Three-way uses a separate compact
example so all three panes remain readable beside the controls.

You can use a real pair of UTF-8 text files instead:

```sh
uv run jiff-configure OLD NEW
```

Those files replace the Side-by-side and Inline examples. The Three-way tab
keeps its compact built-in example.

Choose a theme as a starting point, then set `Preferred output` to ANSI16,
ANSI256 or truecolour. `Palette to edit` switches between the RGB palette and
its indexed and named fallbacks. ANSI256 colour fields open a 16 by 16 grid;
use the mouse or arrow keys to choose an index from 0 to 255. Truecolour fields
accept a six-digit `#RRGGBB` value and show a swatch. Both can select the
terminal default.

The previews use the preferred palette when the terminal can display it. On a
less capable terminal they show the best available fallback and a short notice
instead. Bold, italic and colour settings remain independent between the three
palettes. The three line-number controls style unchanged, added and removed
line numbers. Each covers the complete padded number cell while leaving its
vertical divider alone.

Press `Ctrl+S` to save all three complete palette sections. The save dialog
suggests the standard XDG configuration path and asks before overwriting a
file. Jiff silently falls back from truecolour to ANSI256 and then ANSI16
according to the output terminal.

The [main Jiff README](../README.md#building-a-theme-interactively) describes
the controls and the configuration format in more detail.
