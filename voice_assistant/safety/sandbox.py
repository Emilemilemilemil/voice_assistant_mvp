from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass

from .risk import RiskLevel


@dataclass
class SandboxResult:
    allowed: bool
    output: str = ""
    raw_result: object = None  # Keep raw for unwrapping ToolResult
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
        # SIGALRM-based timeout only works on Unix *and* in the main thread.
        # On Windows, or from worker threads, skip enforcement (don't fail
        # the call - the LLM stream / main loop will still be protected by
        # the duration check below).
        self._supports_alarm = (
            hasattr(signal, "SIGALRM")
            and threading.current_thread() is threading.main_thread()
        )

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
        if self._supports_alarm:
            result = self._run_with_alarm(tool_name, runner)
        else:
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

        if isinstance(result, SandboxResult) and not result.allowed:
            # Returned by _run_with_alarm for TimeoutError path
            return result

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

        # Extract output string, preserving ToolResult if present
        output_str = ""
        if hasattr(result, 'output'):
            output_str = str(result.output)
        else:
            output_str = str(result)

        return SandboxResult(
            allowed=True,
            output=output_str,
            raw_result=result,
            duration=duration,
        )

    def _run_with_alarm(self, tool_name: str, runner):
        """Run ``runner`` under a SIGALRM timeout.

        Critically, the alarm cancel and handler restore are in a
        ``finally`` block so a tool that raises (e.g. an unexpected
        exception inside ``tool.execute``) still cleans up. Otherwise
        the alarm would stay armed and fire later inside the LLM
        stream or the next tool call, surfacing as a phantom
        TimeoutError with no relation to the actual offender.
        """
        def alarm_handler(signum, frame):
            raise TimeoutError(f"sandbox timeout exceeded: {self._timeout}s")

        old_handler = signal.signal(signal.SIGALRM, alarm_handler)
        try:
            signal.alarm(int(self._timeout))
            return runner()
        except TimeoutError as exc:
            duration_msg = str(exc)
            self._log.error("tool %s timeout: %s", tool_name, duration_msg)
            return SandboxResult(
                allowed=False,
                duration=self._timeout,
                error=duration_msg,
            )
        finally:
            # Always cancel the alarm and restore the previous handler,
            # even if runner() raised. Without this, the alarm stays
            # armed and the original SIGALRM handler is lost.
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


def default_sandbox(timeout: float = 30.0) -> ExecutionSandbox:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    return ExecutionSandbox(timeout=timeout)