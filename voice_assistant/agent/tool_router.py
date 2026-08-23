from __future__ import annotations

import json

from agent.tool_executor import ToolExecutor


class ToolRouter:

    def __init__(
        self,
        executor: ToolExecutor,
    ):
        self.executor = executor


    def try_execute(
        self,
        text: str,
    ) -> str | None:
        """
        Проверяет ответ LLM.
        Если это tool call -> выполняет.
        Иначе возвращает None.
        """

        try:
            data = json.loads(text)

        except json.JSONDecodeError:
            return None


        if "tool" not in data:
            return None


        tool_name = data["tool"]
        arguments = data.get(
            "arguments",
            {}
        )


        result = self.executor.execute(
            {
                "tool": tool_name,
                "arguments": arguments,
            }
        )

        return result