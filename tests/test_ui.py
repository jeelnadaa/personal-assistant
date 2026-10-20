"""Unit tests for Phase 5 UI components (Overlay, System Tray, and Confirmations)."""

import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from jarvis.safety import confirm
from jarvis.ui.overlay import AnimatedIndicator, JarvisOverlay
from jarvis.ui.tray import JarvisTray, create_tray_icon_image


@pytest.fixture(scope="session")
def qapp():
    """Initializes a shared QApplication instance for headless Qt tests."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        # Offscreen platform for headless CI / testing
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QtWidgets.QApplication(sys.argv)
    return app


def test_animated_indicator(qapp):
    """Verifies animated indicator state switching and rendering."""
    indicator = AnimatedIndicator()
    for state in ["IDLE", "LISTENING", "PROCESSING", "SPEAKING", "CONFIRM", "DONE", "ERROR"]:
        indicator.set_state(state)
        assert indicator.state == state
        # Simulate tick
        indicator._on_tick()


def test_overlay_state_transitions(qapp):
    """Verifies overlay title, labels, and widget visibility across all assistant states."""
    overlay = JarvisOverlay()

    # Listening
    overlay._on_set_state("LISTENING", "Listening for speech...")
    assert overlay.title_label.text() == "Listening..."
    assert overlay.detail_label.text() == "Listening for speech..."
    assert overlay.actions_widget.isHidden()

    # Processing / Thinking
    overlay._on_set_state("PROCESSING", "Thinking...")
    assert overlay.title_label.text() == "Thinking..."

    # Speaking
    overlay._on_set_state("SPEAKING", "Hello user!")
    assert overlay.title_label.text() == "Speaking"
    assert overlay.detail_label.text() == "Hello user!"

    # Done
    overlay._on_set_state("DONE", "All tasks complete.")
    assert overlay.title_label.text() == "Completed"

    # Idle
    overlay._on_set_state("IDLE", "")
    assert overlay.title_label.text() == "Jarvis"


def test_overlay_confirmation_buttons(qapp):
    """Verifies confirmation request displays buttons and allow/deny triggers appropriate result."""
    overlay = JarvisOverlay()

    overlay._on_confirm_request("delete file test.txt")
    assert not overlay.actions_widget.isHidden()
    assert "delete file test.txt" in overlay.detail_label.text()

    # Click Allow
    overlay._confirm_event.clear()
    overlay._on_allow_clicked()
    assert overlay._confirm_result is True
    assert overlay._confirm_event.is_set()

    # Re-trigger and click Deny
    overlay._confirm_event.clear()
    overlay._on_confirm_request("shutdown PC")
    overlay._on_deny_clicked()
    assert overlay._confirm_result is False
    assert overlay._confirm_event.is_set()


def test_tray_icon_and_menu():
    """Verifies tray icon image generation and menu actions."""
    # Active icon image
    img_active = create_tray_icon_image(size=64, active=True)
    assert img_active.size == (64, 64)
    assert img_active.mode == "RGBA"

    # Inactive icon image
    img_inactive = create_tray_icon_image(size=64, active=False)
    assert img_inactive.size == (64, 64)

    status_queried = []
    quit_called = []

    tray = JarvisTray(
        on_quit=lambda: quit_called.append(True),
        get_status_fn=lambda: "IDLE",
    )
    menu = tray._build_menu()
    assert len(menu.items) >= 6

    # Test toggle pause
    mock_icon = MagicMock()
    tray._on_toggle_pause_clicked(mock_icon, None)
    assert tray.is_paused is True
    tray._on_toggle_pause_clicked(mock_icon, None)
    assert tray.is_paused is False

    # Test stop task
    with patch("jarvis.ui.tray.cancel_current_task") as mock_cancel, patch("jarvis.ui.tray.stop_speech") as mock_stop_speech:
        tray._on_stop_task_clicked(mock_icon, None)
        assert mock_cancel.called
        assert mock_stop_speech.called

    # Test quit
    tray._on_quit_clicked(mock_icon, None)
    assert quit_called == [True]


def test_confirm_ask_overlay_integration(qapp, monkeypatch):
    """Verifies confirm.ask() hooks into overlay buttons and returns boolean user decision."""
    from jarvis.ui.overlay import get_overlay
    overlay = get_overlay()

    # Simulate user clicking Allow on the overlay after 100ms
    def auto_allow(desc):
        def click_btn():
            time.sleep(0.05)
            overlay.btn_allow.click()
        threading.Thread(target=click_btn, daemon=True).start()

    # Patch voice confirm worker so it doesn't try audio hardware
    monkeypatch.setattr("jarvis.safety.confirm._voice_confirm_worker", lambda desc, ev, res: None)

    # Trigger allow click in background thread
    def trigger():
        time.sleep(0.05)
        overlay._on_allow_clicked()

    threading.Thread(target=trigger, daemon=True).start()

    res = confirm.ask("run test tool")
    assert res is True


def test_confirm_voice_worker(monkeypatch):
    """Verifies voice confirmation worker approving on affirmative phrases."""
    confirm_event = threading.Event()
    result_box = [False]

    # Mock audio pipeline to return 'yes please'
    monkeypatch.setattr("jarvis.audio.tts.speak", lambda text, block=True: None)
    monkeypatch.setattr("jarvis.audio.mic.mic_stream.record_until_silence", lambda **kwargs: [1, 2, 3])
    monkeypatch.setattr("jarvis.audio.stt.transcribe", lambda samples: "yes go ahead")

    confirm._voice_confirm_worker("dangerous action", confirm_event, result_box)

    assert confirm_event.is_set()
    assert result_box[0] is True


def test_idle_pill_widget(qapp):
    """Verifies floating idle pill dimension (52x28), wake callback, and hide/show visibility."""
    woken = []
    hidden = []
    from jarvis.ui.widgets import IdlePillWidget
    pill = IdlePillWidget(on_wake=lambda: woken.append(True), on_hide_pill=lambda: hidden.append(True))
    assert pill.width() == 52
    assert pill.height() == 28

    # Simulate click without drag
    pill._has_dragged = False
    pill.mouseReleaseEvent(QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonRelease,
        QtCore.QPointF(26, 14),
        QtCore.QPointF(26, 14),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    ))
    assert woken == [True]


def test_new_popup_states_and_design(qapp):
    """Verifies Listening, Transcribing, and Answer card states matching exact Figma specs."""
    overlay = JarvisOverlay()

    # 1. Listening State
    overlay._on_set_state("LISTENING", "What's the weather like in Beng")
    assert not overlay.popup_card.listening_widget.isHidden()
    assert overlay.popup_card.transcribing_widget.isHidden()
    assert overlay.popup_card.answer_widget.isHidden()
    assert overlay.popup_card.listen_label.text() == "What's the weather like in Beng"
    assert overlay.idle_pill.isHidden()

    # 2. Transcribing State
    overlay._on_set_state("TRANSCRIBING", "What's the weather like in Bengaluru today?")
    assert overlay.popup_card.listening_widget.isHidden()
    assert not overlay.popup_card.transcribing_widget.isHidden()
    assert overlay.popup_card.answer_widget.isHidden()
    assert overlay.popup_card.transcribe_label.text() == "What's the weather like in Bengaluru today?"

    # 3. Answer State
    overlay._on_set_state(
        "SPEAKING",
        "It's sunny and around 28°C in Bengaluru right now.",
        query="What's the weather like in Bengaluru today?",
    )
    assert overlay.popup_card.listening_widget.isHidden()
    assert overlay.popup_card.transcribing_widget.isHidden()
    assert not overlay.popup_card.answer_widget.isHidden()
    assert overlay.popup_card.ans_query_label.text() == "What's the weather like in Bengaluru today?"
    assert "28°C" in overlay.popup_card.ans_text_label.text()
    assert not overlay.popup_card.close_hint.isHidden()
    assert not overlay.popup_card.copy_hint.isHidden()


def test_answer_esc_key_closes_to_idle(qapp):
    """Verifies Esc shortcut closes Answer card and restores the Idle floating pill."""
    overlay = JarvisOverlay()
    overlay.set_idle_pill_visible(True)

    overlay._on_set_state("SPEAKING", "Test answer content", query="Test question?")
    assert not overlay.popup_card.isHidden()
    assert overlay.idle_pill.isHidden()

    # Trigger close to idle (Esc action)
    overlay.popup_card.close_to_idle()
    assert overlay.popup_card.isHidden()
    assert not overlay.idle_pill.isHidden()
    assert overlay.current_state == "IDLE"


def test_answer_ctrl_c_copies_to_clipboard(qapp):
    """Verifies Ctrl+C copies assistant response to the system clipboard."""
    import pyperclip
    overlay = JarvisOverlay()
    answer_text = "Here is the copied text for testing clipboard functionality."
    overlay._on_set_state("SPEAKING", answer_text, query="Copy test")

    overlay.popup_card.copy_answer()
    assert (
        QtWidgets.QApplication.clipboard().text() == answer_text
        or pyperclip.paste() == answer_text
    )


def test_wake_word_barge_in_during_transcribing():
    """Verifies saying wake word during Transcribing cancels previous task and switches to LISTENING."""
    from jarvis.app import AppState, JarvisApp

    state_history = []
    app = JarvisApp(ui_callback=lambda st, msg, *args: state_history.append(st), enable_tray=False)
    app.state = AppState.PROCESSING  # Transcribing / thinking state
    initial_turn = app.turn_counter

    # Mock audio pipeline so worker thread doesn't record hardware audio
    with patch("jarvis.app.mic_stream.record_until_silence", return_value=None), \
         patch("jarvis.app.warmup_wake_greetings"):
        app._on_wake_detected()

    assert app.turn_counter == initial_turn + 1
    # State switches to LISTENING
    assert app.state == AppState.LISTENING

