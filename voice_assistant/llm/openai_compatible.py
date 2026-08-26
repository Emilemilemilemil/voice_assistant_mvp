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
        payload = {
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
    ) -> Iterator[str]:

        payload = self._build_payload(messages, stream=True)

        start_time = time.perf_counter()

        first_token_time: float | None = None
        completion_tokens: int | None = None

        with requests.post(
            self.url,
            headers=self._headers(),
            json=payload,
            stream=True,
            timeout=300,
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