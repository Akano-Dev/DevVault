# Audio (optional)

No audio ships with QuestPanel — do not add copyrighted Minecraft sounds or
music here if you intend to redistribute the app.

QuestPanel works perfectly with this folder empty. Drop in your own files to
enable sound:

| File | Played when |
| --- | --- |
| `task_complete.wav` | a task is checked |
| `task_uncomplete.wav` | a task is unchecked |
| `objective_complete.wav` | every task in the objective is done |
| `ui_click.wav` | optional UI feedback |
| `music/*.ogg` `*.mp3` `*.wav` | background music, shuffled and looped |

Effects must be `.wav` — Qt's `QSoundEffect` only decodes WAV. Music can be any
format the platform's Qt Multimedia backend supports.

Enable and mix everything under **Settings → Audio**.

Good sources for freely licensed audio: freesound.org (check each licence),
OpenGameArt.org, and Kenney's CC0 audio packs.
