from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .risk import RiskLevel


@dataclass
class SandboxResult:
    allowed: bool
    output: str = ""
    duration: float = 0.0
    error: str = ""


class ExecutionSandbox:
    """Wraps a tool call with logging, timing, and basic guards.

    The sandbox is a thin layer: it does not run the tool inside a
    separate process or container. Its job is to:
      - record every invocation for an audit trail
      - measure wall-clock duration
      - enforce a per-call timeout
      - normalize the result into a ``SandboxResult`` for the executor
    """

    def __init__(self, timeout: float = 30.0, logger=None) -> None:
        self._timeout = timeout
        self._log = logger or logging.getLogger("voice_assistant.sandbox")

    def run(
        self,
        tool_name: str,
        risk_level: int,
        arguments: dict,
        runner,
    ) -> SandboxResult:
        start = time.perf_counter()
        self._log.info(
            "tool=%s risk=%s args=%s", tool_name, risk_level, arguments
        )
        try:
            result = runner()
        except Exception as exc:
            duration = time.perf_counter() - start
            self._log.exception("tool %s raised", tool_name)
            return SandboxResult(
                allowed=False,
                duration=duration,
                error=f"{type(exc).__name__}: {exc}",
            )

        duration = time.perf_counter() - start

        if duration > self._timeout:
            self._log.warning(
                "tool %s exceeded timeout: %.2fs", tool_name, duration
            )
            return SandboxResult(
                allowed=False,
                duration=duration,
                error=f"timeout: {duration:.2f}s > {self._timeout:.2f}s",
            )

        return SandboxResult(
            allowed=True,
            output=str(result),
            duration=duration,
        )


def default_sandbox(timeout: float = 30.0) -> ExecutionSandbox:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    return ExecutionSandbox(timeout=timeout)
