"""Integration tests for the SAFETY layer."""

import sys
import io
from unittest.mock import MagicMock

from tools.registry import ToolRegistry
from tools.base import Tool, ToolResult
from agent.tool_executor_safe import SafeToolExecutor
from safety.permissions import PermissionManager
from safety.confirm import ConfirmationPrompter, AutoApprovePrompter
from safety.sandbox import ExecutionSandbox
from safety.risk import RiskLevel


class DummyTool(Tool):
    """Mock tool for testing."""
    name = "dummy"
    description = "Test tool"
    risk = RiskLevel.SAFE

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="dummy result")


class DangerousTool(Tool):
    """Mock dangerous tool for testing."""
    name = "dangerous"
    description = "Test dangerous tool"
    risk = RiskLevel.CONFIRM

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="danger executed")


def test_safe_tool_no_confirmation():
    """SAFE tools should execute without confirmation."""
    registry = MagicMock()
    tool = DummyTool()
    registry.get.return_value = tool

    prompter = MagicMock()
    executor = SafeToolExecutor(
        registry,
        permission_manager=PermissionManager(),
        prompter=prompter,
    )

    result = executor.execute({
        "tool": "dummy",
        "arguments": {},
    })

    assert "dummy result" in result
    prompter.prompt.assert_not_called()
    print("✓ SAFE tools execute without confirmation")


def test_confirm_tool_with_approval():
    """CONFIRM tools should prompt and execute on approval."""
    registry = MagicMock()
    tool = DangerousTool()
    registry.get.return_value = tool

    # Mock approving response
    prompter = MagicMock()
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class MockResult:
        confirmed: bool
        reason: str = ""

    prompter.prompt.return_value = MockResult(confirmed=True)

    executor = SafeToolExecutor(
        registry,
        permission_manager=PermissionManager(),
        prompter=prompter,
    )

    result = executor.execute({
        "tool": "dangerous",
        "arguments": {},
    })

    assert "danger executed" in result
    prompter.prompt.assert_called_once()
    print("✓ CONFIRM tools prompt and execute on approval")


def test_confirm_tool_with_denial():
    """CONFIRM tools should not execute on denial."""
    registry = MagicMock()
    tool = DangerousTool()
    registry.get.return_value = tool

    # Mock denying response
    prompter = MagicMock()
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class MockResult:
        confirmed: bool
        reason: str = ""

    prompter.prompt.return_value = MockResult(confirmed=False, reason="user denied")

    executor = SafeToolExecutor(
        registry,
        permission_manager=PermissionManager(),
        prompter=prompter,
    )

    result = executor.execute({
        "tool": "dangerous",
        "arguments": {},
    })

    assert "confirmation declined" in result
    print("✓ CONFIRM tools blocked on denial")


def test_permission_deny_list():
    """Permission deny list should block execution."""
    registry = MagicMock()
    tool = DummyTool()
    registry.get.return_value = tool

    perms = PermissionManager(denied={"dummy"})
    executor = SafeToolExecutor(
        registry,
        permission_manager=perms,
    )

    result = executor.execute({
        "tool": "dummy",
        "arguments": {},
    })

    assert "permission denied" in result
    print("✓ Permission deny list blocks execution")


def test_permission_allow_list():
    """Permission allow list should bypass confirmation."""
    registry = MagicMock()
    tool = DangerousTool()
    registry.get.return_value = tool

    perms = PermissionManager(allowed={"dangerous"})
    prompter = MagicMock()

    executor = SafeToolExecutor(
        registry,
        permission_manager=perms,
        prompter=prompter,
    )

    result = executor.execute({
        "tool": "dangerous",
        "arguments": {},
    })

    assert "danger executed" in result
    prompter.prompt.assert_not_called()  # Should not prompt (in allow list)
    print("✓ Permission allow list bypasses confirmation")


def test_real_tool_registry():
    """Integration test with real ToolRegistry."""
    registry = ToolRegistry()
    perms = PermissionManager()

    # Simulate user decline
    in_stream = io.StringIO("n\n")
    out_stream = io.StringIO()
    prompter = ConfirmationPrompter(in_stream=in_stream, out_stream=out_stream)

    executor = SafeToolExecutor(
        registry,
        permission_manager=perms,
        prompter=prompter,
    )

    # Try to close a window (CONFIRM level)
    result = executor.execute({
        "tool": "close_window",
        "arguments": {"target": "Test Window"},
    })

    assert "confirmation declined" in result
    print("✓ Real ToolRegistry integration works")


if __name__ == "__main__":
    print("\n=== SAFETY Layer Integration Tests ===\n")

    test_safe_tool_no_confirmation()
    test_confirm_tool_with_approval()
    test_confirm_tool_with_denial()
    test_permission_deny_list()
    test_permission_allow_list()
    test_real_tool_registry()

    print("\n✓ All SAFETY tests passed!")
