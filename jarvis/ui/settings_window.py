"""Centralized, modern In-App Settings window matching the Jarvis dark Figma design system."""

import os
from pathlib import Path
import sys
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.logger import logger
from jarvis.models.discovery import (
    copy_to_clipboard,
    discover_local_llm_models,
    discover_local_stt_models,
    discover_piper_voices,
    ensure_model_directories,
    get_llm_models_dir,
    get_piper_models_dir,
    get_stt_models_dir,
    open_folder_in_explorer,
)
from jarvis.security.vault import get_secret, get_user_data_dir, has_secret, mask_secret, set_secret
from jarvis.settings import settings
from jarvis.system.hardware import get_hardware_diagnostics


class SettingsWindow(QWidget):
    """Modern dark-themed Settings window with categorized tabs, model discovery, and diagnostics."""

    def __init__(self, on_restart_requested: Callable[[], None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.on_restart_requested = on_restart_requested
        self.setWindowTitle("Jarvis Assistant - Settings")
        self.resize(840, 620)
        self.setMinimumSize(780, 560)

        # Ensure directories exist
        ensure_model_directories()

        self._init_window_flags()
        self._init_ui()
        self._load_current_values()

    def _init_window_flags(self) -> None:
        """Applies dark window palette and high-DPI scaling flags."""
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1E1E1E;
                color: #FFFFFF;
                font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            }
            QScrollBar:vertical {
                border: none;
                background: #181818;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3B4048;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #505864;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #2B2B2B;
                border: 1px solid #454545;
                border-radius: 6px;
                padding: 6px 10px;
                color: #FFFFFF;
                font-size: 13px;
                selection-background-color: #60CDFF;
                selection-color: #000000;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #60CDFF;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #2B2B2B;
                border: 1px solid #454545;
                color: #FFFFFF;
                selection-background-color: #3B4048;
                padding: 4px;
            }
            """
        )

    def _init_ui(self) -> None:
        """Constructs layout: Left Sidebar Navigation + Right Stacked Pages + Footer Actions."""
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header Title Bar
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 4)
        title = QLabel("Jarvis Settings", self)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFFFFF;")
        subtitle = QLabel("Configure providers, voices, models, and credentials", self)
        subtitle.setStyleSheet("font-size: 12px; color: #8C8C8C;")
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(subtitle)
        header.addStretch()

        root.addLayout(header)

        # Restart Alert Banner (hidden by default)
        self.restart_banner = QFrame(self)
        self.restart_banner.setStyleSheet(
            """
            QFrame {
                background-color: rgba(96, 205, 255, 0.12);
                border: 1px solid #60CDFF;
                border-radius: 6px;
                padding: 8px 12px;
            }
            """
        )
        banner_layout = QHBoxLayout(self.restart_banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        self.restart_msg = QLabel("Settings saved. Some changes require an application restart.", self.restart_banner)
        self.restart_msg.setStyleSheet("color: #60CDFF; font-size: 13px; font-weight: 500;")
        btn_restart_now = QPushButton("Restart Now", self.restart_banner)
        btn_restart_now.setStyleSheet(
            "background-color: #60CDFF; color: #000000; font-weight: bold; border-radius: 4px; padding: 4px 12px;"
        )
        btn_restart_now.clicked.connect(self._restart_application)

        btn_restart_later = QPushButton("Later", self.restart_banner)
        btn_restart_later.setStyleSheet(
            "background-color: #3B4048; color: #FFFFFF; border-radius: 4px; padding: 4px 10px;"
        )
        btn_restart_later.clicked.connect(lambda: self.restart_banner.hide())

        banner_layout.addWidget(self.restart_msg)
        banner_layout.addStretch()
        banner_layout.addWidget(btn_restart_now)
        banner_layout.addWidget(btn_restart_later)
        self.restart_banner.hide()
        root.addWidget(self.restart_banner)

        # Main Split Area: Navigation Sidebar + Content Stack
        main_body = QHBoxLayout()
        main_body.setSpacing(16)

        # 1. Left Sidebar
        sidebar = QFrame(self)
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            """
            QFrame {
                background-color: #181818;
                border: 1px solid #333333;
                border-radius: 8px;
            }
            """
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(4)

        self.nav_buttons: list[QPushButton] = []
        nav_items = [
            ("General", 0),
            ("Speech-to-Text (STT)", 1),
            ("Text-to-Speech (TTS)", 2),
            ("Brain & LLM", 3),
            ("API & Credentials", 4),
            ("Local Models", 5),
            ("Performance & GPU", 6),
            ("Setup Guides & Help", 7),
        ]

        for text, index in nav_items:
            btn = QPushButton(text, sidebar)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setStyleSheet(
                """
                QPushButton {
                    text-align: left;
                    padding: 8px 12px;
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    color: #A8A8A8;
                    background-color: transparent;
                }
                QPushButton:hover {
                    background-color: #232323;
                    color: #FFFFFF;
                }
                QPushButton:checked {
                    background-color: #2B2B2B;
                    color: #60CDFF;
                    font-weight: bold;
                }
                """
            )
            btn.clicked.connect(lambda checked, idx=index: self._switch_tab(idx))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()
        main_body.addWidget(sidebar)

        # 2. Right Content Stack
        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background-color: transparent;")

        self.stack.addWidget(self._create_general_tab())
        self.stack.addWidget(self._create_stt_tab())
        self.stack.addWidget(self._create_tts_tab())
        self.stack.addWidget(self._create_llm_tab())
        self.stack.addWidget(self._create_credentials_tab())
        self.stack.addWidget(self._create_models_tab())
        self.stack.addWidget(self._create_performance_tab())
        self.stack.addWidget(self._create_guides_tab())

        main_body.addWidget(self.stack, 1)
        root.addLayout(main_body, 1)

        # Footer Actions: Test Config, Reset, Save
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 4, 4, 4)

        self.btn_test = QPushButton("Test Configuration", self)
        self.btn_test.setStyleSheet(
            "background-color: #2B2B2B; border: 1px solid #454545; border-radius: 6px; padding: 7px 14px; color: #FFFFFF; font-size: 13px;"
        )
        self.btn_test.clicked.connect(self._run_test_configuration)
        footer.addWidget(self.btn_test)

        self.lbl_test_result = QLabel("", self)
        self.lbl_test_result.setStyleSheet("font-size: 12px; font-weight: bold;")
        footer.addWidget(self.lbl_test_result)

        footer.addStretch()

        self.btn_reset = QPushButton("Reset to Defaults", self)
        self.btn_reset.setStyleSheet(
            "background-color: transparent; border: 1px solid #454545; border-radius: 6px; padding: 7px 14px; color: #A8A8A8; font-size: 13px;"
        )
        self.btn_reset.clicked.connect(self._reset_to_defaults)
        footer.addWidget(self.btn_reset)

        self.btn_save = QPushButton("Save & Apply Changes", self)
        self.btn_save.setStyleSheet(
            "background-color: #60CDFF; color: #000000; font-weight: bold; border-radius: 6px; padding: 7px 18px; font-size: 13px;"
        )
        self.btn_save.clicked.connect(self._save_changes)
        footer.addWidget(self.btn_save)

        root.addLayout(footer)

        # Default to first tab
        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)
            self.stack.setCurrentIndex(0)

    def _switch_tab(self, index: int) -> None:
        """Switches visible page in the stack."""
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == index)

    def _create_scroll_wrapper(self, inner_widget: QWidget) -> QScrollArea:
        """Wraps inner widget in a clean dark scroll container."""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        scroll.setWidget(inner_widget)
        return scroll

    def _create_card(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        """Creates a standardized dark card frame matching the design system."""
        card = QFrame(self)
        card.setStyleSheet(
            """
            QFrame {
                background-color: #232323;
                border: 1px solid #333333;
                border-radius: 8px;
            }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        t_lbl = QLabel(title, card)
        t_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFFFFF; border: none; background: transparent;")
        layout.addWidget(t_lbl)

        if subtitle:
            sub = QLabel(subtitle, card)
            sub.setStyleSheet("font-size: 12px; color: #8C8C8C; border: none; background: transparent;")
            sub.setWordWrap(True)
            layout.addWidget(sub)

        return card, layout

    # =========================================================================
    # TAB 1: GENERAL
    # =========================================================================
    def _create_general_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card("Assistant & Persona", "Customize how Jarvis addresses you and responds.")
        self.txt_username = QLineEdit(self)
        self.txt_username.setPlaceholderText("Your name (optional)")
        l.addWidget(QLabel("User Name:"))
        l.addWidget(self.txt_username)

        self.txt_honorific = QLineEdit(self)
        self.txt_honorific.setPlaceholderText("sir, boss, ma'am, or custom honorific")
        l.addWidget(QLabel("Honorific (Spoken address):"))
        l.addWidget(self.txt_honorific)
        v.addWidget(card)

        card2, l2 = self._create_card("Voice Activation & Wake Word", "Configure wake sensitivity and keywords.")
        self.combo_wakeword = QComboBox(self)
        self.combo_wakeword.addItems(["hey_jarvis", "alexa", "hey bro", "hey assistant", "jarvis"])
        self.combo_wakeword.setEditable(True)
        l2.addWidget(QLabel("Wake Word Phrase:"))
        l2.addWidget(self.combo_wakeword)

        self.spin_threshold = QDoubleSpinBox(self)
        self.spin_threshold.setRange(0.2, 0.95)
        self.spin_threshold.setSingleStep(0.05)
        self.spin_threshold.setValue(0.6)
        l2.addWidget(QLabel("Wake Sensitivity Threshold (0.5 - 0.7 recommended):"))
        l2.addWidget(self.spin_threshold)

        self.chk_idle_pill = QCheckBox("Show floating idle pill on desktop", self)
        self.chk_idle_pill.setStyleSheet("color: #FFFFFF; font-size: 13px; margin-top: 4px;")
        l2.addWidget(self.chk_idle_pill)

        v.addWidget(card2)
        v.addStretch()
        return self._create_scroll_wrapper(w)

    # =========================================================================
    # TAB 2: SPEECH-TO-TEXT (STT)
    # =========================================================================
    def _create_stt_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card("Speech-to-Text Engine", "Select cloud Whisper (Groq) or local GPU/CPU faster-whisper.")
        self.combo_stt_provider = QComboBox(self)
        self.combo_stt_provider.addItems(["groq", "local"])
        self.combo_stt_provider.currentTextChanged.connect(self._on_stt_provider_changed)
        l.addWidget(QLabel("STT Provider:"))
        l.addWidget(self.combo_stt_provider)

        # Local model options container
        self.frame_local_stt = QFrame(self)
        l_stt = QVBoxLayout(self.frame_local_stt)
        l_stt.setContentsMargins(0, 4, 0, 0)
        l_stt.setSpacing(8)

        l_stt.addWidget(QLabel("Local Whisper Model (Only downloaded models shown):"))
        self.combo_local_stt_model = QComboBox(self)
        l_stt.addWidget(self.combo_local_stt_model)

        self.lbl_stt_status = QLabel("", self)
        self.lbl_stt_status.setStyleSheet("color: #60CDFF; font-size: 12px;")
        l_stt.addWidget(self.lbl_stt_status)

        row_stt_btns = QHBoxLayout()
        btn_refresh_stt = QPushButton("Refresh Local Models", self)
        btn_refresh_stt.clicked.connect(self._refresh_local_stt_models)
        btn_open_stt_dir = QPushButton("Open STT Folder", self)
        btn_open_stt_dir.clicked.connect(lambda: open_folder_in_explorer(get_stt_models_dir()))
        row_stt_btns.addWidget(btn_refresh_stt)
        row_stt_btns.addWidget(btn_open_stt_dir)
        row_stt_btns.addStretch()
        l_stt.addLayout(row_stt_btns)

        l_stt.addWidget(QLabel("Inference Device:"))
        self.combo_stt_device = QComboBox(self)
        self.combo_stt_device.addItems(["auto", "cuda", "cpu"])
        l_stt.addWidget(self.combo_stt_device)

        l.addWidget(self.frame_local_stt)

        # Groq model option
        self.frame_groq_stt = QFrame(self)
        l_groq = QVBoxLayout(self.frame_groq_stt)
        l_groq.setContentsMargins(0, 4, 0, 0)
        l_groq.setSpacing(8)
        l_groq.addWidget(QLabel("Groq Whisper Model:"))
        self.combo_groq_stt_model = QComboBox(self)
        self.combo_groq_stt_model.addItems(["whisper-large-v3-turbo", "whisper-large-v3"])
        self.combo_groq_stt_model.setEditable(True)
        l_groq.addWidget(self.combo_groq_stt_model)
        l.addWidget(self.frame_groq_stt)

        v.addWidget(card)

        # Audio Input Devices
        card_audio, l_audio = self._create_card("Microphone Input", "Choose active recording microphone.")
        self.combo_mic_device = QComboBox(self)
        self._populate_audio_input_devices()
        l_audio.addWidget(QLabel("Input Device:"))
        l_audio.addWidget(self.combo_mic_device)
        v.addWidget(card_audio)

        v.addStretch()
        return self._create_scroll_wrapper(w)

    def _on_stt_provider_changed(self, prov: str) -> None:
        is_local = prov.lower() == "local"
        self.frame_local_stt.setVisible(is_local)
        self.frame_groq_stt.setVisible(not is_local)

    def _populate_audio_input_devices(self) -> None:
        """Queries sounddevice for physical recording microphones."""
        self.combo_mic_device.clear()
        self.combo_mic_device.addItem("Default System Microphone", None)
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    self.combo_mic_device.addItem(f"{dev['name']} (#{i})", i)
        except Exception:
            pass

    def _refresh_local_stt_models(self) -> None:
        """Populates local STT models dropdown with only verified downloads."""
        self.combo_local_stt_model.clear()
        models = discover_local_stt_models()
        if models:
            for m in models:
                self.combo_local_stt_model.addItem(m["name"], m["id"])
            self.lbl_stt_status.setText(f"Found {len(models)} local Whisper model(s).")
        else:
            self.combo_local_stt_model.addItem("No local models found in STT folder", "")
            self.lbl_stt_status.setText("No local models found. See 'Setup Guides' tab to download.")

    # =========================================================================
    # TAB 3: TEXT-TO-SPEECH (TTS)
    # =========================================================================
    def _create_tts_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card("Speech Synthesis (TTS) Engine", "Select Edge-TTS (online cloud neural), Piper (local neural), or pyttsx3.")
        self.combo_tts_provider = QComboBox(self)
        self.combo_tts_provider.addItems(["edge", "piper", "pyttsx3"])
        self.combo_tts_provider.currentTextChanged.connect(self._on_tts_provider_changed)
        l.addWidget(QLabel("TTS Provider:"))
        l.addWidget(self.combo_tts_provider)

        # Piper local voices container
        self.frame_piper = QFrame(self)
        l_piper = QVBoxLayout(self.frame_piper)
        l_piper.setContentsMargins(0, 4, 0, 0)
        l_piper.setSpacing(8)

        l_piper.addWidget(QLabel("Local Piper Voice (Only downloaded .onnx models shown):"))
        self.combo_piper_voice = QComboBox(self)
        l_piper.addWidget(self.combo_piper_voice)

        self.lbl_piper_status = QLabel("", self)
        self.lbl_piper_status.setStyleSheet("color: #60CDFF; font-size: 12px;")
        l_piper.addWidget(self.lbl_piper_status)

        row_piper_btns = QHBoxLayout()
        btn_refresh_piper = QPushButton("Refresh Local Voices", self)
        btn_refresh_piper.clicked.connect(self._refresh_piper_voices)
        btn_open_piper_dir = QPushButton("Open Voices Folder", self)
        btn_open_piper_dir.clicked.connect(lambda: open_folder_in_explorer(get_piper_models_dir()))
        row_piper_btns.addWidget(btn_refresh_piper)
        row_piper_btns.addWidget(btn_open_piper_dir)
        row_piper_btns.addStretch()
        l_piper.addLayout(row_piper_btns)
        l.addWidget(self.frame_piper)

        # Edge-TTS cloud voices container
        self.frame_edge = QFrame(self)
        l_edge = QVBoxLayout(self.frame_edge)
        l_edge.setContentsMargins(0, 4, 0, 0)
        l_edge.setSpacing(8)
        l_edge.addWidget(QLabel("Edge Neural Voice:"))
        self.combo_edge_voice = QComboBox(self)
        self.combo_edge_voice.addItems([
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-ChristopherNeural",
            "en-IN-PrabhatNeural",
        ])
        self.combo_edge_voice.setEditable(True)
        l_edge.addWidget(self.combo_edge_voice)
        l.addWidget(self.frame_edge)

        # Speech Speed Slider
        l.addWidget(QLabel("Speech Speed Rate:"))
        row_speed = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_speed.setRange(80, 160)
        self.slider_speed.setValue(115)
        self.lbl_speed_val = QLabel("1.15x (Conversational)", self)
        self.lbl_speed_val.setFixedWidth(140)
        self.slider_speed.valueChanged.connect(self._on_speed_slider_changed)
        row_speed.addWidget(self.slider_speed)
        row_speed.addWidget(self.lbl_speed_val)
        l.addLayout(row_speed)

        v.addWidget(card)
        v.addStretch()
        return self._create_scroll_wrapper(w)

    def _on_speed_slider_changed(self, val: int) -> None:
        rate = val / 100.0
        self.lbl_speed_val.setText(f"{rate:.2f}x ({'Normal' if rate==1.0 else 'Conversational'})")

    def _on_tts_provider_changed(self, prov: str) -> None:
        self.frame_piper.setVisible(prov.lower() == "piper")
        self.frame_edge.setVisible(prov.lower() == "edge")

    def _refresh_piper_voices(self) -> None:
        """Discovers downloaded Piper voices on disk."""
        self.combo_piper_voice.clear()
        voices = discover_piper_voices()
        if voices:
            for v in voices:
                self.combo_piper_voice.addItem(v["name"], v["id"])
            self.lbl_piper_status.setText(f"Found {len(voices)} verified Piper voice model(s).")
        else:
            self.combo_piper_voice.addItem("No local voices found", "")
            self.lbl_piper_status.setText("No Piper voices installed. See 'Setup Guides' tab.")

    # =========================================================================
    # TAB 4: BRAIN & LLM
    # =========================================================================
    def _create_llm_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card("LLM Orchestration & Providers", "Choose primary brain provider and models.")
        self.combo_llm_provider = QComboBox(self)
        self.combo_llm_provider.addItems(["groq", "gemini", "anthropic"])
        self.combo_llm_provider.currentTextChanged.connect(self._on_llm_provider_changed)
        l.addWidget(QLabel("Primary LLM Provider:"))
        l.addWidget(self.combo_llm_provider)

        self.txt_llm_model = QLineEdit(self)
        l.addWidget(QLabel("Model Identifier:"))
        l.addWidget(self.txt_llm_model)

        self.combo_fallback_provider = QComboBox(self)
        self.combo_fallback_provider.addItems(["gemini", "anthropic", "groq", "none"])
        l.addWidget(QLabel("Fallback Provider (Fast failover if primary hits rate limit):"))
        l.addWidget(self.combo_fallback_provider)

        row_params = QHBoxLayout()
        row_params.addWidget(QLabel("Max Spoken Tokens:"))
        self.spin_max_tokens = QSpinBox(self)
        self.spin_max_tokens.setRange(100, 2048)
        self.spin_max_tokens.setValue(800)
        row_params.addWidget(self.spin_max_tokens)

        row_params.addWidget(QLabel("Temperature:"))
        self.spin_temp = QDoubleSpinBox(self)
        self.spin_temp.setRange(0.0, 1.0)
        self.spin_temp.setSingleStep(0.05)
        self.spin_temp.setValue(0.2)
        row_params.addWidget(self.spin_temp)
        l.addLayout(row_params)

        v.addWidget(card)
        v.addStretch()
        return self._create_scroll_wrapper(w)

    def _on_llm_provider_changed(self, prov: str) -> None:
        p = prov.lower()
        if p == "groq":
            self.txt_llm_model.setText("qwen/qwen3.8-27b")
        elif p == "gemini":
            self.txt_llm_model.setText("gemini-3.5-flash")
        elif p == "anthropic":
            self.txt_llm_model.setText("claude-sonnet-5-5")

    # =========================================================================
    # TAB 5: API & CREDENTIALS
    # =========================================================================
    def _create_credentials_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card(
            "Windows Credential Vault (DPAPI)",
            "API keys are encrypted specifically for your Windows user profile using DPAPI. Never stored in plaintext."
        )

        # Groq API Key
        l.addWidget(QLabel("Groq API Key:"))
        row_groq = QHBoxLayout()
        self.txt_key_groq = QLineEdit(self)
        self.txt_key_groq.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_key_groq.setPlaceholderText("gsk_...")
        btn_eye_groq = QPushButton("Show", self)
        btn_eye_groq.setFixedWidth(56)
        btn_eye_groq.clicked.connect(lambda: self._toggle_echo(self.txt_key_groq, btn_eye_groq))
        row_groq.addWidget(self.txt_key_groq)
        row_groq.addWidget(btn_eye_groq)
        l.addLayout(row_groq)

        # Gemini API Key
        l.addWidget(QLabel("Google Gemini API Key:"))
        row_gemini = QHBoxLayout()
        self.txt_key_gemini = QLineEdit(self)
        self.txt_key_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_key_gemini.setPlaceholderText("AQ... or AIzaSy...")
        btn_eye_gemini = QPushButton("Show", self)
        btn_eye_gemini.setFixedWidth(56)
        btn_eye_gemini.clicked.connect(lambda: self._toggle_echo(self.txt_key_gemini, btn_eye_gemini))
        row_gemini.addWidget(self.txt_key_gemini)
        row_gemini.addWidget(btn_eye_gemini)
        l.addLayout(row_gemini)

        # Anthropic API Key
        l.addWidget(QLabel("Anthropic (Claude) API Key:"))
        row_anthropic = QHBoxLayout()
        self.txt_key_anthropic = QLineEdit(self)
        self.txt_key_anthropic.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_key_anthropic.setPlaceholderText("sk-ant-...")
        btn_eye_anthropic = QPushButton("Show", self)
        btn_eye_anthropic.setFixedWidth(56)
        btn_eye_anthropic.clicked.connect(lambda: self._toggle_echo(self.txt_key_anthropic, btn_eye_anthropic))
        row_anthropic.addWidget(self.txt_key_anthropic)
        row_anthropic.addWidget(btn_eye_anthropic)
        l.addLayout(row_anthropic)

        # ElevenLabs Key
        l.addWidget(QLabel("ElevenLabs Key (Optional alternative TTS):"))
        row_eleven = QHBoxLayout()
        self.txt_key_eleven = QLineEdit(self)
        self.txt_key_eleven.setEchoMode(QLineEdit.EchoMode.Password)
        btn_eye_eleven = QPushButton("Show", self)
        btn_eye_eleven.setFixedWidth(56)
        btn_eye_eleven.clicked.connect(lambda: self._toggle_echo(self.txt_key_eleven, btn_eye_eleven))
        row_eleven.addWidget(self.txt_key_eleven)
        row_eleven.addWidget(btn_eye_eleven)
        l.addLayout(row_eleven)

        v.addWidget(card)
        v.addStretch()
        return self._create_scroll_wrapper(w)

    def _toggle_echo(self, line_edit: QLineEdit, btn: QPushButton) -> None:
        if line_edit.echoMode() == QLineEdit.EchoMode.Password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            btn.setText("Hide")
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            btn.setText("Show")

    # =========================================================================
    # TAB 6: LOCAL MODELS
    # =========================================================================
    def _create_models_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card(
            "Local Model Directories",
            "Store downloaded neural models in user-writable storage. Add or replace models without rebuilding."
        )

        # STT Models
        l.addWidget(QLabel("Faster-Whisper STT Models Directory:"))
        row_stt = QHBoxLayout()
        self.lbl_path_stt = QLabel(str(get_stt_models_dir()), self)
        self.lbl_path_stt.setStyleSheet("background: #2B2B2B; padding: 6px 10px; border-radius: 4px; font-size: 11px;")
        btn_copy_stt = QPushButton("Copy Path", self)
        btn_copy_stt.clicked.connect(lambda: copy_to_clipboard(str(get_stt_models_dir())))
        btn_open_stt = QPushButton("Open Folder", self)
        btn_open_stt.clicked.connect(lambda: open_folder_in_explorer(get_stt_models_dir()))
        row_stt.addWidget(self.lbl_path_stt, 1)
        row_stt.addWidget(btn_copy_stt)
        row_stt.addWidget(btn_open_stt)
        l.addLayout(row_stt)

        # Piper Voices
        l.addWidget(QLabel("Piper Neural Voices Directory (.onnx + .onnx.json):"))
        row_piper = QHBoxLayout()
        self.lbl_path_piper = QLabel(str(get_piper_models_dir()), self)
        self.lbl_path_piper.setStyleSheet("background: #2B2B2B; padding: 6px 10px; border-radius: 4px; font-size: 11px;")
        btn_copy_piper = QPushButton("Copy Path", self)
        btn_copy_piper.clicked.connect(lambda: copy_to_clipboard(str(get_piper_models_dir())))
        btn_open_piper = QPushButton("Open Folder", self)
        btn_open_piper.clicked.connect(lambda: open_folder_in_explorer(get_piper_models_dir()))
        row_piper.addWidget(self.lbl_path_piper, 1)
        row_piper.addWidget(btn_copy_piper)
        row_piper.addWidget(btn_open_piper)
        l.addLayout(row_piper)

        # LLM Models
        l.addWidget(QLabel("Local LLM Weights Directory (.gguf):"))
        row_llm = QHBoxLayout()
        self.lbl_path_llm = QLabel(str(get_llm_models_dir()), self)
        self.lbl_path_llm.setStyleSheet("background: #2B2B2B; padding: 6px 10px; border-radius: 4px; font-size: 11px;")
        btn_copy_llm = QPushButton("Copy Path", self)
        btn_copy_llm.clicked.connect(lambda: copy_to_clipboard(str(get_llm_models_dir())))
        btn_open_llm = QPushButton("Open Folder", self)
        btn_open_llm.clicked.connect(lambda: open_folder_in_explorer(get_llm_models_dir()))
        row_llm.addWidget(self.lbl_path_llm, 1)
        row_llm.addWidget(btn_copy_llm)
        row_llm.addWidget(btn_open_llm)
        l.addLayout(row_llm)

        v.addWidget(card)
        v.addStretch()
        return self._create_scroll_wrapper(w)

    # =========================================================================
    # TAB 7: PERFORMANCE & HARDWARE
    # =========================================================================
    def _create_performance_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card, l = self._create_card("Hardware & GPU Acceleration", "Inspect detected GPU, CUDA readiness, and CPU fallback.")
        diag = get_hardware_diagnostics()

        self.lbl_gpu_name = QLabel(f"GPU Device: {diag['cuda_device_name']}", self)
        self.lbl_gpu_status = QLabel(f"CUDA Acceleration: {diag['status_summary']}", self)
        self.lbl_gpu_status.setStyleSheet("color: #60CDFF; font-weight: bold;")
        self.lbl_ram = QLabel(f"System RAM: {diag['system_ram_gb']} GB total", self)
        self.lbl_cpu = QLabel(f"CPU Cores: {diag['cpu_count']} logical cores", self)

        l.addWidget(self.lbl_gpu_name)
        l.addWidget(self.lbl_gpu_status)
        l.addWidget(self.lbl_ram)
        l.addWidget(self.lbl_cpu)

        self.chk_force_cpu = QCheckBox("Force CPU Fallback (Disable CUDA GPU inference)", self)
        self.chk_force_cpu.setStyleSheet("color: #FFFFFF; font-size: 13px; margin-top: 6px;")
        l.addWidget(self.chk_force_cpu)

        v.addWidget(card)
        v.addStretch()
        return self._create_scroll_wrapper(w)

    # =========================================================================
    # TAB 8: SETUP GUIDES & HELP
    # =========================================================================
    def _create_guides_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # Piper Guide Card
        card_p, l_p = self._create_card("How to Install Piper Voices (Offline Neural TTS)")
        guide_p = QLabel(
            "1. Download your preferred voice from the official HuggingFace repository:\n"
            "   https://huggingface.co/rhasspy/piper-voices\n\n"
            "2. For each voice, you MUST download TWO files:\n"
            "   - The model: [voice-name].onnx\n"
            "   - The config: [voice-name].onnx.json\n\n"
            "3. Click 'Open Voices Folder' in the Local Models tab and place both files there.\n"
            "4. Return to Settings -> TTS and click 'Refresh Local Voices'. Your voice will appear in the dropdown!",
            card_p,
        )
        guide_p.setStyleSheet("color: #CCCCCC; font-size: 12px; line-height: 1.4;")
        guide_p.setWordWrap(True)
        l_p.addWidget(guide_p)
        v.addWidget(card_p)

        # Faster-Whisper Guide Card
        card_w, l_w = self._create_card("How to Install Local Faster-Whisper Models (Offline STT)")
        guide_w = QLabel(
            "1. Faster-Whisper models (e.g. medium.en, small.en, base.en) download automatically on first use\n"
            "   when STT is set to 'Local'.\n"
            "2. Alternatively, place downloaded HuggingFace model folders directly in your STT folder.\n"
            "3. Required files inside the folder: 'model.bin' (or 'model.safetensors') and 'config.json'.\n"
            "4. Once placed, click 'Refresh Local Models' in the STT tab.",
            card_w,
        )
        guide_w.setStyleSheet("color: #CCCCCC; font-size: 12px; line-height: 1.4;")
        guide_w.setWordWrap(True)
        l_w.addWidget(guide_w)
        v.addWidget(card_w)

        # Cloud API Guide Card
        card_c, l_c = self._create_card("How to Obtain Cloud API Keys")
        guide_c = QLabel(
            "- Groq (Fastest cloud Whisper & Qwen/Llama):\n"
            "  Create a free key at https://console.groq.com/keys\n\n"
            "- Google Gemini (High token quota & multimodality):\n"
            "  Get a free API key at https://aistudio.google.com/app/apikey\n\n"
            "- Anthropic (Claude Sonnet 3.5):\n"
            "  Obtain a key from https://console.anthropic.com/settings/keys",
            card_c,
        )
        guide_c.setStyleSheet("color: #CCCCCC; font-size: 12px; line-height: 1.4;")
        guide_c.setWordWrap(True)
        l_c.addWidget(guide_c)
        v.addWidget(card_c)

        v.addStretch()
        return self._create_scroll_wrapper(w)

    # =========================================================================
    # CONFIGURATION LOADING & PERSISTENCE
    # =========================================================================
    def _load_current_values(self) -> None:
        """Loads values from SettingsManager into form widgets."""
        # General
        self.txt_username.setText(settings.get("general", "user_name", ""))
        self.txt_honorific.setText(settings.get("general", "honorific", "sir"))
        self.combo_wakeword.setCurrentText(settings.get("general", "wakeword_phrase", "hey_jarvis"))
        self.spin_threshold.setValue(float(settings.get("general", "wakeword_threshold", 0.6)))
        self.chk_idle_pill.setChecked(bool(settings.get("general", "show_idle_pill", True)))

        # STT
        stt_prov = settings.get("stt", "provider", "groq")
        self.combo_stt_provider.setCurrentText(stt_prov)
        self._on_stt_provider_changed(stt_prov)
        self._refresh_local_stt_models()
        saved_local_stt = settings.get("stt", "local_model", "medium.en")
        idx_stt = self.combo_local_stt_model.findData(saved_local_stt)
        if idx_stt != -1:
            self.combo_local_stt_model.setCurrentIndex(idx_stt)
        self.combo_stt_device.setCurrentText(settings.get("stt", "device", "auto"))

        # TTS
        tts_eng = settings.get("tts", "engine", "edge")
        self.combo_tts_provider.setCurrentText(tts_eng)
        self._on_tts_provider_changed(tts_eng)
        self._refresh_piper_voices()
        saved_piper = settings.get("tts", "piper_voice", "en_GB-alan-medium")
        idx_piper = self.combo_piper_voice.findData(saved_piper)
        if idx_piper != -1:
            self.combo_piper_voice.setCurrentIndex(idx_piper)

        speed_val = int(round(float(settings.get("tts", "speed", 1.15)) * 100))
        self.slider_speed.setValue(speed_val)
        self._on_speed_slider_changed(speed_val)
        self.combo_edge_voice.setCurrentText(settings.get("tts", "edge_voice", "en-GB-RyanNeural"))

        # LLM
        llm_prov = settings.get("llm", "provider", "groq")
        self.combo_llm_provider.setCurrentText(llm_prov)
        self.txt_llm_model.setText(settings.get("llm", "model", "qwen/qwen3.8-27b"))
        self.combo_fallback_provider.setCurrentText(settings.get("llm", "fallback_provider", "gemini"))
        self.spin_max_tokens.setValue(int(settings.get("llm", "max_tokens", 800)))
        self.spin_temp.setValue(float(settings.get("llm", "temperature", 0.2)))

        # API Keys from Vault
        self.txt_key_groq.setText(get_secret("GROQ_API_KEY", ""))
        self.txt_key_gemini.setText(get_secret("GEMINI_API_KEY", ""))
        self.txt_key_anthropic.setText(get_secret("ANTHROPIC_API_KEY", ""))
        self.txt_key_eleven.setText(get_secret("ELEVENLABS_API_KEY", ""))

    def _save_changes(self) -> None:
        """Saves form values into SettingsManager and updates DPAPI vault."""
        # General
        settings.set("general", "user_name", self.txt_username.text().strip())
        settings.set("general", "honorific", self.txt_honorific.text().strip() or "sir")
        old_ww = settings.get("general", "wakeword_phrase")
        new_ww = self.combo_wakeword.currentText().strip()
        settings.set("general", "wakeword_phrase", new_ww, requires_restart=(old_ww != new_ww), restart_reason="Wake word phrase changed")
        settings.set("general", "wakeword_threshold", round(self.spin_threshold.value(), 2))
        settings.set("general", "show_idle_pill", self.chk_idle_pill.isChecked())

        # STT
        old_stt_prov = settings.get("stt", "provider")
        new_stt_prov = self.combo_stt_provider.currentText().lower()
        settings.set("stt", "provider", new_stt_prov, requires_restart=(old_stt_prov != new_stt_prov), restart_reason="STT engine changed")
        if self.combo_local_stt_model.currentData():
            settings.set("stt", "local_model", self.combo_local_stt_model.currentData())
        settings.set("stt", "device", self.combo_stt_device.currentText())

        # TTS
        settings.set("tts", "engine", self.combo_tts_provider.currentText().lower())
        settings.set("tts", "speed", round(self.slider_speed.value() / 100.0, 2))
        settings.set("tts", "edge_voice", self.combo_edge_voice.currentText())
        if self.combo_piper_voice.currentData():
            settings.set("tts", "piper_voice", self.combo_piper_voice.currentData())

        # LLM
        settings.set("llm", "provider", self.combo_llm_provider.currentText().lower())
        settings.set("llm", "model", self.txt_llm_model.text().strip())
        settings.set("llm", "fallback_provider", self.combo_fallback_provider.currentText().lower())
        settings.set("llm", "max_tokens", self.spin_max_tokens.value())
        settings.set("llm", "temperature", round(self.spin_temp.value(), 2))

        # Save credentials to DPAPI vault
        if self.txt_key_groq.text().strip():
            set_secret("GROQ_API_KEY", self.txt_key_groq.text().strip())
        if self.txt_key_gemini.text().strip():
            set_secret("GEMINI_API_KEY", self.txt_key_gemini.text().strip())
        if self.txt_key_anthropic.text().strip():
            set_secret("ANTHROPIC_API_KEY", self.txt_key_anthropic.text().strip())
        if self.txt_key_eleven.text().strip():
            set_secret("ELEVENLABS_API_KEY", self.txt_key_eleven.text().strip())

        ok = settings.save()

        if ok:
            if settings.is_restart_required():
                reasons = ", ".join(settings.get_restart_reasons())
                self.restart_msg.setText(f"Settings saved. Restart required ({reasons}).")
                self.restart_banner.show()
            else:
                self.lbl_test_result.setStyleSheet("color: #60CDFF;")
                self.lbl_test_result.setText("Settings applied live successfully.")

    def _reset_to_defaults(self) -> None:
        """Prompts for confirmation and resets settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            settings.reset_to_defaults()
            self._load_current_values()
            self.lbl_test_result.setStyleSheet("color: #60CDFF;")
            self.lbl_test_result.setText("Settings reset to defaults.")

    def _run_test_configuration(self) -> None:
        """Non-destructively validates active provider credentials and models."""
        self.lbl_test_result.setStyleSheet("color: #A8A8A8;")
        self.lbl_test_result.setText("Testing configuration...")
        QApplication.processEvents()

        prov = self.combo_llm_provider.currentText().lower()
        if prov == "groq" and not (self.txt_key_groq.text().strip() or has_secret("GROQ_API_KEY")):
            self.lbl_test_result.setStyleSheet("color: #FF6B6B;")
            self.lbl_test_result.setText("Error: Groq API key is missing.")
            return

        if prov == "gemini" and not (self.txt_key_gemini.text().strip() or has_secret("GEMINI_API_KEY")):
            self.lbl_test_result.setStyleSheet("color: #FF6B6B;")
            self.lbl_test_result.setText("Error: Gemini API key is missing.")
            return

        self.lbl_test_result.setStyleSheet("color: #60CDFF;")
        self.lbl_test_result.setText("Configuration valid! Ready to use.")

    def _restart_application(self) -> None:
        """Executes application restart."""
        if self.on_restart_requested:
            self.on_restart_requested()
        else:
            python = sys.executable
            os.execl(python, python, *sys.argv)
