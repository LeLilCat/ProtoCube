from __future__ import annotations

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class ChatBubble(QWidget):
    dismissed = pyqtSignal()
    user_activity = pyqtSignal()

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
        self.message = "bwaa…"

        self.close_button = QPushButton("x", self)
        self.close_button.setFixedSize(20, 20)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setToolTip("Close this message")
        self.close_button.setStyleSheet(
            "QPushButton{background:transparent;color:#111;border:none;border-radius:8px;"
            "font-size:12px;font-weight:bold;padding:0}"
            "QPushButton:hover{background:#ddd}QPushButton:pressed{background:#bbb}"
        )
        self.close_button.clicked.connect(self.dismiss_by_user)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.dismiss)
        self._position_close_button()

    def show_message(self, message: str, duration_ms: int = 1_500) -> None:
        self.message = message.strip()
        font = self.font()
        font.setPointSize(10)
        metrics = QFontMetrics(font)
        width = (
            max(230, min(400, metrics.horizontalAdvance(self.message) + 42))
            if len(self.message) <= 34 and "\n" not in self.message
            else 400
        )
        bounds = metrics.boundingRect(
            QRect(0, 0, width - 32, 2_000),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.message,
        )
        self.setFixedSize(width, max(78, min(230, bounds.height() + 40)))
        self._position_close_button()
        self.update()
        self.show()
        self.raise_()
        self.close_button.raise_()
        if duration_ms > 0:
            self.hide_timer.start(duration_ms)
        else:
            self.hide_timer.stop()

    def _position_close_button(self) -> None:
        self.close_button.move(self.width() - self.close_button.width() - 8, 8)

    def dismiss(self) -> None:
        self.hide_timer.stop()
        self.hide()
        self.dismissed.emit()

    def dismiss_by_user(self) -> None:
        self.user_activity.emit()
        self.dismiss()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bubble = QRect(3, 3, self.width() - 6, self.height() - 17)
        path = QPainterPath()
        path.addRoundedRect(
            float(bubble.x()), float(bubble.y()), float(bubble.width()), float(bubble.height()), 13.0, 13.0
        )
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
    clear_requested = pyqtSignal()
    user_activity = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle("ProtoCube Chat History")
        self.resize(500, 380)
        self.transcript = QPlainTextEdit(self)
        self.transcript.setReadOnly(True)
        self.transcript.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.transcript.setPlaceholderText("No chat history yet.")
        clear_button = QPushButton("Clear history", self)
        clear_button.clicked.connect(self.clear_requested.emit)
        clear_button.clicked.connect(lambda _checked=False: self.user_activity.emit())
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.hide)
        close_button.clicked.connect(lambda _checked=False: self.user_activity.emit())
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(clear_button)
        row.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.transcript, 1)
        layout.addLayout(row)
        self.setStyleSheet(
            "QWidget{background:#fff;color:#111}"
            "QPlainTextEdit{background:#f5f5f5;color:#111;border:1px solid #999;"
            "border-radius:7px;padding:8px;selection-background-color:#111;selection-color:#fff}"
            "QPushButton{background:#111;color:#fff;border:none;border-radius:7px;"
            "padding:7px 12px;font-weight:bold}QPushButton:pressed{background:#444}"
        )

    def set_entries(self, entries: list[tuple[str, str]]) -> None:
        self.transcript.setPlainText(
            "\n\n".join(f"{speaker}\n{text}" for speaker, text in entries)
        )
        scrollbar = self.transcript.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_history(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()


class ChatInput(QWidget):
    submitted = pyqtSignal(str, str)
    user_activity = pyqtSignal()

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
        self.prompt_input.textEdited.connect(lambda _text: self.user_activity.emit())
        close_button = QPushButton("x", self)
        close_button.setObjectName("chatCloseButton")
        close_button.setFixedSize(24, 24)
        close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_button.setToolTip("Close chat input")
        close_button.clicked.connect(self.hide_by_user)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(5)
        layout.addWidget(self.prompt_input, 1)
        layout.addWidget(close_button)
        self.setStyleSheet(
            "QWidget#chatPanel{background:white;border:2px solid #111;border-radius:12px}"
            "QLineEdit{background:white;border:none;color:#111;padding:5px;"
            "selection-background-color:#111;selection-color:white}"
            "QPushButton{background:#111;color:white;border:none;border-radius:7px;padding:6px;font-weight:bold}"
            "QPushButton:pressed{background:#444}"
            "QPushButton#chatCloseButton{background:transparent;color:#111;padding:0;font-size:13px}"
            "QPushButton#chatCloseButton:hover{background:#ddd}"
        )
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        shortcut.activated.connect(self.hide_by_user)

    def hide_by_user(self) -> None:
        self.user_activity.emit()
        self.hide()

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            self.hide()
        return super().event(event)

    def show_for_input(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.prompt_input.setFocus(Qt.FocusReason.MouseFocusReason)

    def set_context_hint(self, name: str = "") -> None:
        self.prompt_input.setPlaceholderText(
            f"Ask about {name}…" if name else "Ask ProtoCube…"
        )

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
