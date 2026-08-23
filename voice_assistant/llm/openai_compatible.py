from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator
import json
import time

import requests


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class StreamStats:
    request_time: float = 0.0
    ttft: float = 0.0
    generation_time: float = 0.0
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
    ):
        self.url = f"{base_url}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.last_stream_stats = StreamStats()

    def _build_payload(
        self,
        messages: list[ChatMessage],
        stream: bool = False,
    ) -> dict:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: list[ChatMessage]) -> str:
        payload = self._build_payload(messages, stream=False)

        response = requests.post(
            self.url,
            headers=self._headers(),
            json=payload,
            timeout=300,
        )

        response.raise_for_status()

        data = response.json()

        return data["choices"][0]["message"]["content"].strip()

    def chat_stream(
        self,
        messages: list[ChatMessage],
    ) -> Iterator[str]:

        payload = self._build_payload(messages, stream=True)

        start_time = time.perf_counter()
        first_token_time = None
        completion_tokens = None

        request_start = time.perf_counter()

        with requests.post(
            self.url,
            headers=self._headers(),
            json=payload,
            stream=True,
            timeout=300,
        ) as response:

            response.raise_for_status()

            request_time = time.perf_counter() - request_start

            response.encoding = "utf-8"

            first_token_time = None
            completion_tokens = None

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
                    continue

                # Try to get token usage if the server provides it.
                usage = chunk.get("usage")

                if usage:
                    completion_tokens = usage.get(
                        "completion_tokens"
                    )
                    

                choices = chunk.get("choices")

                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content")

                if not content:
                    continue

                if first_token_time is None:
                    first_token_time = time.perf_counter()

                yield content

        total_time = time.perf_counter() - start_time

        if first_token_time is not None:
            ttft = first_token_time - start_time
            generation_time = total_time - ttft
        else:
            ttft = 0.0
            generation_time = total_time

        if (
            completion_tokens is not None
            and generation_time > 0
        ):
            tokens_per_second = (
                completion_tokens / generation_time
            )
        else:
            tokens_per_second = 0.0

        self.last_stream_stats = StreamStats(
            ttft=ttft,
            total_time=total_time,
            completion_tokens=completion_tokens,
            tokens_per_second=tokens_per_second,
        )