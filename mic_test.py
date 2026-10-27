"""Microphone doctor:  python mic_test.py
Measures noise, your voice level and signal-to-noise ratio, then shows what the speech engine heard."""
import os
import shutil
import subprocess
import time
import wave

import numpy as np

import audio

r = audio.open_reader()
hp = audio.HighPass()
print(f"mic backend: {r.kind}, source: {r.name}")


def record(sec):
    return np.concatenate([hp(r.read()) for _ in range(int(sec * 4))])


def frame_rms(x):
    n = len(x) // audio.FRAME * audio.FRAME
    return np.sqrt((x[:n].reshape(-1, audio.FRAME) ** 2).mean(axis=1))


print("\n1/2  Stay SILENT for 3 seconds...")
time.sleep(0.7)
quiet = record(3)
print("2/2  Now speak for 5 seconds:  echo, what did we decide about authentication")
talk = record(5)
r.close()

noise = float(np.median(frame_rms(quiet)))
speech = float(np.percentile(frame_rms(talk), 90))
snr = 20 * np.log10((speech + 1e-6) / (noise + 1e-6))
print(f"\nNoise level {noise:.0f} | voice level {speech:.0f} | signal-to-noise {snr:.0f} dB | peak {np.abs(talk).max():.0f}")
print("Verdict:", "GOOD" if snr >= 20 else "OK" if snr >= 12 else
      "POOR - move closer (15-20 cm), raise the mic volume, or reduce background noise")

seg = audio.Segmenter()
utts = seg.feed(list(talk[: len(talk) // audio.FRAME * audio.FRAME].reshape(-1, audio.FRAME))) + seg.flush()
if not utts:
    print("No speech detected. The voice is too quiet for the detector: raise the mic volume, "
          "or run with ECHOMIND_VAD_MIN=120.")
else:
    tr = audio.Transcriber()
    print(f"Engine: {tr.kind}")
    clips = []
    for u in utts:
        pcm = audio.prepare(u)
        clips.append(pcm)
        t0 = time.time()
        print(f"Heard: '{tr.transcribe(pcm)}'  ({time.time() - t0:.1f}s)")
    path = "/tmp/echomind_mic_test.wav"
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.concatenate(clips).tobytes())
    player = shutil.which("paplay") or shutil.which("aplay")
    if player:
        print("Playing back what EchoMind captured...")
        subprocess.run([player, path], stderr=subprocess.DEVNULL)
    os.remove(path)
