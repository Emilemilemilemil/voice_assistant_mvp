from __future__ import annotations

import numpy as np
import torch
from silero_vad import load_silero_vad


class SileroVAD:
    """Silero VAD wrapper for 16 kHz mono 512-sample frames."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        try:
            self.model = load_silero_vad()
        except Exception as exc:
            print(f"[vad] WARNING: Silero VAD model load failed: {exc}")
            self.model = None

    def is_speech(self, chunk: np.ndarray, sample_rate: int) -> bool:
        if self.model is None:
            # Fallback: assume speech if chunk has significant energy
            return np.abs(chunk).mean() > 0.01
        if sample_rate != 16000:
            raise ValueError("SAMPLE_RATE must be 16000 for this VAD wrapper.")

        if len(chunk) != 512:
            raise ValueError(
                f"Silero expects 512 samples here; received {len(chunk)}."
            )

        audio = torch.from_numpy(np.asarray(chunk, dtype=np.float32))
        probability = float(self.model(audio, 16000).item())
        return probability >= self.threshold
