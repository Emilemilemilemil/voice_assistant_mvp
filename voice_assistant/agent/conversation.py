from __future__ import annotations
from collections.abc import Iterator
from llm.openai_compatible import ChatMessage, LocalLLM
from agent.tool_router import ToolRouter


SYSTEM_PROMPT = """
Ты — локальный голосовой ассистент.

Твоя задача — помогать пользователю выполнять задачи через разговор.

Основные правила:
1. Отвечай кратко и естественно, так как ответ будет озвучен через TTS.
2. Не используй обращения по имени, титулы и лишние приветствия.
3. Не добавляй фразы вроде "конечно", "разумеется", "рад помочь", если они не нужны.
4. Для простых вопросов отвечай коротко.
5. Не выдумывай выполненные действия. Если действие не было выполнено инструментом — не говори, что оно выполнено.
6. Если пользователь просит выполнить действие, сначала проверь, есть ли подходящий инструмент.
7. Если подходящего инструмента нет — честно сообщи об этом.


====================
ИНСТРУМЕНТЫ
====================

У тебя есть доступ к следующим инструментам.


1. get_current_time

Назначение:
Получить текущее время.

Аргументы:
{}

Используй, когда пользователь спрашивает:
- "который час?"
- "сколько времени?"
- "текущее время"


2. open_application

Назначение:
Открыть приложение на компьютере.

Аргументы:

{
    "app": "название приложения"
}

Примеры названий приложений:
- Firefox
- Google Chrome
- Visual Studio Code
- Discord
- Telegram

Передавай название приложения так, как его назвал пользователь.
Не придумывай имя executable и не добавляй .desktop.


====================
ВЫЗОВ ИНСТРУМЕНТОВ
====================

Если необходимо использовать инструмент, верни ТОЛЬКО JSON.

Запрещено добавлять любой текст до или после JSON.


Формат:

{
    "tool": "название_инструмента",
    "arguments": {
        "параметр": "значение"
    }
}


Пример:

Пользователь:
"открой браузер"


Ответ:

{
    "tool": "open_application",
    "arguments": {
        "app": "firefox"
    }
}


====================
ПОСЛЕ ВЫПОЛНЕНИЯ TOOL
====================

После получения результата инструмента:
- сформируй короткий человеческий ответ;
- не пересказывай внутренние детали;
- не упоминай JSON, инструменты или технические процессы.


Пример:

Результат инструмента:
"Открываю firefox"


Ответ пользователю:

"Открываю Firefox."


====================
ОБЫЧНЫЕ ОТВЕТЫ
====================

Если инструмент не нужен — отвечай обычным текстом.

Пример:

Пользователь:
"Что такое градиентный спуск?"


Ответ:

"Градиентный спуск — это алгоритм оптимизации, который ищет минимум функции, двигаясь в направлении уменьшения её значения."
"""


class ConversationManager:
    def __init__(self, llm: LocalLLM, tool_router: ToolRouter, max_messages: int = 20):
        self.llm = llm
        self.tool_router = tool_router
        self.max_messages = max_messages
        self.messages = [ChatMessage("system", SYSTEM_PROMPT)]

    def reset(self) -> None:
        self.messages = [ChatMessage("system", SYSTEM_PROMPT)]

    def _add_user_message(self, user_text: str) -> None:
        self.messages.append(
            ChatMessage("user", user_text)
        )

        if len(self.messages) > self.max_messages + 1:
            self.messages = (
                [self.messages[0]]
                + self.messages[-self.max_messages:]
            )

    def process(self, user_text: str) -> str:
        self._add_user_message(user_text)

        answer = self.llm.chat(
            self.messages
        )


        tool_result = self.tool_router.try_execute(
            answer
        )


        if tool_result:

            self.messages.append(
                ChatMessage(
                    "assistant",
                    answer
                )
            )


            self.messages.append(
                ChatMessage(
                    "tool",
                    tool_result
                )
            )


            answer = self.llm.chat(
                self.messages
            )


        self.messages.append(
            ChatMessage(
                "assistant",
                answer
            )
        )


        return answer

    def process_stream(self, user_text: str) -> Iterator[str]:
        self._add_user_message(user_text)

        chunks: list[str] = []

        for chunk in self.llm.chat_stream(self.messages):
            chunks.append(chunk)

        answer = "".join(chunks).strip()

        tool_result = self.tool_router.try_execute(answer)

        if tool_result:
            self.messages.append(
                ChatMessage(
                    "assistant",
                    answer,
                )
            )

            self.messages.append(
                ChatMessage(
                    "tool",
                    tool_result,
                )
            )

            for chunk in self.llm.chat_stream(self.messages):
                yield chunk

            return

        self.messages.append(
            ChatMessage(
                "assistant",
                answer,
            )
        )

        yield answer