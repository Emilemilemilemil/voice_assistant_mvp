from __future__ import annotations

import time
from pathlib import Path

from safety.risk import RiskLevel
from tools.base import Tool, ToolResult
from tools.system_backend import (
    SystemBackend,
    SystemBackendFactory,
    PowerAction,
)
from config import Config


# =========================================================
# System tools (SAFE)
# =========================================================

class GetVolumeTool(Tool):
    name = "get_volume"
    risk = RiskLevel.SAFE
    description = """
    Возвращает текущую громкость звука (0–100%).

    Аргументы: нет.

    Примеры:
    - "какая сейчас громкость?"
    - "сколько процентов звука?"
    """
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        result = self._backend.get_volume()
        return ToolResult(
            success=result.success,
            output=result.message,
        )


class SetVolumeTool(Tool):
    name = "set_volume"
    risk = RiskLevel.SAFE
    description = """
    Устанавливает громкость звука (0–100%).

    Аргументы:
    percent: новая громкость в процентах.

    Примеры:
    - 50 (установить на половину)
    """
    parameters = {
        "type": "object",
        "properties": {
            "percent": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Новая громкость (0–100%).",
            }
        },
        "required": ["percent"],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, percent: int) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        result = self._backend.set_volume(percent)
        return ToolResult(
            success=result.success,
            output=result.message,
        )


class ListProcessesTool(Tool):
    name = "list_processes"
    risk = RiskLevel.SAFE
    description = """
    Показывает запущенные процессы (по умолчанию 10 самых ресурсоёмких).

    Аргументы:
    limit: количество процессов для отображения (по умолчанию 10).

    Примеры:
    - 5 (показать 5 процессов)
    """
    parameters = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Количество процессов (по умолчанию 10).",
            }
        },
        "required": [],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, limit: int = 10) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        result = self._backend.list_processes(limit)
        if not result.success:
            return ToolResult(success=False, output=result.message)

        data = result.data
        if not data:
            return ToolResult(success=True, output="Нет запущенных процессов.")

        lines = []
        for proc in data:
            lines.append(
                f"PID {proc.pid:6}  CPU {proc.cpu:5.1f}%  MEM {proc.memory:5.1f}%  {proc.name}"
            )
        return ToolResult(success=True, output="\n".join(lines))


class GetClipboardTool(Tool):
    name = "get_clipboard"
    risk = RiskLevel.SAFE
    description = """
    Возвращает текст из буфера обмена (максимум 500 символов).

    Аргументы: нет.

    Примеры:
    - "что в буфере обмена?"
    """
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        result = self._backend.get_clipboard()
        if not result.success:
            return ToolResult(success=False, output=result.message)

        text = result.data or ""
        if len(text) > 500:
            text = text[:500] + "..."
        return ToolResult(success=True, output=text)


class SetClipboardTool(Tool):
    name = "set_clipboard"
    risk = RiskLevel.SAFE
    description = """
    Копирует текст в буфер обмена.

    Аргументы:
    text: текст для копирования.

    Примеры:
    - "Hello world" (копирует строку)
    """
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Текст для копирования (максимум 1000 символов).",
            }
        },
        "required": ["text"],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, text: str) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        if len(text) > 1000:
            return ToolResult(
                success=False,
                output="Текст слишком длинный (максимум 1000 символов).",
            )
        result = self._backend.set_clipboard(text)
        return ToolResult(
            success=result.success,
            output=result.message,
        )


class TakeScreenshotTool(Tool):
    name = "take_screenshot"
    risk = RiskLevel.SAFE
    description = """
    Делает скриншот и сохраняет в домашней директории.

    Аргументы:
    filename: имя файла (по умолчанию screenshot_YYYYMMDD_HHMMSS.png).
    full_screen: полный экран или выбранная область (по умолчанию true).

    Примеры:
    - screenshot.png
    """
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Имя файла (по умолчанию screenshot_*.png).",
            },
            "full_screen": {
                "type": "boolean",
                "description": "Полный экран (по умолчанию true).",
            },
        },
        "required": [],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, filename: str = "", full_screen: bool = True) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        if not filename:
            filename = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        destination = Path(filename)
        if destination.is_absolute():
            return ToolResult(
                success=False,
                output="Путь должен быть относительным (в домашней директории).",
            )
        # Resolve to home
        resolved = (self._config.fs_root / destination).resolve()
        if not str(resolved).startswith(str(self._config.fs_root)):
            return ToolResult(
                success=False,
                output="Путь выходит за пределы домашней директории.",
            )

        result = self._backend.take_screenshot(resolved, full_screen)
        return ToolResult(
            success=result.success,
            output=result.message,
        )


