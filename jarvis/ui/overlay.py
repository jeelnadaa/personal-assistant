"""PySide6 floating overlay window for Jarvis status, transcript, and confirmation."""

import math
import sys
import threading
import time
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.config import config
from jarvis.logger import logger


class AnimatedIndicator(QWidget):
    """Custom paint widget rendering animated state icons (pulsing orb, spinner, waveform)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self.state = "IDLE"
        self.anim_step = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(33)  # ~30 FPS

    def set_state(self, state: str) -> None:
        """Updates animation mode based on assistant state."""
        self.state = state.upper()
        self.update()

    def _on_tick(self) -> None:
        """Advances animation counters."""
        self.anim_step += 0.1
        if self.anim_step > 1000.0:
            self.anim_step = 0.0
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paints state-specific visual graphics."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2

        if self.state in ("LISTENING", "IDLE"):
            # Pulsing blue orb
            pulse = (math.sin(self.anim_step * 2.0) + 1.0) / 2.0  # 0.0 to 1.0
            r_outer = 16 + 5 * pulse
            r_inner = 10 + 2 * pulse

            # Outer glow
            grad = QtGui.QRadialGradient(cx, cy, r_outer)
            grad.setColorAt(0.0, QColor(0, 195, 255, int(180 * (1.0 - 0.3 * pulse))))
            grad.setColorAt(1.0, QColor(0, 110, 255, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QtCore.QPointF(cx, cy), r_outer, r_outer)

            # Core
            painter.setBrush(QColor(120, 225, 255))
            painter.drawEllipse(QtCore.QPointF(cx, cy), r_inner, r_inner)

        elif self.state in ("PROCESSING", "THINKING"):
            # Rotating cyan spinner arc
            painter.setPen(QPen(QColor(255, 255, 255, 30), 3))
            painter.drawArc(6, 6, 36, 36, 0, 360 * 16)

            angle = int(self.anim_step * 250) % 360
            spin_pen = QPen(QColor(0, 210, 255), 3)
            spin_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(spin_pen)
            painter.drawArc(6, 6, 36, 36, -angle * 16, 100 * 16)

        elif self.state == "SPEAKING":
            # Animated equalizer waveform bars
            bar_count = 5
            spacing = 7
            start_x = cx - ((bar_count - 1) * spacing) / 2
            painter.setPen(Qt.PenStyle.NoPen)

            for i in range(bar_count):
                bar_h = 6 + 18 * abs(math.sin(self.anim_step * 2.5 + i * 0.8))
                x = start_x + i * spacing - 2
                y = cy - bar_h / 2
                painter.setBrush(QColor(0, 230, 255, 230))
                painter.drawRoundedRect(QtCore.QRectF(x, y, 4, bar_h), 2, 2)

        elif self.state in ("CONFIRM", "CONFIRMING"):
            # Amber alert shield / diamond
            painter.setBrush(QColor(255, 170, 0, 40))
            painter.setPen(QPen(QColor(255, 180, 0), 2))
            points = [
                QtCore.QPointF(cx, cy - 16),
                QtCore.QPointF(cx + 14, cy - 6),
                QtCore.QPointF(cx + 10, cy + 14),
                QtCore.QPointF(cx, cy + 18),
                QtCore.QPointF(cx - 10, cy + 14),
                QtCore.QPointF(cx - 14, cy - 6),
            ]
            painter.drawPolygon(points)
            painter.setPen(QPen(QColor(255, 220, 100), 2))
            painter.drawLine(QtCore.QPointF(cx, cy - 7), QtCore.QPointF(cx, cy + 3))
            painter.drawPoint(QtCore.QPointF(cx, cy + 8))

        elif self.state == "DONE":
            # Green success circle with checkmark
            painter.setBrush(QColor(0, 210, 120, 40))
            painter.setPen(QPen(QColor(0, 220, 120), 2))
            painter.drawEllipse(QtCore.QPointF(cx, cy), 16, 16)
            painter.drawLine(QtCore.QPointF(cx - 7, cy), QtCore.QPointF(cx - 2, cy + 5))
            painter.drawLine(QtCore.QPointF(cx - 2, cy + 5), QtCore.QPointF(cx + 7, cy - 5))

        elif self.state == "ERROR":
            # Red error circle with exclamation
            painter.setBrush(QColor(255, 60, 60, 40))
            painter.setPen(QPen(QColor(255, 70, 70), 2))
            painter.drawEllipse(QtCore.QPointF(cx, cy), 16, 16)
            painter.drawLine(QtCore.QPointF(cx, cy - 7), QtCore.QPointF(cx, cy + 2))
            painter.drawPoint(QtCore.QPointF(cx, cy + 7))

        painter.end()


class OverlayBridge(QtCore.QObject):
    """Thread-safe signal dispatcher bridging agent worker threads with Qt GUI main thread."""

    sig_set_state = Signal(str, str)
    sig_confirm_request = Signal(str)
    sig_hide = Signal()
    sig_show = Signal()


class JarvisOverlay(QWidget):
    """Sleek, translucent, always-on-top bottom-center overlay widget."""

    def __init__(self) -> None:
        super().__init__()

        self.bridge = OverlayBridge()
        self.bridge.sig_set_state.connect(self._on_set_state)
        self.bridge.sig_confirm_request.connect(self._on_confirm_request)
        self.bridge.sig_hide.connect(self.hide)
        self.bridge.sig_show.connect(self.show)

        # Confirmation sync event & result
        self._confirm_event = threading.Event()
        self._confirm_result = False

        self._init_ui()
        self._position_overlay()

        # Auto-fade timer for DONE state
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def _init_ui(self) -> None:
        """Initializes window flags, styles, layout, and child widgets."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.setFixedSize(440, 130)

        # Dark modern glassmorphic card container
        self.container = QWidget(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet(
            """
            QWidget#container {
                background-color: rgba(16, 20, 28, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 16px;
                border-radius: 8px;
            }
            QPushButton#btnAllow {
                background-color: #00A86B;
                color: white;
                border: none;
            }
            QPushButton#btnAllow:hover {
                background-color: #00C880;
            }
            QPushButton#btnDeny {
                background-color: rgba(255, 255, 255, 0.12);
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            QPushButton#btnDeny:hover {
                background-color: #D32F2F;
                color: white;
            }
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.container.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(self.container)

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(14, 14, 14, 14)
        container_layout.setSpacing(12)

        # Left graphic indicator
        self.indicator = AnimatedIndicator(self)
        container_layout.addWidget(self.indicator, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Center/Right text and actions layout
        self.text_vbox = QVBoxLayout()
        self.text_vbox.setSpacing(4)
        self.text_vbox.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Header title
        self.title_label = QLabel("Jarvis", self)
        font_title = QFont("Segoe UI", 11, QFont.Weight.Bold)
        self.title_label.setFont(font_title)
        self.title_label.setStyleSheet("color: #00D2FF;")
        self.text_vbox.addWidget(self.title_label)

        # Subtitle / transcript / detail text
        self.detail_label = QLabel("Ready", self)
        font_detail = QFont("Segoe UI", 10)
        self.detail_label.setFont(font_detail)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: rgba(255, 255, 255, 0.85);")
        self.text_vbox.addWidget(self.detail_label)

        # Action button row (for confirmation)
        self.actions_widget = QWidget(self)
        actions_layout = QHBoxLayout(self.actions_widget)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        self.btn_allow = QPushButton("Allow", self)
        self.btn_allow.setObjectName("btnAllow")
        self.btn_allow.clicked.connect(self._on_allow_clicked)
        actions_layout.addWidget(self.btn_allow)

        self.btn_deny = QPushButton("Deny", self)
        self.btn_deny.setObjectName("btnDeny")
        self.btn_deny.clicked.connect(self._on_deny_clicked)
        actions_layout.addWidget(self.btn_deny)

        self.actions_widget.hide()
        self.text_vbox.addWidget(self.actions_widget)

        container_layout.addLayout(self.text_vbox)

    def _position_overlay(self) -> None:
        """Positions overlay at the bottom center of the primary display screen."""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + screen_geo.height() - self.height() - 36
            self.move(x, y)

    @Slot(str, str)
    def _on_set_state(self, state: str, message: str) -> None:
        """Applies state changes on the Qt GUI thread."""
        state_upper = state.upper()
        self.indicator.set_state(state_upper)

        state_titles = {
            "IDLE": "Jarvis",
            "LISTENING": "Listening...",
            "PROCESSING": "Thinking...",
            "SPEAKING": "Speaking",
            "CONFIRM": "Confirmation Required",
            "CONFIRMING": "Confirmation Required",
            "DONE": "Completed",
            "ERROR": "Notice",
        }
        title = state_titles.get(state_upper, "Jarvis")
        self.title_label.setText(title)

        if message:
            self.detail_label.setText(message)

        # Reset button visibility if leaving confirm state
        if state_upper not in ("CONFIRM", "CONFIRMING"):
            self.actions_widget.hide()

        if state_upper == "IDLE":
            self.hide()
        else:
            self.show()
            self.raise_()

        # Auto-hide after timeout if DONE
        if state_upper == "DONE":
            timeout_sec = float(config.get("ui", {}).get("overlay_timeout_seconds", 4))
            self.hide_timer.start(int(timeout_sec * 1000))

    @Slot(str)
    def _on_confirm_request(self, description: str) -> None:
        """Displays Allow/Deny confirmation buttons with action summary."""
        self.indicator.set_state("CONFIRM")
        self.title_label.setText("Action Approval")
        self.detail_label.setText(f"Jarvis wants to: {description}")
        self.actions_widget.show()
        self.show()
        self.raise_()

    def _on_allow_clicked(self) -> None:
        """Handles user clicking Allow."""
        self._confirm_result = True
        self.actions_widget.hide()
        self._confirm_event.set()

    def _on_deny_clicked(self) -> None:
        """Handles user clicking Deny."""
        self._confirm_result = False
        self.actions_widget.hide()
        self._confirm_event.set()

    def update_state(self, state: str, message: str = "") -> None:
        """Thread-safe state update entry point."""
        self.bridge.sig_set_state.emit(state, message)

    def ask_confirmation(self, description: str, timeout: float = 15.0) -> bool:
        """Thread-safe blocking confirmation dialog waiting on user button click or timeout."""
        self._confirm_event.clear()
        self._confirm_result = False

        self.bridge.sig_confirm_request.emit(description)

        # Wait for user click or timeout (pump Qt events if on main thread)
        is_main_thread = threading.current_thread() is threading.main_thread()
        app = QApplication.instance()
        if is_main_thread and app is not None:
            start_time = time.perf_counter()
            approved = False
            while time.perf_counter() - start_time < timeout:
                app.processEvents()
                if self._confirm_event.is_set():
                    approved = True
                    break
                time.sleep(0.02)
        else:
            approved = self._confirm_event.wait(timeout=timeout)

        if not approved:
            logger.info("Confirmation timed out after %.1fs. Denying action.", timeout)
            self._confirm_result = False

        # Hide actions after decision
        self.bridge.sig_set_state.emit("IDLE", "")
        return self._confirm_result


# Singleton holder
_OVERLAY_INSTANCE: JarvisOverlay | None = None


def get_overlay() -> JarvisOverlay:
    """Returns singleton JarvisOverlay instance, initializing QApplication if necessary."""
    global _OVERLAY_INSTANCE
    if _OVERLAY_INSTANCE is None:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        _OVERLAY_INSTANCE = JarvisOverlay()
    return _OVERLAY_INSTANCE
