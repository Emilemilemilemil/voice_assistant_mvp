from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterator
import json
import time

import requests


@dataclass
class ChatMessage:
    role: str
    content: str = ""
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_api(self) -> dict:
        message: dict = {"role": self.role}

        if self.content:
            message["content"] = self.content
        elif self.role == "assistant" and self.tool_calls:
            message["content"] = ""

        if self.tool_calls:
            message["tool_calls"] = self.tool_calls

        if self.tool_call_id is not None:
            message["tool_call_id"] = self.tool_call_id

        if self.name is not None:
            message["name"] = self.name

        return message


@dataclass
class StreamStats:
    ttft: float | None = None
    total_time: float = 0.0
    completion_tokens: int | None = None
    tokens_per_second: float = 0.0


class LocalLLM:
    """Client for any local OpenAI-compatible /v1/chat/completions server."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        provider: str = "ollama",
        keep_alive: str = "10m",
        connect_timeout: float = 10.0,
        read_timeout: float = 120.0,
        max_retries: int = 1,
    ):
        self.url = f"{base_url}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = provider.lower()
        self.keep_alive = keep_alive
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_retries = max_retries

        self.last_stream_stats = StreamStats()
        self.last_tool_calls: list[dict] = []

    def _build_payload(
        self,
        messages: list[ChatMessage],
        stream: bool = False,
        tools: list[dict] | None = None,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                message.to_api()
                for message in messages
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

        # Ollama-specific parameters
        if self.provider == "ollama":
            payload["reasoning_effort"] = "none"
            payload["keep_alive"] = self.keep_alive

        if tools:
            payload["tools"] = tools

        if stream:
            payload["stream_options"] = {"include_usage": True}

        return payload

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> Iterator[str]:

        payload = self._build_payload(messages, stream=True, tools=tools)

        start_time = time.perf_counter()

        first_token_time: float | None = None
        completion_tokens: int | None = None

        pending_calls: dict[int, dict] = {}
        stream_successful = False

        timeout = (self.connect_timeout, self.read_timeout)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                with requests.post(
                    self.url,
                    headers=self._headers(),
                    json=payload,
                    stream=True,
                    timeout=timeout,
                ) as response:

                    response.raise_for_status()
                    response.encoding = "utf-8"

                    for line in response.iter_lines(decode_unicode=True):

                        if not line:
                            continue

                        if not line.startswith("data:"):
                            continue

                        data = line[len("data:"):].strip()

                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            print(f"[llm] warning: skipped malformed JSON chunk: {data[:100]!r}")
                            continue

                        usage = chunk.get("usage")

                        if usage:
                            completion_tokens = usage.get(
                                "completion_tokens"
                            )

                        choices = chunk.get("choices")

                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        for fragment in delta.get("tool_calls") or []:
                            index = fragment.get("index", 0)
                            slot = pending_calls.setdefault(
                                index,
                                {"id": "", "name": "", "arguments": ""},
                            )

                            call_id = fragment.get("id")
                            if call_id:
                                slot["id"] = call_id

                            function = fragment.get("function") or {}

                            name_part = function.get("name")
                            if name_part:
                                slot["name"] += name_part

                            args_part = function.get("arguments")
                            if args_part:
                                slot["arguments"] += args_part

                        content = delta.get("content")

                        if not content:
                            continue

                        if first_token_time is None:
                            first_token_time = time.perf_counter()

                        yield content

                # Success - mark and break out of retry loop
                stream_successful = True
                break

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    print(f"[llm] timeout/error, retrying... ({exc})")
                    continue
                raise

        total_time = time.perf_counter() - start_time

        if first_token_time is not None:
            ttft = first_token_time - start_time
            generation_time = total_time - ttft
        else:
            ttft = None
            generation_time = 0.0

        tokens_per_second = 0.0

        if completion_tokens is not None and generation_time > 0:
            tokens_per_second = (
                completion_tokens / generation_time
            )

        self.last_stream_stats = StreamStats(
            ttft=ttft,
            total_time=total_time,
            completion_tokens=completion_tokens,
            tokens_per_second=tokens_per_second,
        )

        # Only set tool_calls if stream completed successfully
        if stream_successful and pending_calls:
            self.last_tool_calls = [
                {
                    "id": slot["id"] or f"call_{index}",
                    "type": "function",
                    "function": {
                        "name": slot["name"],
                        "arguments": slot["arguments"],
                    },
                }
                for index, slot in sorted(pending_calls.items())
                if slot["name"]  # Only include complete calls
            ]
        else:
            self.last_tool_calls = []
