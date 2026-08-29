from dataclasses import dataclass
from pathlib import Path
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def env_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


@dataclass(frozen=True)
class Config:
    sample_rate: int = env_int("SAMPLE_RATE", 16000)
    channels: int = env_int("CHANNELS", 1)
    chunk_ms: int = env_int("CHUNK_MS", 32)

    microphone_device: int | None = env_optional_int("MIC_DEVICE")

    vad_threshold: float = env_float("VAD_THRESHOLD", 0.50)
    min_speech_ms: int = env_int("MIN_SPEECH_MS", 180)
    end_silence_ms: int = env_int("END_SILENCE_MS", 700)
    max_utterance_ms: int = env_int("MAX_UTTERANCE_MS", 15000)
    max_listen_ms: int = env_int("MAX_LISTEN_MS", 30000)
    pre_roll_ms: int = env_int("PRE_ROLL_MS", 400)

    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    whisper_language: str = os.getenv("WHISPER_LANGUAGE", "ru")
    whisper_beam_size: int = env_int("WHISPER_BEAM_SIZE", 5)

    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "local")
    llm_model: str = os.getenv("LLM_MODEL", "local-model")
    llm_temperature: float = env_float("LLM_TEMPERATURE", 0.2)
    llm_max_tokens: int = env_int("LLM_MAX_TOKENS", 512)
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")

    piper_bin: str = (
        os.getenv("PIPER_BIN")
        or str(Path.home() / "voice_assistant_mvp/bin/piper/piper")
    )
    piper_model: str = (
        os.getenv("PIPER_MODEL")
        or str(Path.home() / "voice_assistant_mvp/models/piper/ru_RU-irina-medium.onnx")
    )

    piper_speaker: str = os.getenv("PIPER_SPEAKER", "")
    piper_length_scale: float = env_float("PIPER_LENGTH_SCALE", 1.0)

    debug_dir: Path = Path(__file__).resolve().parent / "debug"

    @property
    def chunk_samples(self) -> int:
        return self.sample_rate * self.chunk_ms // 1000

    @property
    def pre_roll_chunks(self) -> int:
        return max(1, self.pre_roll_ms // self.chunk_ms)

    @property
    def end_silence_chunks(self) -> int:
        return max(1, self.end_silence_ms // self.chunk_ms)

    @property
    def max_utterance_chunks(self) -> int:
        return max(1, self.max_utterance_ms // self.chunk_ms)

    @property
    def max_listen_chunks(self) -> int:
        return max(1, self.max_listen_ms // self.chunk_ms)

    def validate(self) -> list[str]:
        """Validate config and return list of warnings."""
        warnings: list[str] = []
        if not 0.0 <= self.vad_threshold <= 1.0:
            warnings.append(
                f"VAD_THRESHOLD={self.vad_threshold} is out of range [0.0, 1.0]"
            )
        elif self.vad_threshold > 0.9:
            warnings.append(
                f"VAD_THRESHOLD={self.vad_threshold} is very high — "
                "loud speech may not be detected"
            )
        elif self.vad_threshold < 0.2:
            warnings.append(
                f"VAD_THRESHOLD={self.vad_threshold} is very low — "
                "background noise may trigger false detections"
            )
        if self.min_speech_ms < 50:
            warnings.append(
                f"MIN_SPEECH_MS={self.min_speech_ms} is very low — "
                "may split utterances on brief pauses"
            )
        if self.end_silence_ms < 200:
            warnings.append(
                f"END_SILENCE_MS={self.end_silence_ms} is very low — "
                "may cut off speech mid-sentence"
            )
        return warnings
