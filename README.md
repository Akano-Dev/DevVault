# QuestPanel

A Minecraft-inspired quest tracker for real life — a small, frameless, always-on-top
desktop overlay for Windows that turns your to-do list into an objective panel.

```
┌────────────────────────────────────────────┐
│  ◈   Current Objective                     │   ← header card (yellow / white)
│      Prepare for the Nether                │
└────────────────────────────────────────────┘
   ┌──────────────────────────────────────┐
   │ Getting Ready                        │      ← body card, inset both sides
   │ ⛏  Get Tools and Items          [✓]  │
   │ ✦  Build Nether Portal          [✓]  │
   │ ⚔  Get Full Diamond Armor       [ ]  │
   │ ▤  Enchant All Gear             [ ]  │
   │ ████████░░░░░░░░              2/4    │
   └──────────────────────────────────────┘
```

Not a website, not Electron, no browser, no server. Python + PySide6 + SQLite,
fully offline.

---

## Features

**Overlay behaviour**
- Frameless window with no title bar, drawn entirely with custom `QPainter` code
- Always-on-top (toggleable), adjustable opacity, drag anywhere, resize from any edge
- Remembers position and size across restarts; pulled back on-screen if a monitor disappears
- Lives in the system tray — closing hides, the tray's **Exit** really quits
- Global hotkey (**Ctrl + Shift + Q** by default) toggles visibility from anywhere
- Shows without stealing focus (`WA_ShowWithoutActivating` + `Qt.Tool`)

**Quests**
- `Objective → Section → Task` hierarchy with full CRUD on every level
- Reorder sections and tasks, move tasks between sections, collapse sections
- Per-task priority (None/Low/Medium/High) and optional pixel icon
- Multiple objectives with one active at a time; switch from the context menu
- Segmented pixel progress meter, per-section counts, quest-completion flourish
- Every change is written to SQLite immediately — nothing is held in memory only

**Task timers** — entirely optional, per task
- Any task can carry a clock; tasks without one look and behave exactly as before
- Give it a goal (`21h`, `90m`, `1h 30m`, `2:30`) or leave it blank for a plain stopwatch
- The read-out is an inset item slot with a Minecraft-style durability bar for progress
- Click the chip to start or pause; the digits blink on the separator while it runs
- Only one clock runs at a time, so a stretch of work is never counted twice
- Time is banked to SQLite as it accrues, and ticking a task off stops its clock

**Desktop notifications** — a native Windows toast when a task timer reaches its
target and when an objective is fully checked off. Clicking one brings the panel
back to the front. The whole channel sits behind a single setting (on by default),
and **Settings → Notifications** has a test button, because Windows can suppress
toasts per-app or during Focus Assist without telling the app anything.

**Settings** — startup with Windows, always-on-top, remember position/size, hotkey
capture, UI scale, opacity, icons, progress, compact mode, notifications, and the
full audio mixer.

---

## Running it

**Easiest:** double-click **`QuestPanel.bat`**.

On first run it installs PySide6 for you; after that it starts silently through
`pythonw.exe`, so no console window is left sitting behind the overlay. It works
from any working directory and needs no setup.

| Command | What it does |
| --- | --- |
| `QuestPanel.bat` | Start from source, silently (the double-click case) |
| `QuestPanel.bat /console` | Keep the window open and show output — use when something goes wrong |
| `QuestPanel.bat /exe` | Run the packaged build in `dist\` instead |
| `QuestPanel.bat /reinstall` | Force a dependency reinstall |

Source is the default rather than the packaged build, so your edits always take
effect — a stale `dist\` build silently overriding changes is a nasty thing to
debug. If a silent launch fails, the error is written to `build\launch-error.log`,
and `/console` will show it directly.

**Manually:**

```bash
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+ (developed and tested on 3.11) and PySide6 6.6+.

### Only one copy runs at a time

Launching QuestPanel while it is already running does **not** open a second
overlay — the running one is raised and the new process exits immediately. Two
identical frameless always-on-top panels stacked on the desktop, neither
obviously belonging to a particular process, is a genuinely bad state to be in.

