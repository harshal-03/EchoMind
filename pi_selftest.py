"""Raspberry Pi health + readiness test.   python pi_selftest.py   (add --stress for a 2-min heat test)
Also runs on a laptop: Pi-only checks are skipped."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from config import MODEL, OLLAMA_BASE, VOSK_MODEL_DIR

RESULTS = []
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def report(status, name, detail=""):
    RESULTS.append(status)
    print(f"[{status:4}] {name}" + (f" - {detail}" if detail else ""))


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def temp_c():
    out = sh("vcgencmd measure_temp")           # temp=48.7'C
    try:
        return float(out.split("=")[1].split("'")[0])
    except Exception:
        return None


def throttled():
    out = sh("vcgencmd get_throttled")          # throttled=0x0
    try:
        return int(out.split("=")[1], 16)
    except Exception:
        return None


def check_board():
    model = ""
    try:
        model = open("/proc/device-tree/model").read().strip("\x00\n ")
    except Exception:
        pass
    mem_gb = None
    try:
        kb = int([l for l in open("/proc/meminfo") if l.startswith("MemTotal")][0].split()[1])
        mem_gb = kb / 1024 / 1024
    except Exception:
        pass
    report("PASS" if "Raspberry Pi 5" in model else "SKIP", "Board", model or "not a Raspberry Pi")
    if mem_gb:
        report("PASS" if mem_gb >= 3.5 else "WARN", "RAM", f"{mem_gb:.1f} GB (4 GB Pi: use llama3.2:1b)")
    free = shutil.disk_usage("/").free / 1e9
    report("PASS" if free >= 6 else "WARN", "Free disk", f"{free:.1f} GB")
    t, th = temp_c(), throttled()
    if t is not None:
        report("PASS" if t < 70 else "WARN", "Idle temperature", f"{t:.1f} C")
    if th is not None:
        report("PASS" if th == 0 else "WARN", "Power/throttle flags",
               "clean" if th == 0 else f"0x{th:x} (under-voltage/throttling seen: check 27W PSU + cooler)")


def check_stt():
    import importlib.util
    have_w = importlib.util.find_spec("faster_whisper") is not None
    have_v = importlib.util.find_spec("vosk") is not None and VOSK_MODEL_DIR.exists()
    report("PASS" if have_w else "WARN", "faster-whisper (best accuracy)",
           "installed" if have_w else "missing: pip install faster-whisper, then python fetch_stt_model.py")
    report("PASS" if have_v else "WARN", "Vosk (fallback engine)", "ready" if have_v else "not set up")
    if not (have_w or have_v):
        report("FAIL", "Speech-to-text", "no engine available")
        return
    try:
        import audio
        t0 = time.time()
        tr = audio.Transcriber()
        report("PASS", "Speech model loads", f"{tr.kind} in {time.time() - t0:.1f}s")
    except Exception as e:
        report("FAIL", "Speech model loads", str(e)[:150])


def check_python():
    for mod, need in [("gpiozero", "GPIO")]:
        try:
            __import__(mod)
            report("PASS", f"Python module {mod}", need)
        except Exception:
            report("FAIL", f"Python module {mod}", f"missing ({need})")
    try:
        import sqlite3
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        report("PASS", "SQLite FTS5 search")
    except Exception as e:
        report("FAIL", "SQLite FTS5 search", str(e))
    check_stt()


def check_internet():
    try:
        socket.create_connection(("api.open-meteo.com", 443), 4).close()
        report("PASS", "Internet (for weather/facts)")
    except Exception:
        report("WARN", "Internet", "offline - fine for local demo, needed for weather/facts")


def ollama_json(path, payload=None, timeout=180):
    req = urllib.request.Request(OLLAMA_BASE + path, data=json.dumps(payload).encode() if payload else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(_opener.open(req, timeout=timeout))


def check_llm():
    try:
        names = [m["name"] for m in ollama_json("/api/tags", timeout=3)["models"]]
    except Exception:
        report("FAIL", "Ollama running", "start it: sudo systemctl start ollama")
        return False
    report("PASS", "Ollama running", ", ".join(names) or "no models")
    if not any(n.startswith(MODEL.split(":")[0]) and MODEL in n for n in names):
        report("FAIL", f"Model {MODEL} installed", f"run: ollama pull {MODEL}")
        return False
    report("PASS", f"Model {MODEL} installed")
    return True


def llm_speed(runs=1):
    best = None
    for _ in range(runs):
        t0 = time.time()
        r = ollama_json("/api/generate", {"model": MODEL, "stream": False, "keep_alive": "24h",
                                          "prompt": "Explain in two sentences why offline AI protects privacy.",
                                          "options": {"num_predict": 60, "num_ctx": 2048}})
        wall = time.time() - t0
        tps = r.get("eval_count", 0) / max(r.get("eval_duration", 1) / 1e9, 0.001)
        best = (tps, wall)
    tps, wall = best
    status = "PASS" if tps >= 4 else "WARN" if tps >= 2 else "FAIL"
    report(status, "LLM speed", f"{tps:.1f} tokens/s, {wall:.1f}s for a short answer")


def check_routing():
    from llm import LocalLLM
    llm = LocalLLM()
    from config import ALLOW_FACT_LOOKUP
    cases = [("what did we decide about authentication?", "search_notes"),
             ("when is the demo rehearsal?", "search_notes"),
             ("when did we pick sqlite?", "search_notes"),
             ("what's the weather in Bengaluru?", "get_weather"),
             ("remember that we chose Flask", "remember_note"),
             ("note that the demo is on Friday", "remember_note"),
             ("what have you sent online?", "privacy_report"),
             ("add task finish the slides", "add_task"),
             ("what are my tasks", "list_tasks"),
             ("remind me in thirty seconds to drink water", "set_reminder"),
             ("summarize my notes", "summarize")]
    if ALLOW_FACT_LOOKUP:
        cases.append(("what is the capital of France?", "web_lookup"))
    ok = 0
    for text, want in cases:
        d, engine = llm.decide(text)
        got = d.get("tool", "reply")
        good = got == want
        ok += good
        print(f"        {'ok ' if good else 'BAD'} '{text}' -> {got} via {engine}")
    report("PASS" if ok == len(cases) else "WARN", "Tool routing", f"{ok}/{len(cases)} correct "
           "(guardrail rules route commands; the local model handles open-ended requests)")


def check_audio():
    try:
        import numpy as np
        import audio
        reader = audio.open_reader()
        print(f"        mic: {reader.name} via {reader.kind}")
        print("        Recording 3 s - SPEAK NOW...")
        chunks = [reader.read() for _ in range(12)]
        reader.close()
        rms = float(np.sqrt(np.mean(np.concatenate(chunks).astype("float32") ** 2)))
        peak = float(np.abs(np.concatenate(chunks)).max())
        if rms > 12000 or peak >= 32000:
            report("WARN", "Microphone level", f"RMS {rms:.0f}, peak {peak:.0f}: too loud/clipping "
                   "-> lower capture volume (alsamixer -c 2, then F4)")
        elif rms < 150:
            report("WARN", "Microphone level", f"RMS {rms:.0f}: too quiet (wrong device? try mic_probe.py)")
        else:
            report("PASS", "Microphone level", f"RMS {rms:.0f}, peak {peak:.0f}")
    except Exception as e:
        report("FAIL", "Microphone test", str(e)[:200] + "  -> run: python mic_probe.py")
    try:
        import audio
        print("        Speaker test - you should hear a voice...")
        how = audio.speak("EchoMind speaker test. If you can hear this, audio output works.")
        if how == "paplay":
            report("PASS", "Speaker output", "played through the default sound output (did you hear it?)")
        elif how == "pyttsx3":
            report("WARN", "Speaker output", "fallback voice used, cannot verify. Run: "
                   "sudo apt install -y pulseaudio-utils espeak-ng")
        else:
            report("FAIL", "Speaker output", "no sound path. Check the Bluetooth connection and wpctl status")
    except Exception as e:
        report("FAIL", "Speaker test", str(e))


def stress():
    print("\nHeat test: 2 minutes of continuous LLM load. Watch the fan.")
    peak, flags, end = 0, 0, time.time() + 120
    while time.time() < end:
        ollama_json("/api/generate", {"model": MODEL, "stream": False,
                                      "prompt": "Write a short paragraph about edge computing.",
                                      "options": {"num_predict": 80, "num_ctx": 2048}})
        t, th = temp_c(), throttled()
        peak = max(peak, t or 0)
        flags |= th or 0
        print(f"        temp {t} C, throttle flags 0x{(th or 0):x}")
    report("PASS" if peak < 80 and flags & 0xF == 0 else "WARN", "Heat test",
           f"peak {peak:.1f} C, flags 0x{flags:x} (low bits = under-voltage/throttled/freq-capped now)")


if __name__ == "__main__":
    print("== EchoMind Raspberry Pi self-test ==")
    check_board()
    check_python()
    check_internet()
    if check_llm():
        llm_speed()
        check_routing()
    check_audio()
    if "--stress" in sys.argv:
        stress()
    print(f"\nSummary: {RESULTS.count('PASS')} pass, {RESULTS.count('WARN')} warn, "
          f"{RESULTS.count('FAIL')} fail, {RESULTS.count('SKIP')} skipped")
    print("GPIO wiring is tested separately:  python hw_test.py")
