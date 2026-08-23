from __future__ import annotations

import numpy as np
import torch
from silero_vad import load_silero_vad


class SileroVAD:
    """Silero VAD wrapper for 16 kHz mono 512-sample frames."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.model = load_silero_vad()

    def is_speech(self, chunk: np.ndarray, sample_rate: int) -> bool:
        if sample_rate != 16000:
            raise ValueError("SAMPLE_RATE must be 16000 for this VAD wrapper.")

        if len(chunk) != 512:
            raise ValueError(
                f"Silero expects 512 samples here; received {len(chunk)}."
            )

        audio = torch.from_numpy(np.asarray(chunk, dtype=np.float32))
        probability = float(self.model(audio, 16000).item())
        return probability >= self.threshold
