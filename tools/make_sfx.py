"""Generate QuestPanel's chiptune sound effects.

    python tools/make_sfx.py

Everything here is synthesised from scratch with the standard library, so the
output is original work with no licensing strings attached -- which matters,
because no Mojang audio may be redistributed.

The style is deliberately 1-bit/8-bit: pulse waves, hard envelopes, short
arpeggios. Files are mono 44.1kHz 16-bit PCM and all under ~600ms, so
QSoundEffect can hold them decoded in memory and fire with no audible delay.
"""
from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "audio"

RATE = 44100
PEAK = 0.62          # leave headroom; these layer with music

# Equal temperament, A4 = 440
NOTES = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00,
    "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99,
    "A5": 880.00, "B5": 987.77,
    "C6": 1046.50, "D6": 1174.66, "E6": 1318.51, "G6": 1567.98, "C7": 2093.00,
}


def pulse(phase: float, duty: float = 0.5) -> float:
    """One sample of a pulse wave. Duty shapes the timbre: 0.5 is hollow and
    square, 0.125 is thin and nasal -- the classic NES lead."""
    return 1.0 if (phase % 1.0) < duty else -1.0


def triangle(phase: float) -> float:
    p = phase % 1.0
    return 4.0 * abs(p - 0.5) - 1.0


def env_decay(t: float, length: float, curve: float = 3.0) -> float:
    """Percussive envelope: instant attack, exponential fall."""
    if t >= length:
        return 0.0
    return (1.0 - t / length) ** curve


def env_ar(t: float, length: float, attack: float = 0.004) -> float:
    """Tiny attack ramp then decay. The ramp kills the click on note onset."""
    if t >= length:
        return 0.0
    if t < attack:
        return t / attack
    return (1.0 - (t - attack) / (length - attack)) ** 2.2


def tone(
    freq: float,
    length: float,
    duty: float = 0.5,
    volume: float = 1.0,
    shape: str = "pulse",
    bend: float = 0.0,
    vibrato: float = 0.0,
) -> list[float]:
    """One note. ``bend`` slides the pitch by that many semitones over the note."""
    samples: list[float] = []
    phase = 0.0
    count = int(RATE * length)
    for i in range(count):
        t = i / RATE
        progress = i / max(1, count)
        f = freq * (2.0 ** (bend * progress / 12.0))
        if vibrato:
            f *= 1.0 + vibrato * math.sin(2 * math.pi * 6.0 * t)
        phase += f / RATE
        value = triangle(phase) if shape == "triangle" else pulse(phase, duty)
        samples.append(value * env_ar(t, length) * volume)
    return samples


def noise(length: float, volume: float = 1.0, curve: float = 3.0,
          lowpass: float = 0.35) -> list[float]:
    """Filtered white noise -- used for the delete 'crunch'."""
    samples: list[float] = []
    last = 0.0
    count = int(RATE * length)
    rng = random.Random(1337)          # fixed seed: rebuilds are identical
    for i in range(count):
        t = i / RATE
        white = rng.uniform(-1.0, 1.0)
        last += lowpass * (white - last)
        samples.append(last * env_decay(t, length, curve) * volume)
    return samples


def sequence(parts: list[tuple[float, list[float]]]) -> list[float]:
    """Mix parts, each placed at an offset in seconds."""
    total = max((int(at * RATE) + len(data) for at, data in parts), default=0)
    buffer = [0.0] * total
    for at, data in parts:
        start = int(at * RATE)
        for i, value in enumerate(data):
            buffer[start + i] += value
    return buffer


def write(name: str, samples: list[float]) -> Path:
    peak = max((abs(s) for s in samples), default=0.0) or 1.0
    scale = PEAK / peak
    # 4ms fade-out guarantees the file never ends on a non-zero sample, which
    # is what produces that dry 'tick' at the end of badly cut effects.
    fade = int(RATE * 0.004)
    frames = bytearray()
    for i, value in enumerate(samples):
        v = value * scale
        if i > len(samples) - fade:
            v *= (len(samples) - i) / fade
        frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767))

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    return path


