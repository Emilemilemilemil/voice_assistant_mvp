from datetime import datetime

from tools.base import Tool, ToolResult


class TimeTool(Tool):

    name = "get_current_time"

    description = """
    Получить текущее время.
    Не требует параметров.
    """

    parameters = {
        "type": "object",
        "properties": {},
    }

    def execute(self, **kwargs):

        now = datetime.now()

        return ToolResult(
            success=True,
            output=f"Сейчас {now:%H:%M}"
        )