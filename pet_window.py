"""ProtoCube desktop pet window and interactive behavior."""

from __future__ import annotations

import ctypes
import math
import os
import random
import re
import sys
import time
from collections import deque
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt, QElapsedTimer, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from brain import BrainController, MAX_CONTEXT_CHARACTERS
from asset_manager import (
    count_spoken_words as modular_count_spoken_words,
    discover_files as modular_discover_files,
    discover_first_file as modular_discover_first_file,
    is_edible_item as modular_is_edible_item,
    load_scaled_pixmap,
    load_scaled_pixmaps,
)
from audio_manager import MciClip, ShuffledSoundBank
from idle_mood import IdleMoodController
from system_audio_listener import AdaptiveAudioListener
from physics_engine import advance_body
from system_actions import ActionRouter, SystemAction
from ui_components import (
    ChatBubble as ModularChatBubble,
    ChatHistoryWindow as ModularChatHistoryWindow,
    ChatInput as ModularChatInput,
)
from win32_integration import (
    MediaKeySender,
    WindowSurfaceTracker,
    VK_LEFT as MODULAR_VK_LEFT,
    VK_RIGHT as MODULAR_VK_RIGHT,
    register_hotkeys,
    unregister_hotkeys,
)
from config import *

VK_RIGHT = 0x27
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_LEFT = 0x25


def send_global_media_key(vk_code: int, repeat: int = 1) -> None:
    """Send native Windows virtual key events for system-wide media control."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        keyeventf_keyup = 0x0002
        for _ in range(max(1, repeat)):
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, keyeventf_keyup, 0)
            if repeat > 1:
                time.sleep(0.03)
    except (AttributeError, OSError):
        pass


def discover_files(folder: Path, supported_extensions: set[str]) -> list[Path]:
    """Return all supported files in a customization slot, alphabetically."""
    try:
        return sorted(
            (
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() in supported_extensions
            ),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return []


def discover_first_file(folder: Path, supported_extensions: set[str]) -> Path | None:
    """Return the first supported file in a customization slot."""
    candidates = discover_files(folder, supported_extensions)
    return candidates[0] if candidates else None


def is_edible_item(image_path: Path) -> tuple[bool, str]:
    """Analyze image filename, geometry, and color palette to classify food, fruits (oranges/apples/etc), or RAM sticks."""
    try:
        if not image_path.is_file():
            return False, ""
        stem = image_path.stem.casefold()

        # 1. RAM & Tech snacks
        ram_keywords = ("ram", "ddr", "ddr3", "ddr4", "ddr5", "dimm", "sodimm", "vram", "memory_stick", "memory stick", "ram_stick")
        if any(k in stem for k in ram_keywords):
            return True, "Nom nom nom! Delicious RAM! 💾 [^w^]"

        # 2. Food & Fruit keywords
        food_keywords = ("orange", "apple", "banana", "fruit", "pizza", "burger", "snack", "food", "cake", "cookie", "bread", "cheese", "meat", "candy", "sushi", "taco", "donut", "berry", "citrus", "citron", "peach", "mango", "strawberry", "grape", "melon", "watermelon")
        if any(k in stem for k in food_keywords):
            clean_name = image_path.stem.replace("_", " ")
            return True, f"Nom nom nom! Delicious {clean_name}! 😋 [^w^]"

        # 3. Geometric & visual color palette classifier using QImage
        from PyQt6.QtGui import QColor, QImage
        qimg = QImage(str(image_path))
        if qimg.isNull():
            return False, ""

        w, h = qimg.width(), qimg.height()
        if w < 20 or h < 20:
            return False, ""

        # RAM sticks aspect ratio
        aspect_ratio = max(w / h, h / w)
        if 2.2 <= aspect_ratio <= 7.0:
            return True, "Nom nom nom! Delicious RAM stick! 💾 [^w^]"

        # Sample pixel color distribution for fruit & food palettes (Orange, Red, Yellow)
        orange_pixels = 0
        red_pixels = 0
        yellow_pixels = 0
        total_samples = 0

        for x in range(0, w, max(1, w // 25)):
            for y in range(0, h, max(1, h // 25)):
                c = QColor(qimg.pixel(x, y))
                r, g, b = c.red(), c.green(), c.blue()
                total_samples += 1
                if r > 150 and g > 70 and b < 130 and r > g and g > b:
                    orange_pixels += 1
                elif r > 160 and g < 90 and b < 90 and (r - g) > 60:
                    red_pixels += 1
                elif r > 180 and g > 150 and b < 120 and (r - b) > 60 and (g - b) > 50:
                    yellow_pixels += 1

        if total_samples > 0:
            if (orange_pixels / total_samples) > 0.20:
                return True, "Nom nom nom! Delicious juicy orange! 🍊 [^w^]"
            if (red_pixels / total_samples) > 0.20:
                return True, "Nom nom nom! Delicious red fruit! 🍎 [^w^]"
            if (yellow_pixels / total_samples) > 0.20:
                return True, "Nom nom nom! Delicious snack! 🍌 [^w^]"

        return False, ""
    except Exception:
        return False, ""


def is_window_really_visible(hwnd: int, self_hwnd: int = 0) -> bool:
    """Check if window is visible, not iconic (minimized), not cloaked (AHK WinHide/virtual desktop), and not tool window."""
    if sys.platform != "win32" or not hwnd or hwnd == self_hwnd:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return False
        style_ex = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        if style_ex & 0x00000080:  # WS_EX_TOOLWINDOW
            return False
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        cloaked = ctypes.c_int(0)
        if dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0:
            if cloaked.value != 0:
                return False
        return True
    except Exception:
        return False


def count_spoken_words(message: str) -> int:
    """Count alphabetic words while ignoring bracketed visor expressions."""
    without_expressions = re.sub(r"\[[^\]\r\n]{1,24}\]", " ", message)
    words = re.findall(
        r"(?<!\w)[^\W\d_]+(?:['\u2019][^\W\d_]+)*(?!\w)",
        without_expressions,
        flags=re.UNICODE,
    )
    return len(words)


class ChatBubble(QWidget):
    """A small dismissible speech bubble that follows the pet."""

    dismissed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(300, 82)

        self.close_button = QPushButton("x", self)
        self.close_button.setFixedSize(20, 20)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setToolTip("Close this message")
        self.close_button.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #111111;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover { background: #dddddd; }
            QPushButton:pressed { background: #bbbbbb; }
            """
        )
        self.close_button.clicked.connect(self.dismiss)
        self.position_close_button()
        self.message = "bwaa…"

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.dismiss)

    def show_message(self, message: str, duration_ms: int = 1_500) -> None:
        self.message = message.strip()
        font = self.font()
        font.setPointSize(10)
        metrics = QFontMetrics(font)
        if len(self.message) <= 34 and "\n" not in self.message:
            width = max(230, min(400, metrics.horizontalAdvance(self.message) + 42))
        else:
            width = 400
        text_bounds = metrics.boundingRect(
            QRect(0, 0, width - 32, 2_000),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.message,
        )
        height = max(78, min(230, text_bounds.height() + 40))
        self.setFixedSize(width, height)
        self.position_close_button()
        self.update()
        self.show()
        self.raise_()
        self.close_button.raise_()
        if duration_ms > 0:
            self.hide_timer.start(duration_ms)
        else:
            self.hide_timer.stop()

    def position_close_button(self) -> None:
        self.close_button.move(self.width() - self.close_button.width() - 8, 8)

    def dismiss(self) -> None:
        self.hide_timer.stop()
        self.hide()
        self.dismissed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bubble = QRect(3, 3, self.width() - 6, self.height() - 17)
        path = QPainterPath()
        path.addRoundedRect(float(bubble.x()), float(bubble.y()),
                            float(bubble.width()), float(bubble.height()), 13.0, 13.0)
        path.moveTo(self.width() / 2 - 10, bubble.bottom() - 1)
        path.lineTo(self.width() / 2, self.height() - 3)
        path.lineTo(self.width() / 2 + 10, bubble.bottom() - 1)
        path.closeSubpath()

        painter.setPen(QPen(QColor("#111111"), 2))
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(path)

        painter.setPen(QColor("#111111"))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            bubble.adjusted(12, 7, -28, -7),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.message,
        )


