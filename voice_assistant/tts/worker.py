from __future__ import annotations

from queue import Queue
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

    def start(self):
        self.thread.start()

    def stop(self):
        self.queue.put(None)
        self.thread.join()

    def speak(self, text: str):
        self.queue.put(text)

    def _run(self):
        while True:
            item = self.queue.get()

            if item is None:
                self.queue.task_done()
                break

            try:
                self.tts.speak(item)
            except Exception as exc:
                print(f"[tts] playback failed: {exc!r}")
            finally:
                self.queue.task_done()
