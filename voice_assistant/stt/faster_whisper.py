from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel


class FasterWhisperSTT:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        language: str | None,
        beam_size: int,
    ):
        print(f"[stt] loading {model_name}...")
        try:
            self.model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
            )
        except Exception as exc:
            print(f"[stt] ERROR: Whisper model load failed: {exc}")
            print(f"[stt] Falling back to 'tiny' model with CPU")
            try:
                self.model = WhisperModel(
                    "tiny",
                    device="cpu",
                    compute_type="float32",
                )
            except Exception as exc2:
                print(f"[stt] FATAL: Even tiny model failed: {exc2}")
                raise
        self.language = language or None
        self.beam_size = beam_size

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if self.model is None:
            return ""
        if sample_rate != 16000:
            raise ValueError("STT expects 16 kHz audio.")

        try:
            segments, _ = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            return " ".join(
                segment.text.strip() for segment in segments
            ).strip()
        except Exception as exc:
            print(f"[stt] ERROR: Transcription failed: {exc}")
            return ""
