"""Widget-level tests. Run with: python -m pytest tests -q"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import theme  # noqa: E402
from app.core.hotkey import HotkeyError, MOD_CONTROL, MOD_SHIFT, parse_sequence  # noqa: E402
from app.database.db import Database  # noqa: E402
from app.database.repo import Repo  # noqa: E402
from app.services.settings import SettingsStore  # noqa: E402
from app.ui.overlay import OverlayWindow  # noqa: E402
from app.ui.panel_controller import PanelController  # noqa: E402
from app.utils.dragging import try_start_drag  # noqa: E402
from app.widgets.add_row import AddRow  # noqa: E402
from app.widgets.quest_panel import QuestPanelView, _DragArea  # noqa: E402
from app.widgets.section_header import SectionHeader  # noqa: E402
from app.widgets.task_row import TaskRow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    yield app


@pytest.fixture()
def panel(qapp, tmp_path: Path):
    db = Database(tmp_path / "ui.db")
    repo = Repo(db)
    repo.seed_if_empty()
    settings = SettingsStore(db)
    view = QuestPanelView(repo, settings)
    view.resize(340, 220)
    view.reload()
    yield view, repo, settings
    view.deleteLater()
    db.close()


# ----------------------------------------------------------------------
# Hotkey parsing
# ----------------------------------------------------------------------
def test_parse_sequence_default():
    mods, key = parse_sequence("Ctrl+Shift+Q")
    assert mods & MOD_CONTROL and mods & MOD_SHIFT
    assert key == ord("Q")


def test_parse_sequence_function_key_and_case():
    mods, key = parse_sequence("alt+F9")
    assert key == 0x78  # VK_F9
    assert mods


@pytest.mark.parametrize("bad", ["Q", "", "Ctrl+", "Ctrl+Shift+NotAKey"])
def test_parse_sequence_rejects_invalid(bad):
    with pytest.raises(HotkeyError):
        parse_sequence(bad)


# ----------------------------------------------------------------------
# Panel rendering / interaction
# ----------------------------------------------------------------------
def test_panel_builds_rows_from_data(panel):
    view, _, _ = panel
    rows = view.findChildren(TaskRow)
    assert len(rows) == 4
    assert [r.task.text for r in rows][0] == "Get Tools and Items"


def test_clicking_a_row_toggles_and_persists(panel, qapp):
    view, repo, _ = panel
    controller = PanelController(view, repo, SettingsStore(repo.db), parent=view)

    row = next(r for r in view.findChildren(TaskRow) if not r.task.done)
    task_id = row.task.id
    before = view.progress.value()

    press = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPoint(5, 5),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    row.mouseReleaseEvent(press)
    qapp.processEvents()

    stored = repo.db.query_one("SELECT done FROM tasks WHERE id=?", (task_id,))
    assert stored["done"] == 1, "toggle must be written straight to SQLite"
    assert view.progress.value() > before
    assert controller is not None


def test_progress_reaches_full_and_signals_completion(panel, qapp):
    view, repo, settings = panel
    # The reference must be held: a collected controller silently disconnects.
    controller = PanelController(view, repo, settings, parent=view)
    assert controller is not None

    completed: list[int] = []
    view.objective_completed.connect(completed.append)

    for row in list(view.findChildren(TaskRow)):
        if not row.task.done:
            row.toggled.emit(row.task.id)
    qapp.processEvents()

    assert view.progress.value() == pytest.approx(1.0)
    assert view.progress_value.text() == "4/4"
    assert len(completed) == 1, "completion must fire exactly once"


def test_double_click_edits_without_leaving_the_task_toggled(panel, qapp):
    """Qt sends press/release/double-click/release -- net toggles must be zero."""
    view, repo, _ = panel
    row = next(r for r in view.findChildren(TaskRow) if not r.task.done)

    toggles: list[int] = []
    edits: list[int] = []
    row.toggled.connect(toggles.append)
    row.edit_requested.connect(edits.append)

    def event(kind):
        return QMouseEvent(kind, QPoint(80, 5), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

    row.mousePressEvent(event(QMouseEvent.Type.MouseButtonPress))
    row.mouseReleaseEvent(event(QMouseEvent.Type.MouseButtonRelease))
    row.mouseDoubleClickEvent(event(QMouseEvent.Type.MouseButtonDblClick))
    row.mouseReleaseEvent(event(QMouseEvent.Type.MouseButtonRelease))

    assert len(edits) == 1, "double-click must open the editor once"
    assert len(toggles) % 2 == 0, f"toggles must cancel out, got {len(toggles)}"


def test_single_click_still_toggles_once(panel, qapp):
    view, _, _ = panel
    row = view.findChildren(TaskRow)[0]
    toggles: list[int] = []
    row.toggled.connect(toggles.append)

    row.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPoint(80, 5),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    )
    assert len(toggles) == 1


@pytest.mark.parametrize("widget_type", ["add", "task", "section"])
def test_clickable_rows_never_leak_their_press_to_the_window_drag(panel, qapp, widget_type):
    """Regression: 'Add task' did nothing in the real app.

    QWidget ignores mouse presses by default, so the press bubbled to the
    parent drag area, which called startSystemMove(). On Windows that enters a
    native move loop which swallows the release, so the click never completed.
    This does NOT reproduce under the offscreen platform (startSystemMove is a
    no-op there), so assert the propagation invariant directly instead.
    """
    view, _, _ = panel
    widget = {
        "add": lambda: view.findChildren(AddRow)[0],
        "task": lambda: view.findChildren(TaskRow)[0],
        "section": lambda: view.findChildren(SectionHeader)[0],
    }[widget_type]()

    reached: list[str] = []
    original = _DragArea.mousePressEvent
    _DragArea.mousePressEvent = lambda self, ev: reached.append(widget_type)
    try:
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPoint(widget.width() // 2, widget.height() // 2),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(widget, event)
        assert event.isAccepted(), f"{widget_type} must accept its own press"
        assert not reached, f"{widget_type} press leaked to the window drag handler"
    finally:
        _DragArea.mousePressEvent = original


def test_drag_area_refuses_to_drag_when_the_press_hits_a_child(panel, qapp):
    """Second line of defence behind the accept() calls above."""
    view, _, _ = panel
    row = view.findChildren(TaskRow)[0]
    body = view.body

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(row.geometry().center()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert try_start_drag(body, event) is False, "must not drag from a child's position"


def test_add_task_click_reaches_the_repository(panel, qapp, monkeypatch):
    """The full path: click -> signal -> controller -> dialog -> SQLite."""
    view, repo, settings = panel
    controller = PanelController(view, repo, settings, parent=view)

    captured: dict = {}

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            captured["opened"] = True

        def adjustSize(self):
            pass

        def center_on(self, _anchor):
            pass

        def exec(self):
            from PySide6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted

        def values(self):
            return ("Mine obsidian", 2, "pickaxe")

    monkeypatch.setattr("app.ui.panel_controller.TaskDialog", FakeDialog)

    section_id = view.objective.sections[0].id
    before = view.objective.total_count

    add = next(r for r in view.findChildren(AddRow) if r.section_id == section_id)
    QTest.mouseClick(add, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, add.rect().center())
    qapp.processEvents()

    assert captured.get("opened"), "clicking Add task must open the task dialog"
    stored = repo.db.query_one("SELECT text, priority, icon FROM tasks WHERE text=?",
                               ("Mine obsidian",))
    assert stored is not None, "the new task must be written to SQLite"
    assert (stored["priority"], stored["icon"]) == (2, "pickaxe")
    assert view.objective.total_count == before + 1, "the panel must show the new task"
    assert controller is not None


def test_every_section_offers_a_visible_add_row(panel, qapp):
    """CRUD must be reachable without discovering the right-click menu."""
    view, repo, _ = panel
    add_rows = view.findChildren(AddRow)
    assert len(add_rows) == len(view.objective.sections)

    requested: list[int] = []
    view.task_add_requested.connect(requested.append)
    add_rows[0].clicked.emit(add_rows[0].section_id)
    assert requested == [view.objective.sections[0].id]


def test_header_buttons_emit_close_settings_and_add(panel, qapp):
    """The overlay has no title bar -- these are the only mouse affordances."""
    view, _, _ = panel
    card = view.header
    card.resize(380, card.height())

    rects = card._button_rects()
    assert set(rects) == {"add", "settings", "close"}
    # They must sit inside the card, or they are unclickable.
    for name, rect in rects.items():
        assert card.rect().contains(rect), f"{name} button outside the card"

    quit_calls: list[bool] = []
    hide_calls: list[bool] = []
    view.quit_requested.connect(lambda: quit_calls.append(True))
    view.hide_requested.connect(lambda: hide_calls.append(True))

    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress,
                        rects["close"].center(), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    card.mousePressEvent(press)
    assert quit_calls == [True], "the 'x' must quit the app, not hide it"
    assert hide_calls == [], "the 'x' must not merely hide the overlay"


def test_x_button_reaches_application_quit(panel, qapp):
    """The 'x' must be wired all the way through to a real shutdown."""
    view, repo, settings = panel
    controller = PanelController(view, repo, settings, parent=view)

    quits: list[bool] = []
    controller.quit_requested.connect(lambda: quits.append(True))

    view.header.quit_requested.emit()
    qapp.processEvents()
    assert quits == [True], "panel -> controller -> application quit chain is broken"


def test_header_add_falls_back_to_creating_a_section(panel, qapp):
    view, repo, _ = panel
    for section in list(view.objective.sections):
        repo.delete_section(section.id)
    view.reload()

    asked: list[str] = []
    view.section_add_requested.connect(lambda: asked.append("section"))
    view._on_header_add()
    assert asked == ["section"], "with no sections, '+' must offer to make one"


def test_unchecked_boxes_do_not_render_as_checked(qapp):
    """Regression: a default anim of 1.0 painted every box ticked."""
    from PySide6.QtGui import QImage, QPainter

    from app.core.painting import draw_reference_checkbox
    from app.core.theme import C
    from app.widgets.pixel_controls import paint_checkbox

    def green_pixels(fn, checked: bool) -> int:
        img = QImage(24, 24, QImage.Format.Format_ARGB32)
        img.fill(0xFF000000)
        p = QPainter(img)
        fn(p, QRect(2, 2, 20, 20), checked)
        p.end()
        target = C.GREEN.rgb() & 0xFFFFFF
        return sum(
            1 for y in range(24) for x in range(24)
            if (img.pixel(x, y) & 0xFFFFFF) == target
        )

    for fn in (draw_reference_checkbox, paint_checkbox):
        unchecked = green_pixels(fn, False)
        checked = green_pixels(fn, True)
        assert unchecked == 0, f"{fn.__name__} drew green on an unchecked box"
        assert checked > 0, f"{fn.__name__} drew no green on a checked box"


@pytest.fixture()
def lock_name():
    """A private socket name so these never collide with a real running app."""
    return f"QuestPanel.Test.{uuid.uuid4().hex}"


def test_single_instance_blocks_a_second_launch(qapp, lock_name):
    """A second copy must hand off instead of stacking another overlay."""
    from app.core.single_instance import SingleInstance

    # Parented to qapp so Qt owns the lifetime: a parentless QObject here is
    # collected at an arbitrary later point and took the process down with it.
    first = SingleInstance(lock_name, qapp)
    assert first.try_acquire() is True, "first instance must acquire the lock"
    try:
        second = SingleInstance(lock_name, qapp)
        assert second.try_acquire() is False, "second instance must be refused"
        second.release()
    finally:
        first.release()
        qapp.processEvents()

    # Once released, the name is free again -- otherwise a crash would lock
    # the user out of their own app permanently.
    third = SingleInstance(lock_name, qapp)
    assert third.try_acquire() is True
    third.release()
    qapp.processEvents()


def test_single_instance_notifies_the_running_copy(qapp, lock_name):
    from app.core.single_instance import SingleInstance

    first = SingleInstance(lock_name, qapp)
    assert first.try_acquire() is True
    woken: list[bool] = []
    first.activated.connect(lambda: woken.append(True))
    try:
        second = SingleInstance(lock_name, qapp)
        assert second.try_acquire() is False
        for _ in range(50):
            qapp.processEvents()
            if woken:
                break
        assert woken, "the running copy must be told to show itself"
        second.release()
    finally:
        first.release()
        qapp.processEvents()


def test_database_close_is_idempotent(tmp_path):
    """Shutdown reaches close() from more than one path.

    Regression: quitting closed the overlay, whose closeEvent re-entered
    quit(), and the second db.close() raised -- aborting the rest of the
    teardown and leaving the tray icon behind.
    """
    from app.database.db import Database

    database = Database(tmp_path / "twice.db")
    assert database.is_closed is False
    database.close()
    assert database.is_closed is True
    database.close()          # must not raise
    database.close()


def _audio_service(tmp_path):
    from app.core import paths
    from app.database.db import Database
    from app.services.audio import AudioService
    from app.services.settings import SettingsStore

    (tmp_path / "audio" / "music").mkdir(parents=True, exist_ok=True)
    original = paths.data_dir
    paths.data_dir = lambda: tmp_path
    try:
        db = Database(tmp_path / "audio.db")
        return AudioService(SettingsStore(db)), db
    finally:
        paths.data_dir = original


def test_audio_follows_the_system_default_output(qapp, tmp_path):
    """Regression: music only came out of the earphones.

    Qt pins QAudioOutput to whichever device was default when it was built, so
    starting the app with headphones plugged in routed everything there
    permanently -- unplugging them produced silence from the speakers.
    """
    from PySide6.QtMultimedia import QMediaDevices

    audio, db = _audio_service(tmp_path)
    try:
        assert audio._devices is not None, "must watch for output device changes"

        default = QMediaDevices.defaultAudioOutput()
        if default is None or default.isNull():
            pytest.skip("no audio output device on this machine")

        assert audio._ensure_player() is True
        assert audio._audio_out.device().id() == default.id(), (
            "a new player must bind to the current default device"
        )

        # A device change must be handled without raising, and must leave the
        # output pointed at the (new) default.
        audio._on_output_devices_changed()
        assert audio._audio_out.device().id() == QMediaDevices.defaultAudioOutput().id()
    finally:
        audio.shutdown()
        db.close()


def test_device_change_is_safe_before_any_player_exists(qapp, tmp_path):
    """The signal can fire at any time, including before music ever starts."""
    audio, db = _audio_service(tmp_path)
    try:
        assert audio._player is None
        audio._on_output_devices_changed()      # must not raise
    finally:
        audio.shutdown()
        db.close()


def test_all_sound_effects_ship_and_are_short(qapp, tmp_path):
    """Every effect must exist and stay small enough to preload."""
    import wave

    from app.core.paths import assets_dir
    from app.services.audio import SFX_NAMES

    audio_dir = assets_dir() / "audio"
    for key in SFX_NAMES:
        path = audio_dir / f"{key}.wav"
        assert path.is_file(), f"missing bundled effect: {path.name}"
        with wave.open(str(path)) as w:
            seconds = w.getnframes() / w.getframerate()
        # Long effects defeat QSoundEffect's in-memory decoding and feel laggy.
        assert seconds < 1.0, f"{path.name} is {seconds:.2f}s -- too long for an sfx"


def test_blossom_costs_nothing_when_disabled(qapp):
    """A decoration must not burn CPU while switched off."""
    from app.widgets.blossom import BlossomLayer

    layer = BlossomLayer()
    layer.resize(400, 220)
    assert layer._timer.isActive() is False, "must be idle before being enabled"

    layer.set_enabled(True)
    assert layer._timer.isActive() is True
    assert layer._petals, "enabling must seed petals"

    layer.set_enabled(False)
    assert layer._timer.isActive() is False, "disabling must stop the timer"
    assert layer._petals == [], "disabling must release the particles"
    layer.deleteLater()


def test_blossom_is_click_through(qapp):
    """Petals sit above the panel; they must never eat a click."""
    from app.widgets.blossom import BlossomLayer

    layer = BlossomLayer()
    assert layer.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    layer.deleteLater()


@pytest.fixture()
def overlay(qapp, tmp_path):
    """A shown overlay, torn down deterministically.

    The window must be destroyed before the database it reads from. Leaving it
    alive to be garbage collected later meant its timers and paint events
    touched a closed connection during an unrelated test, which crashed the
    interpreter outright.
    """
    from app.database.db import Database
    from app.database.repo import Repo
    from app.services.settings import SettingsStore
    from app.ui.overlay import OverlayWindow

    db = Database(tmp_path / "overlay.db")
    repo = Repo(db)
    repo.seed_if_empty()
    settings = SettingsStore(db)
    win = OverlayWindow(settings)
    win.set_content(QuestPanelView(repo, settings))
    win.resize(400, 220)
    win.show()
    qapp.processEvents()          # child geometry is not applied until shown

    yield win

    win.blossom.set_enabled(False)
    win.hide()
    win.setParent(None)
    win.deleteLater()
    qapp.processEvents()
    db.close()


def test_overlay_edges_are_reachable_for_resizing(overlay):
    """Regression: content covered the edges, so resizing was impossible.

    Children accept their own presses, so anything they cover can never start
    a resize. The window must own a ring at least as wide as the grip.
    """
    from app.core.theme import M, px

    margin = overlay.layout().contentsMargins().left()
    assert margin >= px(M.RESIZE_GRIP), "content must not cover the resize ring"

    for point in (QPoint(2, 110), QPoint(overlay.width() - 3, 110),
                  QPoint(200, 2), QPoint(200, overlay.height() - 3)):
        assert overlay.childAt(point) is None, f"a child covers the edge at {point}"
        assert overlay._edges_at(point) is not None, f"no edge detected at {point}"

    # Regression: int() on a PySide6 Qt.Edge flag raises, which killed this on
    # every mouse move.
    assert overlay._edges_at(QPoint(2, 2)) is not None
    assert overlay._edges_at(QPoint(200, 110)) is None


def test_overlay_resizes_on_both_axes(overlay):
    overlay.resize(560, 220)
    assert overlay.width() == 560, "must widen"
    overlay.resize(560, 330)
    assert overlay.height() == 330, "must grow taller"
    overlay.resize(10, 10)
    assert overlay.width() == overlay.minimumWidth()
    assert overlay.height() == overlay.minimumHeight()


def test_resize_grip_is_visible_and_in_the_corner(overlay):
    grip = overlay.grip
    assert grip.isVisible(), "the corner handle must be discoverable"
    assert overlay.rect().contains(grip.geometry())
    assert grip.geometry().right() >= overlay.width() - 2
    assert grip.geometry().bottom() >= overlay.height() - 2


def test_application_constructs_end_to_end(qapp, tmp_path, monkeypatch):
    """Build the whole app object graph.

    Regression: a signal was connected to `self.audio.play` before the audio
    service existed, so the app crashed on launch with AttributeError. Nothing
    in the suite constructed QuestPanelApp, so 48 passing tests said nothing
    about whether the program actually starts.
    """
    from app.core import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    (tmp_path / "audio" / "music").mkdir(parents=True, exist_ok=True)

    from app.application import QuestPanelApp

    controller = QuestPanelApp(qapp)
    try:
        assert controller.overlay is not None
        assert controller.panel is not None
        assert controller.audio is not None
        assert controller.tray is not None
        assert controller.panel.objective is not None, "seed data must load"

        # The signals wired in __init__ must all be live, not merely declared.
        controller.panel_controller.sound_requested.emit("task_add")
        controller.panel_controller.ui_interaction.emit()
        controller.apply_appearance()
        controller.overlay.apply_effects()
    finally:
        controller.quit()
        qapp.processEvents()


def test_ui_glyphs_are_not_offered_as_task_icons():
    from app.core.icons import ICON_NAMES, UI_GLYPHS

    assert not set(ICON_NAMES) & set(UI_GLYPHS)


def test_collapsed_section_hides_its_rows(panel, qapp):
    view, repo, _ = panel
    section_id = view.objective.sections[0].id
    repo.set_section_collapsed(section_id, True)
    view.reload()
    assert view.findChildren(TaskRow) == []


def test_empty_state_when_no_objective(panel, qapp):
    view, repo, _ = panel
    repo.delete_objective(view.objective.id)
    view.reload()
    assert view.objective is None
    assert view.progress.value() == 0.0


# ----------------------------------------------------------------------
# Overlay behaviour
# ----------------------------------------------------------------------
def test_overlay_geometry_clamps_to_a_screen(qapp, tmp_path: Path):
    db = Database(tmp_path / "geo.db")
    settings = SettingsStore(db)
    settings.set("win_x", 99999)
    settings.set("win_y", 99999)

    window = OverlayWindow(settings)
    geo = window.geometry()
    assert geo.x() < 99999 and geo.y() < 99999, "offscreen position must be pulled back"

    window.deleteLater()
    db.close()


def test_overlay_respects_always_on_top_flag(qapp, tmp_path: Path):
    db = Database(tmp_path / "top.db")
    settings = SettingsStore(db)
    settings.set("always_on_top", True)
    window = OverlayWindow(settings)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    window.set_always_on_top(False)
    assert not (window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert settings.bool("always_on_top") is False

    window.deleteLater()
    db.close()
