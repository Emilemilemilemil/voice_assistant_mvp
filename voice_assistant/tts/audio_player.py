from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess


class AudioPlayer(ABC):
    """Abstract interface for platform audio playback."""

    @abstractmethod
    def play(self, wav_path: Path) -> tuple[bool, str]:
        """
        Play a WAV file synchronously (blocks until complete).

        Args:
            wav_path: Path to the WAV file to play

        Returns:
            Tuple of (success: bool, message: str)

        Raises:
            Nothing - errors are returned as (False, error_message)
        """
        raise NotImplementedError


class PipeWirePlayer(AudioPlayer):
    """Linux PipeWire audio player (pw-play)."""

    def play(self, wav_path: Path) -> tuple[bool, str]:
        """Play a WAV file using pw-play (PipeWire)."""
        try:
            subprocess.run(
                [
                    "pw-play",
                    str(wav_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            return (True, "playback complete")
        except subprocess.CalledProcessError as exc:
            return (False, f"pw-play failed: {exc.stderr}")
        except FileNotFoundError:
            return (False, "pw-play not found")
        except Exception as exc:
            return (False, f"playback error: {exc}")


class AudioPlayerFactory:
    """Factory for creating platform-specific audio players."""

    @staticmethod
    def create() -> AudioPlayer:
        """
        Create an audio player for the current platform.

        Returns:
            AudioPlayer instance for the detected platform

        Raises:
            RuntimeError: If no audio player backend is available
        """
        if shutil.which("pw-play"):
            return PipeWirePlayer()

        # Future platform support:
        # elif sys.platform == "darwin":
        #     return AFPlayPlayer()
        # elif sys.platform == "win32":
        #     return WindowsMediaPlayer()

        raise RuntimeError(
            "No audio player backend available. "
            "Install PipeWire (pw-play) or configure PIPER_BIN to skip TTS."
        )
