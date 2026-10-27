"""Find which microphone settings actually work:  python mic_probe.py"""
import sounddevice as sd

devs = sd.query_devices()
print(devs)
print("\nTrying every input device...\n")
good = []
for i, d in enumerate(devs):
    if d["max_input_channels"] < 1:
        continue
    for rate in sorted({16000, int(d["default_samplerate"])}):
        for ch in (1, 2):
            if ch > d["max_input_channels"]:
                continue
            try:
                s = sd.RawInputStream(samplerate=rate, blocksize=int(rate * 0.25),
                                      dtype="int16", channels=ch, device=i)
                s.start(); s.read(int(rate * 0.25)); s.stop(); s.close()
                print(f"OK   [{i}] {d['name']} @ {rate} Hz, {ch} ch")
                good.append(i)
            except Exception as e:
                print(f"FAIL [{i}] {d['name']} @ {rate} Hz, {ch} ch: {str(e).splitlines()[0][:70]}")
if good:
    print(f"\nTo force the first working one:  export ECHOMIND_MIC={good[0]}")
else:
    print("\nNo input device opened. Check: lsusb, arecord -l, and that the mic is plugged in.")
