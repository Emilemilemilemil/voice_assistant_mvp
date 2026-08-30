from __future__ import annotations

from tools.base import Tool, ToolResult
from safety.risk import RiskLevel
from tools.media_backend import MediaBackend, MediaBackendFactory


# Shared backend instance (set during main.py init)
_backend: MediaBackend | None = None


def _get_backend() -> MediaBackend:
    """Get or create the shared media backend."""
    global _backend
    if _backend is None:
        _backend = MediaBackendFactory.create()
    return _backend


def set_backend(backend: MediaBackend) -> None:
    """Set the shared backend instance (called from main.py)."""
    global _backend
    _backend = backend


class MediaPlayTool(Tool):
    name = "media_play"
    description = "Resume playback of the current media player"
    parameters = {"type": "object", "properties": {}}
    risk = RiskLevel.SAFE

    def execute(self) -> ToolResult:
        backend = _get_backend()
        result = backend.play()
        return ToolResult(success=result.success, output=result.message)


class MediaPauseTool(Tool):
    name = "media_pause"
    description = "Pause playback of the current media player"
    parameters = {"type": "object", "properties": {}}
    risk = RiskLevel.SAFE

    def execute(self) -> ToolResult:
        backend = _get_backend()
        result = backend.pause()
        return ToolResult(success=result.success, output=result.message)


class MediaStopTool(Tool):
    name = "media_stop"
    description = "Stop playback of the current media player"
    parameters = {"type": "object", "properties": {}}
    risk = RiskLevel.SAFE

    def execute(self) -> ToolResult:
        backend = _get_backend()
        result = backend.stop()
        return ToolResult(success=result.success, output=result.message)


class MediaNextTool(Tool):
    name = "media_next"
    description = "Skip to the next track in the current media player"
    parameters = {"type": "object", "properties": {}}
    risk = RiskLevel.SAFE

    def execute(self) -> ToolResult:
        backend = _get_backend()
        result = backend.next()
        return ToolResult(success=result.success, output=result.message)


class MediaPreviousTool(Tool):
    name = "media_previous"
    description = "Go to the previous track in the current media player"
    parameters = {"type": "object", "properties": {}}
    risk = RiskLevel.SAFE

    def execute(self) -> ToolResult:
        backend = _get_backend()
        result = backend.previous()
        return ToolResult(success=result.success, output=result.message)


class MediaStatusTool(Tool):
    name = "media_status"
    description = "Get the current playback status of the media player (track title and playback state)"
    parameters = {"type": "object", "properties": {}}
    risk = RiskLevel.SAFE

    def execute(self) -> ToolResult:
        backend = _get_backend()
        result = backend.status()
        return ToolResult(success=result.success, output=result.message)
