# Fonts

Two pixel faces are bundled, both under the SIL Open Font License 1.1. Neither
is a Minecraft font — Mojang's typeface is not redistributable.

| File | Family | Role | Licence |
| --- | --- | --- | --- |
| `Silkscreen-Regular.ttf` / `-Bold.ttf` | Silkscreen | `label` — small tracked-out caps | `OFL-Silkscreen.txt` |
| `PixelifySans-Regular.ttf` | Pixelify Sans | `body` — titles and task text | `OFL-PixelifySans.txt` |

## Replacing them

Every `.ttf`/`.otf` in this folder is registered at startup. To make yours the
default, add its family name to the front of `BODY_PREFERRED` or
`LABEL_PREFERRED` in `app/core/theme.py`.

Notes:

- **Silkscreen is drawn on an 8px grid.** Keep `M.EYEBROW_SIZE` and
  `M.SECTION_SIZE` at multiples of 8 or it will render soft.
- Pick a `body` font with true lowercase — the hierarchy between the all-caps
  labels and the mixed-case titles is what makes the panel readable at 340px wide.
- If this folder is empty the app falls back to Consolas and still runs.

Other good OFL/CC0 options: Pixel Operator, Press Start 2P, Jersey 15, VT323,
Departure Mono.
