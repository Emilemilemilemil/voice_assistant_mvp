from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str = ""


class PermissionManager:
    """Decide whether a tool may run.

    Policies cascade in this order:
      1. Explicit deny list (always wins).
      2. Explicit allow list (skips confirmation for SAFE tools).
      3. Tool's declared risk level (``Tool.risk``).

    The manager is intentionally simple: it does not call into the OS
    or the network. It only inspects the tool name, risk level, and the
    caller's arguments. Hooking it into a richer policy language is
    a future step.
    """

    def __init__(
        self,
        allowed: set[str] | None = None,
        denied: set[str] | None = None,
    ) -> None:
        self._allowed: set[str] = set(allowed or ())
        self._denied: set[str] = set(denied or ())

    def deny(self, tool_name: str) -> None:
        self._denied.add(tool_name)

    def allow(self, tool_name: str) -> None:
        self._allowed.add(tool_name)
        self._denied.discard(tool_name)

    def is_explicitly_allowed(self, tool_name: str) -> bool:
        return tool_name in self._allowed

    def check(
        self,
        tool_name: str,
        risk_level: int,
        arguments: dict | None = None,
    ) -> PermissionDecision:
        arguments = arguments or {}

        if tool_name in self._denied:
            return PermissionDecision(
                allowed=False,
                reason=f"Tool '{tool_name}' is denied by policy.",
            )

        if tool_name in self._allowed:
            return PermissionDecision(allowed=True, reason="explicitly allowed")

        if risk_level >= 2:
            # DESTRUCTIVE: Block by default, but allow if explicitly allowed
            # (Confirmation is handled by executor, not here)
            return PermissionDecision(
                allowed=False,
                reason=(
                    f"Tool '{tool_name}' is destructive. "
                    "Add to allow list to enable, or set to confirm."
                ),
            )

        return PermissionDecision(allowed=True, reason="default allow")
