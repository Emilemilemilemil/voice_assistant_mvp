from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfirmationResult:
    confirmed: bool
    reason: str = ""


class ConfirmationPrompter:
    """Asks the user before running a CONFIRM/DESTRUCTIVE tool.

    Default backend writes to stdout and reads from stdin. The output
    is intentionally short so it can be mirrored to TTS if the user
    runs the assistant in a non-interactive shell.
    """

    def __init__(self, in_stream=None, out_stream=None) -> None:
        self._in = in_stream or sys.stdin
        self._out = out_stream or sys.stdout

    def prompt(
        self,
        tool_name: str,
        arguments: dict,
        risk_label: str,
    ) -> ConfirmationResult:
        args_preview = ", ".join(
            f"{k}={v!r}" for k, v in arguments.items()
        ) or "<no args>"

        self._out.write(
            f"\n[safety:{risk_label}] {tool_name}({args_preview})\n"
            f"  Allow? [y/N]: "
        )
        self._out.flush()

        try:
            line = self._in.readline()
        except (EOFError, KeyboardInterrupt):
            return ConfirmationResult(False, "no input")

        answer = line.strip().lower()

        if answer in ("y", "yes", "д", "да"):
            return ConfirmationResult(True)

        return ConfirmationResult(False, "declined by user")


class AutoApprovePrompter:
    """Non-interactive prompter used when stdin is not a TTY.

    Behaves like a denied confirmation. Pair with ``PermissionManager``
    if you want a hard block; for tests this is the deterministic path.
    """

    def prompt(
        self,
        tool_name: str,
        arguments: dict,
        risk_label: str,
    ) -> ConfirmationResult:
        return ConfirmationResult(
            False,
            f"non-interactive mode: auto-denied {tool_name}",
        )
