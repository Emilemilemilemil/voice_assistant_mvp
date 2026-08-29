from __future__ import annotations

import abc
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


# =========================================================
# Data models
# =========================================================

@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    command: str
    user: str
    cpu: float
    memory: float


@dataclass(frozen=True)
class SystemBackendResult:
    success: bool
    message: str
    data: object = None


PowerAction = Literal["sleep", "hibernate", "shutdown", "reboot", "logout"]


# =========================================================
# Abstract interface
# =========================================================

class SystemBackend(abc.ABC):
    """Platform‑agnostic interface for system operations.

    All methods must return a ``SystemBackendResult``.
    No method should ever require root privileges — they must
    use per‑user mechanisms (pactl, ps, wl‑clipboard, grim,
    wf‑recorder, loginctl --user) that work without sudo.
    """

    # ---------- Volume ----------
    @abc.abstractmethod
    def get_volume(self) -> SystemBackendResult:
        """Get current audio output volume (0–100%)."""
        raise NotImplementedError

    @abc.abstractmethod
    def set_volume(self, percent: int) -> SystemBackendResult:
        """Set audio output volume (0–100%)."""
        raise NotImplementedError

    # ---------- Processes ----------
    @abc.abstractmethod
    def list_processes(self, limit: int = 10) -> SystemBackendResult:
        """List running processes (most CPU/memory intensive first)."""
        raise NotImplementedError

    @abc.abstractmethod
    def kill_process(self, pid: int | None, name: str | None) -> SystemBackendResult:
        """Kill a process by PID or name (pkill)."""
        raise NotImplementedError

    # ---------- Clipboard ----------
    @abc.abstractmethod
    def get_clipboard(self) -> SystemBackendResult:
        """Get current clipboard text."""
        raise NotImplementedError

    @abc.abstractmethod
    def set_clipboard(self, text: str) -> SystemBackendResult:
        """Set clipboard text."""
        raise NotImplementedError

    # ---------- Screenshot / Recording ----------
    @abc.abstractmethod
    def take_screenshot(
        self,
        destination: Path,
        full_screen: bool = True,
    ) -> SystemBackendResult:
        """Take a screenshot."""
        raise NotImplementedError

    @abc.abstractmethod
    def start_recording(self, destination: Path) -> SystemBackendResult:
        """Start screen recording (stores PID for later stop)."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop_recording(self) -> SystemBackendResult:
        """Stop current recording."""
        raise NotImplementedError

    # ---------- Power ----------
    @abc.abstractmethod
    def power(self, action: PowerAction) -> SystemBackendResult:
        """Sleep, hibernate, shutdown, reboot, or logout."""
        raise NotImplementedError


# =========================================================
# Linux backend (PipeWire, ps, wl‑clipboard, grim, wf‑recorder, loginctl)
# =========================================================

class LinuxSystemBackend(SystemBackend):
    def __init__(self) -> None:
        # Verify required binaries are present
        self._available = True
        self._missing: list[str] = []
        for cmd in ["pactl", "ps", "wl-copy", "wl-paste", "grim", "wf-recorder"]:
            if not shutil.which(cmd):
                self._missing.append(cmd)
        if self._missing:
            self._available = False
        # Recording state
        self._recording_pid: int | None = None
        self._recording_start: float = 0.0

    def _unsupported(self) -> SystemBackendResult:
        return SystemBackendResult(
            success=False,
            message=f"Недоступно: отсутствуют {', '.join(self._missing)}",
        )

    # ---------- Volume ----------
    def get_volume(self) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        try:
            # PipeWire / PulseAudio: get default sink volume
            cmd = [
                "pactl",
                "get-sink-volume",
                "@DEFAULT_SINK@",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось получить громкость: {result.stderr.strip()}",
                )
            # Output: "Volume: front-left: 65536 / 65536 (100%) ..."
            import re
            match = re.search(r"(\d+)%", result.stdout)
            if not match:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось разобрать вывод: {result.stdout}",
                )
            percent = int(match.group(1))
            return SystemBackendResult(
                success=True,
                message=f"Громкость: {percent}%",
                data=percent,
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при получении громкости: {exc}",
            )

    def set_volume(self, percent: int) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        percent = max(0, min(100, percent))
        try:
            cmd = [
                "pactl",
                "set-sink-volume",
                "@DEFAULT_SINK@",
                f"{percent}%",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось установить громкость: {result.stderr.strip()}",
                )
            return SystemBackendResult(
                success=True,
                message=f"Громкость установлена на {percent}%",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при установке громкости: {exc}",
            )

    # ---------- Processes ----------
    def list_processes(self, limit: int = 10) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        try:
            # ps aux --sort=-%cpu
            cmd = [
                "ps",
                "aux",
                "--sort=-%cpu",
                "--no-headers",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось получить процессы: {result.stderr.strip()}",
                )
            lines = result.stdout.strip().splitlines()
            processes = []
            for line in lines[:limit]:
                parts = line.split(maxsplit=10)
                if len(parts) < 11:
                    continue
                pid = int(parts[1])
                user = parts[0]
                cpu = float(parts[2])
                memory = float(parts[3])
                name = parts[10].split()[0] if parts[10] else ""
                command = parts[10][:50] if parts[10] else ""
                processes.append(
                    ProcessInfo(pid, name, command, user, cpu, memory)
                )
            return SystemBackendResult(
                success=True,
                message=f"Найдено {len(processes)} процессов",
                data=processes,
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при получении процессов: {exc}",
            )

    def kill_process(self, pid: int | None, name: str | None) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        if pid is not None:
            try:
                # Send SIGTERM
                cmd = ["kill", str(pid)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
                if result.returncode != 0:
                    return SystemBackendResult(
                        success=False,
                        message=f"Не удалось завершить процесс {pid}: {result.stderr.strip()}",
                    )
                return SystemBackendResult(
                    success=True,
                    message=f"Процесс {pid} завершён",
                )
            except Exception as exc:
                return SystemBackendResult(
                    success=False,
                    message=f"Ошибка при завершении процесса {pid}: {exc}",
                )
        elif name is not None:
            try:
                cmd = ["pkill", name]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
                # pkill returns 0 if at least one process matched, 1 if none
                if result.returncode == 0:
                    return SystemBackendResult(
                        success=True,
                        message=f"Процессы с именем '{name}' завершены",
                    )
                else:
                    return SystemBackendResult(
                        success=False,
                        message=f"Процессы с именем '{name}' не найдены",
                    )
            except Exception as exc:
                return SystemBackendResult(
                    success=False,
                    message=f"Ошибка при завершении процессов '{name}': {exc}",
                )
        else:
            return SystemBackendResult(
                success=False,
                message="Не указан ни PID, ни имя процесса",
            )

    # ---------- Clipboard ----------
    def get_clipboard(self) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        try:
            # wl‑clipboard (Wayland) first, fallback to xclip (X11)
            for cmd in [["wl-paste"], ["xclip", "-out", "-selection", "clipboard"]]:
                if not shutil.which(cmd[0]):
                    continue
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return SystemBackendResult(
                        success=True,
                        message="Текст из буфера обмена",
                        data=result.stdout.strip(),
                    )
            return SystemBackendResult(
                success=False,
                message="Буфер обмена пуст или недоступен",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при чтении буфера обмена: {exc}",
            )

    def set_clipboard(self, text: str) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        try:
            # wl‑clipboard (Wayland) first, fallback to xclip (X11)
            for cmd in [["wl-copy"], ["xclip", "-in", "-selection", "clipboard"]]:
                if not shutil.which(cmd[0]):
                    continue
                result = subprocess.run(
                    cmd,
                    input=text,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if result.returncode == 0:
                    return SystemBackendResult(
                        success=True,
                        message="Текст скопирован в буфер обмена",
                    )
            return SystemBackendResult(
                success=False,
                message="Не удалось скопировать текст: буфер обмена недоступен",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при копировании в буфер обмена: {exc}",
            )

    # ---------- Screenshot ----------
    def take_screenshot(
        self,
        destination: Path,
        full_screen: bool = True,
    ) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        try:
            # grim (Wayland) first, fallback to scrot (X11)
            if shutil.which("grim"):
                cmd = ["grim", str(destination)]
                if not full_screen:
                    # TODO: implement region selection via slurp
                    return SystemBackendResult(
                        success=False,
                        message="Выбор области пока не поддерживается",
                    )
            elif shutil.which("scrot"):
                cmd = ["scrot", str(destination)]
            else:
                return SystemBackendResult(
                    success=False,
                    message="Не найдены grim или scrot",
                )
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось сделать скриншот: {result.stderr.strip()}",
                )
            return SystemBackendResult(
                success=True,
                message=f"Скриншот сохранён в {destination}",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при создании скриншота: {exc}",
            )

    # ---------- Recording ----------
    def start_recording(self, destination: Path) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        if self._recording_pid is not None:
            return SystemBackendResult(
                success=False,
                message="Запись уже ведётся",
            )
        try:
            # wf-recorder (Wayland) or ffmpeg (X11)
            if shutil.which("wf-recorder"):
                cmd = ["wf-recorder", "-f", str(destination), "-g", "$(slurp)"]
            elif shutil.which("ffmpeg"):
                # Simple X11 screen recording (requires x11grab)
                cmd = [
                    "ffmpeg",
                    "-f", "x11grab",
                    "-i", ":0.0",
                    "-r", "30",
                    str(destination),
                ]
            else:
                return SystemBackendResult(
                    success=False,
                    message="Не найдены wf-recorder или ffmpeg",
                )
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._recording_pid = process.pid
            self._recording_start = time.perf_counter()
            return SystemBackendResult(
                success=True,
                message=f"Запись начата (PID {process.pid})",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при запуске записи: {exc}",
            )

    def stop_recording(self) -> SystemBackendResult:
        if self._recording_pid is None:
            return SystemBackendResult(
                success=False,
                message="Нет активной записи",
            )
        try:
            cmd = ["kill", "-SIGINT", str(self._recording_pid)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            duration = time.perf_counter() - self._recording_start
            self._recording_pid = None
            self._recording_start = 0.0
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось остановить запись: {result.stderr.strip()}",
                )
            return SystemBackendResult(
                success=True,
                message=f"Запись остановлена (длительность {duration:.1f} с)",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при остановке записи: {exc}",
            )

    # ---------- Power ----------
    def power(self, action: PowerAction) -> SystemBackendResult:
        if not self._available:
            return self._unsupported()
        try:
            # Use loginctl (systemd) with --user flag (no root)
            # Requires polkit rules or user session permissions.
            cmd = ["loginctl"]
            if action == "sleep":
                cmd.extend(["suspend"])
            elif action == "hibernate":
                cmd.extend(["hibernate"])
            elif action == "shutdown":
                cmd.extend(["poweroff"])
            elif action == "reboot":
                cmd.extend(["reboot"])
            elif action == "logout":
                cmd.extend(["terminate-user", str(os.getuid())])
            else:
                return SystemBackendResult(
                    success=False,
                    message=f"Неизвестное действие: {action}",
                )
            # Append --user to avoid root requirement
            cmd.append("--user")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось выполнить {action}: {result.stderr.strip()}",
                )
            return SystemBackendResult(
                success=True,
                message=f"Выполняется {action}",
            )
        except Exception as exc:
            return SystemBackendResult(
                success=False,
                message=f"Ошибка при выполнении {action}: {exc}",
            )


# =========================================================
# macOS stub backend (future)
# =========================================================

class MacOSSystemBackend(SystemBackend):
    def __init__(self) -> None:
        self._available = False

    def _unimplemented(self) -> SystemBackendResult:
        return SystemBackendResult(
            success=False,
            message="System tools not yet implemented for macOS",
        )

    def get_volume(self) -> SystemBackendResult:
        return self._unimplemented()

    def set_volume(self, percent: int) -> SystemBackendResult:
        return self._unimplemented()

    def list_processes(self, limit: int = 10) -> SystemBackendResult:
        return self._unimplemented()

    def kill_process(self, pid: int | None, name: str | None) -> SystemBackendResult:
        return self._unimplemented()

    def get_clipboard(self) -> SystemBackendResult:
        return self._unimplemented()

    def set_clipboard(self, text: str) -> SystemBackendResult:
        return self._unimplemented()

    def take_screenshot(
        self,
        destination: Path,
        full_screen: bool = True,
    ) -> SystemBackendResult:
        return self._unimplemented()

    def start_recording(self, destination: Path) -> SystemBackendResult:
        return self._unimplemented()

    def stop_recording(self) -> SystemBackendResult:
        return self._unimplemented()

    def power(self, action: PowerAction) -> SystemBackendResult:
        return self._unimplemented()


# =========================================================
# Windows stub backend (future)
# =========================================================

class WindowsSystemBackend(SystemBackend):
    def __init__(self) -> None:
        self._available = False

    def _unimplemented(self) -> SystemBackendResult:
        return SystemBackendResult(
            success=False,
            message="System tools not yet implemented for Windows",
        )

    def get_volume(self) -> SystemBackendResult:
        return self._unimplemented()

    def set_volume(self, percent: int) -> SystemBackendResult:
        return self._unimplemented()

    def list_processes(self, limit: int = 10) -> SystemBackendResult:
        return self._unimplemented()

    def kill_process(self, pid: int | None, name: str | None) -> SystemBackendResult:
        return self._unimplemented()

    def get_clipboard(self) -> SystemBackendResult:
        return self._unimplemented()

    def set_clipboard(self, text: str) -> SystemBackendResult:
        return self._unimplemented()

    def take_screenshot(
        self,
        destination: Path,
        full_screen: bool = True,
    ) -> SystemBackendResult:
        return self._unimplemented()

    def start_recording(self, destination: Path) -> SystemBackendResult:
        return self._unimplemented()

    def stop_recording(self) -> SystemBackendResult:
        return self._unimplemented()

    def power(self, action: PowerAction) -> SystemBackendResult:
        return self._unimplemented()


# =========================================================
# Factory
# =========================================================

class SystemBackendFactory:
    @staticmethod
    def create() -> SystemBackend:
        """Return a platform‑appropriate system backend.

        If no backend is fully available, returns a stub that
        reports "unavailable" for all operations.
        """
        if sys.platform == "linux":
            backend = LinuxSystemBackend()
            if backend._available:
                return backend
            # Fall through to stub
        elif sys.platform == "darwin":
            return MacOSSystemBackend()
        elif sys.platform == "win32":
            return WindowsSystemBackend()
        # Generic stub (Linux missing binaries)
        class GenericUnavailableBackend(SystemBackend):
            def _unavailable(self) -> SystemBackendResult:
                return SystemBackendResult(
                    success=False,
                    message="System tools unavailable on this platform",
                )
            def get_volume(self) -> SystemBackendResult:
                return self._unavailable()
            def set_volume(self, percent: int) -> SystemBackendResult:
                return self._unavailable()
            def list_processes(self, limit: int = 10) -> SystemBackendResult:
                return self._unavailable()
            def kill_process(self, pid: int | None, name: str | None) -> SystemBackendResult:
                return self._unavailable()
            def get_clipboard(self) -> SystemBackendResult:
                return self._unavailable()
            def set_clipboard(self, text: str) -> SystemBackendResult:
                return self._unavailable()
            def take_screenshot(self, destination: Path, full_screen: bool = True) -> SystemBackendResult:
                return self._unavailable()
            def start_recording(self, destination: Path) -> SystemBackendResult:
                return self._unavailable()
            def stop_recording(self) -> SystemBackendResult:
                return self._unavailable()
            def power(self, action: PowerAction) -> SystemBackendResult:
                return self._unavailable()
        return GenericUnavailableBackend()