from __future__ import annotations

import ctypes
import os
import random
from pathlib import Path


class MciClip:
    """Small, explicitly-owned WinMM/MCI audio clip."""

    _counter = 0

    def __init__(self, path: Path, prefix: str = "protocube", volume: int = 1000) -> None:
        self.path = path
        self.alias = ""
        self.duration_ms = 0
        self._send = None
        if os.name != "nt" or not path.is_file():
            return
        try:
            self._send = ctypes.WinDLL("winmm", use_last_error=True).mciSendStringW
            self._send.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            self._send.restype = ctypes.c_uint
            type(self)._counter += 1
            self.alias = f"{prefix}_{os.getpid()}_{type(self)._counter}"
            quoted = str(path).replace('"', '""')
            media_type = "waveaudio" if path.suffix.casefold() == ".wav" else "mpegvideo"
            if self._command(f'open "{quoted}" type {media_type} alias {self.alias}') != 0:
                self.alias = ""
                return
            self._command(f"setaudio {self.alias} volume to {max(0, min(1000, volume))}")
            self._command(f"set {self.alias} time format milliseconds")
            buffer = ctypes.create_unicode_buffer(64)
            if self._send(f"status {self.alias} length", buffer, len(buffer), None) == 0:
                try:
                    self.duration_ms = max(0, int(buffer.value.strip()))
                except ValueError:
                    pass
        except (AttributeError, OSError):
            self.alias = ""
            self._send = None

    @property
    def is_open(self) -> bool:
        return bool(self.alias and self._send is not None)

    def _command(self, command: str) -> int:
        if self._send is None:
            return 1
        return int(self._send(command, None, 0, None))

    def is_playing(self) -> bool:
        if not self.is_open:
            return False
        buffer = ctypes.create_unicode_buffer(32)
        assert self._send is not None
        if self._send(f"status {self.alias} mode", buffer, len(buffer), None) != 0:
            return False
        return buffer.value.strip().casefold() == "playing"

    def play(
        self,
        *,
        restart: bool = True,
        wait: bool = False,
        repeat: bool = False,
    ) -> bool:
        if not self.is_open:
            return False
        if restart:
            self._command(f"stop {self.alias}")
            self._command(f"seek {self.alias} to start")
        suffix = (" repeat" if repeat else "") + (" wait" if wait else "")
        return self._command(f"play {self.alias}{suffix}") == 0

    def stop(self) -> None:
        if self.is_open:
            self._command(f"stop {self.alias}")

    def close(self) -> None:
        alias = self.alias
        self.alias = ""
        if alias and self._send is not None:
            self._command(f"stop {alias}")
            self._command(f"close {alias}")


class ShuffledSoundBank:
    """Round-robin-shuffled sounds with extra overlap voices opened only on demand."""

    def __init__(
        self,
        paths: list[Path],
        *,
        max_voices_per_sound: int = 1,
        prefix: str = "bank",
        volume: int = 1000,
    ) -> None:
        self.paths = list(paths)
        self.max_voices_per_sound = max(1, max_voices_per_sound)
        self.prefix = prefix
        self.volume = volume
        self._order: list[int] = []
        self._last_index: int | None = None
        self._voices: dict[int, list[MciClip]] = {}

    def _next_index(self) -> int | None:
        if not self.paths:
            return None
        if not self._order:
            self._order = list(range(len(self.paths)))
            random.shuffle(self._order)
            if (
                len(self._order) > 1
                and self._last_index is not None
                and self._order[-1] == self._last_index
            ):
                self._order[-1], self._order[-2] = self._order[-2], self._order[-1]
        index = self._order.pop()
        self._last_index = index
        return index

    def _voice_for(self, index: int) -> MciClip | None:
        voices = self._voices.setdefault(index, [])
        for voice in voices:
            if not voice.is_playing():
                return voice
        if len(voices) < self.max_voices_per_sound:
            voice = MciClip(self.paths[index], self.prefix, self.volume)
            if voice.is_open:
                voices.append(voice)
                return voice
        return voices[0] if voices else None

    def play(self, *, wait: bool = False) -> tuple[Path | None, int]:
        index = self._next_index()
        if index is None:
            return None, 0
        voice = self._voice_for(index)
        if voice is None:
            return self.paths[index], 0
        voice.play(restart=True, wait=wait)
        return self.paths[index], voice.duration_ms

    def close(self) -> None:
        for voices in self._voices.values():
            for voice in voices:
                voice.close()
        self._voices.clear()
        self._order.clear()
        self._last_index = None
