"""Custom painting widgets for Jarvis UI: microphone icon, waveform bars, spinner, and floating idle pill."""

import math
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget


class MicIconWidget(QWidget):
    """Paints the vector microphone SVG icon (24x24 viewBox scaled to widget size)."""

    def __init__(self, size: int = 20, color: str = "#FFFFFF", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_size = size
        self.icon_color = QColor(color)
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        """Updates stroke color and redraws."""
        self.icon_color = QColor(color)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Draws microphone body, lower arc, and stem."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = self.icon_size / 24.0
        painter.scale(scale, scale)

        pen = QPen(self.icon_color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Body: rect x=9, y=3, width=6, height=11, rx=3
        painter.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        # Arc: path d="M5 11a7 7 0 0 0 14 0"
        painter.drawArc(QRectF(5, 4, 14, 14), 0, -180 * 16)
        # Stem: path d="M12 18v3"
        painter.drawLine(QPointF(12, 18), QPointF(12, 21))
        painter.end()


class WaveformBarsWidget(QWidget):
    """5-bar animated equalizer in #60CDFF for active listening state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(22, 20)
        self.step = 0.0
        self.base_heights = [6.0, 14.0, 20.0, 10.0, 16.0]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        """Starts bar height oscillation."""
        if not self.timer.isActive():
            self.timer.start(33)

    def stop(self) -> None:
        """Stops oscillation and resets bars."""
        self.timer.stop()
        self.update()

    def _on_tick(self) -> None:
        self.step += 0.2
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Draws 5 vertical cyan bars with smooth sine-wave height modulation."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#60CDFF"))

        bar_w = 2.0
        gap = 3.0
        center_y = 10.0

        for i, base_h in enumerate(self.base_heights):
            if self.timer.isActive():
                mod = (math.sin(self.step * 2.2 + i * 1.2) + 1.0) / 2.0
                h = 4.0 + (base_h - 4.0) * (0.35 + 0.65 * mod)
            else:
                h = base_h
            x = i * (bar_w + gap)
            y = center_y - (h / 2.0)
            painter.drawRect(QRectF(x, y, bar_w, h))
        painter.end()


class SpinnerWidget(QWidget):
    """20x20 rotating circle spinner: #4A4A4A track circle and #60CDFF rotating arc."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        """Starts spinner rotation."""
        if not self.timer.isActive():
            self.timer.start(33)

    def stop(self) -> None:
        """Stops spinner rotation."""
        self.timer.stop()
        self.update()

    def _on_tick(self) -> None:
        self.angle = (self.angle + 12) % 360
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paints static background circle track and rotating active arc."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = 20.0 / 24.0
        painter.scale(scale, scale)

        # Track circle: cx=12, cy=12, r=9, stroke=#4A4A4A, width=2.4
        pen_track = QPen(QColor("#4A4A4A"), 2.4)
        painter.setPen(pen_track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(3, 3, 18, 18))

        # Rotating arc: stroke=#60CDFF, 90-deg span
        pen_arc = QPen(QColor("#60CDFF"), 2.4)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        start_angle = (-self.angle + 90) * 16
        span_angle = -90 * 16
        painter.drawArc(QRectF(3, 3, 18, 18), start_angle, span_angle)
        painter.end()


class IdlePillWidget(QWidget):
    """Floating 52x28 capsule widget (#2B2B2B, border #454545, mic icon) above taskbar."""

    def __init__(
        self,
        on_wake: Callable[[], None] | None = None,
        on_hide_pill: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_wake = on_wake
        self.on_hide_pill = on_hide_pill
        self.on_open_settings = on_open_settings

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(52, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._drag_start_pos: QPoint | None = None
        self._has_dragged = False

        self.position_at_bottom_center()

    def position_at_bottom_center(self) -> None:
        """Centers pill horizontally ~60px from the primary screen's bottom."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() - self.height() - 16
            self.move(x, y)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paints 52x28 capsule with 14px radius, #2B2B2B fill, #454545 border, and centered mic."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setBrush(QColor("#2B2B2B"))
        painter.setPen(QPen(QColor("#454545"), 1.0))
        painter.drawRoundedRect(rect, 14.0, 14.0)

        # Centered 16x16 mic icon with #BDBDBD stroke
        painter.save()
        painter.translate((self.width() - 16) / 2.0, (self.height() - 16) / 2.0)
        scale = 16.0 / 24.0
        painter.scale(scale, scale)

        pen = QPen(QColor("#BDBDBD"), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        painter.drawArc(QRectF(5, 4, 14, 14), 0, -180 * 16)
        painter.drawLine(QPointF(12, 18), QPointF(12, 21))
        painter.restore()
        painter.end()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Records initial drag position on left button; opens context menu on right button."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._has_dragged = False
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Enables user to drag the floating pill freely on screen."""
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_pos:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            if (new_pos - self.pos()).manhattanLength() > 3:
                self._has_dragged = True
            self.move(new_pos)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Triggers wake listening if user clicked without dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._has_dragged and self.on_wake:
                self.on_wake()
            self._drag_start_pos = None

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """Resets pill to bottom center on double click."""
        self.position_at_bottom_center()

    def _show_context_menu(self, pos: QPoint) -> None:
        """Context menu to wake, hide pill, or configure."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #2B2B2B; color: #FFFFFF; border: 1px solid #454545; border-radius: 6px; padding: 4px; }"
            "QMenu::item:selected { background: #3B4048; border-radius: 4px; }"
        )
        wake_act = menu.addAction("Wake Jarvis")
        hide_act = menu.addAction("Hide Floating Pill")
        menu.addSeparator()
        settings_act = menu.addAction("Settings...")
        reset_act = menu.addAction("Reset Position")

        action = menu.exec(pos)
        if action == wake_act and self.on_wake:
            self.on_wake()
        elif action == hide_act and self.on_hide_pill:
            self.on_hide_pill()
        elif action == settings_act and self.on_open_settings:
            self.on_open_settings()
        elif action == reset_act:
            self.position_at_bottom_center()
