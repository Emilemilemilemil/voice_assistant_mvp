from __future__ import annotations

from tools.base import Tool, ToolResult
from tools.window_manager import WindowManager


class CloseWindowTool(Tool):

    name = "close_window"

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
        self.manager = WindowManager()

    def execute(self, target: str) -> ToolResult:

        if not target or not target.strip():
            return ToolResult(
                success=False,
                output="Не указано окно.",
            )

        success, output = self.manager.close_window(
            target
        )

        return ToolResult(
            success=success,
            output=output,
        )