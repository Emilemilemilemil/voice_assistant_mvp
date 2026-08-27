from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base import Tool


class ToolRegistry:

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._tool_classes = {
            "get_current_time": "tools.time_tool:TimeTool",
            "open_application": "tools.application_tool:OpenApplicationTool",
            "browser_search": "tools.browser_tool:BrowserSearchTool",
            "close_window": "tools.window_tool:CloseWindowTool",
        }

    def get(self, name: str) -> Tool | None:
        if name not in self._tool_classes:
            return None

        if name not in self._tools:
            self._tools[name] = self._lazy_import(name)

        return self._tools.get(name)

    def _lazy_import(self, name: str) -> Tool | None:
        import importlib

        module_path, class_name = self._tool_classes[name].rsplit(":", 1)
        module = importlib.import_module(module_path)
        tool_class = getattr(module, class_name)

        try:
            return tool_class()
        except RuntimeError as exc:
            print(f"[tools] {name} unavailable: {exc}")
            return None

    def list_tools(self) -> list[Tool]:
        tools: list[Tool] = []

        for name in self._tool_classes:
            tool = self.get(name)
            if tool is not None:
                tools.append(tool)

        return tools