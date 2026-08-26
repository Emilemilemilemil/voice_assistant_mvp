from __future__ import annotations

from queue import Queue, Empty
import numpy as np
import sounddevice as sd


class Microphone:
    """Continuously captures mono float32 audio in fixed-size chunks."""

    def __init__(self, sample_rate: int, channels: int, chunk_samples: int):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_samples = chunk_samples
        self.queue: Queue[np.ndarray] = Queue(maxsize=100)
        self.stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"[audio] {status}")

        chunk = np.asarray(indata[:, 0], dtype=np.float32).copy()

        try:
            self.queue.put_nowait(chunk)
        except Exception:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(chunk)
            except Exception:
                pass

    def start(self) -> None:
        self.stream = sd.InputStream(
            device=11,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.chunk_samples,
            callback=self._callback,
        )
        self.stream.start()

    def read(self) -> np.ndarray:
        return self.queue.get()

    def drain(self) -> None:
        """Discards stale audio buffered while the assistant was responding."""
        try:
            while True:
                self.queue.get_nowait()
        except Empty:
            pass

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
