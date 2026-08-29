# Local Voice Assistant

Modular local voice assistant with SAFETY layer:

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

4. **Whisper models** download automatically on first run (requires CUDA/CPU as configured). Includes automatic fallback to `tiny` CPU model on failure.

## Safety Layer (`safety/`)

Every tool execution passes through the SAFETY layer:

### Risk Levels (`safety/risk.py`)
- `SAFE` (0): Read-only, no side effects (`get_current_time`, `browser_search`)
- `CONFIRM` (1): Reversible side effects (`open_application`, `close_window`)
- `DESTRUCTIVE` (2): Hard to reverse (blocked by default, requires explicit allow policy)

### Permission Manager (`safety/permissions.py`)
- `PermissionManager` controls allow/deny lists.
- Denied tools always fail (`[permission denied]`).
- Explicitly allowed tools skip confirmation and run immediately.
- By default all CONFIRM-level tools execute without confirmation (user preference).

### Execution Sandbox (`safety/sandbox.py`)
- `ExecutionSandbox` wraps every tool call.
- Enforces per-call timeout (SIGALRM) — hung `gio` or `hyprctl` commands are killed after timeout.
- Records invocation audit trail (start/end time, duration, result).
- Returns `SandboxResult` with `raw_result` (unmodified ToolResult) to preserve output integrity.

### Confirmation System (`safety/confirm.py`)
- `ConfirmationPrompter`: interactive `[y/N]:` prompt for CONFIRM-level actions.
- `AutoApprovePrompter`: non-interactive mode returns denied automatically.
- User-configured to skip confirmations (current default: no prompts for CONFIRM tools).

### Sandbox + Tool Integration
`agent/tool_executor_safe.py` connects the layers:
1. Check `PermissionManager.check()`
2. Check `ConfirmationPrompter.prompt()` (if risk requires confirmation and not explicitly allowed)
3. Run in `ExecutionSandbox.run()`
4. Unwrap `ToolResult` from `SandboxResult.raw_result`

## LLM Client (`llm/`)

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
- **Clean stream state**: `last_tool_calls` is only set after a successful stream completion; interrupted streams don't leave partial/malformed tool calls in the conversation history.
- **Malformed chunk logging**: Malformed JSON chunks from the LLM are logged (not silently skipped).

### Tool Call Streaming (`openai_compatible.py`)
- Partial `tool_calls` fragments stream correctly across chunks.
- `pending_calls` accumulates fragments; incomplete/empty `name` fields are filtered out before feeding back to the model.

## TTS (`tts/`)

By default Piper is expected at `~/voice_assistant_mvp/bin/piper/piper`
with the model `~/voice_assistant_mvp/models/piper/ru_RU-irina-medium.onnx`.
Override via `PIPER_BIN` and `PIPER_MODEL` in `.env`.

If Piper is not configured, the assistant prints the answer instead of speaking it.

### Subprocess Isolation & Cleanup
- `PiperTTS.speak()` catches `CalledProcessError` (bad model, corrupt audio) and returns `(success, message)` — no crash propagates to the TTS thread.
- `main.py` tracks all spawned `subprocess.Popen` instances (`piper`, `pw-play`, `xdg-open`) and kills them gracefully on `Ctrl+C`.

### Audio Playback Failure Propagation (`tts/audio_player.py`)
- `PipeWirePlayer.play()` returns `(bool, str)` instead of raising — playback failures don't crash the worker.

## Tools (`tools/`)

Tools use native OpenAI function calling (`tools=` in the request). Each tool declares its JSON Schema in `tools/`; the registry feeds schemas to the model, and returned `tool_calls` are executed and fed back as `role: "tool"` messages until the model produces a spoken reply (max 3 rounds).

**Available tools:**
- `get_current_time` (SAFE) — returns current time
- `open_application` (SAFE) — launches apps via `.desktop` file indexing (uses `gio launch`); includes security validation (only launches from allowed directories)
- `browser_search` (SAFE) — opens a Google search tab via `xdg-open`
- `close_window` (SAFE) — closes windows (Hyprland 0.55+ Lua dispatcher syntax); gracefully degrades on other DEs

**Lazy initialization:** Tools that depend on system-specific backends (Hyprland, .desktop indexing) fail gracefully at execution time rather than crashing at startup. The assistant runs on GNOME/KDE/other window managers; unsupported tools return error messages.

### Security: .desktop Launch Validation
`LinuxDesktopLauncher` validates:
- `.desktop` path is inside allowed directories (`/usr/share/applications`, `~/.local/share/applications`)
- File exists and is a regular file
Prevents malicious `.desktop` files with destructive `Exec=` lines from being executed.

