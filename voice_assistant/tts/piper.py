from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from tts.audio_player import AudioPlayer, AudioPlayerFactory


class PiperTTS:
    def __init__(
        self,
        piper_bin: str,
        model: str,
        speaker: str = "",
        length_scale: float = 1.0,
        audio_player: AudioPlayer | None = None,
    ):
        self.piper_bin = piper_bin
        self.model = model
        self.speaker = speaker
        self.length_scale = length_scale

        # Use provided audio player or create one
        if audio_player is None:
            try:
                self.audio_player: AudioPlayer | None = AudioPlayerFactory.create()
            except RuntimeError as exc:
                print(f"[tts] {exc}")
                self.audio_player = None
        else:
            self.audio_player = audio_player

    def speak(self, text: str) -> bool:
        """Synthesize and play speech. Returns True on success, False on failure."""
        if not self.piper_bin or not self.model:
            print(f"[tts-disabled] {text}")
            return False

        if self.audio_player is None:
            print(f"[tts-no-player] {text}")
            return False

        with tempfile.TemporaryDirectory(prefix="assistant_tts_") as tmp:
            wav_path = Path(tmp) / "response.wav"

            command = [
                self.piper_bin,
                "--model", self.model,
                "--output_file", str(wav_path),
                "--length_scale", str(self.length_scale),
            ]

            if self.speaker:
                command += ["--speaker", self.speaker]

            try:
                subprocess.run(
                    command,
                    input=text,
                    text=True,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            except subprocess.CalledProcessError as exc:
                print(f"[tts] Piper failed (exit {exc.returncode}): {exc.stderr}")
                return False
            except FileNotFoundError:
                print(f"[tts] Piper binary not found: {self.piper_bin}")
                return False
            except Exception as exc:
                print(f"[tts] Unexpected error: {exc}")
                return False

            success, message = self.audio_player.play(wav_path)
            if not success:
                print(f"[tts] {message}")
            return success