class StartRecordingTool(Tool):
    name = "start_recording"
    risk = RiskLevel.SAFE
    description = """
    Начинает запись экрана (Wayland/X11).

    Аргументы:
    filename: имя файла (по умолчанию recording_YYYYMMDD_HHMMSS.mp4).

    Примеры:
    - meeting.mp4
    """
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Имя файла (по умолчанию recording_*.mp4).",
            },
        },
        "required": [],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, filename: str = "") -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        if not filename:
            filename = f"recording_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        destination = Path(filename)
        if destination.is_absolute():
            return ToolResult(
                success=False,
                output="Путь должен быть относительным (в домашней директории).",
            )
        resolved = (self._config.fs_root / destination).resolve()
        if not str(resolved).startswith(str(self._config.fs_root)):
            return ToolResult(
                success=False,
                output="Путь выходит за пределы домашней директории.",
            )

        result = self._backend.start_recording(resolved)
        return ToolResult(
            success=result.success,
            output=result.message,
        )


class StopRecordingTool(Tool):
    name = "stop_recording"
    risk = RiskLevel.SAFE
    description = """
    Останавливает текущую запись экрана.

    Аргументы: нет.

    Примеры:
    - "остановить запись"
    """
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        result = self._backend.stop_recording()
        return ToolResult(
            success=result.success,
            output=result.message,
        )


# =========================================================
# System tools (DESTRUCTIVE)
# =========================================================

class KillProcessTool(Tool):
    name = "kill_process"
    risk = RiskLevel.DESTRUCTIVE
    description = """
    Завершает процесс по PID или имени.

    ВНИМАНИЕ: Это разрушительное действие!
    Включите инструмент в .env через ALLOWED_DESTRUCTIVE_TOOLS чтобы использовать.

    Аргументы:
    pid: PID процесса (целое число).
    name: имя процесса (строка) — использует pkill.

    Примеры:
    - pid 1234
    - name firefox
    """
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "PID процесса.",
            },
            "name": {
                "type": "string",
                "description": "Имя процесса.",
            },
        },
        "required": [],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, pid: int | None = None, name: str | None = None) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        if pid is None and name is None:
            return ToolResult(
                success=False,
                output="Укажите либо pid, либо name.",
            )
        result = self._backend.kill_process(pid, name)
        return ToolResult(
            success=result.success,
            output=result.message,
        )


VALID_ACTIONS: set[str] = {"sleep", "hibernate", "shutdown", "reboot", "logout"}


class SystemPowerTool(Tool):
    name = "system_power"
    risk = RiskLevel.DESTRUCTIVE
    description = """
    Выполняет системное действие: сон, гибернация, выключение, перезагрузка или выход из сеанса.

    ВНИМАНИЕ: Это разрушительное действие!
    Включите инструмент в .env через ALLOWED_DESTRUCTIVE_TOOLS чтобы использовать.

    Аргументы:
    action: sleep | hibernate | shutdown | reboot | logout

    Примеры:
    - shutdown (выключить)
    - sleep (перейти в спящий режим)
    """
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["sleep", "hibernate", "shutdown", "reboot", "logout"],
                "description": "Действие: sleep, hibernate, shutdown, reboot, logout.",
            },
        },
        "required": ["action"],
    }

    def __init__(self) -> None:
        self._backend: SystemBackend | None = None
        try:
            self._backend = SystemBackendFactory.create()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, action: str) -> ToolResult:
        if self._backend is None:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )
        if action not in VALID_ACTIONS:
            return ToolResult(
                success=False,
                output=f"Неизвестное действие: {action}. Допустимые: {', '.join(sorted(VALID_ACTIONS))}.",
            )
        result = self._backend.power(action)
        return ToolResult(
            success=result.success,
            output=result.message,
        )