class ChatHistoryWindow(QWidget):
    """A compact, scrollable transcript for the current ProtoCube session."""

    clear_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setWindowTitle("ProtoCube Chat History")
        self.resize(500, 380)

        self.transcript = QPlainTextEdit(self)
        self.transcript.setReadOnly(True)
        self.transcript.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.transcript.setPlaceholderText("No chat history yet.")

        self.clear_button = QPushButton("Clear history", self)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.hide)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.transcript, 1)
        layout.addLayout(button_row)

        self.setStyleSheet(
            """
            QWidget { background: #ffffff; color: #111111; }
            QPlainTextEdit {
                background: #f5f5f5;
                color: #111111;
                border: 1px solid #999999;
                border-radius: 7px;
                padding: 8px;
                selection-background-color: #111111;
                selection-color: #ffffff;
            }
            QPushButton {
                background: #111111;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                padding: 7px 12px;
                font-weight: bold;
            }
            QPushButton:pressed { background: #444444; }
            """
        )

    def set_entries(self, entries: list[tuple[str, str]]) -> None:
        blocks = [f"{speaker}\n{text}" for speaker, text in entries]
        self.transcript.setPlainText("\n\n".join(blocks))
        scrollbar = self.transcript.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_history(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()


class ChatInput(QWidget):
    """A compact input panel shown only after a deliberate click."""

    submitted = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName("chatPanel")
        self.setFixedSize(390, 44)
        self.selected_mode = "auto"

        self.prompt_input = QLineEdit(self)
        self.prompt_input.setPlaceholderText("Ask ProtoCube…")
        self.prompt_input.setMaxLength(4_000)
        self.prompt_input.returnPressed.connect(self.submit_prompt)

        self.close_button = QPushButton("x", self)
        self.close_button.setObjectName("chatCloseButton")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setToolTip("Close chat input")
        self.close_button.clicked.connect(self.hide)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(5)
        layout.addWidget(self.prompt_input, 1)
        layout.addWidget(self.close_button)

        self.setStyleSheet(
            """
            QWidget#chatPanel {
                background: white;
                border: 2px solid #111111;
                border-radius: 12px;
            }
            QLineEdit {
                background: white;
                border: none;
                color: #111111;
                padding: 5px;
                selection-background-color: #111111;
                selection-color: white;
            }
            QPushButton {
                background: #111111;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:pressed { background: #444444; }
            QPushButton#chatCloseButton {
                background: transparent;
                color: #111111;
                padding: 0;
                font-size: 13px;
            }
            QPushButton#chatCloseButton:hover {
                background: #dddddd;
            }
            """
        )

        close_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        close_shortcut.activated.connect(self.hide)

    def show_for_input(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.prompt_input.setFocus(Qt.FocusReason.MouseFocusReason)

    def set_context_hint(self, name: str = "") -> None:
        if name:
            self.prompt_input.setPlaceholderText(f"Ask about {name}…")
        else:
            self.prompt_input.setPlaceholderText("Ask ProtoCube…")

    def submit_prompt(self) -> None:
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return
        mode = self.selected_mode
        self.prompt_input.clear()
        self.set_context_hint()
        self.hide()
        self.submitted.emit(prompt, mode)

    def set_mode(self, mode: str) -> None:
        if mode in {"auto", "casual", "smart", "deep"}:
            self.selected_mode = mode


class ProtoCube(QWidget):
    """A draggable desktop square with event-driven throw physics."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFixedSize(PET_SIZE, PET_SIZE)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag and throw me. Click to chat. Right-click for options.")

        self.idle_image_path = modular_discover_first_file(
            IDLE_IMAGE_DIR,
            SUPPORTED_IDLE_IMAGE_EXTENSIONS,
        )
        self.click_image_paths, self.click_pixmaps = load_scaled_pixmaps(
            CLICK_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.click_image_order: list[int] = []
        self.last_click_image_index: int | None = None
        self.active_click_pixmap: QPixmap | None = None

        self.hurt_image_paths, self.hurt_pixmaps = load_scaled_pixmaps(
            HURT_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.hurt_image_order: list[int] = []
        self.last_hurt_image_index: int | None = None
        self.active_hurt_pixmap: QPixmap | None = None
        self.hurt_sound_paths = modular_discover_files(
            HURT_SOUND_DIR, SUPPORTED_SOUND_EXTENSIONS
        )
        self.hit_wall_sound_paths = modular_discover_files(
            HIT_WALL_SOUND_DIR, SUPPORTED_SOUND_EXTENSIONS
        )
        self.hurt_sounds = ShuffledSoundBank(
            self.hurt_sound_paths,
            max_voices_per_sound=HURT_SOUND_VOICES,
            prefix="ProtoCubeHurt",
            volume=HURT_SOUND_VOLUME,
        )
        self.hit_wall_sounds = ShuffledSoundBank(
            self.hit_wall_sound_paths,
            max_voices_per_sound=HIT_WALL_SOUND_VOICES,
            prefix="ProtoCubeHitWall",
            volume=HIT_WALL_SOUND_VOLUME,
        )
        self.last_impact_sound_time = 0.0

        self.talk_image_paths, self.talk_pixmaps = load_scaled_pixmaps(
            TALK_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.talk_frame_index = 0
        self.active_talk_pixmap: QPixmap | None = None
        self.is_talking = False
        self.click_sound_paths = modular_discover_files(
            CLICK_SOUND_DIR,
            SUPPORTED_SOUND_EXTENSIONS,
        )
        self.talk_sound_path = modular_discover_first_file(
            TALK_SOUND_DIR,
            SUPPORTED_SOUND_EXTENSIONS,
        )
        self.pet_pixmap = load_scaled_pixmap(self.idle_image_path, PET_SIZE)
        self.click_sounds = ShuffledSoundBank(
            self.click_sound_paths,
            max_voices_per_sound=CLICK_SOUND_VOICES,
            prefix="ProtoCubeClick",
            volume=CLICK_SOUND_VOLUME,
        )
        self.talk_clip = MciClip(self.talk_sound_path, "ProtoCubeTalk", 500) if self.talk_sound_path else None
        self.talk_is_open = bool(self.talk_clip and self.talk_clip.is_open)
        self.talk_sound_enabled = ENABLE_TALK_SOUND
        self.talk_words_remaining = 0
        self.talk_interval_ms = max(75, min(300, self.talk_clip.duration_ms)) if self.talk_is_open else 110

        self.dead_sound_paths = modular_discover_files(
            DEAD_SOUND_DIR,
            SUPPORTED_SOUND_EXTENSIONS,
        )
        self.dead_sounds = ShuffledSoundBank(
            self.dead_sound_paths, prefix="ProtoCubeDead", volume=750
        )

        self.spawn_sound_paths = modular_discover_files(
            SPAWN_SOUND_DIR,
            SUPPORTED_SOUND_EXTENSIONS,
        )
        self.last_spawn_duration_ms: int = SPAWN_MESSAGE_DURATION_MS
        self.spawn_sounds = ShuffledSoundBank(
            self.spawn_sound_paths, prefix="ProtoCubeSpawn", volume=750
        )
        self.spawn_is_open = bool(self.spawn_sound_paths)
        self.last_spawn_time = 0.0

        self.sing_sound_paths = modular_discover_files(
            SING_SOUND_DIR,
            SUPPORTED_SOUND_EXTENSIONS,
        )
        self.sing_order: list[int] = []
        self.last_sing_sound_index: int | None = None
        self.sing_is_open = bool(self.sing_sound_paths)
        self.sing_history: list[Path] = []
        self.current_sing_path: Path | None = None
        self.sing_audio_output = QAudioOutput(self)
        self.sing_audio_output.setVolume(0.75)
        self.sing_player = QMediaPlayer(self)
        self.sing_player.setAudioOutput(self.sing_audio_output)
        self.sing_player.setPitchCompensation(False)
        self.refill_sing_order()

        self.singing_image_paths, self.singing_pixmaps = load_scaled_pixmaps(
            SINGING_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.singing_frame_index = 0
        self.active_singing_pixmap: QPixmap | None = None
        self.is_singing_anim_active = False
        self.singing_anim_timer = QTimer(self)
        self.singing_anim_timer.timeout.connect(self.advance_singing_frame)
        self.sing_player.playbackStateChanged.connect(self.on_sing_playback_state_changed)

        self.listening_image_paths, self.listening_pixmaps = load_scaled_pixmaps(
            LISTENING_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.listening_frame_index = 0
        self.measured_ibi = 0.4
        self.active_listening_pixmap = None
        self.is_listening_anim_active = False
        self.last_listening_frame_time = 0.0
        self.audio_listener = AdaptiveAudioListener(
            enabled=ENABLE_LISTENING_ANIMATION and bool(self.listening_pixmaps),
            idle_interval_ms=LISTENING_IDLE_POLL_INTERVAL_MS,
            active_interval_ms=LISTENING_ACTIVE_POLL_INTERVAL_MS,
            activation_threshold=LISTENING_LOUDNESS_THRESHOLD,
            release_threshold=LISTENING_RELEASE_THRESHOLD,
            release_delay_ms=LISTENING_RELEASE_DELAY_MS,
            blocked=self.is_system_audio_listening_blocked,
            parent=self,
        )
        self.audio_listener.active_changed.connect(
            self.set_system_audio_listening_active
        )
        self.audio_listener.peak_sampled.connect(self.animate_system_audio_peak)

        self.thinking_image_paths, self.thinking_pixmaps = load_scaled_pixmaps(
            THINKING_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.thinking_frame_index = 0
        self.active_thinking_pixmap: QPixmap | None = None
        self.is_thinking_anim_active = False

        self.thinking_anim_timer = QTimer(self)
        self.thinking_anim_timer.timeout.connect(self.advance_thinking_frame)

        self.eat_image_paths, self.eat_pixmaps = load_scaled_pixmaps(
            EAT_IMAGE_DIR, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.eat_frame_index = 0
        self.active_eat_pixmap: QPixmap | None = None
        self.is_eating_anim_active = False

        self.eat_sound_paths = modular_discover_files(
            EAT_SOUND_DIR,
            SUPPORTED_SOUND_EXTENSIONS,
        )
        self.eat_audio_output = QAudioOutput(self)
        self.eat_audio_output.setVolume(0.85)
        self.eat_player = QMediaPlayer(self)
        self.eat_player.setAudioOutput(self.eat_audio_output)
        self.eat_player.playbackStateChanged.connect(self.on_eat_playback_state_changed)
        self.current_eat_sound_path: Path | None = None

        self.eat_anim_timer = QTimer(self)
        self.eat_anim_timer.timeout.connect(self.advance_eat_frame)

        self.eat_duration_timer = QTimer(self)
        self.eat_duration_timer.setSingleShot(True)
        self.eat_duration_timer.timeout.connect(self.stop_eating)

        self.death_exit_timer = QTimer(self)
        self.death_exit_timer.setSingleShot(True)
        self.death_exit_timer.timeout.connect(QApplication.quit)

        self.bubble = ModularChatBubble()
        self.chat_input = ModularChatInput()
        self.history_window = ModularChatHistoryWindow()
        self.chat_history: list[tuple[str, str]] = []
        self.brain = BrainController(self)
        self.action_router = ActionRouter()

        self.idle_mood_image_cache: dict[Path, list[QPixmap]] = {}
        self.idle_mood_pixmaps: list[QPixmap] = []
        self.active_idle_mood_pixmap: QPixmap | None = None
        self.idle_mood_frame_index = 0
        self.idle_mood_sound_clip: MciClip | None = None
        self.idle_mood_last_lines: dict[int, str] = {}
        self.idle_mood_anim_timer = QTimer(self)
        self.idle_mood_anim_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.idle_mood_anim_timer.timeout.connect(self.advance_idle_mood_frame)
        self.idle_mood = IdleMoodController(
            IDLE_PHASES,
            enabled=ENABLE_IDLE_MOOD_PHASES,
            parent=self,
        )
        self.idle_mood.phase_changed.connect(self.apply_idle_mood_phase)
        self.idle_mood.chatter_due.connect(self.show_idle_mood_chatter)

        self.shutting_down = False
        self.death_exit_pending = False
        self.spawned = False
        self.hotkey_registered = False
        self.activate_hotkey_registered = False
        self.hotkey_attempted = False
        self.hotkey_hwnd = 0
        self.is_reacting = False
        self.last_click_time = 0.0
        self.system_audio_ignore_until = 0.0
        self.last_eat_time = 0.0
        self.last_click_jump_time = 0.0
        self.window_sitting_enabled = ENABLE_WINDOW_SITTING
        self.window_surfaces = WindowSurfaceTracker()
        self.sat_hwnd: int | None = None
        self.sat_offset_x = 0.0
        self.last_sat_rect: tuple[int, int, int, int] | None = None
        self.sat_motion_until = 0.0
        self.is_dragging = False
        self.drag_moved = False
        self.drag_offset = QPoint()
        self.press_global = QPoint()
        self.drag_samples: deque[tuple[float, QPoint]] = deque(maxlen=12)

        self.position = QPointF(0.0, 0.0)
        self.velocity = QPointF(0.0, 0.0)
        self.physics_screen = QGuiApplication.primaryScreen()
        self.media_keys = MediaKeySender(self)

        self.physics_timer = QTimer(self)
        self.physics_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.physics_timer.setInterval(PHYSICS_INTERVAL_MS)
        self.physics_timer.timeout.connect(self.advance_physics)
        self.elapsed = QElapsedTimer()

        self.window_scan_timer = QTimer(self)
        self.window_scan_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.window_scan_timer.setInterval(WINDOW_SURFACE_SCAN_INTERVAL_MS)
        self.window_scan_timer.timeout.connect(self.refresh_window_surfaces)

        self.window_track_timer = QTimer(self)
        self.window_track_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.window_track_timer.setInterval(WINDOW_SIT_TRACK_INTERVAL_MS)
        self.window_track_timer.timeout.connect(self.track_sat_window)

        self.reaction_timer = QTimer(self)
        self.reaction_timer.setSingleShot(True)
        self.reaction_timer.timeout.connect(self.end_reaction)

        self.talk_timer = QTimer(self)
        self.talk_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.talk_timer.timeout.connect(self.play_next_talk_sound)
        self.bubble.dismissed.connect(self.stop_talking)
        self.bubble.user_activity.connect(self.register_user_activity)

        self.chat_input.submitted.connect(self.submit_prompt)
        self.chat_input.user_activity.connect(self.register_user_activity)
        self.history_window.clear_requested.connect(self.clear_conversation_history)
        self.history_window.user_activity.connect(self.register_user_activity)
        self.brain.status.connect(self.show_brain_status)
        self.brain.reply_ready.connect(self.show_brain_reply)
        self.brain.error.connect(self.show_brain_error)
        self.brain.mode_activated.connect(self.update_idle_mood_for_brain_mode)

        self.place_initially()
        self.idle_mood.start()
        self.audio_listener.start()

    def place_initially(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + max(0, area.height() // 3)
        self.position = QPointF(float(x), float(y))
        self.move(x, y)
        self.physics_screen = screen

    def force_window_visible(self) -> None:
        """Recover when Windows suppresses the process's first show request."""
        self.show()
        self.raise_()
        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            hwnd = wintypes.HWND(int(self.winId()))
            show_window = user32.ShowWindow
            show_window.argtypes = [wintypes.HWND, ctypes.c_int]
            show_window.restype = wintypes.BOOL
            set_window_pos = user32.SetWindowPos
            set_window_pos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            set_window_pos.restype = wintypes.BOOL
            # This is deliberately a second native show request. Windows can
            # ignore the first one when a GUI process inherits a hidden startup
            # state from cmd.exe, PowerShell, or a setup launcher.
            show_window(hwnd, 5)  # SW_SHOW
            set_window_pos(
                hwnd,
                wintypes.HWND(-1),  # HWND_TOPMOST
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0010 | 0x0040,  # no move/size/activate + show
            )
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            pass

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        super().showEvent(event)
        if self.spawned:
            return
        self.spawned = True
        QTimer.singleShot(120, self.start_physics)
        delay = max(0, SPAWN_START_DELAY_MS)
        QTimer.singleShot(delay, self.play_spawn_sound)
        QTimer.singleShot(delay + 50, self.trigger_spawn_greeting)

    def trigger_spawn_greeting(self) -> None:
        if not ENABLE_SPAWN_MESSAGE or not SPAWN_MESSAGE_TEXT:
            return
        self.last_spawn_time = time.perf_counter()
        display_duration = getattr(self, "last_spawn_duration_ms", SPAWN_MESSAGE_DURATION_MS) or SPAWN_MESSAGE_DURATION_MS
        self.bubble.show_message(SPAWN_MESSAGE_TEXT, display_duration)
        self.position_bubble()
        mute_talk_sfx = self.spawn_is_open
        word_count = max(1, int(display_duration / max(1, self.talk_interval_ms)))
        self.start_talking(SPAWN_MESSAGE_TEXT, word_count=word_count, mute_sfx=mute_talk_sfx)

    def nativeEvent(self, event_type, message):  # noqa: N802 - Qt naming convention
        if sys.platform == "win32":
            try:
                native_message = wintypes.MSG.from_address(int(message))
                if native_message.message == WM_HOTKEY:
                    if native_message.wParam == GLOBAL_HOTKEY_ID and self.hotkey_registered:
                        QTimer.singleShot(0, self.handle_global_hotkey)
                        return True, 0
                    if native_message.wParam == ACTIVATE_HOTKEY_ID and getattr(self, "activate_hotkey_registered", False):
                        QTimer.singleShot(0, self.handle_activate_hotkey)
                        return True, 0
            except (TypeError, ValueError):
                pass
        return False, 0

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        allowed = SUPPORTED_TEXT_EXTENSIONS | SUPPORTED_IDLE_IMAGE_EXTENSIONS
        if any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in allowed
            for url in urls
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.register_user_activity()
        if self.brain.is_busy:
            self.show_brain_error("Wait for the current thought before attaching a file")
            event.ignore()
            return

        dropped_files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        image_files = [
            p for p in dropped_files
            if p.suffix.lower() in SUPPORTED_IDLE_IMAGE_EXTENSIONS and p.is_file()
        ]

        if image_files:
            image_path = image_files[0]
            is_food, food_msg = modular_is_edible_item(image_path)
            if is_food:
                self.trigger_eat_reaction(food_msg)
            else:
                self.bubble.show_message(
                    "I can react to food images, but my text-only brain cannot inspect this image [._.]",
                    4_000,
                )
                self.position_bubble()
            event.acceptProposedAction()
            return

        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_TEXT_EXTENSIONS
        ][:3]
        chunks: list[str] = []
        names: list[str] = []
        truncated = False
        for path in paths:
            try:
                if not path.is_file():
                    continue
                with path.open("rb") as stream:
                    raw = stream.read(MAX_DROPPED_FILE_BYTES + 1)
                if len(raw) > MAX_DROPPED_FILE_BYTES:
                    raw = raw[:MAX_DROPPED_FILE_BYTES]
                    truncated = True
                text = raw.decode("utf-8-sig", errors="replace").strip()
                if not text:
                    continue
                remaining = MAX_CONTEXT_CHARACTERS - sum(len(chunk) for chunk in chunks)
                if remaining <= 0:
                    truncated = True
                    break
                if len(text) > remaining:
                    text = text[:remaining]
                    truncated = True
                names.append(path.name)
                chunks.append(f"--- {path.name} ---\n{text}")
            except OSError:
                continue

        if not chunks:
            self.show_brain_error("No readable supported text file was dropped")
            event.ignore()
            return

        label = names[0] if len(names) == 1 else f"{len(names)} files"
        combined = "\n\n".join(chunks)
        used = self.brain.attach_context(label, combined)
        self.chat_input.set_context_hint(label)
        suffix = " (truncated)" if truncated else ""
        self.bubble.show_message(f"Attached {label}{suffix}: {used:,} characters [^w^]", 2_000)
        self.position_bubble()
        self.is_reacting = True
        self.update()
        self.reaction_timer.start(700)
        QTimer.singleShot(900, self.open_chat)
        event.acceptProposedAction()

    def register_user_activity(self) -> None:
        if not ENABLE_IDLE_MOOD_PHASES or self.death_exit_pending:
            return
        was_idle = self.idle_mood.current_index > 0
        self.idle_mood.record_activity()
        if was_idle:
            self.bubble.dismiss()
            self.stop_talking()

    def update_idle_mood_for_brain_mode(self, mode: str) -> None:
        mode_key = mode.strip().casefold()
        disabled_modes = {
            key.casefold() for key in IDLE_MOOD_DISABLED_BRAIN_MODES
        }
        enabled = ENABLE_IDLE_MOOD_PHASES and mode_key not in disabled_modes
        was_idle = self.idle_mood.current_index > 0
        self.idle_mood.set_enabled(enabled)
        if not enabled and was_idle:
            self.bubble.dismiss()
            self.stop_talking()

    def _load_idle_mood_images(self, folder: Path) -> list[QPixmap]:
        folder = Path(folder)
        cached = self.idle_mood_image_cache.get(folder)
        if cached is not None:
            return cached
        _, pixmaps = load_scaled_pixmaps(
            folder, SUPPORTED_IDLE_IMAGE_EXTENSIONS, PET_SIZE
        )
        self.idle_mood_image_cache[folder] = pixmaps
        return pixmaps

    def stop_idle_mood_effects(self) -> None:
        self.idle_mood_anim_timer.stop()
        self.idle_mood_pixmaps = []
        self.active_idle_mood_pixmap = None
        self.idle_mood_frame_index = 0
        if self.idle_mood_sound_clip is not None:
            self.idle_mood_sound_clip.close()
            self.idle_mood_sound_clip = None
        self.update()

    def apply_idle_mood_phase(self, index: int, phase: dict[str, object]) -> None:
        self.stop_idle_mood_effects()
        self.audio_listener.refresh_blocked_state()
        if index <= 0 or self.shutting_down or self.death_exit_pending:
            return
        # Do not layer an idle performance over active model work or music.
        if self.brain.is_busy or self.is_singing_anim_active or self.is_eating_anim_active:
            return

        image_dir = phase.get("image_dir")
        fallback_dir = phase.get("fallback_image_dir")
        pixmaps: list[QPixmap] = []
        if image_dir:
            pixmaps = self._load_idle_mood_images(Path(image_dir))
        if not pixmaps and fallback_dir:
            pixmaps = self._load_idle_mood_images(Path(fallback_dir))
        self.idle_mood_pixmaps = pixmaps
        if pixmaps:
            self.active_idle_mood_pixmap = pixmaps[0]
            if bool(phase.get("animate", False)) and len(pixmaps) > 1:
                interval = int(
                    phase.get(
                        "frame_interval_ms", IDLE_MOOD_DEFAULT_FRAME_INTERVAL_MS
                    )
                )
                self.idle_mood_anim_timer.start(max(40, interval))

        sound_dir = phase.get("sound_dir")
        if sound_dir:
            sound_paths = modular_discover_files(
                Path(sound_dir), SUPPORTED_SOUND_EXTENSIONS
            )
            if sound_paths:
                sound_path = random.choice(sound_paths)
                clip = MciClip(
                    sound_path,
                    f"ProtoCubeIdleMood{index}",
                    IDLE_MOOD_SOUND_VOLUME,
                )
                if clip.is_open:
                    self.idle_mood_sound_clip = clip
                    clip.play(repeat=bool(phase.get("loop_sound", False)))
        self.update()

    def advance_idle_mood_frame(self) -> None:
        if len(self.idle_mood_pixmaps) < 2:
            self.idle_mood_anim_timer.stop()
            return
        self.idle_mood_frame_index = (
            self.idle_mood_frame_index + 1
        ) % len(self.idle_mood_pixmaps)
        self.active_idle_mood_pixmap = self.idle_mood_pixmaps[
            self.idle_mood_frame_index
        ]
        self.update()

    def show_idle_mood_chatter(self, index: int, phase: dict[str, object]) -> None:
        if (
            index != self.idle_mood.current_index
            or self.shutting_down
            or self.death_exit_pending
            or self.brain.is_busy
            or self.is_dragging
            or self.is_reacting
            or self.is_talking
            or self.is_singing_anim_active
            or self.is_thinking_anim_active
            or self.is_eating_anim_active
        ):
            return
        raw_lines = phase.get("lines", [])
        if not isinstance(raw_lines, (list, tuple)):
            return
        lines = [str(line).strip() for line in raw_lines if str(line).strip()]
        if not lines:
            return
        previous = self.idle_mood_last_lines.get(index)
        choices = [line for line in lines if line != previous] or lines
        line = random.choice(choices)
        self.idle_mood_last_lines[index] = line
        duration = max(1_000, int(phase.get("bubble_duration_ms", 5_000)))
        self.bubble.show_message(line, duration)
        self.position_bubble()
        self.start_talking(
            line,
            mute_sfx=(
                not bool(phase.get("talk_sound", True))
                or self.idle_mood_sound_clip is not None
            ),
        )
        if bool(phase.get("add_to_history", False)):
            self.add_history_entry("ProtoCube (idle)", line)

    def is_system_audio_listening_blocked(self) -> bool:
        phase_allows_listening = True
        phase_index = self.idle_mood.current_index
        if 0 <= phase_index < len(self.idle_mood.phases):
            phase_allows_listening = bool(
                self.idle_mood.phases[phase_index].get(
                    "system_audio_listening", True
                )
            )
        spawn_still_playing = (
            time.perf_counter() - self.last_spawn_time
            < self.last_spawn_duration_ms / 1_000.0 + 0.25
        )
        self_audio_suppressed = time.monotonic() < self.system_audio_ignore_until
        return bool(
            self.shutting_down
            or not phase_allows_listening
            or self_audio_suppressed
            or self.death_exit_pending
            or self.is_reacting
            or self.is_talking
            or self.is_singing_anim_active
            or self.is_thinking_anim_active
            or self.is_eating_anim_active
            or self.brain.is_busy
            or self.idle_mood_sound_clip is not None
            or spawn_still_playing
        )

    def set_system_audio_listening_active(self, active: bool) -> None:
        if active and self.listening_pixmaps:
            self.is_listening_anim_active = True
            self.listening_frame_index = 0
            self.active_listening_pixmap = self.listening_pixmaps[0]
            self.last_listening_frame_time = time.monotonic()
        else:
            self.is_listening_anim_active = False
            self.active_listening_pixmap = None
        self.update()

    def animate_system_audio_peak(self, peak: float) -> None:
        if not self.is_listening_anim_active or len(self.listening_pixmaps) < 2:
            return
        normalized = min(
            1.0,
            max(
                0.0,
                (peak - LISTENING_RELEASE_THRESHOLD)
                / max(0.001, 0.30 - LISTENING_RELEASE_THRESHOLD),
            ),
        )
        interval_ms = int(
            LISTENING_FRAME_MAX_INTERVAL_MS
            - normalized
            * (LISTENING_FRAME_MAX_INTERVAL_MS - LISTENING_FRAME_MIN_INTERVAL_MS)
        )
        now = time.monotonic()
        if (now - self.last_listening_frame_time) * 1_000.0 < interval_ms:
            return
        self.last_listening_frame_time = now
        self.listening_frame_index = (
            self.listening_frame_index + 1
        ) % len(self.listening_pixmaps)
        self.active_listening_pixmap = self.listening_pixmaps[
            self.listening_frame_index
        ]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        del event
        painter = QPainter(self)
        current_pixmap = (
            self.active_hurt_pixmap
            if self.is_reacting and self.active_hurt_pixmap and not self.active_hurt_pixmap.isNull()
            else (
                self.active_click_pixmap
                if self.is_reacting and self.active_click_pixmap and not self.active_click_pixmap.isNull()
                else (
                    self.active_eat_pixmap
                    if self.is_eating_anim_active and self.active_eat_pixmap and not self.active_eat_pixmap.isNull()
                    else (
                        self.active_talk_pixmap
                        if self.is_talking and self.active_talk_pixmap and not self.active_talk_pixmap.isNull()
                        else (
                            self.active_singing_pixmap
                            if self.is_singing_anim_active and self.active_singing_pixmap and not self.active_singing_pixmap.isNull()
                            else (
                                self.active_thinking_pixmap
                                if self.is_thinking_anim_active and self.active_thinking_pixmap and not self.active_thinking_pixmap.isNull()
                                else (
                                    self.active_listening_pixmap
                                    if self.is_listening_anim_active and self.active_listening_pixmap and not self.active_listening_pixmap.isNull()
                                    else (
                                        self.active_idle_mood_pixmap
                                        if self.active_idle_mood_pixmap is not None
                                        and not self.active_idle_mood_pixmap.isNull()
                                        else self.pet_pixmap
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
        if current_pixmap.isNull():
            painter.fillRect(
                self.rect(),
                QColor(
                    "#ffffff"
                    if (
                        self.is_reacting
                        or self.is_talking
                        or self.is_singing_anim_active
                        or self.is_thinking_anim_active
                        or self.is_listening_anim_active
                        or self.is_eating_anim_active
                        or self.active_idle_mood_pixmap is not None
                    )
                    else "#000000"
                ),
            )
            return
        x = (self.width() - current_pixmap.width()) // 2
        y = (self.height() - current_pixmap.height()) // 2
        painter.drawPixmap(x, y, current_pixmap)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.register_user_activity()
        if event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self.is_dragging = True
        self.drag_moved = False
        self.physics_timer.stop()
        self.window_scan_timer.stop()
        self.detach_from_window()
        self.velocity = QPointF(0.0, 0.0)
        self.drag_offset = event.position().toPoint()
        self.press_global = event.globalPosition().toPoint()
        self.drag_samples.clear()
        self.record_drag_sample(event.globalPosition().toPoint())
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.is_dragging or not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        cursor = event.globalPosition().toPoint()
        if (cursor - self.press_global).manhattanLength() > 6:
            self.drag_moved = True

        target = cursor - self.drag_offset
        target = self.clamp_to_screen(target, cursor)
        self.position = QPointF(float(target.x()), float(target.y()))
        self.move(target)
        self.position_companion_windows()
        self.record_drag_sample(cursor)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self.is_dragging:
            return

        self.is_dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        cursor = event.globalPosition().toPoint()
        self.record_drag_sample(cursor)

        if not self.drag_moved:
            self.react_to_click()
        else:
            self.velocity = self.calculate_throw_velocity()

        self.choose_physics_screen(cursor)
        self.position = QPointF(float(self.x()), float(self.y()))
        self.start_physics()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.request_quit()
            return
        super().keyPressEvent(event)

    def show_context_menu(self, global_position: QPoint) -> None:
        menu = QMenu(self)
        history_action = menu.addAction("Chat history...")
        ask_action = menu.addAction("Ask ProtoCube…")
        hotkey_action = menu.addAction(
            "Clipboard hotkey: Ctrl+Shift+Space"
            + ("" if self.hotkey_registered else " (unavailable)")
        )
        hotkey_action.setEnabled(False)
        mode_labels = {
            "auto": "Auto",
            "casual": "Casual (CPU)",
            "smart": "Smart (Hybrid)",
            "deep": "Deep (Experimental Hybrid)",
        }
        brain_menu = menu.addMenu(
            f"Brain mode: {mode_labels[self.chat_input.selected_mode]}"
        )
        mode_action_map: dict[object, str] = {}
        for mode_key, mode_label in mode_labels.items():
            mode_action = brain_menu.addAction(mode_label)
            mode_action.setCheckable(True)
            mode_action.setChecked(self.chat_input.selected_mode == mode_key)
            mode_action_map[mode_action] = mode_key
        menu.addSeparator()
        action_menu = menu.addMenu("System actions")
        action_map: dict[object, SystemAction] = {}
        for system_action in self.action_router.list_actions():
            menu_action = action_menu.addAction(system_action.name)
            menu_action.setToolTip(system_action.description)
            action_map[menu_action] = system_action
        if not action_map:
            empty_action = action_menu.addAction("No configured actions")
            empty_action.setEnabled(False)
        clear_action = menu.addAction("Clear conversation memory")
        clear_attachment_action = None
        if self.brain.attached_context_name:
            clear_attachment_action = menu.addAction(
                f"Clear attachment: {self.brain.attached_context_name}"
            )
        unload_action = menu.addAction("Unload Smart / Deep brain")
        sitting_action = menu.addAction("Sit on application windows")
        sitting_action.setCheckable(True)
        sitting_action.setChecked(self.window_sitting_enabled)
        talk_sound_action = menu.addAction("Talking sound")
        talk_sound_action.setCheckable(True)
        talk_sound_action.setChecked(self.talk_sound_enabled)
        talk_sound_action.setEnabled(self.talk_is_open)
        cancel_action = menu.addAction("Cancel current response")
        cancel_action.setEnabled(self.brain.is_busy)
        menu.addSeparator()
        quit_action = menu.addAction("Quit ProtoCube")
        selected = menu.exec(global_position)
        if selected == ask_action:
            self.open_chat()
        elif selected == history_action:
            self.open_history()
        elif selected == sitting_action:
            self.window_sitting_enabled = not self.window_sitting_enabled
            if self.window_sitting_enabled:
                self.refresh_window_surfaces()
                self.start_physics()
                status = "enabled"
            else:
                self.detach_from_window()
                self.start_physics()
                status = "disabled"
            self.bubble.show_message(
                f"Application-window sitting: {status} 🪟 [^w^]", 2_500
            )
            self.position_bubble()
        elif selected == talk_sound_action:
            self.talk_sound_enabled = not self.talk_sound_enabled
            if not self.talk_sound_enabled and self.talk_clip is not None:
                self.talk_clip.stop()
            status = "enabled" if self.talk_sound_enabled else "muted"
            self.bubble.show_message(f"Talking sound: {status} [^w^]", 2_500)
            self.position_bubble()
        elif selected == cancel_action:
            self.brain.cancel_current()
            self.stop_thinking_animation()
        elif selected in mode_action_map:
            selected_mode = mode_action_map[selected]
            self.chat_input.set_mode(selected_mode)
            self.update_idle_mood_for_brain_mode(selected_mode)
            self.bubble.setToolTip("ProtoCube brain mode")
            self.bubble.show_message(f"Brain mode: {mode_labels[selected_mode]}", 2_500)
            self.position_bubble()
        elif selected in action_map:
            self.confirm_and_run_action(action_map[selected])
        elif selected == clear_action:
            self.clear_conversation_history()
        elif clear_attachment_action is not None and selected == clear_attachment_action:
            self.brain.clear_attached_context()
            self.chat_input.set_context_hint()
            self.show_brain_reply("Attachment cleared [^w^]", "ProtoCube")
        elif selected == unload_action:
            if self.brain.unload_hybrid():
                self.show_brain_reply("Hybrid brain tucked away. VRAM returned [^w^]", "ProtoCube")
            elif not self.brain.is_busy:
                self.show_brain_reply("Smart and Deep were already asleep [._.]", "ProtoCube")
        elif selected == quit_action:
            self.request_quit()

    def react_to_click(self) -> None:
        self.last_click_time = time.perf_counter()
        self.play_boop()
        self.active_click_pixmap = self.get_next_click_pixmap()
        self.is_reacting = True
        self.update()
        self.reaction_timer.start(CLICK_REACTION_DURATION_MS)

        if ENABLE_CLICK_JUMP:
            now = time.perf_counter()
            if now - self.last_click_jump_time >= (CLICK_JUMP_COOLDOWN_MS / 1_000.0):
                self.last_click_jump_time = now
                self.position = QPointF(float(self.x()), float(self.y()))
                self.velocity = QPointF(self.velocity.x(), -abs(CLICK_JUMP_IMPULSE))
                self.start_physics()

        self.open_chat()

    def refill_click_image_order(self) -> None:
        self.click_image_order = list(range(len(self.click_pixmaps)))
        random.shuffle(self.click_image_order)
        if (
            len(self.click_image_order) > 1
            and self.last_click_image_index is not None
            and self.click_image_order[-1] == self.last_click_image_index
        ):
            self.click_image_order[-1], self.click_image_order[-2] = (
                self.click_image_order[-2],
                self.click_image_order[-1],
            )

    def get_next_click_pixmap(self) -> QPixmap | None:
        if not self.click_pixmaps:
            return None
        if not self.click_image_order:
            self.refill_click_image_order()
        if not self.click_image_order:
            return None
        index = self.click_image_order.pop()
        self.last_click_image_index = index
        return self.click_pixmaps[index]

    def refill_hurt_image_order(self) -> None:
        self.hurt_image_order = list(range(len(self.hurt_pixmaps)))
        random.shuffle(self.hurt_image_order)
        if (
            len(self.hurt_image_order) > 1
            and self.last_hurt_image_index is not None
            and self.hurt_image_order[-1] == self.last_hurt_image_index
        ):
            self.hurt_image_order[-1], self.hurt_image_order[-2] = (
                self.hurt_image_order[-2],
                self.hurt_image_order[-1],
            )

    def get_next_hurt_pixmap(self) -> QPixmap | None:
        if not self.hurt_pixmaps:
            return None
        if not self.hurt_image_order:
            self.refill_hurt_image_order()
        if not self.hurt_image_order:
            return None
        index = self.hurt_image_order.pop()
        self.last_hurt_image_index = index
        return self.hurt_pixmaps[index]

    def trigger_hurt_reaction(self) -> None:
        self.play_impact_sounds()
        pixmap = self.get_next_hurt_pixmap()
        if pixmap is not None and not pixmap.isNull():
            self.active_hurt_pixmap = pixmap
            self.is_reacting = True
            self.update()
            self.reaction_timer.start(HURT_REACTION_DURATION_MS)

    def play_impact_sounds(self) -> None:
        now = time.monotonic()
        if now - self.last_impact_sound_time < IMPACT_SOUND_COOLDOWN_MS / 1_000.0:
            return
        hit_path, hit_duration = self.hit_wall_sounds.play()
        hurt_path, hurt_duration = self.hurt_sounds.play()
        if hit_path is None and hurt_path is None:
            return
        self.last_impact_sound_time = now
        duration_ms = max(hit_duration, hurt_duration)
        if duration_ms <= 0:
            duration_ms = HURT_SOUND_LISTENING_FALLBACK_MS
        self.system_audio_ignore_until = max(
            self.system_audio_ignore_until,
            now + (duration_ms + HURT_SOUND_LISTENING_TAIL_MS) / 1_000.0,
        )
        self.audio_listener.refresh_blocked_state()

    def play_boop(self) -> None:
        sound_path, duration_ms = self.click_sounds.play()
        if sound_path is None:
            return
        if duration_ms <= 0:
            duration_ms = CLICK_SOUND_LISTENING_FALLBACK_MS
        suppress_seconds = (
            duration_ms + CLICK_SOUND_LISTENING_TAIL_MS
        ) / 1_000.0
        self.system_audio_ignore_until = max(
            self.system_audio_ignore_until,
            time.monotonic() + suppress_seconds,
        )
        self.audio_listener.refresh_blocked_state()

    def refill_boop_order(self) -> None:
        self.boop_order = list(range(len(self.boop_voice_pools)))
        random.shuffle(self.boop_order)
        if (
            len(self.boop_order) > 1
            and self.last_boop_sound_index is not None
            and self.boop_order[-1] == self.last_boop_sound_index
        ):
            self.boop_order[-1], self.boop_order[-2] = (
                self.boop_order[-2],
                self.boop_order[-1],
            )

    def initialize_boop_sound(self) -> None:
        if sys.platform != "win32" or not self.click_sound_paths:
            return
        mci_send = None
        opened_aliases: list[str] = []
        try:
            winmm = ctypes.WinDLL("winmm")
            mci_send = winmm.mciSendStringW
            mci_send.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                wintypes.UINT,
                wintypes.HWND,
            ]
            mci_send.restype = wintypes.UINT
            for index, sound_path in enumerate(self.click_sound_paths):
                media_type = "waveaudio" if sound_path.suffix.lower() == ".wav" else "mpegvideo"
                quoted_path = f'"{sound_path}"'
                voice_pool: list[str] = []
                for voice_index in range(CLICK_SOUND_VOICES):
                    alias = f"ProtoCubeBoop_{os.getpid()}_{index}_{voice_index}"
                    result = mci_send(
                        f"open {quoted_path} type {media_type} alias {alias}",
                        None,
                        0,
                        None,
                    )
                    if result != 0:
                        continue
                    opened_aliases.append(alias)
                    voice_pool.append(alias)
                    mci_send(f"setaudio {alias} volume to 650", None, 0, None)
                if voice_pool:
                    self.boop_voice_pools.append(voice_pool)
                    self.boop_voice_positions.append(0)

            self.boop_aliases = opened_aliases
            self.boop_mci_send = mci_send if opened_aliases else None
            self.boop_is_open = bool(opened_aliases)
            self.refill_boop_order()
        except (AttributeError, OSError):
            if mci_send is not None:
                for alias in opened_aliases:
                    mci_send(f"close {alias}", None, 0, None)
            self.boop_aliases.clear()
            self.boop_voice_pools.clear()
            self.boop_voice_positions.clear()
            self.boop_order.clear()
            self.boop_mci_send = None
            self.boop_is_open = False

    def close_boop_sound(self) -> None:
        self.click_sounds.close()

    def initialize_talk_sound(self) -> None:
        if sys.platform != "win32" or self.talk_sound_path is None:
            return
        try:
            winmm = ctypes.WinDLL("winmm")
            mci_send = winmm.mciSendStringW
            mci_send.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                wintypes.UINT,
                wintypes.HWND,
            ]
            mci_send.restype = wintypes.UINT
            media_type = "waveaudio" if self.talk_sound_path.suffix.lower() == ".wav" else "mpegvideo"
            quoted_path = f'"{self.talk_sound_path}"'
            result = mci_send(
                f"open {quoted_path} type {media_type} alias {self.talk_alias}",
                None,
                0,
                None,
            )
            if result != 0:
                return
            self.talk_mci_send = mci_send
            self.talk_is_open = True
            mci_send(f"set {self.talk_alias} time format milliseconds", None, 0, None)
            mci_send(f"setaudio {self.talk_alias} volume to 500", None, 0, None)

            length_buffer = ctypes.create_unicode_buffer(32)
            if mci_send(
                f"status {self.talk_alias} length",
                length_buffer,
                len(length_buffer),
                None,
            ) == 0:
                try:
                    clip_length_ms = int(length_buffer.value)
                    self.talk_interval_ms = max(75, min(300, clip_length_ms))
                except ValueError:
                    pass
        except (AttributeError, OSError):
            self.talk_mci_send = None
            self.talk_is_open = False

    def start_talking(self, message: str, word_count: int | None = None, mute_sfx: bool = False) -> None:
        self.stop_talking()
        self.mute_talk_sfx = mute_sfx
        self.talk_words_remaining = (
            modular_count_spoken_words(message) if word_count is None else max(0, word_count)
        )
        if self.talk_words_remaining <= 0:
            return
        self.is_talking = True
        self.talk_frame_index = 0
        if self.talk_pixmaps:
            self.active_talk_pixmap = self.talk_pixmaps[0]
            self.update()
        self.play_next_talk_sound()
        if self.talk_words_remaining > 0:
            self.talk_timer.start(self.talk_interval_ms)

    def play_next_talk_sound(self) -> None:
        if self.talk_words_remaining <= 0:
            self.stop_talking()
            return
        if self.talk_pixmaps:
            self.active_talk_pixmap = self.talk_pixmaps[self.talk_frame_index % len(self.talk_pixmaps)]
            self.talk_frame_index += 1
            self.update()
        if (
            self.talk_sound_enabled
            and not getattr(self, "mute_talk_sfx", False)
            and self.talk_clip is not None
        ):
            self.talk_clip.play()
        self.talk_words_remaining -= 1
        if self.talk_words_remaining <= 0:
            self.stop_talking()

    def stop_talking(self) -> None:
        self.talk_timer.stop()
        self.talk_words_remaining = 0
        self.is_talking = False
        self.active_talk_pixmap = None
        self.update()
        if self.talk_clip is not None:
            self.talk_clip.stop()

    def close_talk_sound(self) -> None:
        self.stop_talking()
        if self.talk_clip is not None:
            self.talk_clip.close()
        self.talk_is_open = False

    def refill_dead_order(self) -> None:
        self.dead_order = list(range(len(self.dead_aliases)))
        random.shuffle(self.dead_order)
        if (
            len(self.dead_order) > 1
            and self.last_dead_sound_index is not None
            and self.dead_order[-1] == self.last_dead_sound_index
        ):
            self.dead_order[-1], self.dead_order[-2] = (
                self.dead_order[-2],
                self.dead_order[-1],
            )

    def initialize_dead_sound(self) -> None:
        if sys.platform != "win32" or not self.dead_sound_paths:
            return
        mci_send = None
        opened_aliases: list[str] = []
        try:
            winmm = ctypes.WinDLL("winmm")
            mci_send = winmm.mciSendStringW
            mci_send.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                wintypes.UINT,
                wintypes.HWND,
            ]
            mci_send.restype = wintypes.UINT
            for index, sound_path in enumerate(self.dead_sound_paths):
                media_type = "waveaudio" if sound_path.suffix.lower() == ".wav" else "mpegvideo"
                quoted_path = f'"{sound_path}"'
                alias = f"ProtoCubeDead_{os.getpid()}_{index}"
                result = mci_send(
                    f"open {quoted_path} type {media_type} alias {alias}",
                    None,
                    0,
                    None,
                )
                if result == 0:
                    opened_aliases.append(alias)
                    mci_send(f"setaudio {alias} volume to 750", None, 0, None)

            self.dead_aliases = opened_aliases
            self.dead_mci_send = mci_send if opened_aliases else None
            self.dead_is_open = bool(opened_aliases)
            self.refill_dead_order()
        except (AttributeError, OSError):
            if mci_send is not None:
                for alias in opened_aliases:
                    mci_send(f"close {alias}", None, 0, None)
            self.dead_aliases.clear()
            self.dead_order.clear()
            self.dead_mci_send = None
            self.dead_is_open = False

    def play_dead_sound(self) -> int:
        """Start one lazily-opened death sound and return its bounded lifetime."""
        sound_path, duration = self.dead_sounds.play()
        if sound_path is None:
            return 0
        if duration <= 0:
            duration = DEAD_SOUND_FALLBACK_DURATION_MS
        return min(duration + 100, DEAD_SOUND_MAX_DURATION_MS)

    def close_dead_sound(self) -> None:
        self.dead_sounds.close()

    def refill_spawn_order(self) -> None:
        self.spawn_order = list(range(len(self.spawn_aliases)))
        random.shuffle(self.spawn_order)
        if (
            len(self.spawn_order) > 1
            and self.last_spawn_sound_index is not None
            and self.spawn_order[-1] == self.last_spawn_sound_index
        ):
            self.spawn_order[-1], self.spawn_order[-2] = (
                self.spawn_order[-2],
                self.spawn_order[-1],
            )

    def initialize_spawn_sound(self) -> None:
        if sys.platform != "win32" or not self.spawn_sound_paths:
            return
        mci_send = None
        opened_aliases: list[str] = []
        try:
            winmm = ctypes.WinDLL("winmm")
            mci_send = winmm.mciSendStringW
            mci_send.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                wintypes.UINT,
                wintypes.HWND,
            ]
            mci_send.restype = wintypes.UINT
            for index, sound_path in enumerate(self.spawn_sound_paths):
                media_type = "waveaudio" if sound_path.suffix.lower() == ".wav" else "mpegvideo"
                quoted_path = f'"{sound_path}"'
                alias = f"ProtoCubeSpawn_{os.getpid()}_{index}"
                result = mci_send(
                    f"open {quoted_path} type {media_type} alias {alias}",
                    None,
                    0,
                    None,
                )
                if result == 0:
                    opened_aliases.append(alias)
                    mci_send(f"setaudio {alias} volume to 750", None, 0, None)
                    mci_send(f"set {alias} time format milliseconds", None, 0, None)
                    length_buffer = ctypes.create_unicode_buffer(32)
                    if mci_send(f"status {alias} length", length_buffer, len(length_buffer), None) == 0:
                        try:
                            self.spawn_sound_lengths[alias] = int(length_buffer.value)
                        except ValueError:
                            pass

            self.spawn_aliases = opened_aliases
            self.spawn_mci_send = mci_send if opened_aliases else None
            self.spawn_is_open = bool(opened_aliases)
            self.refill_spawn_order()
        except (AttributeError, OSError):
            if mci_send is not None:
                for alias in opened_aliases:
                    mci_send(f"close {alias}", None, 0, None)
            self.spawn_aliases.clear()
            self.spawn_order.clear()
            self.spawn_sound_lengths.clear()
            self.spawn_mci_send = None
            self.spawn_is_open = False

    def play_spawn_sound(self) -> None:
        _, duration = self.spawn_sounds.play()
        if duration > 0:
            self.last_spawn_duration_ms = duration

    def close_spawn_sound(self) -> None:
        self.spawn_sounds.close()
        self.spawn_is_open = False

    def refill_sing_order(self) -> None:
        self.sing_order = list(range(len(self.sing_sound_paths)))
        random.shuffle(self.sing_order)
        if (
            len(self.sing_order) > 1
            and self.last_sing_sound_index is not None
            and self.sing_order[-1] == self.last_sing_sound_index
        ):
            self.sing_order[-1], self.sing_order[-2] = (
                self.sing_order[-2],
                self.sing_order[-1],
            )

    def play_sing_sound(self) -> None:
        if not self.sing_is_open or not self.sing_sound_paths:
            return
        if not self.sing_order:
            self.refill_sing_order()
        if not self.sing_order:
            return

        sound_index = self.sing_order.pop()
        sound_path = self.sing_sound_paths[sound_index]
        self._start_sing_file(sound_path)
        self.last_sing_sound_index = sound_index

    def find_sing_track(self, query: str) -> tuple[Path, str] | None:
        """Search filenames for all query words (case-insensitive)."""
        query_words = query.casefold().split()
        if not query_words:
            return None
        for sound_path in self.sing_sound_paths:
            clean_name = sound_path.stem.replace("_", " ").replace("-", " ").casefold()
            if all(word in clean_name for word in query_words):
                return sound_path, sound_path.stem
        return None

    def start_singing_animation(self) -> None:
        if not self.singing_pixmaps:
            return
        self.is_singing_anim_active = True
        self.singing_frame_index = 0
        self.active_singing_pixmap = self.singing_pixmaps[0]
        self.measured_ibi = 0.4
        self.update()
        total_frames = len(self.singing_pixmaps)
        base_interval = max(80, min(1000, int((self.measured_ibi * 1000) / max(1, math.ceil(total_frames / 4.0)))))
        self.singing_anim_timer.start(base_interval)

    def advance_singing_frame(self) -> None:
        if not self.is_singing_anim_active or not self.singing_pixmaps:
            self.stop_singing_animation()
            return
        self.singing_frame_index = (self.singing_frame_index + 1) % len(self.singing_pixmaps)
        self.active_singing_pixmap = self.singing_pixmaps[self.singing_frame_index]
        self.update()

    def stop_singing_animation(self) -> None:
        self.singing_anim_timer.stop()
        self.is_singing_anim_active = False
        self.active_singing_pixmap = None
        self.update()

    def sync_singing_anim_to_playback_rate(self) -> None:
        """Adjust singing animation timer interval to match current playback rate."""
        if not self.is_singing_anim_active or not self.singing_pixmaps:
            return
        rate = self.sing_player.playbackRate()
        if rate <= 0.0:
            rate = 1.0
        total_frames = len(self.singing_pixmaps)
        base_ibi = self.measured_ibi / rate
        target_interval = max(40, min(1200, int((base_ibi * 1000) / max(1, math.ceil(total_frames / 4.0)))))
        self.singing_anim_timer.setInterval(target_interval)

    def start_thinking_animation(self) -> None:
        if not self.thinking_pixmaps:
            return
        self.is_thinking_anim_active = True
        self.thinking_frame_index = 0
        self.active_thinking_pixmap = self.thinking_pixmaps[0]
        self.update()
        self.thinking_anim_timer.start(THINKING_FRAME_INTERVAL_MS)

    def advance_thinking_frame(self) -> None:
        if not self.is_thinking_anim_active or not self.thinking_pixmaps:
            self.stop_thinking_animation()
            return
        self.thinking_frame_index = (self.thinking_frame_index + 1) % len(self.thinking_pixmaps)
        self.active_thinking_pixmap = self.thinking_pixmaps[self.thinking_frame_index]
        self.update()

    def stop_thinking_animation(self) -> None:
        self.thinking_anim_timer.stop()
        self.is_thinking_anim_active = False
        self.active_thinking_pixmap = None
        self.update()

    def start_eating_animation(self) -> None:
        if not self.eat_pixmaps:
            return
        self.is_eating_anim_active = True
        self.eat_frame_index = 0
        self.active_eat_pixmap = self.eat_pixmaps[0]
        self.update()
        self.eat_anim_timer.start(EATING_FRAME_INTERVAL_MS)

    def advance_eat_frame(self) -> None:
        if not self.is_eating_anim_active or not self.eat_pixmaps:
            self.stop_eating()
            return
        self.eat_frame_index = (self.eat_frame_index + 1) % len(self.eat_pixmaps)
        self.active_eat_pixmap = self.eat_pixmaps[self.eat_frame_index]
        self.update()

    def play_eat_sound(self) -> None:
        if not self.eat_sound_paths:
            return
        sound_path = random.choice(self.eat_sound_paths)
        self.current_eat_sound_path = sound_path
        self.eat_player.stop()
        self.eat_player.setSource(QUrl.fromLocalFile(str(sound_path.resolve())))
        self.eat_player.play()

    def on_eat_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState and self.is_eating_anim_active:
            if self.current_eat_sound_path and self.current_eat_sound_path.is_file():
                self.eat_player.setSource(QUrl.fromLocalFile(str(self.current_eat_sound_path.resolve())))
                self.eat_player.play()

    def trigger_eat_reaction(self, message: str = "Nom nom nom! Delicious RAM! 💾 [^w^]") -> None:
        self.last_eat_time = time.perf_counter()
        self.start_eating_animation()
        self.play_eat_sound()
        self.eat_duration_timer.start(EATING_DURATION_MS)
        self.bubble.show_message(message, EATING_DURATION_MS)
        self.position_bubble()

    def stop_eating(self) -> None:
        self.last_eat_time = time.perf_counter()
        self.eat_anim_timer.stop()
        self.eat_duration_timer.stop()
        # Clear the active flag before stop() emits playbackStateChanged.
        self.is_eating_anim_active = False
        self.active_eat_pixmap = None
        self.current_eat_sound_path = None
        self.eat_player.stop()
        self.update()

    def on_sing_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.stop_singing_animation()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.singing_anim_timer.stop()
        elif state == QMediaPlayer.PlaybackState.PlayingState:
            if self.is_singing_anim_active:
                self.singing_anim_timer.start(SINGING_FRAME_INTERVAL_MS)
            else:
                self.start_singing_animation()

    def play_specific_sing_sound(self, sound_path: Path) -> None:
        if not self.sing_is_open:
            return
        self._start_sing_file(sound_path)

    def _start_sing_file(self, sound_path: Path) -> None:
        if not self.sing_is_open:
            return
        current_rate = self.sing_player.playbackRate()
        self.sing_player.stop()
        self.sing_player.setSource(QUrl.fromLocalFile(str(sound_path.resolve())))
        self.sing_player.setPitchCompensation(False)
        if current_rate != 1.0:
            self.sing_player.setPlaybackRate(current_rate)
        self.sing_player.play()

        self.current_sing_path = sound_path
        if not self.sing_history or self.sing_history[-1] != sound_path:
            self.sing_history.append(sound_path)
            del self.sing_history[:-100]
        self.start_singing_animation()

    def play_prev_sing_sound(self) -> None:
        if not self.sing_is_open or not self.sing_history:
            return
        if len(self.sing_history) > 1 and self.sing_history[-1] == self.current_sing_path:
            self.sing_history.pop()
        if self.sing_history:
            prev_path = self.sing_history.pop()
            self._start_sing_file(prev_path)

    def toggle_sing_pause(self) -> None:
        if not self.current_sing_path:
            return
        if self.sing_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.sing_player.pause()
        else:
            self.sing_player.play()

    def stop_sing_sound(self) -> None:
        self.sing_player.stop()
        self.current_sing_path = None
        self.stop_singing_animation()

    def open_chat(self) -> None:
        if self.brain.is_busy:
            self.bubble.show_message("Still thinking—one thought at a time [>_>]", 2_500)
            self.position_bubble()
            return
        self.bubble.dismiss()
        self.chat_input.set_context_hint(self.brain.attached_context_name)
        self.position_chat_input()
        self.chat_input.show_for_input()
        self.position_chat_input()

    def open_history(self) -> None:
        self.history_window.set_entries(self.chat_history)
        self.position_history_window()
        self.history_window.show_history()
        self.position_history_window()

    def add_history_entry(self, speaker: str, message: str) -> None:
        cleaned = message.strip()
        if not cleaned:
            return
        self.chat_history.append((speaker, cleaned))
        while len(self.chat_history) > 100:
            del self.chat_history[0]
        while (
            len(self.chat_history) > 2
            and sum(len(text) for _, text in self.chat_history) > 50_000
        ):
            del self.chat_history[0]
        if self.history_window.isVisible():
            self.history_window.set_entries(self.chat_history)

    def clear_conversation_history(self, announce: bool = True) -> None:
        self.brain.clear_history()
        self.chat_history.clear()
        self.history_window.set_entries(self.chat_history)
        if announce:
            self.bubble.setToolTip("ProtoCube")
            self.bubble.show_message("Memory cleared. Tiny brain, fresh desk [^w^]", 6_000)
            self.position_bubble()

    def submit_prompt(self, prompt: str, mode: str) -> None:
        self.register_user_activity()
        command = prompt.strip()
        lowered = command.lower()
        if lowered == "/reset":
            self.clear_conversation_history(announce=False)
        self.add_history_entry("You", command)
        if lowered == "/actions":
            actions = self.action_router.list_actions()
            if not actions:
                self.show_brain_error(self.action_router.last_error or "No system actions are configured")
                return
            names = ", ".join(action.name for action in actions)
            self.show_brain_reply(f"Available actions: {names}", "ProtoCube actions")
            return
        if lowered.startswith("/run "):
            action = self.action_router.get(command[5:].strip())
            if action is None:
                self.show_brain_error("Unknown action. Use /actions to list allowed names")
                return
            self.confirm_and_run_action(action)
            return
        if lowered.startswith("/global"):
            sub = command[7:].strip()
            sub_lowered = sub.lower()
            if sub_lowered in ("pause", "resume", "play", "toggle"):
                self.media_keys.send(VK_MEDIA_PLAY_PAUSE)
                self.bubble.show_message("Global play/pause 🌐 [^w^]", 2_500)
            elif sub_lowered in ("stop", "off"):
                self.media_keys.send(VK_MEDIA_STOP)
                self.bubble.show_message("Global media stopped 🌐 [._.]", 2_500)
            elif sub_lowered in ("next", "n"):
                self.media_keys.send(VK_MEDIA_NEXT_TRACK)
                self.bubble.show_message("Global next track 🌐 [^w^]", 2_500)
            elif sub_lowered in ("prev", "p", "back"):
                self.media_keys.send(VK_MEDIA_PREV_TRACK)
                self.bubble.show_message("Global previous track 🌐 [^w^]", 2_500)
            elif re.match(r"^>\d+$", sub_lowered):
                sec = int(sub_lowered[1:])
                self.media_keys.send(MODULAR_VK_RIGHT, repeat=min(30, sec))
                self.bubble.show_message(f"Global seek +{sec}s 🌐 [^w^]", 2_000)
            elif re.match(r"^<\d+$", sub_lowered):
                sec = int(sub_lowered[1:])
                self.media_keys.send(MODULAR_VK_LEFT, repeat=min(30, sec))
                self.bubble.show_message(f"Global rewind -{sec}s 🌐 [^w^]", 2_000)
            else:
                self.bubble.show_message("Use /global pause/stop/next/prev/>5/<5 🌐 [^w^]", 3_000)
            return
        if lowered.startswith(("/speedup", "/spedup")):
            parts = command.split()
            pct = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            current_rate = self.sing_player.playbackRate()
            new_rate = min(3.0, round(current_rate + (pct / 100.0), 2))
            self.sing_player.setPlaybackRate(new_rate)
            self.sync_singing_anim_to_playback_rate()
            pct_display = int(round(new_rate * 100))
            self.bubble.show_message(f"Playback speed: {pct_display}% (Pitch up ♪) [^w^]", 2_500)
            return
        if lowered.startswith(("/slowdown", "/sloweddown")):
            parts = command.split()
            pct = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            current_rate = self.sing_player.playbackRate()
            new_rate = max(0.2, round(current_rate - (pct / 100.0), 2))
            self.sing_player.setPlaybackRate(new_rate)
            self.sync_singing_anim_to_playback_rate()
            pct_display = int(round(new_rate * 100))
            self.bubble.show_message(f"Playback speed: {pct_display}% (Pitch down ♪) [^w^]", 2_500)
            return
        if lowered.startswith("/speed"):
            parts = command.split()
            if len(parts) > 1:
                arg = parts[1].lower()
                if arg in ("reset", "normal", "100", "1"):
                    new_rate = 1.0
                elif arg.isdigit():
                    new_rate = max(0.2, min(3.0, int(arg) / 100.0))
                else:
                    try:
                        new_rate = max(0.2, min(3.0, float(arg)))
                    except ValueError:
                        new_rate = 1.0
                self.sing_player.setPlaybackRate(new_rate)
                self.sync_singing_anim_to_playback_rate()
                pct_display = int(round(new_rate * 100))
                self.bubble.show_message(f"Playback speed: {pct_display}% ♪ [^w^]", 2_500)
            else:
                current_pct = int(round(self.sing_player.playbackRate() * 100))
                self.bubble.show_message(f"Current speed: {current_pct}% (Use /speed 100 or /speedup 10) [^w^]", 3_000)
            return
        if lowered.startswith("/vol"):
            parts = command.split()
            if len(parts) > 1 and parts[1].isdigit():
                vol_pct = max(0, min(100, int(parts[1])))
                self.sing_audio_output.setVolume(vol_pct / 100.0)
                self.bubble.show_message(f"Volume: {vol_pct}% ♪ [^w^]", 2_500)
            else:
                current_pct = int(round(self.sing_audio_output.volume() * 100))
                self.bubble.show_message(f"Current volume: {current_pct}% (Use /vol 0-100) [^w^]", 3_000)
            return
        if lowered in ("/next", "/n"):
            self.play_sing_sound()
            self.bubble.show_message("Next track ♪ [^w^]", 2_500)
            return
        if lowered in ("/prev", "/p", "/back"):
            self.play_prev_sing_sound()
            self.bubble.show_message("Previous track ♪ [^w^]", 2_500)
            return
        if lowered == "/pause":
            if self.current_sing_path:
                self.sing_player.pause()
                self.bubble.show_message("Paused music ♪ [._.]", 2_500)
            return
        if lowered in ("/resume", "/play"):
            if self.current_sing_path:
                self.sing_player.play()
                self.bubble.show_message("Resumed music ♪ [^w^]", 2_500)
            return
        if re.match(r"^/>\d+$", lowered):
            sec = int(lowered[2:])
            if self.current_sing_path and self.sing_player.duration() > 0:
                new_pos = min(self.sing_player.duration(), self.sing_player.position() + sec * 1_000)
                self.sing_player.setPosition(new_pos)
                self.bubble.show_message(f"Jumped +{sec}s ♪ [^w^]", 2_000)
            return
        if re.match(r"^/<\d+$", lowered):
            sec = int(lowered[2:])
            if self.current_sing_path and self.sing_player.duration() > 0:
                new_pos = max(0, self.sing_player.position() - sec * 1_000)
                self.sing_player.setPosition(new_pos)
                self.bubble.show_message(f"Rewound -{sec}s ♪ [^w^]", 2_000)
            return
        if lowered in ("/stop", "/shhh", "/mute"):
            self.stop_sing_sound()
            self.bubble.show_message("Shh... ♪ [._.]", 2_500)
            return
        if lowered.startswith("/sing"):
            if not self.sing_is_open:
                self.show_brain_error("No audio files found in assets/sfx/sing [._.]")
                return
            search_query = command[5:].strip()
            if search_query.lower() in ("stop", "off", "mute", "quiet", "shh"):
                self.stop_sing_sound()
                self.bubble.show_message("Shh... ♪ [._.]", 2_500)
                return
            if not search_query:
                self.play_sing_sound()
                self.bubble.show_message("La la la~ ♪ [^w^]", 4_000)
            else:
                match = self.find_sing_track(search_query)
                if match:
                    sound_path, track_name = match
                    self.play_specific_sing_sound(sound_path)
                    self.bubble.show_message(f"Playing '{track_name}' ♪ [^w^]", 4_000)
                else:
                    self.show_brain_error(f"Couldn't find '{search_query}' in sing folder [._.]")
            return
        self.brain.ask(command, mode)

    def confirm_and_run_action(self, action: SystemAction) -> None:
        answer = QMessageBox.question(
            self,
            "Run ProtoCube action?",
            f"Run '{action.name}'?\n\n{action.description}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.show_brain_reply("Action cancelled [._.]", "ProtoCube actions")
            return
        success, message = self.action_router.execute(action)
        if success:
            self.show_brain_reply(message + " [^w^]", "ProtoCube actions")
        else:
            self.show_brain_error(message)

    def handle_global_hotkey(self) -> None:
        self.register_user_activity()
        if self.brain.is_busy:
            self.show_brain_error("Wait for the current thought before using the clipboard hotkey")
            return
        clipboard_text = QApplication.clipboard().text().replace("\x00", "").strip()
        if not clipboard_text:
            self.show_brain_error("The clipboard has no text. Copy a code block or error first")
            return
        self.add_history_entry("You", "Clipboard hotkey: explain the copied code or error")
        self.brain.ask(
            "Explain what is wrong with this code or error concisely. If no fault is evident, say what it appears to do.",
            "smart",
            context_name="Clipboard",
            context_text=clipboard_text,
        )

    def handle_activate_hotkey(self) -> None:
        """Activate ProtoCube, bring it to front, and open chat input."""
        self.register_user_activity()
        self.force_window_visible()
        self.open_chat()

    def register_global_hotkey(self) -> None:
        if self.hotkey_attempted:
            return
        self.hotkey_attempted = True
        if sys.platform != "win32" or os.environ.get("PROTOCUBE_DISABLE_GLOBAL_HOTKEY") == "1":
            return
        self.hotkey_hwnd = int(self.winId())
        self.hotkey_registered, self.activate_hotkey_registered = register_hotkeys(
            self.hotkey_hwnd
        )

    def unregister_global_hotkey(self) -> None:
        unregister_hotkeys(
            self.hotkey_hwnd,
            self.hotkey_registered,
            self.activate_hotkey_registered,
        )
        self.hotkey_registered = False
        self.activate_hotkey_registered = False
        self.hotkey_hwnd = 0

    def show_brain_status(self, message: str) -> None:
        self.bubble.show_message(message, 120_000)
        self.position_bubble()
        self.start_thinking_animation()

    def show_brain_reply(self, message: str, brain_name: str) -> None:
        self.stop_thinking_animation()
        self.add_history_entry("ProtoCube", message)
        duration = max(6_000, min(16_000, 3_000 + len(message) * 28))
        spoken_word_count = (
            modular_count_spoken_words(message)
            if self.talk_pixmaps or self.talk_is_open
            else 0
        )
        if spoken_word_count:
            duration = max(duration, spoken_word_count * self.talk_interval_ms + 500)
        self.bubble.show_message(message, duration)
        self.position_bubble()
        self.start_talking(message, spoken_word_count)
        self.is_reacting = True
        self.update()
        self.reaction_timer.start(600)

    def show_brain_error(self, message: str) -> None:
        self.stop_thinking_animation()
        self.add_history_entry("ProtoCube error", message)
        self.bubble.setToolTip("ProtoCube brain error")
        suffix = "" if re.search(r"\[(?:\^w\^|>_>|\._\.|>_<)\]", message) else " [._.]"
        self.bubble.show_message(f"Brain bonk: {message}{suffix}", 12_000)
        self.position_bubble()

    def end_reaction(self) -> None:
        self.is_reacting = False
        self.active_click_pixmap = None
        self.active_hurt_pixmap = None
        self.update()

    def record_drag_sample(self, global_position: QPoint) -> None:
        now = time.perf_counter()
        self.drag_samples.append((now, QPoint(global_position)))
        while len(self.drag_samples) > 2 and now - self.drag_samples[0][0] > 0.14:
            self.drag_samples.popleft()

    def calculate_throw_velocity(self) -> QPointF:
        if len(self.drag_samples) < 2:
            return QPointF(0.0, 0.0)

        start_time, start_position = self.drag_samples[0]
        end_time, end_position = self.drag_samples[-1]
        duration = max(end_time - start_time, 0.001)
        vx = (end_position.x() - start_position.x()) / duration
        vy = (end_position.y() - start_position.y()) / duration
        speed = math.hypot(vx, vy)
        if speed > MAX_THROW_SPEED:
            scale = MAX_THROW_SPEED / speed
            vx *= scale
            vy *= scale
        return QPointF(vx, vy)

    def choose_physics_screen(self, global_point: QPoint) -> None:
        screen = QGuiApplication.screenAt(global_point)
        if screen is not None:
            self.physics_screen = screen

    def clamp_to_screen(self, target: QPoint, cursor: QPoint) -> QPoint:
        screen = QGuiApplication.screenAt(cursor) or self.physics_screen or QGuiApplication.primaryScreen()
        if screen is None:
            return target
        self.physics_screen = screen
        area = screen.availableGeometry()
        max_x = area.x() + area.width() - self.width()
        max_y = area.y() + area.height() - self.height()
        return QPoint(
            max(area.x(), min(target.x(), max_x)),
            max(area.y(), min(target.y(), max_y)),
        )

    def start_physics(self) -> None:
        if self.is_dragging or self.physics_timer.isActive():
            return
        self.detach_from_window()
        if self.window_sitting_enabled:
            self.refresh_window_surfaces()
            self.window_scan_timer.start()
        self.elapsed.start()
        self.physics_timer.start()

    def _excluded_window_handles(self) -> set[int]:
        handles: set[int] = set()
        for window in (self, self.bubble, self.chat_input, self.history_window):
            try:
                handles.add(int(window.winId()))
            except (RuntimeError, TypeError, ValueError):
                pass
        return handles

    def refresh_window_surfaces(self) -> None:
        if not self.window_sitting_enabled or sys.platform != "win32":
            self.window_scan_timer.stop()
            return
        self.window_surfaces.refresh(
            self._excluded_window_handles(),
            min_width=WINDOW_SIT_MIN_WIDTH,
            min_height=WINDOW_SIT_MIN_HEIGHT,
        )

    def detach_from_window(self) -> None:
        self.window_track_timer.stop()
        self.window_track_timer.setInterval(WINDOW_SIT_TRACK_INTERVAL_MS)
        self.sat_hwnd = None
        self.sat_offset_x = 0.0
        self.last_sat_rect = None
        self.sat_motion_until = 0.0

    def track_sat_window(self) -> None:
        hwnd = self.sat_hwnd
        if not self.window_sitting_enabled or hwnd is None:
            self.detach_from_window()
            return
        surface = self.window_surfaces.window_rect(hwnd, self._excluded_window_handles())
        if (
            surface is None
            or surface.right - surface.left <= WINDOW_SIT_MIN_WIDTH
            or surface.bottom - surface.top <= WINDOW_SIT_MIN_HEIGHT
        ):
            self.detach_from_window()
            self.position = QPointF(float(self.x()), float(self.y()))
            self.velocity = QPointF(0.0, 0.0)
            self.start_physics()
            return

        current_rect = (surface.left, surface.top, surface.right, surface.bottom)
        now = time.monotonic()
        if self.last_sat_rect is not None and current_rect != self.last_sat_rect:
            self.sat_motion_until = now + WINDOW_SIT_MOTION_HOLD_MS / 1_000.0
        self.last_sat_rect = current_rect
        target_interval = (
            WINDOW_SIT_MOVING_TRACK_INTERVAL_MS
            if now < self.sat_motion_until
            else WINDOW_SIT_TRACK_INTERVAL_MS
        )
        if self.window_track_timer.interval() != target_interval:
            self.window_track_timer.setInterval(target_interval)

        center = QPoint((surface.left + surface.right) // 2, surface.top)
        screen = QGuiApplication.screenAt(center) or self.physics_screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.physics_screen = screen
        area = screen.availableGeometry()
        new_y = surface.top - self.height()
        if new_y < area.y() or new_y > area.y() + area.height() - self.height():
            self.detach_from_window()
            self.position = QPointF(float(self.x()), float(self.y()))
            self.velocity = QPointF(0.0, 0.0)
            self.start_physics()
            return

        surface_max_x = max(surface.left, surface.right - self.width())
        new_x = int(max(surface.left, min(surface.left + self.sat_offset_x, surface_max_x)))
        new_x = max(area.x(), min(new_x, area.x() + area.width() - self.width()))
        self.position = QPointF(float(new_x), float(new_y))
        self.velocity = QPointF(0.0, 0.0)
        self.move(new_x, new_y)
        self.position_companion_windows()

    def get_window_titlebar_floor(self, cube_x: float, cube_y: float, min_y: float) -> tuple[float, int, int] | None:
        """Query the cached window-surface map without any Win32 calls per frame."""
        if not self.window_sitting_enabled:
            return None
        return self.window_surfaces.best_floor(
            cube_x=cube_x,
            cube_y=cube_y,
            cube_width=self.width(),
            cube_height=self.height(),
            min_y=min_y,
            edge_margin=WINDOW_SIT_EDGE_MARGIN,
            landing_tolerance=WINDOW_SIT_LANDING_TOLERANCE,
        )

    def advance_physics(self) -> None:
        if self.is_dragging:
            self.physics_timer.stop()
            return

        dt = min(max(self.elapsed.restart() / 1_000.0, 0.001), 0.04)
        screen = self.physics_screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        min_x = float(area.x())
        min_y = float(area.y())
        max_x = float(area.x() + area.width() - self.width())
        max_y = float(area.y() + area.height() - self.height())

        window_floor = self.get_window_titlebar_floor(
            self.position.x(), self.position.y(), min_y
        )
        target_max_y = window_floor[0] if window_floor is not None else max_y

        result = advance_body(
            x=self.position.x(),
            y=self.position.y(),
            vx=self.velocity.x(),
            vy=self.velocity.y(),
            dt=dt,
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=target_max_y,
            gravity=GRAVITY,
            bounce=BOUNCE,
            wall_bounce=WALL_BOUNCE,
            hurt_threshold=HURT_IMPACT_THRESHOLD,
        )
        if result.hard_impact:
            self.trigger_hurt_reaction()
        self.position = QPointF(result.x, result.y)
        self.velocity = QPointF(result.vx, result.vy)
        self.move(round(result.x), round(result.y))
        self.position_companion_windows()

        if result.grounded and result.vx == 0.0 and result.vy == 0.0:
            self.physics_timer.stop()
            self.window_scan_timer.stop()
            if window_floor is not None:
                self.sat_hwnd = window_floor[1]
                self.sat_offset_x = result.x - window_floor[2]
                self.sat_motion_until = (
                    time.monotonic() + WINDOW_SIT_MOTION_HOLD_MS / 1_000.0
                )
                self.window_track_timer.setInterval(
                    WINDOW_SIT_MOVING_TRACK_INTERVAL_MS
                )
                self.window_track_timer.start()
            else:
                self.detach_from_window()

    def position_bubble(self) -> None:
        screen = self.physics_screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = self.x() + (self.width() - self.bubble.width()) // 2
        y = self.y() - self.bubble.height() - 8
        x = max(area.x(), min(x, area.x() + area.width() - self.bubble.width()))
        if y < area.y():
            y = self.y() + self.height() + 8
        self.bubble.move(x, y)

    def position_chat_input(self) -> None:
        screen = self.physics_screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = self.x() + (self.width() - self.chat_input.width()) // 2
        y = self.y() - self.chat_input.height() - 8
        x = max(area.x(), min(x, area.x() + area.width() - self.chat_input.width()))
        if y < area.y():
            y = self.y() + self.height() + 8
        self.chat_input.move(x, y)

    def position_history_window(self) -> None:
        screen = self.physics_screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = self.x() + (self.width() - self.history_window.width()) // 2
        y = self.y() - self.history_window.height() - 10
        x = max(area.x(), min(x, area.x() + area.width() - self.history_window.width()))
        if y < area.y():
            y = self.y() + self.height() + 10
        y = max(area.y(), min(y, area.y() + area.height() - self.history_window.height()))
        self.history_window.move(x, y)

    def position_companion_windows(self) -> None:
        if self.bubble.isVisible():
            self.position_bubble()
        if self.chat_input.isVisible():
            self.position_chat_input()
        if self.history_window.isVisible():
            self.position_history_window()

    def _stop_frontend_for_exit(self) -> None:
        self.idle_mood.stop()
        self.audio_listener.close()
        for timer in (
            self.physics_timer,
            self.window_scan_timer,
            self.window_track_timer,
            self.reaction_timer,
            self.talk_timer,
            self.singing_anim_timer,
            self.thinking_anim_timer,
            self.eat_anim_timer,
            self.eat_duration_timer,
            self.idle_mood_anim_timer,
        ):
            timer.stop()
        self.unregister_global_hotkey()
        self.close_boop_sound()
        self.hurt_sounds.close()
        self.hit_wall_sounds.close()
        self.close_talk_sound()
        self.close_spawn_sound()
        self.stop_idle_mood_effects()
        self.stop_sing_sound()
        self.eat_player.stop()

    def request_quit(self) -> None:
        """Hide immediately, play one death clip, then finish the process cleanup."""
        if self.death_exit_pending or self.shutting_down:
            return
        self.death_exit_pending = True
        self.bubble.hide()
        self.chat_input.hide()
        self.history_window.hide()
        self.hide()
        self._stop_frontend_for_exit()
        wait_ms = self.play_dead_sound()
        self.death_exit_timer.start(max(1, wait_ms))
        # Model termination may take a moment, but the pet is already hidden and
        # MCI playback continues asynchronously during that cleanup.
        self.brain.shutdown()

    def shutdown(self) -> None:
        if self.shutting_down:
            return
        self.shutting_down = True
        self.death_exit_timer.stop()
        self._stop_frontend_for_exit()
        self.close_dead_sound()
        self.brain.shutdown()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.death_exit_pending and not self.shutting_down:
            event.ignore()
            self.request_quit()
            return
        self.shutdown()
        self.bubble.close()
        self.chat_input.close()
        self.history_window.close()
        super().closeEvent(event)
