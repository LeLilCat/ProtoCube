from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ACTIONS_ROOT = (ROOT / "actions").resolve()
CONFIG_PATH = ROOT / "actions.json"
SAFE_ACTION_NAME = re.compile(r"^[a-z0-9_-]+$")


@dataclass(frozen=True)
class SystemAction:
    name: str
    description: str
    action_type: str
    path: str
    arguments: tuple[str, ...] = ()


class ActionRouter:
    """Executes only named, locally configured actions after UI confirmation."""

    def __init__(self) -> None:
        self.actions: dict[str, SystemAction] = {}
        self.last_error = ""
        self.reload()

    def reload(self) -> None:
        self.actions.clear()
        self.last_error = ""
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.last_error = f"Could not read actions.json: {exc}"
            return

        entries = raw.get("actions", {}) if isinstance(raw, dict) else {}
        if not isinstance(entries, dict):
            self.last_error = "actions.json must contain an 'actions' object."
            return

        for name, config in entries.items():
            if not isinstance(name, str) or not SAFE_ACTION_NAME.fullmatch(name):
                continue
            if not isinstance(config, dict) or not config.get("enabled", True):
                continue
            action_type = config.get("type", "")
            path = config.get("path", "")
            description = config.get("description", name.replace("_", " "))
            arguments = config.get("arguments", [])
            if (
                action_type not in {"open_folder", "run_script"}
                or not isinstance(path, str)
                or not isinstance(description, str)
                or not isinstance(arguments, list)
                or not all(isinstance(item, str) for item in arguments)
            ):
                continue
            self.actions[name] = SystemAction(
                name=name,
                description=description,
                action_type=action_type,
                path=path,
                arguments=tuple(arguments),
            )

    def list_actions(self) -> list[SystemAction]:
        self.reload()
        return sorted(self.actions.values(), key=lambda action: action.name)

    def get(self, name: str) -> SystemAction | None:
        self.reload()
        return self.actions.get(name.strip().lower())

    def execute(self, action: SystemAction) -> tuple[bool, str]:
        try:
            if action.action_type == "open_folder":
                target = self._resolve_project_path(action.path)
                if not target.is_dir():
                    return False, f"Folder does not exist: {target.name}"
                os.startfile(str(target))  # type: ignore[attr-defined]
                return True, f"Opened {action.description}."

            script = self._resolve_action_script(action.path)
            if not script.is_file():
                return False, f"Action file does not exist: {script.name}"
            command = self._script_command(script, action.arguments)
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                command,
                cwd=ACTIONS_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                shell=False,
            )
            return True, f"Started {action.description}."
        except (OSError, ValueError) as exc:
            return False, str(exc)

    @staticmethod
    def _resolve_project_path(relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise ValueError("System action paths must be relative to ProtoCube.")
        target = (ROOT / path).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError("System action path escapes the ProtoCube folder.")
        return target

    @staticmethod
    def _resolve_action_script(relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise ValueError("Script paths must be relative to the actions folder.")
        target = (ACTIONS_ROOT / path).resolve()
        if not target.is_relative_to(ACTIONS_ROOT):
            raise ValueError("Script path escapes the ProtoCube actions folder.")
        return target

    @staticmethod
    def _script_command(script: Path, arguments: tuple[str, ...]) -> list[str]:
        suffix = script.suffix.lower()
        if suffix == ".py":
            pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
            if not pythonw.is_file():
                raise ValueError("ProtoCube's local Python environment is missing.")
            return [str(pythonw), str(script), *arguments]
        if suffix == ".bat":
            return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(script), *arguments]
        if suffix == ".ps1":
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                *arguments,
            ]
        if suffix == ".ahk":
            autohotkey = ROOT / "runtime" / "autohotkey" / "AutoHotkey64.exe"
            if not autohotkey.is_file():
                raise ValueError("Place AutoHotkey64.exe in runtime/autohotkey first.")
            return [str(autohotkey), str(script), *arguments]
        if suffix == ".exe":
            return [str(script), *arguments]
        raise ValueError("Allowed action files are .py, .bat, .ps1, .ahk, and .exe.")
