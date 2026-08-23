from tools.time_tool import TimeTool
from tools.application_tool import OpenApplicationTool


class ToolRegistry:

    def __init__(self):
        self.tools = {
            TimeTool.name: TimeTool(),
            OpenApplicationTool.name: OpenApplicationTool(),
        }


    def get(self, name):
        return self.tools.get(name)


    def list_tools(self):
        return list(self.tools.values())