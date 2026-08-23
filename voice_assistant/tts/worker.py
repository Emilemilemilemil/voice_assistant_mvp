from __future__ import annotations

from queue import Queue
from threading import Thread, Event

from tts.piper import PiperTTS


class TTSWorker:
    def __init__(self, tts: PiperTTS):
        self.tts = tts
        self.queue = Queue()
        self.stop_event = Event()

        self.thread = Thread(
            target=self._run,
            daemon=True,
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.queue.put(None)
        self.thread.join()

    def speak(self, text: str):
        self.queue.put(text)

    def _run(self):
        while True:
            item = self.queue.get()

            if item is None:
                break

            self.tts.speak(item)

            self.queue.task_done()