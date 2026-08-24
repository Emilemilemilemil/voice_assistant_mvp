from urllib.parse import quote
import subprocess

from tools.base import ToolResult


class BrowserSearchTool:
    name = "browser_search"

    def execute(self, query: str):

        if not query:
            return ToolResult(
                success=False,
                output="Не указан поисковый запрос."
            )

        url = (
            "https://www.google.com/search?q="
            + quote(query)
        )

        try:
            subprocess.Popen(
                [
                    "xdg-open",
                    url,
                ]
            )

            return ToolResult(
                success=True,
                output=f"Ищу в браузере: {query}"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Ошибка открытия браузера: {e}"
            )