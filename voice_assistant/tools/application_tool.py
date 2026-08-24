from __future__ import annotations

from tools.base import Tool, ToolResult
from tools.application_launcher import ApplicationLauncher


class OpenApplicationTool(Tool):
    name = "open_application"

    description = """
    Открывает установленное графическое приложение.

    Аргументы:
    app: название приложения.

    Примеры:
    - Firefox
    - Google Chrome
    - Chromium
    - Visual Studio Code
    - Discord
    - Steam
    - Telegram
    """

    def __init__(self) -> None:
        self.launcher = ApplicationLauncher()

    def execute(self, app: str) -> ToolResult:
        if not app or not app.strip():
            return ToolResult(
                success=False,
                output="Не указано приложение.",
            )

        success, output = self.launcher.launch(app)

        return ToolResult(
            success=success,
            output=output,
        )