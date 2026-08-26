from tools.time_tool import TimeTool
from tools.application_tool import OpenApplicationTool
from tools.browser_tool import BrowserSearchTool
from tools.window_tool import CloseWindowTool


class ToolRegistry:

    def __init__(self):
        self.tools = {
            TimeTool.name: TimeTool(),
            OpenApplicationTool.name: OpenApplicationTool(),
            BrowserSearchTool.name: BrowserSearchTool(),
            CloseWindowTool.name: CloseWindowTool(),
        }


    def get(self, name):
        return self.tools.get(name)


    def list_tools(self):
        return list(self.tools.values())