from __future__ import annotations
import re


class SentenceBuffer:
    """
    Collects streaming text chunks and emits complete sentences.
    Only breaks on sentence-ending punctuation followed by whitespace or end of text.
    """

    SENTENCE_ENDINGS = ".!?"

    def __init__(self, min_length: int = 10):
        self.buffer = ""
        self.min_length = min_length

    def add(self, chunk: str) -> list[str]:
        self.buffer += chunk

        sentences = []

        while True:
            boundary = self._find_boundary()

            if boundary is None:
                break

            sentence = self.buffer[:boundary].strip()

            if sentence:
                sentences.append(sentence)

            self.buffer = self.buffer[boundary:].lstrip()

        return sentences

    def _find_boundary(self) -> int | None:
        if len(self.buffer) < self.min_length:
            return None

        # Find sentence-ending punctuation followed by whitespace or end of text
        # This avoids breaking on abbreviations like "т. д.", "г.", decimals "3.14"
        pattern = r'[.!?](?=\s|$)'

        match = re.search(pattern, self.buffer[self.min_length:])

        if match:
            # +1 to include the punctuation itself
            return self.min_length + match.start() + 1

        return None

    def flush(self) -> str | None:
        remaining = self.buffer.strip()
        self.buffer = ""

        return remaining or None