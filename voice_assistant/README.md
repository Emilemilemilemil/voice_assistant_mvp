# Local Voice Assistant

Modular local voice assistant:

Microphone -> Ctrl+Space activation -> Silero VAD -> faster-whisper -> local OpenAI-compatible LLM -> Piper TTS.

The spoken request contains no wake-word name. Activation is a separate event.

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
sudo pacman -S ffmpeg portaudio
```

Copy `.env.example` to `.env` and configure it.

## LLM

Run any local OpenAI-compatible server. Example endpoint:

`http://127.0.0.1:8080/v1/chat/completions`

Set `LLM_BASE_URL` and `LLM_MODEL` in `.env`.

## Piper

Install Piper and download a compatible voice model. Set `PIPER_BIN` and `PIPER_MODEL`.

If Piper is not configured, the assistant prints the answer instead of speaking it.

## Run

```bash
python main.py
```

Press Ctrl+Space, speak, and stop speaking. VAD detects the end of the utterance.

The last captured utterance is saved as `debug/last_segment.wav`.

## Current scope

Implemented:
- microphone stream
- hotkey activation
- Silero VAD
- speech segmentation
- pre-roll buffer
- faster-whisper STT
- conversation history
- OpenAI-compatible local LLM client
- Piper TTS

Not yet implemented:
- real wake-word detector
- tool calling
- permission system
- long-term memory
- streaming LLM/TTS
