from __future__ import annotations
from collections.abc import Iterator
import json
import time

from llm.openai_compatible import ChatMessage, LocalLLM
from agent.tool_protocol import Executable


SYSTEM_PROMPT = """
Ты — локальный голосовой ассистент.

Твоя задача — помогать пользователю выполнять задачи через разговор.

Основные правила:
1. Отвечай кратко и естественно, так как ответ будет озвучен через TTS.
2. Не используй обращения по имени, титулы и лишние приветствия.
3. Не добавляй фразы вроде "конечно", "разумеется", "рад помочь", если они не нужны.
4. Для простых вопросов отвечай коротко.
5. Если пользователь просит выполнить действие или спрашивает фактические данные (время, дата) — вызывай подходящий инструмент, а не отвечай по памяти.
6. Не выдумывай выполненные действия и факты, которые можно узнать инструментом. Не говори, что действие выполнено, если инструмент его не выполнил.
7. После результата инструмента ответь короткой человеческой фразой, без технических деталей.
"""


MAX_TOOL_ROUNDS = 3


class ConversationManager:
    def __init__(
        self,
        llm: LocalLLM,
        executor: Executable,
        max_messages: int = 20,
    ):
        self.llm = llm
        self.executor = executor
        self.max_messages = max_messages
        self.messages = [ChatMessage("system", SYSTEM_PROMPT)]
        self.last_turn_time: float = 0.0
        # Track tool errors to prevent infinite loops
        self._tool_errors: dict[str, int] = {}
        self._max_tool_errors: int = 2

    def reset(self) -> None:
        self.messages = [ChatMessage("system", SYSTEM_PROMPT)]
        self.last_turn_time = 0.0
        self._tool_errors.clear()

    def _tool_schemas(self) -> list[dict]:
        return [
            tool.api_schema()
            for tool in self.executor.registry.list_tools()
        ]

    def _add_user_message(self, user_text: str) -> None:
        self.messages.append(
            ChatMessage("user", user_text)
        )

        # Trim history, keeping system prompt + recent semantic turns
        # Remove old tool/function messages to prevent pollution
        if len(self.messages) > self.max_messages + 1:
            system_msg = self.messages[0]
            recent_msgs = self.messages[-self.max_messages:]

            # Filter out tool messages and assistant messages with dangling tool_calls
            semantic_msgs = []
            for msg in recent_msgs:
                if msg.role == "tool":
                    continue  # Drop tool responses
                if msg.role == "assistant" and msg.tool_calls:
                    # Assistant with tool_calls needs matching tool responses
                    # Since we're dropping tool messages, drop this too
                    continue
                semantic_msgs.append(msg)

            self.messages = [system_msg] + semantic_msgs

    def _execute_call(self, call: dict) -> str:
        function = call.get("function", {})
        name = function.get("name", "")
        raw_arguments = function.get("arguments") or "{}"

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return (
                f"Ошибка: не удалось разобрать аргументы "
                f"инструмента {name}: {raw_arguments!r}"
            )

        if not isinstance(arguments, dict):
            return (
                f"Ошибка: аргументы инструмента "
                f"{name} должны быть JSON-объектом."
            )

        return self.executor.execute(
            {"tool": name, "arguments": arguments}
        )

    def process_stream(self, user_text: str) -> Iterator[str]:
        turn_start = time.perf_counter()

        self._add_user_message(user_text)

        tools = self._tool_schemas()

        for _ in range(MAX_TOOL_ROUNDS):
            emitted: list[str] = []

            for chunk in self.llm.chat_stream(self.messages, tools=tools):
                emitted.append(chunk)
                yield chunk

            tool_calls = self.llm.last_tool_calls

            if not tool_calls:
                self._remember_assistant(emitted)
                self.last_turn_time = time.perf_counter() - turn_start
                return

            self.messages.append(
                ChatMessage(
                    role="assistant",
                    content="".join(emitted).strip(),
                    tool_calls=tool_calls,
                )
            )

            for call in tool_calls:
                tool_name = call['function']['name']
                result = self._execute_call(call)

                print(f"[tool] {tool_name} -> {result!r}")

                # Track tool errors to prevent infinite loops
                # Check for error prefix from SafeToolExecutor or other failure signals
                is_error = (
                    result.startswith("[ошибка]")
                    or result.startswith("[permission denied]")
                    or result.startswith("[sandbox blocked]")
                    or result.startswith("[confirmation declined]")
                )
                if is_error:
                    self._tool_errors[tool_name] = self._tool_errors.get(tool_name, 0) + 1
                    if self._tool_errors[tool_name] >= self._max_tool_errors:
                        # Give up on this tool - inject a final message
                        result = f"[{tool_name} failed {self._max_tool_errors} times, giving up]"
                        self.messages.append(
                            ChatMessage(
                                role="tool",
                                content=result,
                                tool_call_id=call["id"],
                                name=tool_name,
                            )
                        )
                        # Force a final response without tools
                        tools = None
                        break
                else:
                    # Reset error count on success
                    self._tool_errors.pop(tool_name, None)

                self.messages.append(
                    ChatMessage(
                        role="tool",
                        content=result,
                        tool_call_id=call["id"],
                        name=tool_name,
                    )
                )

        final: list[str] = []

        for chunk in self.llm.chat_stream(self.messages, tools=None):
            final.append(chunk)
            yield chunk

        self._remember_assistant(final)
        self.last_turn_time = time.perf_counter() - turn_start

    def _remember_assistant(self, chunks: list[str]) -> None:
        text = "".join(chunks)

        if text.strip():
            self.messages.append(
                ChatMessage("assistant", text)
            )
