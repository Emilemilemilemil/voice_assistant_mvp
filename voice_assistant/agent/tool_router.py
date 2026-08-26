from __future__ import annotations

import json
import re

from agent.tool_executor import ToolExecutor


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ToolRouter:

    def __init__(
        self,
        executor: ToolExecutor,
    ):
        self.executor = executor

    @staticmethod
    def _extract_json(text: str) -> str | None:
        value = _FENCE_RE.sub(r"\1", text).strip()

        if not value.startswith("{"):
            return None

        return value

    def try_execute(
        self,
        text: str,
    ) -> str | None:

        candidate = self._extract_json(text)

        if candidate is None:
            return None

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            print(f"[tool router] JSON error: {exc}")
            return None

        if not isinstance(data, dict):
            print("[tool router] not a JSON object")
            return None

        tool_name = data.get("tool")

        if not isinstance(tool_name, str) or not tool_name.strip():
            print("[tool router] no valid tool field")
            return None

        arguments = data.get("arguments", {})

        if not isinstance(arguments, dict):
            arguments = {}

        print(
            f"[tool router] executing: "
            f"{tool_name} {arguments}"
        )

        try:
            result = self.executor.execute(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                }
            )
        except Exception as exc:
            print(f"[tool router] executor error: {exc!r}")
            return f"Ошибка при выполнении инструмента {tool_name}: {exc}"

        print(f"[tool router] result: {result!r}")

        return result
