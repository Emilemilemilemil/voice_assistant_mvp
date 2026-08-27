# Local Voice Assistant

Modular local voice assistant:

Microphone → Enter activation → Silero VAD → faster-whisper → local OpenAI-compatible LLM → Piper TTS.

The spoken request contains no wake-word name. Activation is a separate event (Enter).

## Install

Recommended: Python 3.11/3.12.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

On Arch, install audio dependencies as needed:

```bash
sudo pacman -S ffmpeg portaudio pipewire
```

### Setup

1. **Copy `.env.example` to `.env` and configure it.**

2. **Install Ollama** (or another OpenAI-compatible LLM server):
   ```bash
   # Install Ollama from https://ollama.com
   ollama pull qwen3:8b
   ollama serve
   ```

3. **Install Piper TTS** (optional, falls back to text output):
   - Download from https://github.com/rhasspy/piper
   - Place binary at `~/voice_assistant_mvp/bin/piper/piper`
   - Download a voice model (e.g., `ru_RU-irina-medium.onnx`) to `~/voice_assistant_mvp/models/piper/`
   - Or override paths via `PIPER_BIN` and `PIPER_MODEL` in `.env`

4. **Whisper models** download automatically on first run (requires CUDA/CPU as configured).

## LLM

Default setup is a local [Ollama](https://ollama.com) server with `qwen3:8b`:

`http://127.0.0.1:11434/v1/chat/completions`

Set `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_PROVIDER` in `.env`. Any OpenAI-compatible server works (LM Studio, llama.cpp server, vLLM, real OpenAI API).

### Provider-Specific Behavior

Set `LLM_PROVIDER` in `.env`:
- **`ollama`** (default): Sends `reasoning_effort: "none"` so thinking models don't burn latency before speech, and `keep_alive` so the model stays warm between turns.
- **`openai`** or other: Sends only standard OpenAI API parameters (no `reasoning_effort` or `keep_alive`).

The client includes:
- **Error recovery**: HTTP errors, network issues, and server restarts print a recoverable error instead of crashing the session.
- **Timeout/retry**: 10s connect timeout, 120s read timeout, 1 automatic retry on timeout/connection errors.

## Piper

By default Piper is expected at `~/voice_assistant_mvp/bin/piper/piper`
with the model `~/voice_assistant_mvp/models/piper/ru_RU-irina-medium.onnx`.
Override via `PIPER_BIN` and `PIPER_MODEL` in `.env`.

If Piper is not configured, the assistant prints the answer instead of speaking it.

## Tools

Tools use native OpenAI function calling (`tools=` in the request). Each tool declares its JSON Schema in `tools/`; the registry feeds schemas to the model, and returned `tool_calls` are executed and fed back as `role: "tool"` messages until the model produces a spoken reply (max 3 rounds).

**Available tools:**
- `get_current_time` — returns current time
- `open_application` — launches apps via `.desktop` file indexing (uses `gio launch`)
- `browser_search` — opens a Google search in the default browser
- `close_window` — closes windows (Hyprland only; gracefully degrades on other DEs)

**Lazy initialization:** Tools that depend on system-specific backends (Hyprland, .desktop indexing) fail gracefully at execution time rather than crashing at startup. The assistant runs on GNOME/KDE/other window managers; unsupported tools return error messages.

## Run

```bash
python main.py
```

Press Enter, speak, and stop speaking. VAD detects the end of the utterance.

- If you don't speak within 30 seconds (configurable via `MAX_LISTEN_MS`), the assistant times out with "didn't hear you (timeout)" and returns to the prompt.
- If the LLM fails (network error, timeout, server crash), the assistant prints the error and continues to the next turn.

The assistant streams the answer sentence by sentence to TTS and waits until playback finishes before the next turn.

The last captured utterance is saved as `debug/last_segment.wav`.

## Configuration

All configuration is via environment variables (`.env` file). See `.env.example` for the full list.

**Key options:**
- `MIC_DEVICE` — audio input device index (empty = system default)
- `MAX_LISTEN_MS` — timeout for silent activation (default 30000 = 30s)
- `LLM_PROVIDER` — `ollama` or `openai` (controls which params are sent)
- `LLM_BASE_URL`, `LLM_MODEL` — LLM endpoint and model name
- `WHISPER_MODEL`, `WHISPER_DEVICE` — STT model and device (cuda/cpu)
- `PIPER_BIN`, `PIPER_MODEL` — TTS binary and voice model paths

## Roadmap

Legend: `[x]` done · `[~]` partial · `[ ]` not started

### FOUNDATION — done
- [x] Microphone (device selectable via `MIC_DEVICE`)
- [x] PCM streaming
- [x] Silero VAD
- [x] Speech segmentation
- [x] Pre-buffer (pre-roll)
- [x] faster-whisper STT
- [x] Local LLM (Ollama qwen3:8b, OpenAI-compatible)
- [x] ConversationManager
- [x] TTS (Piper)
- [x] Error recovery (LLM failures don't crash the session)
- [x] Listen timeout (prevents infinite hang on silent activation)
- [ ] Hotkey activation — **removed** (commit c8657f3 dropped the pynput activation package); current activation is Enter push-to-talk. Superseded by the wake-word work in ACTIVATION.

### LOW LATENCY — done
- [x] Streaming LLM (`chat_stream` yields content chunks)
- [x] Streaming TTS (`TTSWorker` thread)
- [x] Audio buffering (mic queue + `drain()`)
- [x] Sentence-level TTS (`SentenceBuffer` with improved Russian splitting)
- [x] Latency instrumentation — TTFT (first token from last LLM call), turn-level wall-clock timing, tok/s
- [ ] EoS → First-Audio benchmark

### AGENT — done
- [x] Tool interface (`tools/base.py`: `Tool` / `ToolResult` / `api_schema`)
- [x] Tool registry (`tools/registry.py` with lazy initialization)
- [x] Structured tool calls (native OpenAI function calling)
- [x] Tool executor (`agent/tool_executor.py`)
- [x] Tool results → LLM (`role: "tool"` messages, max 3 rounds)
- [x] Ephemeral tool results (filtered during history trimming to prevent pollution)

### SAFETY — not started
- [ ] Permission Manager
- [ ] Tool risk levels
- [ ] Confirmation system (e.g. before `close_window` / app launch)
- [ ] Execution sandboxing

### TOOLS — partial
- [x] Applications — launch via `gio` + `.desktop` indexing
- [ ] Filesystem
- [ ] System (volume / brightness / processes)
- [x] Window management — `close_window` (Hyprland-only, graceful degradation on other DEs)
- [ ] Media
- [~] Web — `browser_search` opens a Google tab via `xdg-open`; no fetch/parse
- [x] Time — `get_current_time`

### MEMORY
- [x] Short-term conversation (`ConversationManager.messages`; tool results are ephemeral and filtered on trim)
- [ ] Long-term memory
- [ ] Memory extraction
- [ ] Memory retrieval

### ACTIVATION
- [ ] Wake-word detector (replaces removed hotkey)
- [ ] False-positive testing
- [ ] False-negative testing
- [ ] Activation latency

### POLISH
- [ ] Barge-in / interruption (assistant cannot be interrupted while speaking)
- [ ] Echo cancellation
- [ ] TOOLS expansion is blocked behind the SAFETY layer

### PLATFORM ABSTRACTION — done
- [x] AudioPlayer backend (PipeWire → abstracted)
- [x] BrowserBackend (xdg-open → abstracted)
- [x] AppLauncherBackend (.desktop indexing → abstracted)
- [x] WindowBackend (Hyprland → already abstracted)
- [ ] macOS backends (AFPlay, open, .app parsing)
- [ ] Windows backends (Media.SoundPlayer, start, Start Menu)

## Architecture

```
main.py
├── Microphone (sounddevice stream)
├── SpeechSegmenter (VAD + chunking)
│   └── SileroVAD (16kHz, 512-sample frames)
├── FasterWhisperSTT (transcription)
├── ConversationManager (history + tool orchestration)
│   ├── LocalLLM (OpenAI-compatible streaming client)
│   └── ToolExecutor
│       └── ToolRegistry (lazy tool loading)
│           ├── TimeTool
│           ├── OpenApplicationTool → AppLauncherBackend
│           │   └── LinuxDesktopLauncher (gio + .desktop)
│           ├── BrowserSearchTool → BrowserBackend
│           │   └── XdgBrowserOpener (xdg-open)
│           └── CloseWindowTool → WindowBackend
│               └── HyprlandWindowBackend (hyprctl)
├── SentenceBuffer (streaming sentence splitter)
└── TTSWorker (background Piper thread)
    └── PiperTTS → AudioPlayer
        └── PipeWirePlayer (pw-play)
```

## Platform Abstraction

The codebase uses **backend interfaces** for all OS-specific operations, following the "t() on day 1" principle: wrap every OS call now, implement other platforms later.

### Pattern

Each platform-specific operation has:
1. **Abstract interface** (`AudioPlayer`, `BrowserBackend`, `AppLauncherBackend`, `WindowBackend`)
2. **Linux implementation** (`PipeWirePlayer`, `XdgBrowserOpener`, `LinuxDesktopLauncher`, `HyprlandWindowBackend`)
3. **Factory** with runtime detection (`AudioPlayerFactory.create()`, etc.)
4. **Graceful degradation** - tools fail softly if backend unavailable

### Current Platform Support

| Feature | Linux | macOS | Windows |
|---------|-------|-------|---------|
| Audio playback | ✅ PipeWire | ⏳ Future | ⏳ Future |
| App launching | ✅ .desktop | ⏳ Future | ⏳ Future |
| Browser opening | ✅ xdg-open | ⏳ Future | ⏳ Future |
| Window management | ✅ Hyprland | ⏳ Future | ⏳ Future |

**Adding a new platform:** Implement ~150 LOC of backend classes (e.g., `AFPlayPlayer`, `MacOSLauncher`). Zero callsite changes required.

### Benefits

- **Future-proof**: macOS/Windows support is a bounded task
- **Testable**: Mock backends for unit tests
- **SAFETY-ready**: Permission checks sit between tool interface and backend
- **TOOLS expansion**: New tools code against interfaces from day 1

## Known Issues

- **No barge-in**: TTS plays to completion; you can't interrupt the assistant mid-sentence.
- **No pinned dependencies**: `requirements.txt` has unpinned versions; consider pinning for reproducibility.
- **Hyprland window closing only**: `close_window` tool requires Hyprland 0.55+ (Lua dispatcher syntax); gracefully degrades on other DEs.
- **Linux-only backends**: Audio, app launching, browser, and window management currently Linux-only (see Platform Abstraction section).
- **Russian-centric**: Default Whisper language is `ru`, Piper model is Russian. Override via `.env` for other languages.

## Contributing

Bug reports and PRs welcome. For major changes, open an issue first.

## License

MIT
