"""Optional local audio.

Every asset is optional. If ``assets/audio`` is empty -- which it is by
default, since no Mojang audio may be redistributed -- every method here is a
silent no-op and the application behaves exactly as before.

Expected (user-supplied) layout::

    assets/audio/task_complete.wav
    assets/audio/objective_complete.wav
    assets/audio/ui_click.wav
    assets/audio/music/*.ogg|*.mp3|*.wav
"""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from ..core.paths import audio_search_dirs, user_audio_dir
from .settings import SettingsStore

SFX_NAMES = {
    "task_complete": ("task_complete", "task-complete", "complete"),
    "task_uncomplete": ("task_uncomplete", "task-uncomplete", "uncheck"),
    "task_add": ("task_add", "task-add", "add"),
    "task_delete": ("task_delete", "task-delete", "delete"),
    "objective_complete": ("objective_complete", "objective-complete", "quest_complete"),
    "ui_click": ("ui_click", "ui-click", "click"),
    "timer_start": ("timer_start", "timer-start"),
    "timer_pause": ("timer_pause", "timer-pause"),
    "timer_done": ("timer_done", "timer-done", "timer"),
}
SFX_EXTS = (".wav",)
MUSIC_EXTS = (".ogg", ".mp3", ".wav", ".flac", ".m4a")


class AudioService(QObject):
    """Thin wrapper over Qt Multimedia that fails soft in every direction."""

    def __init__(self, settings: SettingsStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._effects: dict[str, object] = {}
        self._player = None
        self._audio_out = None
        self._playlist: list[Path] = []
        self._devices = None
        self._available = self._probe_multimedia()
        if self._available:
            self._watch_output_devices()
            self._load_effects()

    # ------------------------------------------------------------------
    # Output device tracking
    # ------------------------------------------------------------------
    def _watch_output_devices(self) -> None:
        """Follow the system default output when headphones come and go.

        Qt binds QAudioOutput and QSoundEffect to whichever device was default
        at construction time and never revisits that choice. Starting the app
        with earphones plugged in therefore pinned every sound to the earphones
        -- unplugging them left playback going to a device that was no longer
        there, and nothing came out of the speakers.
        """
        try:
            from PySide6.QtMultimedia import QMediaDevices
        except ImportError:  # pragma: no cover
            return
        # Held as an attribute: a temporary would be collected and the signal
        # would never arrive.
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._on_output_devices_changed)

    @staticmethod
    def _default_output():
        from PySide6.QtMultimedia import QMediaDevices

        return QMediaDevices.defaultAudioOutput()

    def _on_output_devices_changed(self) -> None:
        """Re-point music and effects at the new default device."""
        device = self._default_output()
        if device is None or device.isNull():
            return

        for effect in self._effects.values():
            try:
                effect.setAudioDevice(device)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - device races
                pass

        if self._audio_out is None or self._player is None:
            return
        if self._audio_out.device().id() == device.id():
            return

        # Re-binding drops the audio stream, so resume where we left off
        # instead of restarting the track from the beginning.
        was_playing = self._is_playing()
        position = self._player.position()
        self._audio_out.setDevice(device)
        if was_playing:
            self._player.play()
            if position > 0:
                self._player.setPosition(position)

    # ------------------------------------------------------------------
    @staticmethod
    def _probe_multimedia() -> bool:
        try:
            import PySide6.QtMultimedia  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    def _find_sfx(self, key: str) -> Path | None:
        for base in audio_search_dirs():
            if not base.is_dir():
                continue
            for stem in SFX_NAMES.get(key, (key,)):
                for ext in SFX_EXTS:
                    path = base / f"{stem}{ext}"
                    if path.is_file():
                        return path
        return None

    def _load_effects(self) -> None:
        from PySide6.QtMultimedia import QSoundEffect

        for key in SFX_NAMES:
            path = self._find_sfx(key)
            if path is None:
                continue
            device = self._default_output()
            effect = (
                QSoundEffect(device, self)
                if device is not None and not device.isNull()
                else QSoundEffect(self)
            )
            effect.setSource(QUrl.fromLocalFile(str(path)))
            self._effects[key] = effect

    def _sfx_volume(self) -> float:
        if not self.settings.bool("sfx_enabled"):
            return 0.0
        return max(0.0, min(1.0, self.settings.float("sfx_volume")
                            * self.settings.float("master_volume")))

    def play(self, key: str) -> None:
        """Play a one-shot effect. Missing file or disabled setting -> no-op."""
        effect = self._effects.get(key)
        if effect is None:
            return
        volume = self._sfx_volume()
        if volume <= 0.0:
            return
        try:
            effect.setVolume(volume)  # type: ignore[attr-defined]
            effect.play()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - audio device failures
            pass

    # ------------------------------------------------------------------
    # Music
    # ------------------------------------------------------------------
    def music_files(self) -> list[Path]:
        """Every playable track across the user folder and the bundled folder."""
        found: list[Path] = []
        seen: set[str] = set()
        for base in audio_search_dirs():
            music = base / "music"
            if not music.is_dir():
                continue
            for path in sorted(music.iterdir()):
                if path.suffix.lower() in MUSIC_EXTS and path.name.lower() not in seen:
                    seen.add(path.name.lower())
                    found.append(path)
        return found

    def _music_volume(self) -> float:
        if not self.settings.bool("music_enabled"):
            return 0.0
        return max(0.0, min(1.0, self.settings.float("music_volume")
                            * self.settings.float("master_volume")))

    def _ensure_player(self) -> bool:
        if self._player is not None:
            return True
        if not self._available:
            return False
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:  # pragma: no cover
            return False
        self._audio_out = QAudioOutput(self)
        # Bind explicitly to the current default rather than trusting whatever
        # Qt cached, so playback starts on the device in use right now.
        device = self._default_output()
        if device is not None and not device.isNull():
            self._audio_out.setDevice(device)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        return True

    def _on_media_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._next_track()

    def _next_track(self) -> None:
        if not self._playlist or self._player is None:
            return
        track = random.choice(self._playlist) if len(self._playlist) > 1 else self._playlist[0]
        self._player.setSource(QUrl.fromLocalFile(str(track)))
        self._player.play()

    def start_music(self) -> None:
        """Rescan the music folder and begin playback.

        Rescanning here means dropping a file in and toggling music off/on
        picks it up without restarting the app.
        """
        if self._music_volume() <= 0.0:
            return
        self._playlist = self.music_files()
        if not self._playlist or not self._ensure_player():
            return
        self._audio_out.setVolume(self._music_volume())  # type: ignore[union-attr]
        self._next_track()

    def stop_music(self) -> None:
        if self._player is not None:
            self._player.stop()

    def _is_playing(self) -> bool:
        if self._player is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer

        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def apply_settings(self) -> None:
        """Re-read volumes; start or stop music to match the new state."""
        volume = self._music_volume()
        if volume <= 0.0:
            self.stop_music()
            return
        if not self._is_playing():
            self.start_music()
        elif self._audio_out is not None:
            self._audio_out.setVolume(volume)

    def shutdown(self) -> None:
        self.stop_music()
