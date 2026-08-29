from __future__ import annotations
from typing import Protocol


class Executable(Protocol):
    """Protocol matching both ToolExecutor and SafeToolExecutor."""
    registry: object

    def execute(self, tool_call: dict) -> str:
        ...
