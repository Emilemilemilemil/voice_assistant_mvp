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
        # Per-capability binary checks (not a single global flag)
        self._capabilities: dict[str, bool] = {}
        capabilities = {
            "volume": "pactl",
            "processes": "ps",
            "clipboard_in": "wl-paste",
            "clipboard_out": "wl-copy",
            "clipboard_fallback": "xclip",
            "screenshot": "grim",
            "recording": "wf-recorder",
            "recording_fallback": "ffmpeg",
            "power": "loginctl",
        }
        for cap, cmd in capabilities.items():
            self._capabilities[cap] = shutil.which(cmd) is not None
        # Recording state
        self._recording_pid: int | None = None
        self._recording_start: float = 0.0

    def _capable(self, cap: str) -> bool:
        return self._capabilities.get(cap, False)

    def _unsupported(self, cap: str | None = None) -> SystemBackendResult:
        cap_name = cap or "system"
        missing = [cmd for cmd, c in {
            "volume": "pactl", "processes": "ps",
            "clipboard_in": "wl-paste", "clipboard_out": "wl-copy",
            "clipboard_fallback": "xclip", "screenshot": "grim",
            "recording": "wf-recorder", "recording_fallback": "ffmpeg",
            "power": "loginctl",
        }.items() if c == cap_name and not shutil.which(cmd)]
        return SystemBackendResult(
            success=False,
            message=f"Недоступно: отсутствуют {cap_name} (отсутствует: {', '.join(missing) if missing else 'неизвестно'})",
        )

    # ---------- Volume ----------
    def _default_sink(self) -> str | None:
        """Resolve @DEFAULT_SINK@ to its actual name. Cached to avoid
        drift if the default changes mid-session."""
        if not hasattr(self, "_cached_sink") or not hasattr(self, "_sink_resolved_at"):
            self._cached_sink = None
            self._sink_resolved_at = 0.0
        # Re-resolve every 5s (default-sink can change when a headset plugs in)
        if self._cached_sink and (time.perf_counter() - self._sink_resolved_at) < 5.0:
            return self._cached_sink
        try:
            res = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True, text=True, timeout=2.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                self._cached_sink = res.stdout.strip()
                self._sink_resolved_at = time.perf_counter()
                return self._cached_sink
        except Exception:
            pass
        return self._cached_sink or "@DEFAULT_SINK@"

    def get_volume(self) -> SystemBackendResult:
        if not self._capable("volume"):
            return SystemBackendResult(success=False, message="pactl не найден")
        try:
            sink = self._default_sink()
            cmd = ["pactl", "get-sink-volume", sink]
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
            import re
            # Output: "Volume: front-left: 65536 / 65536 (100%) ..."
            # The first % may be the first channel; if multiple channels,
            # use the LAST match (the "% / %" line often shows the average).
            matches = re.findall(r"(\d+)%", result.stdout)
            if not matches:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось разобрать вывод: {result.stdout}",
                )
            percent = int(matches[-1])
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
        if not self._capable("volume"):
            return SystemBackendResult(success=False, message="pactl не найден")
        percent = max(0, min(100, percent))
        try:
            sink = self._default_sink()

            # Set sink volume
            result = subprocess.run(
                ["pactl", "set-sink-volume", sink, f"{percent}%"],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось установить громкость: {result.stderr.strip()}",
                )

            # Also apply to all active streams (pw-play, etc.)
            # so changing sink volume also silences any already-playing audio
            streams = subprocess.run(
                ["pactl", "list", "sink-inputs", "short"],
                capture_output=True, text=True, timeout=5.0,
            )
            if streams.returncode == 0:
                for line in streams.stdout.strip().splitlines():
                    parts = line.split()
                    if parts:
                        stream_id = parts[0]
                        subprocess.run(
                            ["pactl", "set-sink-input-volume", stream_id, f"{percent}%"],
                            capture_output=True, timeout=2.0,
                        )

            # Verify the change actually took effect
            verify = self.get_volume()
            actual = verify.data if verify.success else None
            if actual is None or abs(actual - percent) > 2:
                return SystemBackendResult(
                    success=False,
                    message=(
                        f"Запрошено {percent}%, фактически {actual}% "
                        f"(sink={sink}). Громкость не изменилась."
                    ),
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
        if not self._capable("processes"):
            return SystemBackendResult(success=False, message="ps не найден")
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
        if not self._capable("processes"):
            return SystemBackendResult(success=False, message="ps/kill не найдены")
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
        if not (self._capable("clipboard_in") or self._capable("clipboard_fallback")):
            return SystemBackendResult(success=False, message="wl-paste/xclip не найдены")
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
        if not (self._capable("clipboard_out") or self._capable("clipboard_fallback")):
            return SystemBackendResult(success=False, message="wl-copy/xclip не найдены")
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
        if not self._capable("screenshot"):
            return SystemBackendResult(success=False, message="grim/scrot не найдены")
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
        if not self._capable("recording"):
            return SystemBackendResult(success=False, message="wf-recorder или ffmpeg не найдены")
        if self._recording_pid is not None:
            return SystemBackendResult(
                success=False,
                message="Запись уже ведётся",
            )
        try:
            # Detect Wayland vs X11
            wayland_display = os.environ.get("WAYLAND_DISPLAY")
            x11_display = os.environ.get("DISPLAY")

            if wayland_display and shutil.which("wf-recorder"):
                cmd = ["wf-recorder", "-f", str(destination)]
            elif x11_display and shutil.which("ffmpeg"):
                cmd = [
                    "ffmpeg",
                    "-f", "x11grab",
                    "-i", x11_display,
                    "-r", "30",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-y",
                    str(destination),
                ]
            else:
                return SystemBackendResult(
                    success=False,
                    message="Не найдены wf-recorder (Wayland) или ffmpeg+x11grab (X11)",
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
            proc = subprocess.run(
                ["kill", "-TERM", str(self._recording_pid)],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            duration = time.perf_counter() - self._recording_start
            self._recording_pid = None
            self._recording_start = 0.0
            if proc.returncode != 0:
                return SystemBackendResult(
                    success=False,
                    message=f"Не удалось остановить запись: {proc.stderr.strip()}",
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
        if not self._capable("power"):
            return SystemBackendResult(success=False, message="loginctl не найден")
        try:
            # loginctl operates on the calling user's session (no root needed)
            # --user flag is only valid for user-scoped commands
            if action == "logout":
                # terminate-user requires --user flag
                cmd = ["loginctl", "--user", "terminate-user", str(os.getuid())]
            else:
                # suspend / hibernate / poweroff / reboot act on current session
                subcmd = {"sleep": "suspend", "hibernate": "hibernate",
                          "shutdown": "poweroff", "reboot": "reboot"}[action]
                cmd = ["loginctl", subcmd]
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
            # Per-capability: if at least one capability is available, use the
            # real backend (unavailable capabilities return errors per-call).
            if any(backend._capabilities.values()):
                return backend
            # Fall through to stub only if every binary is missing
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