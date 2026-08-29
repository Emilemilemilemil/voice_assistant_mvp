from urllib.parse import quote

from safety.risk import RiskLevel
from tools.base import Tool, ToolResult
from tools.browser_backend import BrowserBackend, BrowserFactory


class BrowserSearchTool(Tool):
    name = "browser_search"

    risk = RiskLevel.SAFE

    description = """
    Открывает браузер с поисковым запросом.

    Аргументы:
    query: текст поиска.
    """

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Поисковый запрос.",
            }
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        self._backend: BrowserBackend | None = None
        self._init_error: str | None = None

        try:
            self._backend = BrowserFactory.create()
        except RuntimeError as exc:
            self._init_error = str(exc)

    def execute(self, query: str):

        if not query:
            return ToolResult(
                success=False,
                output="Не указан поисковый запрос."
            )

        if self._backend is None:
            return ToolResult(
                success=False,
                output=self._init_error or "Browser backend недоступен."
            )

        url = (
            "https://www.google.com/search?q="
            + quote(query)
        )

        success, output = self._backend.open_url(url)

        return ToolResult(
            success=success,
            output=output
        )