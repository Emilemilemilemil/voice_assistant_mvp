from __future__ import annotations


class SentenceBuffer:
    """
    Collects streaming text chunks and emits complete sentences.
    """

    SENTENCE_ENDINGS = ".!?"

    def __init__(self, min_length: int = 20):
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

            self.buffer = self.buffer[boundary:]

        return sentences

    def _find_boundary(self) -> int | None:
        if len(self.buffer) < self.min_length:
            return None

        for i, char in enumerate(self.buffer):
            if char in self.SENTENCE_ENDINGS:
                return i + 1

        return None

    def flush(self) -> str | None:
        remaining = self.buffer.strip()
        self.buffer = ""

        return remaining or None