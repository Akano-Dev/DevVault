# Task icons (optional)

QuestPanel draws its built-in icons from code — there are no sprite files to
ship. The built-ins are defined as 8x8 ASCII grids in `app/core/icons.py`:

`quest` `sword` `pickaxe` `book` `star` `flame` `heart` `gear` `clock` `potion`

## Adding your own

Drop a small PNG here, e.g. `anvil.png`, and it appears in the icon dropdown of
the task editor as **Anvil**. Guidelines:

- Square, 16x16 or 32x32, transparent background
- Nearest-neighbour friendly — they are scaled with `FastTransformation` to keep
  pixel edges hard
- Any name that does not collide with a built-in

## Adding a built-in instead

Add an entry to `GLYPHS` in `app/core/icons.py`. The grid legend is:

```
.  transparent      X  primary colour
o  secondary        +  accent
```

Code-drawn glyphs recolour themselves (dimmed when a task is complete) and stay
crisp at every DPI, which imported PNGs cannot do.