### Unicode Normalization
`ApplicationLauncher` uses `unicodedata.normalize("NFKC", ...)` before matching, ensuring consistent matching regardless of composed/decomposed Unicode forms.

### Filesystem Tools (`tools/filesystem.py`)
- `fs_guard(path)` resolves symlinks, then enforces the path is inside `FS_ROOT` (default `~`). Outside the boundary → deny.
- Token blacklist rejects any path component containing `sudo`, `pkexec`, `doas`, or `su` — privilege-escalation attempts cannot pass through `run_script`.
- DESTRUCTIVE tools (`delete_file`, `delete_directory`, `run_script`) are blocked unless listed in `ALLOWED_DESTRUCTIVE_TOOLS` in `.env` AND the user confirms.

### System Tools (`tools/system_tool.py`)
- `SystemBackend` ABC abstracts all OS-specific operations; `LinuxSystemBackend` uses per-user binaries (`pactl`, `ps`, `wl-copy`/`wl-paste`, `grim`, `wf-recorder`, `loginctl --user`) — **no root required**.
- macOS/Windows backends exist as stubs that return "not yet implemented"; factory falls back to a generic unavailable backend if Linux binaries are missing.
- DESTRUCTIVE tools (`kill_process`, `system_power`) are blocked unless listed in `ALLOWED_DESTRUCTIVE_TOOLS` in `.env` AND the user confirms.
- `take_screenshot` / `start_recording` are restricted to the home directory; absolute paths are rejected.

## Run

```bash
python main.py
```

Press Enter, speak, and stop speaking. VAD detects the end of the utterance.

- If you don't speak within 30 seconds (configurable via `MAX_LISTEN_MS`), the assistant times out with "didn't hear you (timeout)", resets the conversation state, and returns to the prompt.
- If the LLM fails (network error, timeout, server crash), the assistant prints the error and continues to the next turn.
- Audio queue overflow warnings print once (not spammed): if capture exceeds processing speed, oldest chunks are dropped and a single warning is shown.

The assistant streams the answer sentence by sentence to TTS and waits until playback finishes before the next turn.

The last captured utterance is saved as `debug/last_segment.wav`.

## Configuration

All configuration is via environment variables (`.env` file). See `.env.example` for the full list.

**Key options:**
- `MIC_DEVICE` — audio input device index (empty = system default)
- `MAX_LISTEN_MS` — timeout for silent activation (default 30000 = 30s)
- `LLM_PROVIDER` — `ollama` or `openai` (controls which params are sent)
- `LLM_BASE_URL`, `LLM_MODEL` — LLM endpoint and model name
- `WHISPER_MODEL`, `WHISPER_DEVICE` — STT model and device (cuda/cpu); includes automatic fallback to `tiny` CPU model
- `PIPER_BIN`, `PIPER_MODEL` — TTS binary and voice model paths
- `VAD_THRESHOLD` — validated at startup (default 0.50, range [0.0, 1.0])
- `FS_ROOT` — filesystem tool boundary (default `~`); tools cannot escape this directory
- `ALLOWED_DESTRUCTIVE_TOOLS` — comma-separated list of destructive tools enabled (e.g. `delete_file,system_power`); empty by default

## Bug Fixes (Implemented)

- **Audio queue overflow**: Queue overflow warnings print once per session (not spammed); chunks are silently recovered after initial warning.
- **LLM stream cleanup**: `last_tool_calls` only set after successful stream; interrupted streams don't leave malformed tool data.
- **History trimming**: Assistant messages with dangling `tool_calls` are removed during trim, preventing invalid message sequences.
- **Piper crash isolation**: `CalledProcessError` caught; TTS thread continues functioning.
- **STT error messages**: Empty results show informative message ("speech may be too quiet"); failures show "speech recognition failed".
- **VAD/STT download errors**: Graceful fallback (`tiny` CPU model for Whisper, energy-based fallback for VAD).
- **Timeout reset**: Conversation state reset after timeout (prevents stale context).
- **Malformed LLM JSON**: Logged with chunk preview instead of silently skipped.
- **Subprocess cleanup**: All spawned subprocesses killed gracefully on SIGINT.

## Roadmap

Legend: `[x]` done · `[~]` partial · `[ ]` not started

