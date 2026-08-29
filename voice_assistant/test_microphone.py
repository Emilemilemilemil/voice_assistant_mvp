#!/usr/bin/env python3
"""Quick microphone diagnostic tool."""

import numpy as np
import sounddevice as sd
from vad.silero import SileroVAD

print("=== Microphone Diagnostic ===\n")

# List devices
print("Available input devices:")
devices = sd.query_devices()
for i, dev in enumerate(devices):
    if dev['max_input_channels'] > 0:
        marker = " <- DEFAULT" if i == sd.default.device[0] else ""
        print(f"  {i}: {dev['name']}{marker}")

print("\n--- Recording 3 seconds of audio ---")
print("Speak into your microphone now!\n")

# Record
sample_rate = 16000
duration = 3
audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
sd.wait()

print("Recording complete.\n")

# Analyze
audio_flat = audio.flatten()
print(f"Audio stats:")
print(f"  Min: {audio_flat.min():.4f}")
print(f"  Max: {audio_flat.max():.4f}")
print(f"  Mean: {audio_flat.mean():.4f}")
print(f"  RMS: {np.sqrt(np.mean(audio_flat**2)):.4f}")

# Test VAD
print("\n--- Testing VAD (Silero) ---")
vad = SileroVAD(threshold=0.50)

chunk_size = 512
total_chunks = len(audio_flat) // chunk_size
speech_chunks = 0

for i in range(total_chunks):
    chunk = audio_flat[i * chunk_size:(i + 1) * chunk_size]
    if vad.is_speech(chunk, sample_rate):
        speech_chunks += 1

print(f"Total chunks: {total_chunks}")
print(f"Speech chunks detected: {speech_chunks}")
print(f"Speech percentage: {speech_chunks / total_chunks * 100:.1f}%")

if speech_chunks == 0:
    print("\n❌ NO SPEECH DETECTED!")
    print("Possible issues:")
    print("  1. Microphone volume too low")
    print("  2. Wrong microphone selected")
    print("  3. VAD threshold too high (currently 0.50)")
    print("\nTry:")
    print("  - Check system microphone volume")
    print("  - Set MIC_DEVICE in .env to correct device number")
    print("  - Lower VAD_THRESHOLD in .env (try 0.3)")
else:
    print(f"\n✅ Speech detected successfully!")
