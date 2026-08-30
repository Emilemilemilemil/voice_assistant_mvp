from __future__ import annotations

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
        # Set when TTS is actively playing; main loop can read this to
        # know whether to enable the interrupt key.
        self.is_speaking: bool = False

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
        player = getattr(self.tts, "audio_player", None)
        if player is not None and hasattr(player, "interrupt"):
            player.interrupt()
        # Drain pending sentences so we don't start the next one
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

            self.is_speaking = True
            try:
                self.tts.speak(item)
            except Exception as exc:
                print(f"[tts] playback failed: {exc!r}")
            finally:
                self.is_speaking = False
                self.queue.task_done()
