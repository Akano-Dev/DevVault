"""Compact settings window in the same pixel design language."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QKeySequence, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core import painting
from ..core.hotkey import HotkeyError, parse_sequence
from ..core.theme import C, M, font, label_font, px
from ..services.settings import SettingsStore
from ..widgets.pixel_controls import (
    PixelButton,
    PixelCheckBox,
    PixelSlider,
    style_line_edit,
)

_MOD_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_unknown,
}


class HotkeyEdit(QLineEdit):
    """Captures a real key combination instead of accepting typed text."""

    captured = Signal(str)

    def __init__(self, sequence: str, parent: QWidget | None = None) -> None:
        super().__init__(sequence, parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click, then press a combination")
        style_line_edit(self)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = Qt.Key(event.key())
        if key in _MOD_KEYS:
            return
        if key == Qt.Key.Key_Escape:
            self.clearFocus()
            return

        mods = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        if not parts:
            return  # a global hotkey needs at least one modifier

        name = QKeySequence(key).toString()
        if not name:
            return
        sequence = "+".join(parts + [name])
        try:
            parse_sequence(sequence)
        except HotkeyError:
            return
        self.setText(sequence)
        self.captured.emit(sequence)


class SettingsWindow(QWidget):
    """Frameless settings panel. Emits granular signals as values change."""

    appearance_changed = Signal()
    audio_changed = Signal()
    always_on_top_changed = Signal(bool)
    hotkey_changed = Signal(str)
    closed = Signal()

    def __init__(self, settings: SettingsStore, parent: QWidget | None = None) -> None:
        super().__init__(None)
        self.settings = settings
        self._anchor = parent
        self._drag = None
        self._loading = True

        self.setWindowTitle("QuestPanel Settings")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.resize(px(340), px(470))

        b = px(M.BORDER) + px(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(b + px(8), b + px(8), b + px(8), b + px(8))
        outer.setSpacing(px(M.GAP))

        title = QLabel("SETTINGS", self)
        title.setFont(label_font(M.EYEBROW_SIZE))
        title.setStyleSheet(f"color: {C.EYEBROW.name()}; background: transparent;")
        outer.addWidget(title)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"""
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: {px(5)}px; }}
            QScrollBar::handle:vertical {{ background: {C.SEPARATOR.lighter(150).name()}; }}
            QScrollBar::add-line, QScrollBar::sub-line,
            QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
            """
        )
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, px(M.GAP), 0)
        self.body_layout.setSpacing(px(M.GAP_SMALL))
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_general()
        self._build_appearance()
        self._build_audio()
        self.body_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close = PixelButton("Close", self)
        close.setFont(font(M.TASK_SIZE))
        close.clicked.connect(self.close)
        footer.addWidget(close)
        outer.addLayout(footer)

        self._loading = False

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------
    def _heading(self, text: str) -> None:
        if self.body_layout.count():
            spacer = QWidget()
            spacer.setFixedHeight(px(M.GAP))
            self.body_layout.addWidget(spacer)
        label = QLabel(text.upper())
        label.setFont(label_font(M.SECTION_SIZE))
        label.setStyleSheet(f"color: {C.SECTION.name()}; background: transparent;")
        self.body_layout.addWidget(label)

    def _checkbox(self, text: str, key: str, on_change=None) -> PixelCheckBox:
        box = PixelCheckBox(text)
        box.setFont(font(M.TASK_SIZE))
        box.setChecked(self.settings.bool(key))

        def handler(checked: bool) -> None:
            if self._loading:
                return
            self.settings.set(key, bool(checked))
            if on_change is not None:
                on_change(bool(checked))

        box.toggled.connect(handler)
        self.body_layout.addWidget(box)
        return box

    def _slider(
        self, text: str, key: str, minimum: int, maximum: int, scale: float, on_change=None
    ) -> PixelSlider:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(M.GAP))

        caption = QLabel(text)
        caption.setFont(font(M.TASK_SIZE))
        caption.setStyleSheet(f"color: {C.TASK.name()}; background: transparent;")
        caption.setMinimumWidth(px(96))

        value_label = QLabel()
        value_label.setFont(label_font(M.SECTION_SIZE))
        value_label.setStyleSheet(f"color: {C.GREEN.name()}; background: transparent;")
        value_label.setMinimumWidth(px(34))
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        slider = PixelSlider(row)
        slider.setRange(minimum, maximum)
        slider.setValue(int(round(self.settings.float(key) / scale)))

        def handler(value: int) -> None:
            suffix = "%" if scale <= 0.01 else ""
            value_label.setText(f"{value}{suffix}")
            if self._loading:
                return
            self.settings.set(key, round(value * scale, 4))
            if on_change is not None:
                on_change()

        slider.valueChanged.connect(handler)
        handler(slider.value())

        layout.addWidget(caption)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label)
        self.body_layout.addWidget(row)
        return slider

    def _build_general(self) -> None:
        from ..services import startup

        self._heading("General")

        self.startup_box = PixelCheckBox("Start with Windows")
        self.startup_box.setFont(font(M.TASK_SIZE))
        self.startup_box.setChecked(startup.is_enabled())
        self.startup_box.setEnabled(startup.IS_WINDOWS)

        def on_startup(checked: bool) -> None:
            if self._loading:
                return
            ok = startup.set_enabled(bool(checked))
            self.settings.set("start_with_windows", bool(checked) and ok)
            if not ok:
                self.startup_box.blockSignals(True)
                self.startup_box.setChecked(startup.is_enabled())
                self.startup_box.blockSignals(False)

        self.startup_box.toggled.connect(on_startup)
        self.body_layout.addWidget(self.startup_box)

        self._checkbox("Always on Top", "always_on_top", self.always_on_top_changed.emit)
        self._checkbox("Remember Position", "remember_position")
        self._checkbox("Remember Size", "remember_size")
        self._checkbox("Close Hides to Tray", "hide_to_tray")

        caption = QLabel("GLOBAL HOTKEY")
        caption.setFont(label_font(M.SECTION_SIZE))
        caption.setStyleSheet(f"color: {C.SECTION.name()}; background: transparent;")
        self.body_layout.addWidget(caption)

        self.hotkey_edit = HotkeyEdit(self.settings.str("hotkey"))
        self.hotkey_edit.setFont(font(M.TASK_SIZE))
        self.hotkey_edit.captured.connect(self._on_hotkey_captured)
        self.body_layout.addWidget(self.hotkey_edit)

        self.hotkey_status = QLabel("")
        self.hotkey_status.setFont(label_font(M.SECTION_SIZE))
        self.hotkey_status.setStyleSheet(f"color: {C.MUTED.name()}; background: transparent;")
        self.hotkey_status.setWordWrap(True)
        self.body_layout.addWidget(self.hotkey_status)

    def _on_hotkey_captured(self, sequence: str) -> None:
        self.hotkey_changed.emit(sequence)

    def report_hotkey_result(self, ok: bool, message: str = "") -> None:
        self.hotkey_status.setText(message or ("Registered" if ok else "Unavailable"))
        color = C.GREEN if ok else C.RED
        self.hotkey_status.setStyleSheet(f"color: {color.name()}; background: transparent;")
        if not ok:
            self.hotkey_edit.setText(self.settings.str("hotkey"))

    def _build_appearance(self) -> None:
        self._heading("Appearance")
        self._slider("UI Scale", "ui_scale", 75, 200, 0.01, self.appearance_changed.emit)
        self._slider("Opacity", "opacity", 30, 100, 0.01, self.appearance_changed.emit)
        self._checkbox("Show Icons", "show_icons", lambda _: self.appearance_changed.emit())
        self._checkbox("Show Progress", "show_progress", lambda _: self.appearance_changed.emit())
        self._checkbox("Compact Mode", "compact_mode", lambda _: self.appearance_changed.emit())
        self._checkbox("Blossom Effect", "blossom_enabled",
                       lambda _: self.appearance_changed.emit())
        self._checkbox("Animations", "animations_enabled",
                       lambda _: self.appearance_changed.emit())

    def _build_audio(self) -> None:
        self._heading("Audio")
        self._checkbox("Enable Music", "music_enabled", lambda _: self.audio_changed.emit())
        self._slider("Music Volume", "music_volume", 0, 100, 0.01, self.audio_changed.emit)
        self._checkbox("Enable Sounds", "sfx_enabled", lambda _: self.audio_changed.emit())
        self._slider("Sound Volume", "sfx_volume", 0, 100, 0.01, self.audio_changed.emit)
        self._slider("Master Volume", "master_volume", 0, 100, 0.01, self.audio_changed.emit)

        self.track_label = QLabel()
        self.track_label.setWordWrap(True)
        self.track_label.setFont(font(M.SECTION_SIZE))
        self.body_layout.addWidget(self.track_label)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, px(M.GAP_SMALL), 0, 0)
        row.setSpacing(px(M.GAP))

        open_btn = PixelButton("Open Music Folder", buttons)
        open_btn.setFont(font(M.TASK_SIZE))
        open_btn.clicked.connect(self._open_music_folder)
        rescan = PixelButton("Rescan", buttons)
        rescan.setFont(font(M.TASK_SIZE))
        rescan.clicked.connect(self._rescan_music)
        row.addWidget(open_btn)
        row.addWidget(rescan)
        row.addStretch(1)
        self.body_layout.addWidget(buttons)

        note = QLabel(
            "Put .mp3/.ogg/.wav files in the music folder. Effects go one level "
            "up as task_complete.wav, objective_complete.wav, ui_click.wav "
            "(effects must be .wav). Nothing ships with QuestPanel."
        )
        note.setWordWrap(True)
        note.setFont(font(M.SECTION_SIZE))
        note.setStyleSheet(f"color: {C.MUTED.name()}; background: transparent;")
        self.body_layout.addWidget(note)
        self._refresh_tracks()

    def _refresh_tracks(self) -> None:
        from ..core.paths import user_audio_dir
        from ..services.audio import MUSIC_EXTS

        music = user_audio_dir() / "music"
        tracks = (
            sorted(p.name for p in music.iterdir() if p.suffix.lower() in MUSIC_EXTS)
            if music.is_dir() else []
        )
        if tracks:
            listed = ", ".join(tracks[:3]) + (f" (+{len(tracks) - 3} more)"
                                              if len(tracks) > 3 else "")
            self.track_label.setText(f"{len(tracks)} track(s) found: {listed}")
            color = C.GREEN
        else:
            self.track_label.setText("No music found. Click Open Music Folder and drop "
                                     "a file in, then press Rescan.")
            color = C.MUTED
        self.track_label.setStyleSheet(f"color: {color.name()}; background: transparent;")

    def _open_music_folder(self) -> None:
        from PySide6.QtGui import QDesktopServices

        from ..core.paths import user_audio_dir

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_audio_dir() / "music")))

    def _rescan_music(self) -> None:
        self._refresh_tracks()
        self.audio_changed.emit()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        painting.crisp(p)
        painting.draw_bevel_panel(p, self.rect(), thickness=px(M.BORDER))
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def show_near(self, anchor: QWidget | None) -> None:
        if anchor is not None and anchor.isVisible():
            geo = anchor.geometry()
            self.move(geo.center().x() - self.width() // 2,
                      max(20, geo.center().y() - self.height() // 2))
        self.show()
        self.raise_()
        self.activateWindow()
