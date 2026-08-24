from tools.base import ToolResult


class BrowserSearchTool:
    name = "browser_search"

    def execute(self, query: str):

        if not query:
            return ToolResult(
                output="Не указан поисковый запрос."
            )

        url = (
            "https://www.google.com/search?q="
            + quote(query)
        )

        subprocess.Popen(
            [
                "xdg-open",
                url,
            ]
        )

        return ToolResult(
            output=f"Ищу в браузере: {query}"
        )