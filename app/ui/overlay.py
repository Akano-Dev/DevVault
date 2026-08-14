"""The frameless always-on-top overlay window (the app's chrome).

Responsibilities kept here: window flags, dragging, edge resizing, geometry
persistence, opacity, show/hide animation. The actual quest content lives in
:class:`app.widgets.quest_panel.QuestPanelView`, which this window hosts.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ..core import painting
from ..core.theme import C, M, px
from ..services.settings import SettingsStore
from ..widgets.blossom import BlossomLayer
from ..widgets.resize_grip import ResizeGrip


class OverlayWindow(QWidget):
    """Frameless widget-style window that floats above other applications."""

    visibility_changed = Signal(bool)
    close_requested = Signal()

    def __init__(self, settings: SettingsStore) -> None:
        super().__init__(None)
        self.settings = settings

        self._drag_origin: QPoint | None = None
        self._resize_edges: Qt.Edge | None = None
        self._resize_start_geom: QRect | None = None
        self._resize_start_pos: QPoint | None = None
        self._fade: QPropertyAnimation | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_geometry)

        self.setWindowTitle("QuestPanel")
        # The panel is two floating cards with gaps between them, so the window
        # itself must be transparent -- the cards paint their own backgrounds.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.blossom = BlossomLayer(self)
        self.grip = ResizeGrip(self)
        # Set explicitly: without this the floor comes from the layout, which
        # disagreed with the value the manual-resize path clamped to.
        self.setMinimumSize(px(M.MIN_W), px(M.MIN_H))
        self.setMaximumSize(px(M.MAX_W), px(M.MAX_H))
        self._apply_flags()

        self.content = QWidget(self)
        self.content.setMouseTracking(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.content)

        self.restore_geometry()
        self.apply_opacity()

    # ------------------------------------------------------------------
    # Window flags / state
    # ------------------------------------------------------------------
    def _apply_flags(self) -> None:
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        # Tool keeps it out of the taskbar and the Alt+Tab list -- it is a
        # widget, not an application window.
        flags |= Qt.WindowType.Tool
        if self.settings.bool("always_on_top"):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_always_on_top(self, enabled: bool) -> None:
        self.settings.set("always_on_top", bool(enabled))
        was_visible = self.isVisible()
        self._apply_flags()
        if was_visible:
            self.show_overlay(animate=False)

    def apply_opacity(self) -> None:
        self.setWindowOpacity(max(0.25, min(1.0, self.settings.float("opacity"))))

    def set_content(self, widget: QWidget) -> None:
        """Swap in the real panel content."""
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.removeWidget(self.content)
        self.content.deleteLater()
        self.content = widget
        widget.setParent(self)
        widget.setMouseTracking(True)
        layout.addWidget(widget)
        self._update_margins()

    def refresh_metrics(self) -> None:
        """Re-apply scale-dependent chrome after the UI scale changes."""
        self._update_margins()
        self.update()

    def _update_margins(self) -> None:
        """Reserve a transparent ring the window itself owns.

        The content must NOT reach the window edge: children swallow their own
        mouse presses, so anything they cover can never start a resize. The
        ring is exactly the grip width, which is what makes the edges draggable
        at all.
        """
        b = px(M.RESIZE_GRIP)
        layout: QVBoxLayout = self.layout()  # type: ignore[assignment]
        layout.setContentsMargins(b, b, b, b)
        self._position_grip()

    def _position_grip(self) -> None:
        if getattr(self, "blossom", None) is not None:
            self.blossom.setGeometry(self.rect())
            self.blossom.raise_()
        if getattr(self, "grip", None) is None:
            return
        size = px(M.GRIP_VISUAL)
        self.grip.resize(size, size)
        self.grip.move(self.width() - size, self.height() - size)
        self.grip.raise_()

    def apply_effects(self) -> None:
        """Re-read the effect settings. Called on startup and from Settings."""
        self.blossom.set_enabled(self.settings.bool("blossom_enabled"))
        if self.blossom.enabled:
            self.blossom.setGeometry(self.rect())
            self.blossom.raise_()
            self.grip.raise_()

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------
    def restore_geometry(self) -> None:
        w = self.settings.int("win_w") if self.settings.bool("remember_size") else M.DEFAULT_W
        h = self.settings.int("win_h") if self.settings.bool("remember_size") else M.DEFAULT_H
        w = max(M.MIN_W, min(M.MAX_W, w))
        h = max(M.MIN_H, min(M.MAX_H, h))

        x = self.settings.int("win_x")
        y = self.settings.int("win_y")
        if not self.settings.bool("remember_position") or x < 0 or y < 0:
            x, y = self._default_position(w, h)

        self.resize(w, h)
        self.move(*self._clamp_to_screens(x, y, w, h))
        self._update_margins()

    @staticmethod
    def _default_position(w: int, h: int) -> tuple[int, int]:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 80, 80
        area = screen.availableGeometry()
        return area.right() - w - 24, area.top() + 24

    @staticmethod
    def _clamp_to_screens(x: int, y: int, w: int, h: int) -> tuple[int, int]:
        """Keep the panel reachable if a monitor was unplugged since last run."""
        rect = QRect(x, y, w, h)
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(rect):
                return x, y
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 80, 80
        area = screen.availableGeometry()
        return (
            max(area.left(), min(area.right() - w, x)),
            max(area.top(), min(area.bottom() - h, y)),
        )

    def save_geometry(self) -> None:
        if self.isMinimized():
            return
        geom = self.geometry()
        if self.settings.bool("remember_position"):
            self.settings.set("win_x", geom.x())
            self.settings.set("win_y", geom.y())
        if self.settings.bool("remember_size"):
            self.settings.set("win_w", geom.width())
            self.settings.set("win_h", geom.height())

    def _schedule_save(self) -> None:
        self._save_timer.start()

    # ------------------------------------------------------------------
    # Show / hide
    # ------------------------------------------------------------------
    def show_overlay(self, animate: bool = True) -> None:
        self.setWindowOpacity(0.0 if animate else self._target_opacity())
        self.show()
        self.raise_()
        if animate:
            self._animate_opacity(self._target_opacity())
        self.visibility_changed.emit(True)

    def hide_overlay(self, animate: bool = True) -> None:
        self.save_geometry()
        if not animate:
            self.hide()
            self.visibility_changed.emit(False)
            return
        self._animate_opacity(0.0, on_finish=self._finish_hide)

    def _finish_hide(self) -> None:
        self.hide()
        self.setWindowOpacity(self._target_opacity())
        self.visibility_changed.emit(False)

    def toggle_overlay(self) -> None:
        if self.isVisible():
            self.hide_overlay()
        else:
            self.show_overlay()

    def _target_opacity(self) -> float:
        return max(0.25, min(1.0, self.settings.float("opacity")))

    def _animate_opacity(self, to: float, on_finish=None) -> None:
        if self._fade is not None:
            self._fade.stop()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(130)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(to)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if on_finish is not None:
            anim.finished.connect(on_finish)
        anim.start()
        self._fade = anim

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        """Nothing to paint -- the cards inside draw themselves on transparency."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(M.DEFAULT_W, M.DEFAULT_H)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(M.MIN_W, M.MIN_H)

    # ------------------------------------------------------------------
    # Drag & resize
    # ------------------------------------------------------------------
    def _edges_at(self, pos: QPoint) -> Qt.Edge | None:
        """Which window edges the point is on, or None.

        The mask is accumulated as a plain int: PySide6's Qt.Edge is a flag
        enum that raises on int(), so the obvious `Qt.Edge(0)` accumulator blew
        up on every mouse move and stopped resizing before it started.
        """
        g = px(M.RESIZE_GRIP)
        mask = 0
        if pos.x() <= g:
            mask |= Qt.Edge.LeftEdge.value
        elif pos.x() >= self.width() - g:
            mask |= Qt.Edge.RightEdge.value
        if pos.y() <= g:
            mask |= Qt.Edge.TopEdge.value
        elif pos.y() >= self.height() - g:
            mask |= Qt.Edge.BottomEdge.value
        return Qt.Edge(mask) if mask else None

    @staticmethod
    def _cursor_for(edges: Qt.Edge | None):
        if edges is None:
            return Qt.CursorShape.ArrowCursor
        left = bool(edges & Qt.Edge.LeftEdge)
        right = bool(edges & Qt.Edge.RightEdge)
        top = bool(edges & Qt.Edge.TopEdge)
        bottom = bool(edges & Qt.Edge.BottomEdge)
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        pos = event.position().toPoint()
        edges = self._edges_at(pos)
        handle = self.windowHandle()
        if edges is not None:
            if handle is not None and handle.startSystemResize(edges):
                return
            self._resize_edges = edges
            self._resize_start_geom = QRect(self.geometry())
            self._resize_start_pos = event.globalPosition().toPoint()
            return
        if handle is not None and handle.startSystemMove():
            self._schedule_save()
            return
        self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self.setCursor(self._cursor_for(self._edges_at(pos)))
            return super().mouseMoveEvent(event)

        gpos = event.globalPosition().toPoint()
        if self._resize_edges is not None and self._resize_start_geom is not None:
            self._manual_resize(gpos)
        elif self._drag_origin is not None:
            self.move(gpos - self._drag_origin)

    def _manual_resize(self, gpos: QPoint) -> None:
        """Fallback path when the platform cannot do a native resize."""
        assert self._resize_start_geom is not None and self._resize_start_pos is not None
        d = gpos - self._resize_start_pos
        g = QRect(self._resize_start_geom)
        mask = self._resize_edges.value if self._resize_edges is not None else 0
        min_w = max(M.MIN_W, self.minimumWidth())
        min_h = max(M.MIN_H, self.minimumHeight())
        if mask & Qt.Edge.LeftEdge.value:
            g.setLeft(min(g.left() + d.x(), g.right() - min_w))
        if mask & Qt.Edge.RightEdge.value:
            g.setRight(max(g.right() + d.x(), g.left() + min_w))
        if mask & Qt.Edge.TopEdge.value:
            g.setTop(min(g.top() + d.y(), g.bottom() - min_h))
        if mask & Qt.Edge.BottomEdge.value:
            g.setBottom(max(g.bottom() + d.y(), g.top() + min_h))
        self.setGeometry(g)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self._resize_edges = None
        self._resize_start_geom = None
        self._resize_start_pos = None
        self._schedule_save()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.unsetCursor()
        super().leaveEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802
        self._schedule_save()
        super().moveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._schedule_save()
        self._position_grip()
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        """Closing hides to the tray; real exit goes through the tray menu."""
        self.save_geometry()
        if self.settings.bool("hide_to_tray") and not QApplication.instance().property("quitting"):
            event.ignore()
            self.hide_overlay()
            return
        event.accept()
        self.close_requested.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide_overlay()
            return
        super().keyPressEvent(event)
