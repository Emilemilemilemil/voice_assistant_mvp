from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base import Tool


class ToolRegistry:

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._tool_classes = {
            # Time
            "get_current_time": "tools.time_tool:TimeTool",
            # Applications
            "open_application": "tools.application_tool:OpenApplicationTool",
            "close_window": "tools.window_tool:CloseWindowTool",
            # Web
            "browser_search": "tools.browser_tool:BrowserSearchTool",
            # Filesystem (SAFE)
            "read_file": "tools.filesystem:ReadFileTool",
            "list_directory": "tools.filesystem:ListDirectoryTool",
            "search_files": "tools.filesystem:SearchFilesTool",
            # Filesystem (CONFIRM)
            "write_file": "tools.filesystem:WriteFileTool",
            "create_directory": "tools.filesystem:CreateDirectoryTool",
            "copy_file": "tools.filesystem:CopyFileTool",
            "move_file": "tools.filesystem:MoveFileTool",
            # Filesystem (DESTRUCTIVE)
            "delete_file": "tools.filesystem:DeleteFileTool",
            "delete_directory": "tools.filesystem:DeleteDirectoryTool", # not destructive 
            "run_script": "tools.filesystem:RunScriptTool",
            # System (SAFE)
            "get_volume": "tools.system_tool:GetVolumeTool",
            "set_volume": "tools.system_tool:SetVolumeTool",
            "list_processes": "tools.system_tool:ListProcessesTool",
            "get_clipboard": "tools.system_tool:GetClipboardTool",
            "set_clipboard": "tools.system_tool:SetClipboardTool",
            "take_screenshot": "tools.system_tool:TakeScreenshotTool",
            "start_recording": "tools.system_tool:StartRecordingTool",
            "stop_recording": "tools.system_tool:StopRecordingTool",
            # System (DESTRUCTIVE)
            "kill_process": "tools.system_tool:KillProcessTool",
            "system_power": "tools.system_tool:SystemPowerTool",
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