### FOUNDATION — done
- [x] Microphone (device selectable via `MIC_DEVICE`)
- [x] PCM streaming
- [x] Silero VAD (with download error recovery)
- [x] Speech segmentation
- [x] Pre-buffer (pre-roll)
- [x] faster-whisper STT (with fallback model)
- [x] Local LLM (Ollama qwen3:8b, OpenAI-compatible; clean stream state)
- [x] ConversationManager (history trim + tool execution + error tracking)
- [x] TTS (Piper; crash isolation + playback failure propagation)
- [x] Error recovery (LLM failures don't crash session; STT errors distinguishable)
- [x] Listen timeout (prevents infinite hang + resets conversation state)
- [x] Subprocess cleanup (SIGINT kills piper, pw-play, xdg-open)
- [x] Audio overflow handling (once-per-session warning, no silent data loss)
- [ ] Hotkey activation — **removed** (commit c8657f3 dropped the pynput activation package); current activation is Enter push-to-talk. Superseded by the wake-word work in ACTIVATION.

### LOW LATENCY — done
- [x] Streaming LLM (`chat_stream` yields content chunks)
- [x] Streaming TTS (`TTSWorker` thread; isolated from Piper crashes)
- [x] Audio buffering (mic queue + `drain()`; overflow recovery)
- [x] Sentence-level TTS (`SentenceBuffer` with improved Russian splitting; NFKC normalization for matching)
- [x] Latency instrumentation — TTFT (first token from last LLM call), turn-level wall-clock timing, tok/s
- [ ] EoS → First-Audio benchmark

### AGENT — done
- [x] Tool interface (`tools/base.py`: `Tool` / `ToolResult` / `api_schema`)
- [x] Tool registry (`tools/registry.py` with lazy initialization)
- [x] Structured tool calls (native OpenAI function calling; clean stream state)
- [x] Safe tool executor (`agent/tool_executor_safe.py` with SAFETY layer integration)
- [x] Tool results → LLM (`role: "tool"` messages; history trim filters dangling calls; max 3 rounds; retry limits prevent loops)
- [x] Ephemeral tool results (filtered during history trimming to prevent pollution; assistant messages with dangling tool_calls dropped)
- [x] Sandbox result unwrapping (raw `ToolResult` preserved, not mangled by `str()`)

### SAFETY — done
- [x] Permission Manager (`safety/permissions.py`: allow/deny lists, confirmation bypass for allowed tools, destructive tool policy)
- [x] Tool risk levels (`SAFE` / `CONFIRM` / `DESTRUCTIVE`; per-tool declaration; user-configurable)
- [x] Confirmation system (`safety/confirm.py`: interactive `ConfirmationPrompter`, non-interactive `AutoApprovePrompter`; bypassed for SAFE-level tools)
- [x] Execution sandboxing (`safety/sandbox.py`: audit logging, SIGALRM timeout enforcement, `SandboxResult` with raw result preservation)
- [x] Sandbox + executor integration (`agent/tool_executor_safe.py`: permission check → confirmation → sandbox → unwrapped result)
- [x] Security: `.desktop` validation (`ALLOWED_DIRS`, file existence, regular file check)

### TOOLS — partial
- [x] Applications — launch via `gio` + `.desktop` indexing + security validation (+ NFKC normalization)
- [x] Filesystem — `fs_guard` (symlink resolution + FS_ROOT boundary + token blacklist); SAFE (`read`, `list`, `search`), CONFIRM (`write`, `create_dir`, `copy`, `move`), DESTRUCTIVE (`delete_file`, `delete_dir`, `run_script`) gated by `.env` allow-list + confirmation
- [x] System — `SystemBackend` ABC + `LinuxSystemBackend` (pactl/ps/wl-clipboard/grim/wf-recorder/loginctl); SAFE (`volume`, `clipboard`, `screenshot`, `recording`, `processes`), DESTRUCTIVE (`kill_process`, `system_power`) gated by `.env` allow-list; macOS/Windows stubs included; no-root enforcement (per-user binaries only)
- [x] Window management — `close_window` (Hyprland 0.55+; graceful degradation; abstracted `WindowBackend` interface)
- [ ] Media
- [~] Web — `browser_search` opens a Google tab via `xdg-open`; no fetch/parse
- [x] Time — `get_current_time`

### MEMORY
- [x] Short-term conversation (`ConversationManager.messages`; tool results are ephemeral and filtered on trim; dangling assistant(tool_calls) removed)
- [x] Timeout reset (conversation state cleared after `MAX_LISTEN_MS` timeout)
- [ ] Long-term memory
- [ ] Memory extraction
- [ ] Memory retrieval

### ACTIVATION
- [ ] Wake-word detector (replaces removed hotkey)
- [ ] False-positive testing
- [ ] False-negative testing
- [ ] Activation latency

### POLISH
- [x] Audio overflow warnings (once per session, not spammed)
- [x] STT error differentiation (empty = too quiet; exception = recognition failed)
- [x] Config validation (VAD threshold range check, min/end silence warnings)
- [x] Subprocess cleanup (SIGINT kills all spawned processes gracefully)
- [x] Sandbox timeout enforcement (SIGALRM; hung tools blocked)
- [x] Sandbox result preservation (raw `ToolResult` preserved, `str()` mangling prevented)
- [x] Tool retry limits (max 2 errors per tool, then final block message)
- [x] Malformed LLM chunk logging (chunk preview logged, not silently skipped)
- [x] Tool interface protocol (`agent/tool_protocol.py` for type clarity)
- [ ] Barge-in / interruption (assistant cannot be interrupted while speaking)
- [ ] Echo cancellation
- [x] TOOLS expansion protected by SAFETY layer (permission + sandbox + confirmation before any new backend is wired)

### PLATFORM ABSTRACTION — done
- [x] AudioPlayer backend (PipeWire → abstracted; failure propagation)
- [x] BrowserBackend (xdg-open → abstracted)
- [x] AppLauncherBackend (.desktop indexing → abstracted; security validation)
- [x] WindowBackend (Hyprland → abstracted; factory with graceful degradation)
- [ ] macOS backends (AFPlay, open, .app parsing)
- [ ] Windows backends (Media.SoundPlayer, start, Start Menu)

## Architecture

```
main.py
├── Microphone (sounddevice stream + Queue overflow recovery)
│   └── SileroVAD (16kHz, 512-sample frames; download error recovery)
├── SpeechSegmenter (VAD + chunking; reset on timeout)
├── FasterWhisperSTT (transcription; model download fallback; empty/error differentiation)
├── ConversationManager (history + tool orchestration + error tracking)
│   ├── LocalLLM (OpenAI-compatible streaming; clean stream state; malformed chunk logging)
│   └── SafeToolExecutor (SAFETY layer integration)
│       ├── PermissionManager (allow/deny; destructive gating via .env)
│       ├── ConfirmationPrompter (interactive/non-interactive)
│       ├── ExecutionSandbox (audit + timeout + raw result preservation)
│       └── ToolRegistry (lazy tool loading)
│           ├── TimeTool (SAFE)
│           ├── OpenApplicationTool (SAFE; security-validated .desktop)
│           ├── BrowserSearchTool (SAFE; URL-quoted query)
│           ├── CloseWindowTool (SAFE; abstracted WindowBackend)
│           ├── FilesystemTool* (SAFE/CONFIRM/DESTRUCTIVE; fs_guard security)
│           └── SystemTool* (SAFE/DESTRUCTIVE; SystemBackend; no-root)
├── SentenceBuffer (streaming sentence splitter; NFKC normalization support)
└── TTSWorker (background Piper thread; isolated from crashes)
    └── PiperTTS → AudioPlayer
        └── PipeWirePlayer (pw-play; failure propagation)
```

## Safety Layer Details

### 1. Permission Check (`safety/permissions.py`)
Every tool call passes through `PermissionManager.check()`:
- Denied list wins always
- Explicit allow list bypasses confirmation (for SAFE-level tools)
- `DESTRUCTIVE` (risk >= 2) blocked by default; requires explicit allow to run
- `CONFIRM` (risk >= 1) confirmed by user unless explicitly allowed
- `SAFE` (risk == 0) runs immediately (current default for all tools)

### 2. Confirmation System (`safety/confirm.py`)
- Interactive: writes to stdout, reads from stdin (`[y/N]` prompt)
- Non-interactive: `AutoApprovePrompter` denies automatically
- Configured globally; user can disable confirmations (current default)

### 3. Execution Sandbox (`safety/sandbox.py`)
- Records audit trail (start/end time, duration, result)
- Enforces timeout via `SIGALRM` (Unix-only; blocks hung subprocesses)
- Normalizes errors into `SandboxResult`
- Preserves raw `ToolResult` in `SandboxResult.raw_result`
- Unwrapped in `SafeToolExecutor.execute()` before feeding back to LLM

### 4. Integration Pattern (`agent/tool_executor_safe.py`)
```python
# Execute path:
1. Permission check (PermissionManager.check)
2. Confirmation prompt (if required, not explicitly allowed)
3. Sandbox run (ExecutionSandbox.run)
4. Unwrap ToolResult (SandboxResult.raw_result)
5. Format result (prefix + output / error message)
```

## Platform Abstraction

The codebase uses **backend interfaces** for all OS-specific operations, following the "t() on day 1" principle: wrap every OS call now, implement other platforms later.

### Pattern

Each platform-specific operation has:
1. **Abstract interface** (`AudioPlayer`, `BrowserBackend`, `AppLauncherBackend`, `WindowBackend`)
2. **Linux implementation** (`PipeWirePlayer`, `XdgBrowserOpener`, `LinuxDesktopLauncher`, `HyprlandWindowBackend`)
3. **Factory** with runtime detection (`AudioPlayerFactory.create()`, etc.)
4. **Graceful degradation** - tools fail softly if backend unavailable

### Security Layer

For `.desktop` file launching (`LinuxDesktopLauncher`):
- Whitelist: only `ALLOWED_DIRS` (`/usr/share/applications`, `~/.local/share/applications`)
- File must exist and be a regular file
- No arbitrary `.desktop` execution allowed

For tool execution (`SafeToolExecutor`):
- All results pass through `ExecutionSandbox`
- Tool errors tracked (`_tool_errors`) — max 2 failures before giving up
- Conversation reset after timeout prevents stale context

### Current Platform Support

| Feature | Linux | macOS | Windows |
|---------|-------|-------|---------|
| Audio playback | ✅ PipeWire | ⏳ Future | ⏳ Future |
| App launching | ✅ `.desktop` + security validation | ⏳ Future | ⏳ Future |
| Browser opening | ✅ `xdg-open` | ⏳ Future | ⏳ Future |
| Window management | ✅ Hyprland (abstracted) | ⏳ Future | ⏳ Future |
| Filesystem tools | ✅ fs_guard + home-only + token blacklist | ⏳ Future | ⏳ Future |
| System tools | ✅ pactl/ps/wl-clipboard/grim/wf-recorder/loginctl | ⏳ Future | ⏳ Future |
| Safety layer | ✅ Full (permission + sandbox + confirmation) | ⏳ Future | ⏳ Future |

**Adding a new platform:** Implement ~150 LOC of backend classes (e.g., `AFPlayPlayer`, `MacOSLauncher`). Zero callsite changes required for tools; SAFETY layer applies globally.

### Benefits

- **Future-proof**: macOS/Windows support is a bounded task
- **Testable**: Mock backends for unit tests; `test_safety.py` covers sandbox behavior
- **SAFETY-ready**: Permission checks sit between tool interface and backend; sandbox enforces timeout
- **Security**: `.desktop` validation prevents arbitrary command execution; sandbox audit trail records every tool invocation
- **TOOLS expansion**: New tools code against interfaces from day 1; all protected by SAFETY layer
- **Stability**: Crash isolation (Piper failure doesn't kill TTS thread; STT failure reports clearly; VAD download failure falls back to energy-based detection)

## Known Issues

- **No barge-in**: TTS plays to completion; you can't interrupt the assistant mid-sentence.
- **No pinned dependencies**: `requirements.txt` has unpinned versions; consider pinning for reproducibility.
- **Audio queue overflow**: If processing is slower than capture (Whisper + LLM latency), oldest chunks are dropped. Warning prints once per session (not spammed). Not a crash, but audio may be truncated.
- **Hyprland window closing only**: `close_window` tool requires Hyprland 0.55+ (Lua dispatcher syntax); gracefully degrades on other DEs.
- **Linux-only backends**: Audio, app launching, browser, and window management currently Linux-only.
- **Window backend abstraction only**: Window backend is abstracted but only Hyprland is implemented. Future platforms (macOS, Windows, GNOME) need new `WindowBackend` implementations.
- **Russian-centric**: Default Whisper language is `ru`, Piper model is Russian. Override via `.env` for other languages.
- **Sandbox timeout**: SIGALRM-based timeout works on Unix; not portable to Windows.

## Performance Notes

- **Audio overflow**: Queue maxsize=100. At 16kHz with 32ms chunks, this holds ~3.2s of audio. If Whisper + LLM takes >3.2s per turn, overflow occurs. Not a crash — oldest chunks are dropped silently after initial warning.
- **LLM timeout**: 120s read timeout. Large models (`qwen3:8b`) typically respond in <5s for short answers. Timeout is recoverable (retry once).
- **STT model**: `large-v3-turbo` (~1GB download on first run). Falls back to `tiny` CPU model if download/load fails.

## Contributing

Bug reports and PRs welcome. For major changes, open an issue first.

### Testing

- `test_safety.py`: SAFETY layer integration (sandbox behavior, confirmation, permission, error tracking)
- `test_microphone.py`: Microphone device testing
- `test_filesystem_system.py`: Filesystem tools (`fs_guard`, SAFE/CONFIRM/DESTRUCTIVE), system backend factory, system tools

Add sandbox-covered test cases for any new tool to prevent the critical `str()` mangling bug (fixed: raw `ToolResult` preserved through `SandboxResult.raw_result`).

## License

MIT
