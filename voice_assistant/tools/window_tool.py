from __future__ import annotations

from safety.risk import RiskLevel
from tools.base import Tool, ToolResult
from tools.window_manager import WindowManager


class CloseWindowTool(Tool):

    name = "close_window"

    risk = RiskLevel.SAFE  # User requested no confirmation for window close

    description = """
    Закрывает окно приложения.

    Аргументы:
    target: название приложения или окна.

    Примеры:
    - Telegram
    - Firefox
    - Google Chrome
    - Visual Studio Code
    """

    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Название приложения или окна.",
            }
        },
        "required": ["target"],
    }

    def __init__(self) -> None:
        self._manager: WindowManager | None = None
        self._init_error: str | None = None

        try:
            self._manager = WindowManager()
        except RuntimeError as exc:
            self._init_error = str(exc)

    def execute(self, target: str) -> ToolResult:

        if not target or not target.strip():
            return ToolResult(
                success=False,
                output="Не указано окно.",
            )

        if self._manager is None:
            return ToolResult(
                success=False,
                output=self._init_error or "Оконный менеджер недоступен.",
            )

        success, output = self._manager.close_window(
            target
        )

        return ToolResult(
            success=success,
            output=output,
        )