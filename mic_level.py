"""Measure the microphone: python mic_level.py
Run it twice: once in silence (do not speak), once while talking normally about 20 cm away."""
import numpy as np

import audio

r = audio.open_reader()
print(f"mic backend: {r.kind}, source: {r.name}   (measuring 3 s)")
x = np.concatenate([r.read().astype(np.float64) for _ in range(12)])
r.close()

dc = float(x.mean())
ac_rms = float(np.sqrt(((x - dc) ** 2).mean()))
peak = float(np.abs(x).max())
clipped = float((np.abs(x) >= 32000).mean() * 100)

print(f"Offset (steady shift) : {dc:8.0f}   EchoMind removes this automatically")
print(f"Signal level          : {ac_rms:8.0f}   silence should be under 300, talking 1000 to 8000")
print(f"Peak (raw)            : {peak:8.0f}   32767 is the maximum")
print(f"Clipped samples       : {clipped:7.2f} %")
print()
if clipped > 0.05 or peak >= 32000:
    print("VERDICT: CLIPPING. The microphone is too loud and speech is being distorted.")
    print("         Lower the capture volume:  bash mic_fix.sh 25   (or alsamixer, F4)")
elif ac_rms < 40:
    print("VERDICT: SILENT or very quiet. Check the plug, mute switch and capture volume.")
elif ac_rms > 1200 and peak < 28000:
    print("VERDICT: busy signal. If you were silent, the room or the microphone is noisy.")
    print("         If you were talking, this is fine.")
else:
    print("VERDICT: usable level.")
if abs(dc) > 8000:
    print(f"NOTE: the offset is large ({dc:.0f}). That leaves less headroom before clipping, so keep the gain low.")
