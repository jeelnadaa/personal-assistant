"""PySide6 floating overlay window matching Figma design specs for Idle, Listening, Transcribing, and Answer states."""

import math
import sys
import threading
import time
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from jarvis.config import config
from jarvis.logger import logger
from jarvis.ui.widgets import IdlePillWidget, MicIconWidget, SpinnerWidget, WaveformBarsWidget


class AnimatedIndicator(QWidget):
    """Compatibility indicator for legacy UI tests and visual indicator rendering."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self.state = "IDLE"
        self.anim_step = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(33)

    def set_state(self, state: str) -> None:
        self.state = state.upper()
        self.update()

    def _on_tick(self) -> None:
        self.anim_step += 0.1
        if self.anim_step > 1000.0:
            self.anim_step = 0.0
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        if self.state in ("LISTENING", "IDLE"):
            pulse = (math.sin(self.anim_step * 2.0) + 1.0) / 2.0
            painter.setBrush(QColor(96, 205, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QtCore.QPointF(cx, cy), 12 + 3 * pulse, 12 + 3 * pulse)
        elif self.state in ("PROCESSING", "THINKING"):
            painter.setPen(QPen(QColor(74, 74, 74), 2.4))
            painter.drawArc(6, 6, 36, 36, 0, 360 * 16)
            angle = int(self.anim_step * 250) % 360
            spin_pen = QPen(QColor(96, 205, 255), 2.4)
            spin_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(spin_pen)
            painter.drawArc(6, 6, 36, 36, -angle * 16, 90 * 16)
        painter.end()


class OverlayBridge(QtCore.QObject):
    """Thread-safe signal dispatcher bridging worker threads with Qt GUI main thread."""

    sig_set_state = Signal((str, str), (str, str, str))  # (state, message) or (state, message, query)
    sig_confirm_request = Signal(str)
    sig_hide = Signal()
    sig_show = Signal()
    sig_set_pill_visible = Signal(bool)
    sig_open_settings = Signal()


class ActivePopupCard(QWidget):
    """440px wide dark card (#2B2B2B, border #454545) rendering Listening, Transcribing, and Answer states."""

    def __init__(self, on_close: Callable[[], None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.on_close = on_close
        self.current_answer = ""
        self.current_query = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(440)
        self.setMaximumWidth(460)

        self._drag_start_pos: QtCore.QPoint | None = None
        self._custom_positioned = False

        self._init_ui()
        self._init_shortcuts()

    def _init_ui(self) -> None:
        """Builds container layout with states: Listening, Transcribing, Answer, Confirm."""
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(8, 8, 8, 8)

        self.container = QWidget(self)
        self.container.setObjectName("popupContainer")
        self.container.setStyleSheet(
            """
            QWidget#popupContainer {
                background-color: #2B2B2B;
                border: 1px solid #454545;
                border-radius: 8px;
            }
            QLabel {
                font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)
        self.root_layout.addWidget(self.container)

        # Delegate container mouse events for effortless dragging
        self.container.mousePressEvent = self.mousePressEvent
        self.container.mouseMoveEvent = self.mouseMoveEvent
        self.container.mouseReleaseEvent = self.mouseReleaseEvent

        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 14, 16, 14)
        self.container_layout.setSpacing(8)

        # 1. Listening widget: [Mic (20x20)] [Text: 15px] [Waveform (5 bars)]
        self.listening_widget = QWidget(self)
        listen_layout = QHBoxLayout(self.listening_widget)
        listen_layout.setContentsMargins(0, 0, 0, 0)
        listen_layout.setSpacing(14)
        self.listen_mic = MicIconWidget(size=20, color="#FFFFFF", parent=self)
        self.listen_label = QLabel("Listening...", self)
        self.listen_label.setStyleSheet("font-size: 15px; color: #FFFFFF;")
        self.listen_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.waveform_bars = WaveformBarsWidget(self)
        listen_layout.addWidget(self.listen_mic, alignment=Qt.AlignmentFlag.AlignVCenter)
        listen_layout.addWidget(self.listen_label, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        listen_layout.addWidget(self.waveform_bars, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.container_layout.addWidget(self.listening_widget)

        # 2. Transcribing widget: [Spinner (20x20)] [Text: 15px]
        self.transcribing_widget = QWidget(self)
        trans_layout = QHBoxLayout(self.transcribing_widget)
        trans_layout.setContentsMargins(0, 0, 0, 0)
        trans_layout.setSpacing(14)
        self.spinner = SpinnerWidget(self)
        self.transcribe_label = QLabel("Transcribing...", self)
        self.transcribe_label.setStyleSheet("font-size: 15px; color: #FFFFFF;")
        self.transcribe_label.setWordWrap(True)
        self.transcribe_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        trans_layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignVCenter)
        trans_layout.addWidget(self.transcribe_label, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.container_layout.addWidget(self.transcribing_widget)

        # 3. Answer widget: [Query: 13px #A8A8A8] -> [Answer: 16px #FFFFFF] -> [Footer: Esc Close, Ctrl C Copy]
        self.answer_widget = QWidget(self)
        ans_layout = QVBoxLayout(self.answer_widget)
        ans_layout.setContentsMargins(0, 0, 0, 0)
        ans_layout.setSpacing(8)

        self.ans_query_label = QLabel("", self)
        self.ans_query_label.setStyleSheet("font-size: 13px; color: #A8A8A8;")
        self.ans_query_label.setWordWrap(True)
        self.ans_query_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.ans_text_label = QLabel("", self)
        self.ans_text_label.setStyleSheet("font-size: 16px; line-height: 1.45; color: #FFFFFF;")
        self.ans_text_label.setWordWrap(True)
        self.ans_text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Footer with shortcuts
        self.footer_widget = QWidget(self)
        footer_layout = QHBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(16)

        # Esc Close item
        self.close_item = QWidget(self)
        self.close_item.setCursor(Qt.CursorShape.PointingHandCursor)
        close_item_layout = QHBoxLayout(self.close_item)
        close_item_layout.setContentsMargins(0, 0, 0, 0)
        close_item_layout.setSpacing(6)
        self.tag_esc = QLabel("Esc", self.close_item)
        self.tag_esc.setFixedHeight(18)
        self.tag_esc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.tag_esc.setStyleSheet(
            "border: 1px solid #5A5A5A; border-radius: 4px; padding: 1px 5px; color: #A8A8A8; font-size: 11px;"
        )
        self.lbl_close = QLabel("Close", self.close_item)
        self.lbl_close.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_close.setStyleSheet("color: #A8A8A8; font-size: 12px;")
        close_item_layout.addWidget(self.tag_esc, alignment=Qt.AlignmentFlag.AlignVCenter)
        close_item_layout.addWidget(self.lbl_close, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.close_item.mousePressEvent = lambda e: self.close_to_idle()
        self.close_hint = self.close_item

        # Ctrl C Copy item
        self.copy_item = QWidget(self)
        self.copy_item.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_item_layout = QHBoxLayout(self.copy_item)
        copy_item_layout.setContentsMargins(0, 0, 0, 0)
        copy_item_layout.setSpacing(6)
        self.tag_copy = QLabel("Ctrl C", self.copy_item)
        self.tag_copy.setFixedHeight(18)
        self.tag_copy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.tag_copy.setStyleSheet(
            "border: 1px solid #5A5A5A; border-radius: 4px; padding: 1px 5px; color: #A8A8A8; font-size: 11px;"
        )
        self.lbl_copy = QLabel("Copy", self.copy_item)
        self.lbl_copy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_copy.setStyleSheet("color: #A8A8A8; font-size: 12px;")
        copy_item_layout.addWidget(self.tag_copy, alignment=Qt.AlignmentFlag.AlignVCenter)
        copy_item_layout.addWidget(self.lbl_copy, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.copy_item.mousePressEvent = lambda e: self.copy_answer()
        self.copy_hint = self.copy_item

        footer_layout.addWidget(self.close_item, alignment=Qt.AlignmentFlag.AlignVCenter)
        footer_layout.addWidget(self.copy_item, alignment=Qt.AlignmentFlag.AlignVCenter)
        footer_layout.addStretch()

        ans_layout.addWidget(self.ans_query_label)
        ans_layout.addWidget(self.ans_text_label)
        ans_layout.addWidget(self.footer_widget)
        self.container_layout.addWidget(self.answer_widget)

        # 4. Confirmation action widget (Allow/Deny buttons)
        self.confirm_widget = QWidget(self)
        conf_layout = QVBoxLayout(self.confirm_widget)
        conf_layout.setContentsMargins(0, 0, 0, 0)
        conf_layout.setSpacing(8)

        self.confirm_title = QLabel("Action Approval Required", self)
        self.confirm_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #60CDFF;")
        self.confirm_detail = QLabel("", self)
        self.confirm_detail.setStyleSheet("font-size: 14px; color: #FFFFFF;")
        self.confirm_detail.setWordWrap(True)

        btns_row = QWidget(self)
        btns_layout = QHBoxLayout(btns_row)
        btns_layout.setContentsMargins(0, 4, 0, 0)
        btns_layout.setSpacing(10)

        self.btn_allow = QPushButton("Allow", self)
        self.btn_allow.setStyleSheet("background: #00A86B; color: #FFF; font-weight: 600; padding: 6px 16px; border-radius: 6px; border: none;")
        self.btn_deny = QPushButton("Deny", self)
        self.btn_deny.setStyleSheet("background: #4A4A4A; color: #FFF; font-weight: 600; padding: 6px 16px; border-radius: 6px; border: 1px solid #5A5A5A;")

        btns_layout.addWidget(self.btn_allow)
        btns_layout.addWidget(self.btn_deny)
        btns_layout.addStretch()

        conf_layout.addWidget(self.confirm_title)
        conf_layout.addWidget(self.confirm_detail)
        conf_layout.addWidget(btns_row)
        self.container_layout.addWidget(self.confirm_widget)

    def _init_shortcuts(self) -> None:
        """Binds Esc to close and Ctrl+C to copy."""
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.esc_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.esc_shortcut.activated.connect(self.close_to_idle)

        self.copy_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self)
        self.copy_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.copy_shortcut.activated.connect(self.copy_answer)

        self.copy_ctrl_c = QShortcut(QKeySequence("Ctrl+C"), self)
        self.copy_ctrl_c.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.copy_ctrl_c.activated.connect(self.copy_answer)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self.setFocus()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and getattr(self, "_drag_start_pos", None):
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(new_pos)
            self._custom_positioned = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """Resets popup card to default bottom-center position on double click."""
        self._custom_positioned = False
        self.reposition_above_taskbar()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Fallback keyPress handler ensuring Esc closes and Ctrl+C copies."""
        if event.key() == Qt.Key.Key_Escape:
            self.close_to_idle()
            event.accept()
        elif event.matches(QKeySequence.StandardKey.Copy) or (
            event.key() == Qt.Key.Key_C and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.copy_answer()
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_mode(self, mode: str, text: str = "", query: str = "") -> None:
        """Switches active section: LISTENING, TRANSCRIBING, ANSWER, or CONFIRM."""
        mode_upper = mode.upper()
        self.listening_widget.hide()
        self.waveform_bars.stop()
        self.transcribing_widget.hide()
        self.spinner.stop()
        self.answer_widget.hide()
        self.confirm_widget.hide()

        if mode_upper == "LISTENING":
            self.listen_label.setText(text or "Listening...")
            self.listening_widget.show()
            self.waveform_bars.start()

        elif mode_upper in ("TRANSCRIBING", "PROCESSING", "THINKING"):
            self.transcribe_label.setText(text or "Transcribing...")
            self.transcribing_widget.show()
            self.spinner.start()

        elif mode_upper in ("ANSWER", "SPEAKING", "DONE"):
            self.current_answer = text
            self.ans_text_label.setText(text)
            display_query = query or self.current_query
            if display_query:
                self.ans_query_label.setText(display_query)
                self.ans_query_label.show()
            else:
                self.ans_query_label.hide()
            self.answer_widget.show()
            self.activateWindow()
            self.setFocus()

        elif mode_upper in ("CONFIRM", "CONFIRMING"):
            self.confirm_detail.setText(text)
            self.confirm_widget.show()

        self.root_layout.activate()
        self.container_layout.activate()
        self.adjustSize()
        self.reposition_above_taskbar()

    def reposition_above_taskbar(self) -> None:
        """Positions card horizontally centered, anchored above taskbar (or maintains custom position)."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            hint = self.sizeHint()
            w = max(self.width(), hint.width(), 440)
            h = max(self.height(), hint.height())
            if not getattr(self, "_custom_positioned", False):
                x = geo.x() + (geo.width() - w) // 2
                y = geo.y() + geo.height() - h - 16
                self.setGeometry(x, y, w, h)
            else:
                curr_x = self.x()
                curr_y = self.y()
                clamped_x = max(geo.x(), min(curr_x, geo.x() + geo.width() - w))
                clamped_y = max(geo.y(), min(curr_y, geo.y() + geo.height() - h))
                self.setGeometry(clamped_x, clamped_y, w, h)

    def close_to_idle(self) -> None:
        """Dismisses the popup card and returns to idle floating pill."""
        from jarvis.audio.tts import stop as stop_speech
        stop_speech()
        self.hide()
        if self.on_close:
            self.on_close()

    def copy_answer(self) -> None:
        """Copies assistant reply text to system clipboard and provides feedback."""
        text = self.current_answer or self.ans_text_label.text()
        if text:
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception:
                pass
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            self.tag_copy.setStyleSheet(
                "border: 1px solid #60CDFF; border-radius: 4px; padding: 1px 5px; color: #60CDFF; font-size: 11px;"
            )
            self.lbl_copy.setText("Copied!")
            self.lbl_copy.setStyleSheet("color: #60CDFF; font-size: 12px;")
            QTimer.singleShot(
                1500,
                lambda: (
                    self.tag_copy.setStyleSheet(
                        "border: 1px solid #5A5A5A; border-radius: 4px; padding: 1px 5px; color: #A8A8A8; font-size: 11px;"
                    ),
                    self.lbl_copy.setText("Copy"),
                    self.lbl_copy.setStyleSheet("color: #A8A8A8; font-size: 12px;"),
                ),
            )


class JarvisOverlay(QWidget):
    """Coordinator managing IdlePillWidget, ActivePopupCard, and safety confirmations."""

    def __init__(self, on_wake: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.bridge = OverlayBridge()
        self.bridge.sig_set_state[str, str].connect(lambda s, m: self._on_set_state(s, m, ""))
        self.bridge.sig_set_state[str, str, str].connect(self._on_set_state)
        self.bridge.sig_confirm_request.connect(self._on_confirm_request)
        self.bridge.sig_hide.connect(self.hide)
        self.bridge.sig_show.connect(self.show)
        self.bridge.sig_set_pill_visible.connect(self.set_idle_pill_visible)
        self.bridge.sig_open_settings.connect(self._show_settings_window)

        self._show_idle_pill = bool(config.get("ui", {}).get("show_idle_pill", True))
        self.current_state = "IDLE"
        self.last_query = ""
        self._settings_window: Any = None

        # Compatibility widgets for tests
        self.title_label = QLabel("Jarvis", self)
        self.detail_label = QLabel("", self)
        self.actions_widget = QWidget(self)
        self.btn_allow = QPushButton("Allow", self.actions_widget)
        self.btn_deny = QPushButton("Deny", self.actions_widget)
        self.indicator = AnimatedIndicator(self)
        self.actions_widget.hide()

        # Confirmation sync event & result
        self._confirm_event = threading.Event()
        self._confirm_result = False
        self.btn_allow.clicked.connect(self._on_allow_clicked)
        self.btn_deny.clicked.connect(self._on_deny_clicked)

        # Sub-widgets
        self.popup_card = ActivePopupCard(on_close=self._on_popup_closed)
        self.idle_pill = IdlePillWidget(
            on_wake=self._on_pill_wake,
            on_hide_pill=lambda: self.set_idle_pill_visible(False),
            on_open_settings=self.open_settings,
        )

        self.on_wake_handler = on_wake
        self.on_close_handler: Callable[[], None] | None = None
        if self._show_idle_pill:
            self.idle_pill.show()
        else:
            self.idle_pill.hide()

    def set_wake_handler(self, handler: Callable[[], None]) -> None:
        self.on_wake_handler = handler

    def set_close_handler(self, handler: Callable[[], None]) -> None:
        self.on_close_handler = handler

    def _on_pill_wake(self) -> None:
        """User clicked idle pill; starts listening."""
        if self.on_wake_handler:
            self.on_wake_handler()
        else:
            self.update_state("LISTENING", "Listening...")

    def _on_popup_closed(self) -> None:
        """Active popup was closed; transitions state to IDLE and restores idle pill."""
        self.current_state = "IDLE"
        self.title_label.setText("Jarvis")
        if self._show_idle_pill:
            self.idle_pill.show()
            self.idle_pill.position_at_bottom_center()
        if self.on_close_handler:
            try:
                self.on_close_handler()
            except Exception as e:
                logger.debug("Error in overlay on_close_handler: %s", e)

    def is_idle_pill_visible(self) -> bool:
        return self._show_idle_pill

    def set_idle_pill_visible(self, visible: bool) -> None:
        self._show_idle_pill = visible
        if self.current_state == "IDLE":
            if visible:
                self.idle_pill.show()
                self.idle_pill.position_at_bottom_center()
            else:
                self.idle_pill.hide()

    def toggle_idle_pill_visible(self) -> bool:
        self.set_idle_pill_visible(not self._show_idle_pill)
        return self._show_idle_pill

    @Slot(str, str, str)
    def _on_set_state(self, state: str, message: str = "", query: str = "") -> None:
        """Applies state changes on Qt GUI thread."""
        state_upper = state.upper()
        self.current_state = state_upper
        self.indicator.set_state(state_upper)

        state_titles = {
            "IDLE": "Jarvis",
            "LISTENING": "Listening...",
            "PROCESSING": "Thinking...",
            "TRANSCRIBING": "Thinking...",
            "SPEAKING": "Speaking",
            "CONFIRM": "Confirmation Required",
            "CONFIRMING": "Confirmation Required",
            "DONE": "Completed",
            "ERROR": "Notice",
        }
        self.title_label.setText(state_titles.get(state_upper, "Jarvis"))
        if message:
            self.detail_label.setText(message)

        if query:
            self.last_query = query
            self.popup_card.current_query = query
        elif state_upper in ("TRANSCRIBING", "PROCESSING") and message and message != "Transcribing...":
            clean_q = message.replace("Thinking: '", "").rstrip("'").replace("Thinking: ", "")
            self.last_query = clean_q
            self.popup_card.current_query = clean_q

        if state_upper == "IDLE":
            self.popup_card.hide()
            if self._show_idle_pill:
                self.idle_pill.show()
                self.idle_pill.position_at_bottom_center()
            else:
                self.idle_pill.hide()
        else:
            self.idle_pill.hide()
            self.popup_card.set_mode(state_upper, text=message, query=self.last_query)
            self.popup_card.show()
            self.popup_card.raise_()
            self.popup_card.activateWindow()
            self.popup_card.setFocus()

    @Slot(str)
    def _on_confirm_request(self, description: str) -> None:
        """Displays Allow/Deny confirmation on popup card."""
        self.current_state = "CONFIRM"
        self.indicator.set_state("CONFIRM")
        self.title_label.setText("Action Approval")
        self.detail_label.setText(f"Jarvis wants to: {description}")
        self.actions_widget.show()

        self.idle_pill.hide()
        self.popup_card.confirm_detail.setText(f"Jarvis wants to: {description}")
        self.popup_card.btn_allow.clicked.connect(self._on_allow_clicked)
        self.popup_card.btn_deny.clicked.connect(self._on_deny_clicked)
        self.popup_card.set_mode("CONFIRM", text=f"Jarvis wants to: {description}")
        self.popup_card.show()
        self.popup_card.raise_()

    def _on_allow_clicked(self) -> None:
        self._confirm_result = True
        self.actions_widget.hide()
        self._confirm_event.set()

    def _on_deny_clicked(self) -> None:
        self._confirm_result = False
        self.actions_widget.hide()
        self._confirm_event.set()

    def update_state(self, state: str, message: str = "", query: str = "") -> None:
        """Thread-safe state update entry point."""
        if query:
            self.bridge.sig_set_state[str, str, str].emit(state, message, query)
        else:
            self.bridge.sig_set_state[str, str].emit(state, message)

    def ask_confirmation(self, description: str, timeout: float = 15.0) -> bool:
        """Thread-safe blocking confirmation dialog waiting on user button click or timeout."""
        self._confirm_event.clear()
        self._confirm_result = False
        self.bridge.sig_confirm_request.emit(description)

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

        self.bridge.sig_set_state.emit("IDLE", "", "")
        return self._confirm_result

    def open_settings(self) -> None:
        """Emits thread-safe signal to open the In-App Settings window on the Qt GUI thread."""
        self.bridge.sig_open_settings.emit()

    @Slot()
    def _show_settings_window(self) -> None:
        """Instantiates and displays the SettingsWindow on the main Qt GUI thread."""
        if self._settings_window is None:
            from jarvis.ui.settings_window import SettingsWindow
            self._settings_window = SettingsWindow()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()


# Singleton holder
_OVERLAY_INSTANCE: JarvisOverlay | None = None


def get_overlay() -> JarvisOverlay:
    """Returns singleton JarvisOverlay instance, initializing QApplication if necessary."""
    global _OVERLAY_INSTANCE
    if _OVERLAY_INSTANCE is None:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        _OVERLAY_INSTANCE = JarvisOverlay()
    return _OVERLAY_INSTANCE
