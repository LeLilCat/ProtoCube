from __future__ import annotations

import random
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class IdleMoodController(QObject):
    """Event-driven inactivity phases using only two single-shot timers."""

    phase_changed = pyqtSignal(int, object)
    chatter_due = pyqtSignal(int, object)

    def __init__(
        self,
        phases: list[dict[str, object]],
        *,
        enabled: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.enabled = enabled
        self.phases = sorted(
            (dict(phase) for phase in phases),
            key=lambda phase: int(phase.get("inactivity_ms", 0)),
        )
        self.current_index = -1
        self.last_activity = time.monotonic()

        self.transition_timer = QTimer(self)
        self.transition_timer.setSingleShot(True)
        self.transition_timer.timeout.connect(self._sync_phase)

        self.chatter_timer = QTimer(self)
        self.chatter_timer.setSingleShot(True)
        self.chatter_timer.timeout.connect(self._emit_chatter)

    def start(self) -> None:
        if not self.enabled or not self.phases:
            return
        self.record_activity()

    def stop(self) -> None:
        self.transition_timer.stop()
        self.chatter_timer.stop()

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.record_activity()
            return
        self.stop()
        self.current_index = -1
        self.phase_changed.emit(-1, {})

    def record_activity(self) -> None:
        if not self.enabled or not self.phases:
            return
        self.last_activity = time.monotonic()
        self._enter_phase(0, force=True)

    def _sync_phase(self) -> None:
        if not self.enabled or not self.phases:
            return
        elapsed_ms = max(0, int((time.monotonic() - self.last_activity) * 1_000))
        target = 0
        for index, phase in enumerate(self.phases):
            if elapsed_ms >= int(phase.get("inactivity_ms", 0)):
                target = index
            else:
                break
        self._enter_phase(target)

    def _enter_phase(self, index: int, *, force: bool = False) -> None:
        if not self.phases:
            return
        index = max(0, min(index, len(self.phases) - 1))
        changed = index != self.current_index
        self.current_index = index
        self.transition_timer.stop()
        self.chatter_timer.stop()

        phase = self.phases[index]
        if changed or force:
            self.phase_changed.emit(index, phase)

        elapsed_ms = max(0, int((time.monotonic() - self.last_activity) * 1_000))
        if index + 1 < len(self.phases):
            next_threshold = int(self.phases[index + 1].get("inactivity_ms", 0))
            self.transition_timer.start(max(1, min(2_147_483_647, next_threshold - elapsed_ms)))
        self._schedule_chatter(phase)

    def _schedule_chatter(self, phase: dict[str, object]) -> None:
        interval = phase.get("chatter_interval_ms")
        lines = phase.get("lines")
        if not isinstance(interval, (tuple, list)) or len(interval) != 2 or not lines:
            return
        minimum = max(1, int(interval[0]))
        maximum = max(minimum, int(interval[1]))
        self.chatter_timer.start(random.randint(minimum, maximum))

    def _emit_chatter(self) -> None:
        if self.current_index < 0 or self.current_index >= len(self.phases):
            return
        phase = self.phases[self.current_index]
        self.chatter_due.emit(self.current_index, phase)
        self._schedule_chatter(phase)
