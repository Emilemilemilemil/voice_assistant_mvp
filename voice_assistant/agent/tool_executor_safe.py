from __future__ import annotations

from tools.base import ToolResult
from safety.permissions import PermissionManager
from safety.confirm import ConfirmationPrompter, AutoApprovePrompter
from safety.risk import RiskLevel
from safety.sandbox import ExecutionSandbox


class SafeToolExecutor:

    def __init__(
        self,
        registry,
        permission_manager: PermissionManager | None = None,
        prompter=None,
        sandbox: ExecutionSandbox | None = None,
    ):
        self.registry = registry
        self.permissions = permission_manager or PermissionManager()
        self.prompter = prompter
        self.sandbox = sandbox

        if self.prompter is None:
            try:
                import sys
                self.prompter = (
                    ConfirmationPrompter()
                    if sys.stdin.isatty()
                    else AutoApprovePrompter()
                )
            except Exception:
                self.prompter = AutoApprovePrompter()

    def execute(self, tool_call) -> str:
        name = tool_call.get("tool")
        arguments = tool_call.get("arguments")

        if not isinstance(name, str) or not name.strip():
            return "Ошибка: не указано имя инструмента."

        tool = self.registry.get(name)

        if tool is None:
            return f"Ошибка: инструмент не найден: {name}"

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, dict):
            return f"Ошибка: аргументы инструмента {name} должны быть объектом."

        # 1. Permission check
        decision = self.permissions.check(
            name,
            tool.risk,
            arguments,
        )
        if not decision.allowed:
            return f"[permission denied] {decision.reason}"

        # 2. Confirmation prompt (if required and not explicitly allowed
        #     for SAFE/CONFIRM; DESTRUCTIVE always confirms).
        if (
            tool.risk == RiskLevel.DESTRUCTIVE
            or (
                tool.risk.requires_confirmation()
                and not self.permissions.is_explicitly_allowed(name)
            )
        ):
            confirmed = self.prompter.prompt(
                name,
                arguments,
                tool.risk.label(),
            )
            if not confirmed.confirmed:
                return f"[confirmation declined] {confirmed.reason}"

        # 3. Execute with optional sandbox
        try:
            if self.sandbox:
                sandbox_result = self.sandbox.run(
                    name,
                    tool.risk,
                    arguments,
                    lambda: tool.execute(**arguments),
                )
                if not sandbox_result.allowed:
                    return f"[sandbox blocked] {sandbox_result.error}"

                # Unwrap ToolResult from sandbox's raw_result
                raw = sandbox_result.raw_result
                if isinstance(raw, ToolResult):
                    prefix = "" if raw.success else "[ошибка] "
                    return prefix + raw.output
                return sandbox_result.output
            else:
                result = tool.execute(**arguments)

            if isinstance(result, ToolResult):
                prefix = "" if result.success else "[ошибка] "
                return prefix + result.output

            return str(result)

        except TypeError as exc:
            return f"Ошибка: неверные аргументы для {name}: {exc}"
        except Exception as exc:
            return f"Ошибка при выполнении {name}: {exc}"