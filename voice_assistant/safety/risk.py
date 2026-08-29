from __future__ import annotations

from enum import IntEnum


class RiskLevel(IntEnum):
    """Risk classification for tool execution.

    Order matters: higher value = higher risk. Comparisons like
    ``risk >= RiskLevel.CONFIRM`` mean "at least confirmation required".
    """

    SAFE = 0       # No side effects, pure read
    CONFIRM = 1    # Side effect, but reversible / non-destructive
    DESTRUCTIVE = 2  # Hard to reverse or affects the user's environment

    def requires_confirmation(self) -> bool:
        return self >= RiskLevel.CONFIRM

    def label(self) -> str:
        return {
            RiskLevel.SAFE: "safe",
            RiskLevel.CONFIRM: "confirm",
            RiskLevel.DESTRUCTIVE: "destructive",
        }[self]
