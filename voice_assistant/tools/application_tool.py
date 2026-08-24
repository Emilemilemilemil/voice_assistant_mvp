from __future__ import annotations

import subprocess

from tools.base import Tool, ToolResult


class OpenApplicationTool(Tool):

    name = "open_application"

    description = """
    Открывает приложение на компьютере.

    Аргументы:
    app: название приложения

    Доступные приложения:
    firefox,
    google-chrome,
    code,
    terminal
    """

    APPLICATIONS = {
        "firefox": [
            "firefox"
        ],

        "google-chrome": [
            "google-chrome-stable"
        ],

        "code": [
            "code"
        ],

        "terminal": [
            "kitty"
        ],
    }


    def execute(self, app: str) -> ToolResult:

        command = self.APPLICATIONS.get(app.lower())

        if command is None:
            return ToolResult(
                success=False,
                output=f"Неизвестное приложение: {app}"
            )


        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return ToolResult(
                success=True,
                output=f"Открываю {app}"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Ошибка запуска {app}: {e}"
            )