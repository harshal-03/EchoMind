"""Run once inside ~/echomind:   python apply_mic_autodetect.py
1. The USB microphone card is detected automatically (no more hard-coded plughw:2,0).
2. At startup EchoMind prints a level check: silent, OK or clipping.
Backup: audio.py.before_mic_autodetect   (safe to run twice)"""
import shutil

s = open("audio.py").read()
if "_detect_alsa_device" in s:
    print("already patched")
    raise SystemExit

DETECT = '''def _detect_alsa_device():
    """ECHOMIND_ALSA_DEVICE if set, else the first USB capture card from `arecord -l`."""
    env = os.getenv("ECHOMIND_ALSA_DEVICE", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5).stdout
        cards = re.findall(r"^card (\\d+): ([^\\n]*)", out, flags=re.M)
        usb = [n for n, label in cards if re.search(r"usb|pnp|c-media", label, re.I)]
        pick = usb or [n for n, label in cards if "hdmi" not in label.lower()]
        if pick:
            return f"plughw:{pick[0]},0"
    except Exception:
        pass
    return "plughw:2,0"


'''
CHECK = '''            # Startup level check: says straight away if the mic is silent or clipping.
            try:
                _hp = HighPass()
                _lv = np.concatenate([_hp(reader.read()) for _ in range(4)])
                _rms = float(np.sqrt(np.mean(_lv * _lv)))
                _peak = float(np.abs(_lv).max())
                _verdict = ("SILENT: check the plug, mute and capture volume" if _peak < 150
                            else "TOO LOUD, clipping: run  bash mic_fix.sh 30" if _peak >= 30000
                            else "OK")
                print(f"[mic] level check: rms {_rms:.0f}, peak {_peak:.0f} -> {_verdict}", flush=True)
            except Exception as e:
                print(f"[mic] level check failed: {e}", flush=True)

'''
problems = []
a1 = "class AlsaReader:"
a2 = '''        self.device = os.getenv(
            "ECHOMIND_ALSA_DEVICE",
            "plughw:2,0"
        )
'''
a3 = "            hp = HighPass()\n            seg = Segmenter()\n"
for a in (a1, a2, a3):
    if a not in s:
        problems.append(a.strip()[:50])
if "import re\n" not in s:
    problems.append("import re")
if problems:
    print("PROBLEMS: could not find", problems, "(audio.py differs from the expected version; send me that part)")
    raise SystemExit(1)
shutil.copy("audio.py", "audio.py.before_mic_autodetect")
s = s.replace(a1, DETECT + a1, 1)
s = s.replace(a2, "        self.device = _detect_alsa_device()\n", 1)
s = s.replace(a3, CHECK + a3, 1)
open("audio.py", "w").write(s)
print("Patched. Restart EchoMind and watch for:  [mic] backend=alsa source='plughw:N,0'  and the level check.")
