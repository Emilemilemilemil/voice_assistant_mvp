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

## Roadmap

Legend: `[x]` done · `[~]` partial · `[ ]` not started

### FOUNDATION — done
- [x] Microphone (device selectable via `MIC_DEVICE`)
- [x] PCM streaming
- [x] Silero VAD
- [x] Speech segmentation
- [x] Pre-buffer (pre-roll)
- [x] faster-whisper STT
- [x] Local LLM (Ollama qwen3:8b)
- [x] ConversationManager
- [x] TTS (Piper)
- [ ] Hotkey activation — **removed** (commit c8657f3 dropped the pynput activation package); current activation is Enter push-to-talk. Superseded by the wake-word work in ACTIVATION.

### LOW LATENCY — mostly done
- [x] Streaming LLM (`chat_stream` yields content chunks)
- [x] Streaming TTS (`TTSWorker` thread)
- [x] Audio buffering (mic queue + `drain()`)
- [x] Sentence-level TTS (`SentenceBuffer`)
- [~] Latency instrumentation — per-LLM-call TTFT/tok-s only; no end-to-end capture→first-audio metric, and only the last tool round is reported (see open issue)
- [ ] EoS → First-Audio benchmark

### AGENT — done
- [x] Tool interface (`tools/base.py`: `Tool` / `ToolResult` / `api_schema`)
- [x] Tool registry (`tools/registry.py`)
- [x] Structured tool calls (native OpenAI function calling)
- [x] Tool executor (`agent/tool_executor.py`)
- [x] Tool results → LLM (`role: "tool"` messages, max 3 rounds)

### SAFETY — not started
- [ ] Permission Manager
- [ ] Tool risk levels
- [ ] Confirmation system (e.g. before `close_window` / app launch)
- [ ] Execution sandboxing

### TOOLS — partial
- [~] Applications — launch only (`gio`), no list/close
- [ ] Filesystem
- [ ] System (volume / brightness / processes)
- [~] Window management — `close_window`, Hyprland-only
- [ ] Media
- [~] Web — `browser_search` opens a Google *tab* via `xdg-open`; no fetch/parse

### MEMORY
- [x] Short-term conversation (`ConversationManager.messages`; note: tool results persist in history)
- [ ] Long-term memory
- [ ] Memory extraction
- [ ] Memory retrieval

### ACTIVATION
- [ ] Wake-word detector (replaces removed hotkey)
- [ ] False-positive testing
- [ ] False-negative testing
- [ ] Activation latency

### Other open work (from code review)
- [ ] LLM errors crash the session (uncaught `requests` errors in `main.py`)
- [ ] `SentenceBuffer` splits on Russian abbreviations/decimals ("т. д.", "3.14")
- [ ] End-to-end latency instrumentation + EoS→first-audio benchmark
- [ ] Barge-in / interruption (assistant cannot be interrupted while speaking)
- [ ] TOOLS expansion is blocked behind the SAFETY layer
