from __future__ import annotations

from safety.risk import RiskLevel
from tools.base import Tool, ToolResult
from tools.application_launcher import ApplicationLauncher


class OpenApplicationTool(Tool):
    name = "open_application"

    risk = RiskLevel.CONFIRM

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

    parameters = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "Название приложения, как его назвал пользователь.",
            }
        },
        "required": ["app"],
    }

    def __init__(self) -> None:
        self._launcher: ApplicationLauncher | None = None
        self._init_error: str | None = None

        try:
            self._launcher = ApplicationLauncher()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, app: str) -> ToolResult:
        if not app or not app.strip():
            return ToolResult(
                success=False,
                output="Не указано приложение.",
            )

        if self._launcher is None:
            return ToolResult(
                success=False,
                output=self._init_error or "Launcher недоступен.",
            )

        success, output = self._launcher.launch(app)

        return ToolResult(
            success=success,
            output=output,
        )