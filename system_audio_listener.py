from __future__ import annotations

import ctypes
import sys
import time
import uuid
from collections.abc import Callable
from ctypes import wintypes

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        parsed = uuid.UUID(value)
        return cls(
            parsed.time_low,
            parsed.time_mid,
            parsed.time_hi_version,
            (ctypes.c_ubyte * 8)(*parsed.bytes[8:]),
        )


class SystemAudioMeter:
    """Windows WASAPI peak meter with deterministic COM interface cleanup."""

    def __init__(self) -> None:
        self._ole32 = None
        self._com_initialized = False
        self._enum = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._meter = ctypes.c_void_p()
        self._get_peak = None
        if sys.platform != "win32":
            return
        try:
            self._ole32 = ctypes.WinDLL("ole32", use_last_error=True)
            result = int(self._ole32.CoInitialize(None))
            self._com_initialized = result in (0, 1)  # S_OK or S_FALSE

            enumerator_class = GUID.from_string("BCDE0395-E52F-467C-8E3D-C4579291692E")
            enumerator_interface = GUID.from_string("A95664D2-9614-4F35-A746-DE8DB63617E6")
            meter_interface = GUID.from_string("C02216F6-8C67-4B5B-9D00-D008E73E0064")
            created = self._ole32.CoCreateInstance(
                ctypes.byref(enumerator_class),
                None,
                1,
                ctypes.byref(enumerator_interface),
                ctypes.byref(self._enum),
            )
            if created != 0 or not self._enum:
                self.close()
                return

            enum_vtable = ctypes.cast(
                self._enum, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            ).contents
            get_endpoint_type = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            )
            get_endpoint = get_endpoint_type(enum_vtable[4])
            if get_endpoint(self._enum, 0, 0, ctypes.byref(self._device)) != 0 or not self._device:
                self.close()
                return

            device_vtable = ctypes.cast(
                self._device, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            ).contents
            activate_type = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.POINTER(GUID),
                ctypes.c_ulong,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            )
            activate = activate_type(device_vtable[3])
            if (
                activate(
                    self._device,
                    ctypes.byref(meter_interface),
                    1,
                    None,
                    ctypes.byref(self._meter),
                )
                != 0
                or not self._meter
            ):
                self.close()
                return

            meter_vtable = ctypes.cast(
                self._meter, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            ).contents
            get_peak_type = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)
            )
            self._get_peak = get_peak_type(meter_vtable[3])
        except (AttributeError, OSError, TypeError, ValueError):
            self.close()

    @property
    def available(self) -> bool:
        return bool(self._meter and self._get_peak is not None)

    def get_peak_level(self) -> float:
        if not self.available:
            return 0.0
        peak = ctypes.c_float(0.0)
        try:
            assert self._get_peak is not None
            if self._get_peak(self._meter, ctypes.byref(peak)) == 0:
                return max(0.0, min(1.0, float(peak.value)))
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        return 0.0

    @staticmethod
    def _release(pointer: ctypes.c_void_p) -> None:
        if not pointer:
            return
        try:
            vtable = ctypes.cast(
                pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            ).contents
            release_type = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
            release_type(vtable[2])(pointer)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

    def close(self) -> None:
        self._get_peak = None
        for pointer in (self._meter, self._device, self._enum):
            self._release(pointer)
        self._meter = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._enum = ctypes.c_void_p()
        if self._com_initialized and self._ole32 is not None:
            try:
                self._ole32.CoUninitialize()
            except (AttributeError, OSError):
                pass
        self._com_initialized = False


class AdaptiveAudioListener(QObject):
    """Poll slowly while quiet and temporarily accelerate while audio is active."""

    active_changed = pyqtSignal(bool)
    peak_sampled = pyqtSignal(float)

    def __init__(
        self,
        *,
        enabled: bool,
        idle_interval_ms: int,
        active_interval_ms: int,
        activation_threshold: float,
        release_threshold: float,
        release_delay_ms: int,
        blocked: Callable[[], bool],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.enabled = enabled
        self.idle_interval_ms = max(100, idle_interval_ms)
        self.active_interval_ms = max(25, active_interval_ms)
        self.activation_threshold = max(0.0, activation_threshold)
        self.release_threshold = max(0.0, min(activation_threshold, release_threshold))
        self.release_delay_seconds = max(0, release_delay_ms) / 1_000.0
        self.blocked = blocked
        self.meter = SystemAudioMeter() if enabled else None
        self.active = False
        self.last_audible_time = 0.0

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.timer.setInterval(self.idle_interval_ms)
        self.timer.timeout.connect(self._poll)

    @property
    def available(self) -> bool:
        return bool(self.meter and self.meter.available)

    def start(self) -> None:
        if self.enabled and self.available:
            self.timer.start(self.idle_interval_ms)

    def stop(self) -> None:
        self.timer.stop()
        self._set_active(False)

    def close(self) -> None:
        self.stop()
        if self.meter is not None:
            self.meter.close()
            self.meter = None

    def refresh_blocked_state(self) -> None:
        """Immediately leave active mode when the owner's state blocks listening."""
        if self.blocked():
            self._set_active(False)
            self._set_interval(self.idle_interval_ms)

    def _set_active(self, active: bool) -> None:
        if active == self.active:
            return
        self.active = active
        self.active_changed.emit(active)

    def _set_interval(self, interval_ms: int) -> None:
        if self.timer.interval() != interval_ms:
            self.timer.setInterval(interval_ms)

    def _poll(self) -> None:
        if not self.available:
            self.stop()
            return
        if self.blocked():
            self._set_active(False)
            self._set_interval(self.idle_interval_ms)
            return

        assert self.meter is not None
        peak = self.meter.get_peak_level()
        now = time.monotonic()
        if not self.active:
            if peak >= self.activation_threshold:
                self.last_audible_time = now
                self._set_active(True)
                self._set_interval(self.active_interval_ms)
                self.peak_sampled.emit(peak)
            return

        self.peak_sampled.emit(peak)
        if peak >= self.release_threshold:
            self.last_audible_time = now
        elif now - self.last_audible_time >= self.release_delay_seconds:
            self._set_active(False)
            self._set_interval(self.idle_interval_ms)
