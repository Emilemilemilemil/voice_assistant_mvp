from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    success: bool
    output: str


class Tool:
    name: str
    description: str

    def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError