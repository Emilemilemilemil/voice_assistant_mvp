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

        print(f"[tool router] input: {text!r}")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[tool router] JSON error: {e}")
            return None

        print(f"[tool router] parsed: {data}")

        if "tool" not in data:
            print("[tool router] no tool field")
            return None

        tool_name = data["tool"]
        arguments = data.get("arguments", {})

        print(
            f"[tool router] executing: "
            f"{tool_name} {arguments}"
        )

        result = self.executor.execute(
            {
                "tool": tool_name,
                "arguments": arguments,
            }
        )

        print(f"[tool router] result: {result!r}")

        return result

    
    # def try_execute(
    #     self,
    #     text: str,
    # ) -> str | None:
    #     """
    #     Проверяет ответ LLM.
    #     Если это tool call -> выполняет.
    #     Иначе возвращает None.
    #     """

    #     try:
    #         data = json.loads(text)

    #     except json.JSONDecodeError:
    #         return None


    #     if "tool" not in data:
    #         return None


    #     tool_name = data["tool"]
    #     arguments = data.get(
    #         "arguments",
    #         {}
    #     )


    #     result = self.executor.execute(
    #         {
    #             "tool": tool_name,
    #             "arguments": arguments,
    #         }
    #     )

    #     return result