from __future__ import annotations

import ctypes
import sys
import time
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTimer

from config import (
    ACTIVATE_HOTKEY_ID,
    GLOBAL_HOTKEY_ID,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    VK_F,
    VK_SPACE,
)


VK_LEFT = 0x25
VK_RIGHT = 0x27


@dataclass(frozen=True)
class WindowSurface:
    hwnd: int
    left: int
    top: int
    right: int
    bottom: int


class WindowSurfaceTracker:
    """Cache usable window rectangles and cheaply track one landed-on window."""

    def __init__(self) -> None:
        self.surfaces: tuple[WindowSurface, ...] = ()
        self.last_refresh = 0.0
        self._user32 = None
        self._dwmapi = None
        if sys.platform == "win32":
            try:
                self._user32 = ctypes.WinDLL("user32", use_last_error=True)
                self._dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
            except (AttributeError, OSError):
                self._user32 = None
                self._dwmapi = None

    def _is_usable(self, hwnd: int, excluded: set[int]) -> bool:
        user32 = self._user32
        if user32 is None or not hwnd or hwnd in excluded:
            return False
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return False
            if user32.GetWindowLongW(hwnd, -20) & 0x00000080:  # WS_EX_TOOLWINDOW
                return False
            if self._dwmapi is not None:
                cloaked = ctypes.c_int(0)
                result = self._dwmapi.DwmGetWindowAttribute(
                    hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                )
                if result == 0 and cloaked.value:
                    return False
            return True
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def window_rect(self, hwnd: int, excluded: set[int] | None = None) -> WindowSurface | None:
        user32 = self._user32
        excluded = excluded or set()
        if user32 is None or not self._is_usable(hwnd, excluded):
            return None
        rect = wintypes.RECT()
        try:
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
        except (AttributeError, OSError, TypeError, ValueError):
            return None
        return WindowSurface(hwnd, rect.left, rect.top, rect.right, rect.bottom)

    def refresh(
        self,
        excluded: set[int],
        *,
        min_width: int,
        min_height: int,
    ) -> None:
        user32 = self._user32
        if user32 is None:
            self.surfaces = ()
            return
        found: list[WindowSurface] = []

        def enum_proc(raw_hwnd, _lparam):
            hwnd = int(raw_hwnd)
            surface = self.window_rect(hwnd, excluded)
            if surface is not None:
                if surface.right - surface.left > min_width and surface.bottom - surface.top > min_height:
                    found.append(surface)
            return True

        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        try:
            user32.EnumWindows(callback_type(enum_proc), 0)
            self.surfaces = tuple(found)
            self.last_refresh = time.monotonic()
        except (AttributeError, OSError, TypeError, ValueError):
            self.surfaces = ()

    def best_floor(
        self,
        *,
        cube_x: float,
        cube_y: float,
        cube_width: int,
        cube_height: int,
        min_y: float,
        edge_margin: int,
        landing_tolerance: int,
    ) -> tuple[float, int, int] | None:
        cube_right = cube_x + cube_width
        best: tuple[float, int, int] | None = None
        for surface in self.surfaces:
            if cube_right <= surface.left + edge_margin or cube_x >= surface.right - edge_margin:
                continue
            floor = float(surface.top - cube_height)
            if floor < min_y or cube_y > floor + landing_tolerance:
                continue
            if best is None or floor < best[0]:
                best = (floor, surface.hwnd, surface.left)
        return best


class MediaKeySender(QObject):
    """Send repeated Windows media keys without sleeping on the GUI thread."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: deque[int] = deque()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._send_next)

    def send(self, vk_code: int, repeat: int = 1) -> None:
        if sys.platform != "win32":
            return
        self._queue.extend([vk_code] * max(1, repeat))
        if not self._timer.isActive():
            self._send_next()

    def _send_next(self) -> None:
        if not self._queue:
            self._timer.stop()
            return
        vk_code = self._queue.popleft()
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, 0x0002, 0)
        except (AttributeError, OSError):
            self._queue.clear()
        if self._queue:
            self._timer.start()
        else:
            self._timer.stop()


def register_hotkeys(hwnd: int) -> tuple[bool, bool]:
    if sys.platform != "win32":
        return False, False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        register = user32.RegisterHotKey
        register.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        register.restype = wintypes.BOOL
        clipboard_ok = bool(
            register(hwnd, GLOBAL_HOTKEY_ID, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE)
        )
        activate_ok = bool(
            register(hwnd, ACTIVATE_HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F)
        )
        return clipboard_ok, activate_ok
    except (AttributeError, OSError):
        return False, False


def unregister_hotkeys(hwnd: int, clipboard: bool, activate: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if clipboard:
            user32.UnregisterHotKey(hwnd, GLOBAL_HOTKEY_ID)
        if activate:
            user32.UnregisterHotKey(hwnd, ACTIVATE_HOTKEY_ID)
    except (AttributeError, OSError):
        pass