To make a Start Menu or taskbar entry, right-click `QuestPanel.bat` → *Send to* →
*Desktop (create shortcut)*, then pin that shortcut.

The database is created at `data/questpanel.db` when running from source, and at
`%APPDATA%\QuestPanel\questpanel.db` when running the packaged executable.

---

## Controls

The header card carries three always-visible buttons in its top-right corner —
**+** (add task), **⚙** (settings) and **×**.

**× quits QuestPanel completely** — it closes the window, removes the tray icon
and ends the process. It does not hide to the tray. Everything is already
saved to SQLite as you go, so quitting never loses work.

To get the panel out of the way *without* quitting, use `Esc`, `Ctrl+Shift+Q`,
the tray icon, or right-click → *Hide Panel*.

Each section also ends with a dim **+ Add task** row, so nothing requires
discovering the right-click menu first.

| Action | Result |
| --- | --- |
| `Ctrl+Shift+Q` | Show / hide the overlay (configurable) |
| **×** on the header card | **Quit the app entirely** |
| `Esc` | Hide the overlay (keeps running in the tray) |
| **+** on the header card | Add a task to the last section |
| **+ Add task** row | Add a task to that section |
| Click a task | Toggle complete |
| Click a task's timer chip | Start / pause that task's clock |
| Double-click a task | Edit text, priority, icon, timer |
| Double-click the objective title | Edit objective |
| Click a section header | Collapse / expand |
| Right-click a task / section / panel | Context menu for that level |
| Drag the panel background | Move the window |
| Drag any edge or corner | Resize |
| `Space` / `Enter` on a focused row | Toggle complete |
| `F2` on a focused row | Edit task |
| `T` on a focused row | Start / pause its timer |
| `Esc` | Hide the overlay |
| Double-click the tray icon | Show / hide |

---

## Assets

**No Mojang/Microsoft assets are bundled.** The visual style is an original
interpretation: every icon, checkbox, border, and the tray icon are drawn at
runtime from code (`app/core/icons.py`, `app/core/painting.py`), so there are no
sprite files to license and nothing to blur at high DPI.

```
assets/
├── fonts/      Silkscreen + Pixelify Sans (both SIL OFL 1.1, licenses included)
├── icons/      optional: drop <name>.png here to add custom task icons
├── textures/   optional
└── audio/      optional: see below
```

### Fonts

Two OFL-licensed pixel faces are bundled and used for two roles:

| Role | Font | Used for |
| --- | --- | --- |
| `label` | **Silkscreen** (Jason Kottke, OFL 1.1) | small tracked-out caps — eyebrow, section headers, progress |
| `body` | **Pixelify Sans** (Stefie Justprince, OFL 1.1) | objective titles and task text (true lowercase) |

To swap either one, drop a `.ttf`/`.otf` into `assets/fonts/` and add its family
name to `BODY_PREFERRED` / `LABEL_PREFERRED` in [`app/core/theme.py`](app/core/theme.py).
If `assets/fonts/` is empty the app falls back to Consolas and still runs.

### Audio and music

Nine original chiptune sound effects ship with QuestPanel (see below). **No music
ships** — and no Mojang audio is bundled or redistributed. Your own files go in a
writable folder that survives app updates and rebuilds:

