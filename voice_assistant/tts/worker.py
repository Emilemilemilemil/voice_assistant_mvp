from __future__ import annotations

import subprocess
import time
from queue import Queue, Empty
from threading import Thread

from tts.piper import PiperTTS


class TTSWorker:
    def __init__(self, tts: PiperTTS):
        self.tts = tts
        self.queue: Queue[str | None] = Queue()
        self.thread = Thread(
            target=self._run,
            daemon=True,
        )
        # Reference to the currently-running audio playback process (or None).
        # The interrupt listener uses this to kill playback on key press.
        self._current_proc: subprocess.Popen | None = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.queue.put(None)
        self.thread.join()

    def speak(self, text: str):
        self.queue.put(text)

    def interrupt(self):
        """Stop current playback and clear the queue."""
        # Kill the active audio process (pw-play) if any
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        # Drain pending sentences
        try:
            while True:
                self.queue.get_nowait()
                self.queue.task_done()
        except Empty:
            pass

    def _run(self):
        while True:
            item = self.queue.get()

            if item is None:
                self.queue.task_done()
                break

            # Track the active audio process so the main thread can interrupt it
            self._current_proc = None
            try:
                # Synthesize first (no audio running yet)
                wav_path = self.tts.synthesize(item)
                if wav_path is None:
                    continue
                # Play with an interruptible wrapper
                self.tts.play_with_interrupt(wav_path, self)
            except Exception as exc:
                print(f"[tts] playback failed: {exc!r}")
            finally:
                self._current_proc = None
                self.queue.task_done()
