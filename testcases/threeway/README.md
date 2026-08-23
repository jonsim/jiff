# Three-way comparison examples

Jiff treats the second file as the common base. Pass the files in `LOCAL BASE
REMOTE` order:

```sh
uv run jiff \
    testcases/threeway/independent/local.py \
    testcases/threeway/independent/base.py \
    testcases/threeway/independent/remote.py
```

The default output is side by side. Add `--inline` to see the same comparisons
as two inline diffs. `-U2` is also handy when deciding whether the section
break between the comparisons carries enough context.

The examples exercise different shapes of merge:

- `independent` changes separate parts of a Python file on each side;
- `overlapping` changes the same Python lines in two different ways;
- `line-shapes` mixes insertions, removals and reordering in plain text;
- `repeated` keeps duplicate lines anchored consistently.

Swap `uv run jiff` for `cargo run --` to try the Rust implementation. Voilà,
the three paths and every other option stay the same.
