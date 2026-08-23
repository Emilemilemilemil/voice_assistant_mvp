from __future__ import annotations

from collections import deque
from enum import Enum, auto
import numpy as np


class SegmentState(Enum):
    WAITING = auto()
    SPEAKING = auto()


class SpeechSegmenter:
    """Converts chunk-level VAD decisions into complete utterances."""

    def __init__(
        self,
        sample_rate: int,
        chunk_samples: int,
        pre_roll_chunks: int,
        min_speech_ms: int,
        end_silence_chunks: int,
        max_utterance_chunks: int,
    ):
        self.sample_rate = sample_rate
        self.chunk_samples = chunk_samples
        self.pre_roll = deque(maxlen=pre_roll_chunks)
        self.state = SegmentState.WAITING

        chunk_ms = chunk_samples * 1000 / sample_rate
        self.min_speech_chunks = max(1, int(np.ceil(min_speech_ms / chunk_ms)))
        self.end_silence_chunks = end_silence_chunks
        self.max_utterance_chunks = max_utterance_chunks

        self.current: list[np.ndarray] = []
        self.speech_chunks = 0
        self.silence_chunks = 0

    def reset(self) -> None:
        self.pre_roll.clear()
        self.state = SegmentState.WAITING
        self.current.clear()
        self.speech_chunks = 0
        self.silence_chunks = 0

    def process(self, chunk: np.ndarray, is_speech: bool) -> np.ndarray | None:
        chunk = np.asarray(chunk, dtype=np.float32)
        self.pre_roll.append(chunk)

        if self.state is SegmentState.WAITING:
            if is_speech:
                self.state = SegmentState.SPEAKING
                self.current = list(self.pre_roll)
                self.speech_chunks = 1
                self.silence_chunks = 0
            return None

        self.current.append(chunk)

        if is_speech:
            self.speech_chunks += 1
            self.silence_chunks = 0
        else:
            self.silence_chunks += 1

        speech_was_long_enough = self.speech_chunks >= self.min_speech_chunks
        silence_ended_utterance = (
            self.silence_chunks >= self.end_silence_chunks
            and speech_was_long_enough
        )
        utterance_too_long = len(self.current) >= self.max_utterance_chunks

        if silence_ended_utterance or utterance_too_long:
            result = np.concatenate(self.current)
            self.reset()
            return result

        return None
