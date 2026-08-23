from __future__ import annotations

import time

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
from agent.tool_executor import ToolExecutor
from agent.tool_router import ToolRouter

def main():
    config = Config()
    config.debug_dir.mkdir(parents=True, exist_ok=True)

    print("[assistant] initializing...")

    microphone = Microphone(
        config.sample_rate,
        config.channels,
        config.chunk_samples,
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
    )

    registry = ToolRegistry()

    executor = ToolExecutor(
        registry
    )

    tool_router = ToolRouter(
        executor
    )

    conversation = ConversationManager(llm, tool_router)

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

    try:
        while True:
            input("[Enter] чтобы говорить... ")
            print("[assistant] listening...")

            microphone.drain()
            segmenter.reset()
            utterance = None

            while utterance is None:
                chunk = microphone.read()
                is_speech = vad.is_speech(chunk, config.sample_rate)
                utterance = segmenter.process(chunk, is_speech)

            debug_path = config.debug_dir / "last_segment.wav"
            sf.write(debug_path, utterance, config.sample_rate)

            duration = len(utterance) / config.sample_rate
            print(f"[audio] {duration:.2f}s captured")

            start = time.perf_counter()
            text = stt.transcribe(utterance, config.sample_rate)
            print(f"[stt] {text!r} ({time.perf_counter() - start:.2f}s)")

            if not text:
                print("[assistant] nothing recognized")
                continue

            start = time.perf_counter()

            chunks = []
            sentence_buffer = SentenceBuffer()

            first_token = True

            print("[assistant] ", end="", flush=True)

            for chunk in conversation.process_stream(text):

                if first_token:
                    print(
                        f"\n[LLM first token] {time.perf_counter() - start:.3f}s"
                    )
                    first_token = False

                print(chunk, end="", flush=True)
                chunks.append(chunk)

                sentences = sentence_buffer.add(chunk)

                for sentence in sentences:
                    print()
                    print(f"[sentence] {sentence}")

                    tts_worker.speak(sentence)

            print()
            
            print(
                f"[llm total] {time.perf_counter() - start:.3f}s"
            )

            remaining = sentence_buffer.flush()

            if remaining:
                print()
                print(f"[sentence] {remaining}")

            print()

            answer = "".join(chunks).strip()       #!!!!!!!!!!

            stats = llm.last_stream_stats

            print(f"[llm] TTFT: {stats.ttft:.3f}s")
            print(f"[llm] total: {stats.total_time:.3f}s")

            if stats.completion_tokens is not None:
                print(f"[llm] tokens: {stats.completion_tokens}")
                print(f"[llm] speed: {stats.tokens_per_second:.2f} tok/s")
            else:
                print("[llm] tokens: unavailable")
                print("[llm] speed: unavailable")

            

    except KeyboardInterrupt:
        print("\n[assistant] stopping...")
    finally:
        microphone.stop()


if __name__ == "__main__":
    main()
