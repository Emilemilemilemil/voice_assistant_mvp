from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile



class PiperTTS:
    def __init__(
        self,
        piper_bin: str,
        model: str,
        speaker: str = "",
        length_scale: float = 1.0,
    ):
        self.piper_bin = piper_bin
        self.model = model
        self.speaker = speaker
        self.length_scale = length_scale

    def speak(self, text: str) -> None:
        if not self.piper_bin or not self.model:
            print(f"[tts-disabled] {text}")
            return

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

            subprocess.run(
                command,
                input=text,
                text=True,
                check=True,
                stdout=subprocess.DEVNULL,
            )

            subprocess.run(
                [
                    "pw-play",
                    str(wav_path),
                ],
                check=True,
            )
