from dataclasses import dataclass

from safety.risk import RiskLevel


@dataclass
class ToolResult:
    success: bool
    output: str


class Tool:
    name: str
    description: str
    parameters: dict = {"type": "object", "properties": {}}
    risk: RiskLevel = RiskLevel.SAFE

    def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError

    def api_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (self.description or self.name).strip(),
                "parameters": self.parameters,
            },
        }
