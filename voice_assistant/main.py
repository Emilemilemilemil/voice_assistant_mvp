from __future__ import annotations

import time
import subprocess
from contextlib import contextmanager

import soundfile as sf

from config import Config
from audio.microphone import Microphone
from audio.segmenter import SpeechSegmenter
from vad.silero import SileroVAD
from stt.faster_whisper import FasterWhisperSTT
from llm.openai_compatible import LocalLLM
from agent.conversation import ConversationManager
from tts.piper import PiperTTS
from tts.sentence_buffer import SentenceBuffer
from tts.worker import TTSWorker
from tools.registry import ToolRegistry
from agent.tool_executor_safe import SafeToolExecutor
from safety.permissions import PermissionManager
from safety.confirm import ConfirmationPrompter
from safety.sandbox import default_sandbox


@contextmanager
def tracked_subprocesses():
    """Context manager that tracks spawned subprocesses for cleanup.

    Usage:
        with tracked_subprocesses() as tracked:
            proc = subprocess.Popen([...])  # automatically tracked
            ...
        # on exit, all tracked processes are killed gracefully
    """
    running: list[subprocess.Popen] = []

    original_popen = subprocess.Popen

    def tracking_popen(*args, **kwargs):
        proc = original_popen(*args, **kwargs)
        running.append(proc)
        return proc

    subprocess.Popen = tracking_popen
    try:
        yield running
    finally:
        subprocess.Popen = original_popen
        # Clean up all spawned processes
        for proc in running:
            try:
                if proc.poll() is None:  # Still running
                    proc.kill()
                    proc.wait(timeout=2)
            except Exception:
                pass


def main():
    config = Config()

    # Validate config and print warnings
    for warning in config.validate():
        print(f"[config] WARNING: {warning}")

    if config.sample_rate != 16000 or config.chunk_samples != 512:
        raise SystemExit(
            "Silero VAD requires 16 kHz audio in 512-sample chunks: "
            "set SAMPLE_RATE=16000 and CHUNK_MS=32."
        )

    config.debug_dir.mkdir(parents=True, exist_ok=True)

    print("[assistant] initializing...")

    microphone = Microphone(
        config.sample_rate,
        config.channels,
        config.chunk_samples,
        device=config.microphone_device,
    )

    vad = SileroVAD(config.vad_threshold)

    segmenter = SpeechSegmenter(
        sample_rate=config.sample_rate,
        chunk_samples=config.chunk_samples,
        pre_roll_chunks=config.pre_roll_chunks,
        min_speech_ms=config.min_speech_ms,
        end_silence_chunks=config.end_silence_chunks,
        max_utterance_chunks=config.max_utterance_chunks,
    )

    stt = FasterWhisperSTT(
        model_name=config.whisper_model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        language=config.whisper_language,
        beam_size=config.whisper_beam_size,
    )

    llm = LocalLLM(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model,
        temperature=config.llm_temperature,
        max_tokens=config.llm_max_tokens,
        provider=config.llm_provider,
    )

    registry = ToolRegistry()

    # SAFETY layer
    permissions = PermissionManager(
        allowed=set(),  # Empty allow list = rely on risk levels
        denied=set(),
    )
    prompter = ConfirmationPrompter()
    sandbox = default_sandbox(timeout=30.0)

    executor = SafeToolExecutor(
        registry,
        permission_manager=permissions,
        prompter=prompter,
        sandbox=sandbox,
    )

    conversation = ConversationManager(llm, executor)

    tts = PiperTTS(
        piper_bin=config.piper_bin,
        model=config.piper_model,
        speaker=config.piper_speaker,
        length_scale=config.piper_length_scale,
    )

    tts_worker = TTSWorker(tts)
    tts_worker.start()

    microphone.start()

    print()
    print("======================================")
    print(" Local Voice Assistant")
    print(" Enter   -> speak")
    print(" Ctrl+C  -> exit")
    print("======================================")
    print()

    with tracked_subprocesses() as running_subprocesses:
        try:
            while True:
                input("[Enter] чтобы говорить... ")
                print("[assistant] listening...")

                microphone.drain()
                segmenter.reset()
                utterance = None
                chunks_read = 0

                while utterance is None and chunks_read < config.max_listen_chunks:
                    chunk = microphone.read()
                    is_speech = vad.is_speech(chunk, config.sample_rate)
                    utterance = segmenter.process(chunk, is_speech)
                    chunks_read += 1

                if utterance is None:
                    print("[assistant] didn't hear you (timeout)")
                    conversation.reset()  # Clear stale context after timeout
                    continue

                debug_path = config.debug_dir / "last_segment.wav"
                sf.write(debug_path, utterance, config.sample_rate)

                duration = len(utterance) / config.sample_rate
                print(f"[audio] {duration:.2f}s captured")

                start = time.perf_counter()
                try:
                    text = stt.transcribe(utterance, config.sample_rate)
                except Exception as exc:
                    print(f"[stt] ERROR: {exc}")
                    print("[assistant] speech recognition failed")
                    continue

                print(f"[stt] {text!r} ({time.perf_counter() - start:.2f}s)")

                if not text:
                    print("[assistant] nothing recognized (speech may be too quiet)")
                    continue

                try:
                    sentence_buffer = SentenceBuffer()

                    print("[assistant] ", end="", flush=True)

                    for chunk in conversation.process_stream(text):
                        print(chunk, end="", flush=True)

                        for sentence in sentence_buffer.add(chunk):
                            print()
                            print(f"[sentence] {sentence}")

                            tts_worker.speak(sentence)

                    remaining = sentence_buffer.flush()

                    if remaining:
                        print()
                        print(f"[sentence] {remaining}")

                        tts_worker.speak(remaining)

                    print()

                    stats = llm.last_stream_stats

                    if stats.ttft is not None:
                        print(f"[llm] first token: {stats.ttft:.3f}s")
                    else:
                        print("[llm] first token: unavailable")

                    print(f"[llm] turn total: {conversation.last_turn_time:.3f}s")

                    if stats.completion_tokens is not None:
                        print(f"[llm] tokens: {stats.completion_tokens}")
                        print(f"[llm] speed: {stats.tokens_per_second:.2f} tok/s")
                    else:
                        print("[llm] tokens: unavailable")
                        print("[llm] speed: unavailable")

                    if not tts_worker.queue.empty():
                        print("[assistant] speaking...")

                    tts_worker.queue.join()

                except Exception as exc:
                    print(f"\n[assistant] error: {exc}")
                    print("[assistant] recovering...")
                    continue

        except KeyboardInterrupt:
            print("\n[assistant] stopping...")
        finally:
            microphone.stop()
            tts_worker.stop()
            # Subprocess cleanup handled by tracked_subprocesses() context manager


if __name__ == "__main__":
    main()
