class ToolExecutor:

    def __init__(self, registry):
        self.registry = registry


    def execute(self, tool_call):

        name = tool_call["tool"]
        args = tool_call["arguments"]

        tool = self.registry.get(name)

        if not tool:
            return "Инструмент не найден"

        result = tool.execute(**args)

        if hasattr(result, "output"):
            return result.output

        return result

    