# Local Voice Assistant

Modular local voice assistant:

Microphone -> Enter activation -> Silero VAD -> faster-whisper -> local OpenAI-compatible LLM -> Piper TTS.

The spoken request contains no wake-word name. Activation is a separate event (Enter).

## Install

Recommended: Python 3.11/3.12.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

On Arch, install audio dependencies as needed, for example:

```bash
sudo pacman -S ffmpeg portaudio pipewire
```

Copy `.env.example` to `.env` and configure it.

## LLM

Default setup is a local [Ollama](https://ollama.com) server with `qwen3:8b`:

`http://127.0.0.1:11434/v1/chat/completions`

Set `LLM_BASE_URL` and `LLM_MODEL` in `.env`. Any OpenAI-compatible server
works (LM Studio, llama.cpp server, vLLM).

The client sends `reasoning_effort: "none"` (honored by Ollama) so thinking
models do not burn latency before speech, skips reasoning deltas defensively,
and uses `keep_alive` so the model stays warm between voice turns.

## Piper

By default Piper is expected at `~/voice_assistant_mvp/bin/piper/piper`
with the model `~/voice_assistant_mvp/models/piper/ru_RU-irina-medium.onnx`.
Override via `PIPER_BIN` and `PIPER_MODEL` in `.env`.

If Piper is not configured, the assistant prints the answer instead of speaking it.

## Tools

Tools use native OpenAI function calling (`tools=` in the request). Each tool
declares its JSON Schema in `tools/`; the registry feeds schemas to the model,
and returned `tool_calls` are executed and fed back as `role: "tool"`
messages until the model produces a spoken reply (max 3 rounds). Available:
current time, app launching (.desktop indexing), browser search, Hyprland
window closing.

## Run

```bash
python main.py
```

Press Enter, speak, and stop speaking. VAD detects the end of the utterance.
The assistant streams the answer sentence by sentence to TTS and waits until
playback finishes before the next turn.

The last captured utterance is saved as `debug/last_segment.wav`.

## Current scope

Implemented:
- microphone stream (device selectable via `MIC_DEVICE`)
- Enter activation
- Silero VAD
- speech segmentation with pre-roll buffer
- faster-whisper STT
- conversation history
- OpenAI-compatible local LLM client (streaming, native function calling)
- streaming sentence-level Piper TTS
- tools: time, application launch, browser search, close window

Not yet implemented:
- real wake-word detector
- permission system
- long-term memory
- barge-in / echo cancellation (assistant cannot be interrupted while speaking)