| How you run it | Your audio folder |
| --- | --- |
| From source (`python main.py`) | `data/audio/` |
| Packaged (`QuestPanel.exe`) | `%APPDATA%\QuestPanel\audio\` |

The folder is created on first launch. The quickest way to find it is
**Settings → Audio → Open Music Folder**.

```
<audio folder>/
├── music/                    background music — .mp3 .ogg .wav .flac .m4a
│   └── your-track.mp3        shuffled and looped forever
├── task_add.wav              overrides the bundled effect, if you want
├── task_complete.wav
├── task_uncomplete.wav
├── task_delete.wav
├── objective_complete.wav
├── ui_click.wav
├── timer_start.wav
├── timer_pause.wav
└── timer_done.wav
```

**To get music playing:** drop a file into `music/`, open Settings → Audio,
confirm **Enable Music** is ticked, and press **Rescan**. No restart needed —
`Rescan` re-reads the folder. Effective volume is `Music Volume × Master
Volume`, so check both if it stays silent.

Sound effects must be `.wav` — Qt's `QSoundEffect` only decodes WAV. Music can
be any format the platform media backend supports; mp3 and ogg both work.

**Nine chiptune effects ship with QuestPanel** — task add, complete, uncomplete,
delete, objective complete, a UI click, and timer start / pause / target-reached. They are synthesised from scratch by
`tools/make_sfx.py` (pulse waves, hard envelopes, short arpeggios) so they are
original work with no licensing strings attached. Rerun that script to retune
them; drop a file with the same name in your audio folder to replace one.

All nine are under 650ms and mono 44.1kHz, so `QSoundEffect` keeps them decoded
in memory — measured `play()` latency is under 1ms.

**Output device:** audio follows whatever Windows is currently using. Plug in
headphones and playback moves to them; unplug and it returns to the speakers,
without restarting the app or losing your place in the track. Qt does not do
this on its own — it pins the output to whichever device was default when the
app launched, so QuestPanel watches `QMediaDevices.audioOutputsChanged` and
re-binds both music and effects.

The bundled `assets/audio/` is still read as a fallback, but files in your
folder win when the names collide.

---

## Building the Windows executable

```bash
pip install -r requirements-dev.txt
python tools/make_icon.py          # generates build/questpanel.ico
pyinstaller QuestPanel.spec --noconfirm
```

Output: `dist/QuestPanel/QuestPanel.exe`.

The spec uses **onedir** rather than onefile — onefile re-extracts ~150 MB of Qt
to a temp directory on every launch, which is the wrong trade for something you
toggle a dozen times a day. `assets/` is copied next to the executable, so users
can drop in their own fonts, icons, and audio on an installed copy.

To distribute, zip the whole `dist/QuestPanel/` folder.

---

## Development

```bash
python -m pytest tests -q     # 85 unit + widget tests
python tests/preview.py       # render every surface to build/preview-*.png
python tests/smoke_run.py     # boot the real app, verify tray/hotkey/geometry
```

`tests/preview.py` is the fastest way to check a visual change — it renders the
overlay, compact mode, the celebration banner, settings, a dialog, and a 150% DPI
pass to PNGs in `build/`.

### Layout

```
QuestPanel.bat           double-click launcher (see "Running it")
main.py                  entry point; sets DPI env vars before Qt loads
app/
├── application.py       bootstrap: owns db, settings, overlay, tray, hotkey, audio
├── core/
│   ├── single_instance.py  named-pipe guard; a 2nd launch raises the 1st
│   ├── paths.py         asset/data resolution (dev + PyInstaller _MEIPASS)
│   ├── theme.py         all colours, metrics, fonts, UI scale  ← retune here
│   ├── painting.py      bevel panels, inset boxes, pixel check/diamond
│   ├── icons.py         8x8 ASCII-grid glyphs + tray icon, drawn at runtime
│   └── hotkey.py        RegisterHotKey + native event filter (no polling)
├── database/
│   ├── db.py            connection, schema, WAL
│   └── repo.py          CRUD + dense reordering + first-launch seed
├── models/entities.py   Objective / Section / Task dataclasses
├── utils/duration.py    parse "21h"/"1h 30m"/"2:30"; format the clock read-out
├── services/
│   ├── settings.py      typed key/value store, write-through to SQLite
│   ├── timers.py        one shared 1s tick driving the per-task clocks
│   ├── audio.py         optional Qt Multimedia wrapper, fails soft
│   └── startup.py       HKCU Run key (no elevation)
├── ui/
│   ├── overlay.py       frameless window: flags, drag, resize, geometry, opacity
│   ├── panel_controller.py  every CRUD interaction and context menu
│   ├── settings_window.py   settings + live hotkey capture
│   ├── dialogs.py       frameless pixel dialogs
│   └── tray.py          tray icon and menu
└── widgets/
    ├── quest_panel.py   data-driven view: header card + inset body card
    ├── objective_card.py    header card (icon, eyebrow, objective name)
    ├── section_header.py / task_row.py
    ├── pixel_controls.py    checkbox, button, slider, progress, menu style
    └── celebration.py       quest-completion banner