# ---------------------------------------------------------------------------
# The effects
# ---------------------------------------------------------------------------
def task_complete() -> list[float]:
    """Bright rising arpeggio -- the 'ding' of ticking something off."""
    return sequence([
        (0.000, tone(NOTES["C5"], 0.070, duty=0.5, volume=0.75)),
        (0.055, tone(NOTES["E5"], 0.070, duty=0.5, volume=0.80)),
        (0.110, tone(NOTES["G5"], 0.170, duty=0.25, volume=0.95)),
        (0.130, tone(NOTES["C6"], 0.150, duty=0.125, volume=0.45)),
        (0.150, tone(NOTES["E6"], 0.120, duty=0.125, volume=0.22)),
    ])


def task_uncomplete() -> list[float]:
    """The same shape inverted -- unmistakably 'undo'."""
    return sequence([
        (0.000, tone(NOTES["G5"], 0.060, duty=0.25, volume=0.70)),
        (0.050, tone(NOTES["E5"], 0.060, duty=0.5, volume=0.60)),
        (0.100, tone(NOTES["C5"], 0.130, duty=0.5, volume=0.55, bend=-1.0)),
    ])


def task_add() -> list[float]:
    """Short upward blip. Quiet and quick -- this fires often."""
    return sequence([
        (0.000, tone(NOTES["E5"], 0.045, duty=0.25, volume=0.55)),
        (0.038, tone(NOTES["B5"], 0.090, duty=0.125, volume=0.70, bend=1.0)),
    ])


def task_delete() -> list[float]:
    """Downward bend with a crunch of noise underneath."""
    return sequence([
        (0.000, noise(0.090, volume=0.40, curve=2.4)),
        (0.000, tone(NOTES["A4"], 0.150, duty=0.5, volume=0.70, bend=-7.0)),
        (0.060, tone(NOTES["C4"], 0.110, duty=0.5, volume=0.35, bend=-3.0)),
    ])


def objective_complete() -> list[float]:
    """A small fanfare. Longer, because it is rare and worth marking."""
    lead = [
        (0.000, NOTES["C5"], 0.100), (0.090, NOTES["E5"], 0.100),
        (0.180, NOTES["G5"], 0.100), (0.270, NOTES["C6"], 0.260),
    ]
    parts: list[tuple[float, list[float]]] = []
    for at, freq, length in lead:
        parts.append((at, tone(freq, length, duty=0.25, volume=0.85)))
        parts.append((at, tone(freq / 2, length, shape="triangle", volume=0.35)))
    # Sparkle tail
    parts.append((0.300, tone(NOTES["E6"], 0.200, duty=0.125, volume=0.30)))
    parts.append((0.340, tone(NOTES["G6"], 0.220, duty=0.125, volume=0.24, vibrato=0.010)))
    parts.append((0.380, tone(NOTES["C7"], 0.240, duty=0.125, volume=0.18, vibrato=0.014)))
    return sequence(parts)


def ui_click() -> list[float]:
    """Barely-there tick for menus and buttons."""
    return sequence([
        (0.000, tone(NOTES["C6"], 0.022, duty=0.125, volume=0.45)),
    ])


EFFECTS = {
    "task_complete.wav": task_complete,
    "task_uncomplete.wav": task_uncomplete,
    "task_add.wav": task_add,
    "task_delete.wav": task_delete,
    "objective_complete.wav": objective_complete,
    "ui_click.wav": ui_click,
}


def main() -> int:
    print(f"Writing to {OUT}")
    for name, builder in EFFECTS.items():
        path = write(name, builder())
        size = path.stat().st_size
        ms = (size - 44) / 2 / RATE * 1000
        print(f"  {name:<26} {ms:6.0f} ms  {size / 1024:5.1f} KB")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
