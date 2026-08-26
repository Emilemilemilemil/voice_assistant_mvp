from __future__ import annotations

from tools.base import ToolResult


class ToolExecutor:

    def __init__(self, registry):
        self.registry = registry

    def execute(self, tool_call) -> str:
        name = tool_call.get("tool")
        arguments = tool_call.get("arguments")

        if not isinstance(name, str) or not name.strip():
            return "Ошибка: не указано имя инструмента."

        tool = self.registry.get(name)

        if tool is None:
            return f"Ошибка: инструмент не найден: {name}"

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, dict):
            return f"Ошибка: аргументы инструмента {name} должны быть объектом."

        try:
            result = tool.execute(**arguments)
        except TypeError as exc:
            return f"Ошибка: неверные аргументы для {name}: {exc}"
        except Exception as exc:
            return f"Ошибка при выполнении {name}: {exc}"

        if isinstance(result, ToolResult):
            prefix = "" if result.success else "[ошибка] "
            return prefix + result.output

        return str(result)