```

### Resizing

Drag any edge or corner, or use the pixel grip in the bottom-right. The window
reserves a transparent ring exactly as wide as the grip: child widgets accept
their own mouse presses, so anything they cover can never start a resize.

### Motion

| Setting | What it does | Idle cost |
| --- | --- | --- |
| **Blossom Effect** | Cherry-blossom petals drifting over the panel | ~2.5% of one core |
| **Animations** | Staggered row entrance, checkbox pop, 1px icon bob | ~1% |
| Both off | — | ~0% |

Both are in Settings → Appearance. The costs are measured, not guessed: every
frame of an animation on a translucent always-on-top window forces the Windows
compositor to recomposite the whole window, which is what the effect actually
pays for — the drawing itself is negligible. That is why the petal layer runs at
20fps rather than 60, and why the idle icon bob repaints only the icon's
rectangle; repainting the whole card for a one-pixel movement measured 3.9%.

Timers stop dead when an effect is switched off or the overlay is hidden.

### Design notes

The layout follows the reference image measurement-for-measurement:

- **Two cards, not one panel.** A wide header card carries the item icon plus the
  yellow `Current Objective` line and the white objective name; a second card,
  inset on both sides, holds the sections and task rows. The overlay window
  itself is fully transparent — each card paints its own `#212121` fill inside a
  1px `#4A4A4A` outline, so the gaps show the desktop through.
- **Yellow is the accent, not green.** `#FCFC54` for the eyebrow and section
  headings, `#FFFFFF` for the objective name, `#CCCCCC` for task text. Green
  (`#54FC54`) appears only on a checked box.
- **Checkboxes are right-aligned into a column** and completed tasks are *not*
  dimmed or struck through — the reference leaves finished text at full
  strength, and only the box changes.
- **Every string carries a 1px drop shadow** (`painting.draw_text`), which is
  what makes the type read as game UI rather than a desktop app.
- **Icons are colour, drawn from code.** Each 8x8 glyph has its own three-tone
  palette in `icons.PALETTES`, so rows show coloured items like the reference
  without shipping a single sprite file.
- **The timer chip is an item slot, not a badge.** It reuses
  `painting.draw_inset_box` and fills the bottom two pixels with a segmented
  durability bar, so a task's progress toward its goal reads the way tool wear
  does in-game. The digits are the *only* thing in the panel set in Silkscreen
  rather than the body face and the only text with no drop shadow: at nine
  pixels the body face garbles numerals (a `5` comes out as an `8`) and the
  shadow doubles every stroke.

Engineering notes:

- **Everything visual is in `app/core/theme.py`.** Colours in `C`, spacing and
  sizes in `M`, both in design pixels multiplied by the user's UI scale through
  `px()`. Retuning the whole look means editing one file.
- **Widget heights are measured, never guessed.** `drawText` clips to its
  rectangle, and pixel faces routinely draw past their metric height — heights
  come from `QFontMetrics` plus slack, which fixed the title being clipped at
  150% scale and the yellow heading losing its capitals.
- **No anti-aliasing except on card corners.** `painting.crisp()` disables
  smoothing so checkboxes and glyphs stay on the pixel grid at every DPI.
- **No polling anywhere.** The hotkey is delivered as `WM_HOTKEY`; geometry saves
  are debounced through a single-shot timer. Idle CPU is zero. A running task
  clock is the one exception, and it is a single shared 1s `QTimer` for the whole
  panel rather than one per row.
- **Elapsed time is measured, not counted.** `services/timers.py` diffs
  `time.monotonic()` instead of adding a second per tick, so a stalled event loop
  cannot lose time. It banks the total to SQLite every 15s and on every
  pause/quit, and it deliberately does **not** persist the *running* flag: a
  timer left running when the app closes comes back paused, because restoring it
  as running would silently bill every offline hour to the task.

---

## Licence

Application code: yours to use.

Bundled fonts are SIL Open Font License 1.1 — see `assets/fonts/OFL-Silkscreen.txt`
and `assets/fonts/OFL-PixelifySans.txt`. QuestPanel is not affiliated with,
endorsed by, or associated with Mojang or Microsoft.
