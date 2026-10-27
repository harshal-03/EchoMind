"""Optional offline voice I/O. Core app works without any of this.
Audio lives only in RAM and is discarded immediately; nothing is written or uploaded.
Set ECHOMIND_MIC=<device index or name part> to force a specific microphone.
"""
import importlib.util
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import deque

import numpy as np

os.environ.setdefault("HF_HUB_OFFLINE", "1")   # at runtime the speech model never touches the network

from config import VOSK_MODEL_DIR

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)
    _VOSK = True
except Exception:
    _VOSK = False

PAREC = shutil.which("parec")
PACTL = shutil.which("pactl")

_WHISPER = importlib.util.find_spec("faster_whisper") is not None
_VOSK_READY = _VOSK and VOSK_MODEL_DIR.exists()

VOICE_AVAILABLE = (_WHISPER or _VOSK_READY) and (sd is not None or bool(PAREC))

ESPEAK = shutil.which("espeak-ng") or shutil.which("espeak")
PAPLAY = shutil.which("paplay")

try:
    import pyttsx3
    _PYTTSX3 = True
except Exception:
    _PYTTSX3 = False

TTS_AVAILABLE = bool(ESPEAK) or _PYTTSX3


def _candidate_devices():
    pref = os.getenv("ECHOMIND_MIC", "").strip()
    devs = sd.query_devices()

    inputs = [
        i for i, d in enumerate(devs)
        if d["max_input_channels"] > 0
    ]

    if pref:
        if pref.isdigit():
            return [int(pref)]

        return [
            i for i in inputs
            if pref.lower() in devs[i]["name"].lower()
        ]

    soft = [
        i for i in inputs
        if any(
            k in devs[i]["name"].lower()
            for k in ("pipewire", "pulse", "default")
        )
    ]

    return soft + [None] + [i for i in inputs if i not in soft]


def open_input():
    """sounddevice fallback: try device / rate / channel combos.
    Returns (stream, rate, ch, name).
    """
    errors = []

    for dev in _candidate_devices():
        try:
            info = sd.query_devices(dev, "input")
        except Exception:
            continue

        for rate in dict.fromkeys([
            int(info["default_samplerate"]),
            16000
        ]):
            for ch in (1, 2):
                if ch > info["max_input_channels"]:
                    continue

                try:
                    s = sd.RawInputStream(
                        samplerate=rate,
                        blocksize=int(rate * 0.25),
                        dtype="int16",
                        channels=ch,
                        device=dev
                    )
                    s.start()
                    return s, rate, ch, info["name"]

                except Exception as e:
                    errors.append(
                        f"{info['name']} @{rate}Hz/{ch}ch: "
                        f"{str(e).splitlines()[0][:60]}"
                    )

    raise RuntimeError(
        "No working microphone. Last errors: "
        + " | ".join(errors[-3:])
    )


def read_16k(stream, rate, ch):
    """Read 0.25 s and return mono 16 kHz int16 samples."""
    data, _ = stream.read(int(rate * 0.25))

    a = np.frombuffer(
        bytes(data),
        dtype=np.int16
    )

    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)

    if rate != 16000:
        from scipy.signal import resample_poly

        divisor = math.gcd(rate, 16000)
        up = 16000 // divisor
        down = rate // divisor

        # Filtered resampling avoids the aliasing of simple interpolation.
        a = resample_poly(
            a.astype(np.float32),
            up,
            down
        )

    return np.clip(
        np.rint(a),
        -32768,
        32767
    ).astype(np.int16)


class SDReader:
    kind = "sounddevice"

    def __init__(self):
        self.stream, self.rate, self.ch, self.name = open_input()

    def read(self):
        return read_16k(
            self.stream,
            self.rate,
            self.ch
        )

    def close(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


def _pick_source():
    """Choose the PipeWire/Pulse capture source:
    ECHOMIND_SOURCE, else a real (non-monitor) USB mic.
    """
    env = os.getenv("ECHOMIND_SOURCE", "").strip()

    if env:
        return env

    if not PACTL:
        return None

    try:
        out = subprocess.run(
            [PACTL, "list", "short", "sources"],
            capture_output=True,
            text=True,
            timeout=5
        ).stdout

        names = [
            ln.split("\t")[1]
            for ln in out.splitlines()
            if "\t" in ln
        ]

    except Exception:
        return None

    real = [
        n for n in names
        if not n.endswith(".monitor")
    ]

    usb = [
        n for n in real
        if "usb" in n.lower()
    ]

    return (usb or real or [None])[0]


class ParecReader:
    """Capture through the sound server: it resamples to a clean
    16 kHz mono stream for us.
    """

    kind = "parec"

    def __init__(self):
        self.name = _pick_source()

        vol = os.getenv(
            "ECHOMIND_MIC_VOLUME",
            ""
        ).strip()

        if vol and PACTL and self.name:
            subprocess.run(
                [
                    PACTL,
                    "set-source-volume",
                    self.name,
                    f"{vol}%"
                ],
                stderr=subprocess.DEVNULL
            )

        cmd = [
            PAREC,
            "--format=s16le",
            "--rate=16000",
            "--channels=1",
            "--latency-msec=100"
        ]

        if self.name:
            cmd += ["-d", self.name]

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

    def read(self):
        buf = b""

        while len(buf) < 8000:
            part = self.proc.stdout.read(
                8000 - len(buf)
            )

            if not part:
                raise RuntimeError(
                    "parec stopped "
                    "(is the USB mic the default input?)"
                )

            buf += part

        return np.frombuffer(
            buf,
            dtype=np.int16
        )

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)

        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _detect_alsa_device():
    """ECHOMIND_ALSA_DEVICE if set, else the first USB capture card from `arecord -l`."""
    env = os.getenv("ECHOMIND_ALSA_DEVICE", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5).stdout
        cards = re.findall(r"^card (\d+): ([^\n]*)", out, flags=re.M)
        usb = [n for n, label in cards if re.search(r"usb|pnp|c-media", label, re.I)]
        pick = usb or [n for n, label in cards if "hdmi" not in label.lower()]
        if pick:
            return f"plughw:{pick[0]},0"
    except Exception:
        pass
    return "plughw:2,0"


class AlsaReader:
    """Capture directly from the USB microphone through ALSA plughw.
    The ALSA plug layer converts the native 44.1/48 kHz microphone
    stream to the exact 16 kHz mono S16 format Vosk expects.
    """

    kind = "alsa"

    def __init__(self):
        self.device = _detect_alsa_device()
        # Keep the same interface expected by EchoMind's
        # existing microphone/status code.
        self.name = self.device

        self.proc = subprocess.Popen(
            [
                "arecord",
                "-q",
                "-D", self.device,
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                "-t", "raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Give arecord a moment to initialize.
        time.sleep(0.2)

        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode(
                errors="replace"
            ).strip()

            raise RuntimeError(
                f"arecord failed for {self.device}: {err}"
            )

    def read(self):
        buf = b""

        while len(buf) < 8000:
            part = self.proc.stdout.read(
                8000 - len(buf)
            )

            if not part:
                err = self.proc.stderr.read().decode(
                    errors="replace"
                ).strip()

                raise RuntimeError(
                    "arecord stopped"
                    + (f": {err}" if err else "")
                )

            buf += part

        return np.frombuffer(
            buf,
            dtype=np.int16
        )

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def open_reader():
    """Best available microphone reader.
    ECHOMIND_MIC_BACKEND = auto | parec | sd.
    """
    backend = os.getenv(
        "ECHOMIND_MIC_BACKEND",
        "auto"
    ).lower()

    errors = []

    if backend in ("auto", "alsa"):
        r = None

        try:
            r = AlsaReader()

            # Proves audio is flowing.
            r.read()

            return r

        except Exception as e:
            errors.append(
                f"alsa: {e}"
            )

            if r:
                r.close()

    if backend in ("auto", "parec") and PAREC:
        r = None

        try:
            r = ParecReader()

            # Proves audio is flowing.
            r.read()

            return r

        except Exception as e:
            errors.append(
                f"parec: {e}"
            )

            if r:
                r.close()

    if backend in ("auto", "sd", "sounddevice") and sd is not None:
        try:
            return SDReader()

        except Exception as e:
            errors.append(
                f"sounddevice: {e}"
            )

    raise RuntimeError(
        "No working microphone. "
        + " | ".join(errors)
    )


PROMPT = (
    "EchoMind. echo, remember that we chose SQLite. "
    "echo, what did we decide about authentication? "
    "echo, add task finish the slides. "
    "echo, remind me in thirty seconds to drink water. "
    "echo, summarize my notes and tasks. "
    "echo, what is the weather in Pune?"
)

_HALLUCINATIONS = {
    "thank you",
    "thanks for watching",
    "you",
    "bye",
    "okay",
    "the",
    "thanks"
}

FRAME = 250                                  # 15.6 ms at 16 kHz


class HighPass:
    """~80 Hz high-pass filter: removes DC offset and low-frequency rumble."""

    def __init__(self, fc=80.0, fs=16000.0):
        self.a = math.exp(
            -2 * math.pi * fc / fs
        )

        self.px = None
        self.py = 0.0

    def __call__(self, chunk):
        x = chunk.astype(
            np.float32
        ).tolist()

        if self.px is None:
            self.px = x[0]

        a, px, py = (
            self.a,
            self.px,
            self.py
        )

        out = [0.0] * len(x)

        for i, v in enumerate(x):
            py = a * (
                py + v - px
            )

            px = v
            out[i] = py

        self.px, self.py = (
            px,
            py
        )

        return np.asarray(
            out,
            dtype=np.float32
        )


class Segmenter:
    """Adaptive energy VAD. Keeps 0.5 s of pre-roll so the first syllable is never lost,
    and ends an utterance after 0.8 s of silence.
    """

    def __init__(self):
        self.min_level = float(
            os.getenv(
                "ECHOMIND_VAD_MIN",
                "220"
            )
        )

        self.floor = None
        self.reset()

    def reset(self):
        self.pre = deque(
            maxlen=32
        )

        self.hot = deque(
            maxlen=6
        )

        self.buf = []
        self.active = False
        self.silence = 0
        self.voiced = 0

    def _finish(self):
        voiced = self.voiced

        trim = max(
            self.silence - 12,
            0
        )

        seg = (
            np.concatenate(
                self.buf[:len(self.buf) - trim]
            )
            if self.buf
            else None
        )

        self.active = False
        self.buf = []
        self.silence = 0
        self.voiced = 0

        return (
            seg
            if (
                seg is not None
                and voiced >= 14
            )
            else None
        )

    def feed(self, frames):
        out = []

        for f in frames:
            rms = (
                float(
                    np.sqrt(
                        np.mean(f * f)
                    )
                )
                + 1e-6
            )

            if self.floor is None:
                self.floor = max(
                    rms,
                    20.0
                )

            start_thr = max(
                self.floor * 2.0,
                self.min_level
            )

            stay_thr = max(
                self.floor * 2.2,
                self.min_level * 0.55
            )

            if not self.active:
                self.pre.append(f)

                self.hot.append(
                    rms > start_thr
                )

                self.floor = (
                    0.9 * self.floor
                    + 0.1 * rms
                    if rms < self.floor
                    else
                    0.998 * self.floor
                    + 0.002 * rms
                )

                if sum(self.hot) >= 4:
                    self.active = True
                    self.buf = list(self.pre)
                    self.silence = 0

                    self.voiced = sum(
                        self.hot
                    )

                    self.pre.clear()
                    self.hot.clear()

            else:
                self.buf.append(f)

                self.silence = (
                    0
                    if rms > stay_thr
                    else self.silence + 1
                )

                self.voiced += (
                    rms > stay_thr
                )

                if (
                    self.silence >= 50
                    or len(self.buf) >= 940
                ):
                    seg = self._finish()

                    if seg is not None:
                        out.append(seg)

        return out

    def flush(self):
        return [
            s
            for s in [
                self._finish()
                if self.active
                else None
            ]
            if s is not None
        ]


def prepare(x):
    """Peak-normalise an utterance and convert to int16 for the speech engine."""
    peak = (
        float(
            np.abs(x).max()
        )
        + 1e-6
    )

    gain = min(
        0.85 * 32767 / peak,
        10.0
    )

    return np.clip(
        x * gain,
        -32768,
        32767
    ).astype(np.int16)


class Transcriber:
    """faster-whisper (best accuracy, fully offline once downloaded) with Vosk as fallback."""

    def __init__(self):
        self.kind = ""
        self._w = None
        self._vosk = None
        self._vad = True

        want = os.getenv(
            "ECHOMIND_STT",
            "auto"
        ).lower()

        if (
            want in ("auto", "whisper")
            and _WHISPER
        ):
            try:
                from faster_whisper import WhisperModel

                name = os.getenv(
                    "ECHOMIND_STT_MODEL",
                    "base.en"
                )

                self._w = WhisperModel(
                    name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4
                )

                self.kind = (
                    f"faster-whisper {name}"
                )

            except Exception as e:
                print(
                    f"[stt] faster-whisper unavailable "
                    f"({str(e)[:90]}). "
                    "Run: python fetch_stt_model.py   "
                    "(falling back to Vosk)",
                    flush=True
                )

        if (
            self._w is None
            and _VOSK_READY
        ):
            self._vosk = Model(
                str(VOSK_MODEL_DIR)
            )

            self.kind = "vosk"

        if (
            self._w is None
            and self._vosk is None
        ):
            raise RuntimeError(
                "No speech-to-text engine available"
            )

    def transcribe(self, pcm):
        if self._w is not None:
            return self._whisper(pcm)

        rec = KaldiRecognizer(
            self._vosk,
            16000
        )

        rec.AcceptWaveform(
            pcm.tobytes()
        )

        return json.loads(
            rec.FinalResult()
        ).get(
            "text",
            ""
        ).strip()

    def _whisper(self, pcm):
        audio_f = (
            pcm.astype(
                np.float32
            )
            / 32768.0
        )

        kw = dict(
            language="en",
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=PROMPT,
            no_speech_threshold=0.6,
            without_timestamps=True
        )

        try:
            segs, _ = self._w.transcribe(
                audio_f,
                vad_filter=self._vad,
                vad_parameters={
                    "min_silence_duration_ms": 400
                },
                **kw
            )

            segs = list(segs)

        except Exception:
            self._vad = False

            segs, _ = self._w.transcribe(
                audio_f,
                **kw
            )

            segs = list(segs)

        text = " ".join(
            s.text.strip()
            for s in segs
            if (
                s.no_speech_prob < 0.6
                and s.avg_logprob > -1.3
            )
        ).strip()

        if (
            re.sub(
                r"[^a-z ]",
                "",
                text.lower()
            ).strip()
            in _HALLUCINATIONS
        ):
            return ""

        return text


class VoiceInput:
    """Continuous listening:
    capture -> filter -> VAD -> speech-to-text -> on_text(text).

    stop() truly closes the microphone (used by Mute).
    Audio is never written or sent anywhere.
    """

    def __init__(self, on_text):
        self.on_text = on_text
        self.paused = False
        self.engine = ""
        self._running = False
        self._gen = 0
        self._stt = None

        # Small queue because we never want old speech/audio
        # accumulating while EchoMind is processing or speaking.
        self._jobs = queue.Queue(
            maxsize=2
        )

    def start(self):
        if (
            self._running
            or not VOICE_AVAILABLE
        ):
            return

        if self._stt is None:
            self._stt = Transcriber()
            self.engine = self._stt.kind

            print(
                f"[stt] engine: {self.engine}",
                flush=True
            )

        self._running = True
        self._gen += 1

        threading.Thread(
            target=self._loop,
            args=(self._gen,),
            daemon=True
        ).start()

        threading.Thread(
            target=self._worker,
            args=(self._gen,),
            daemon=True
        ).start()

    def stop(self):
        self._running = False

        # Discard anything already waiting.
        self._clear_jobs()

    def _clear_jobs(self):
        """Discard audio captured before/while EchoMind is speaking."""
        try:
            while True:
                self._jobs.get_nowait()

        except queue.Empty:
            pass

    def _loop(self, gen):
        reader = None

        debug = (
            os.getenv(
                "ECHOMIND_DEBUG_MIC"
            )
            == "1"
        )

        try:
            reader = open_reader()

            print(
                f"[mic] backend={reader.kind} "
                f"source='{reader.name}'",
                flush=True
            )

            # Startup level check: says straight away if the mic is silent or clipping.
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

            hp = HighPass()
            seg = Segmenter()

            was_paused = False
            ignore_until = 0.0

            while (
                self._running
                and gen == self._gen
            ):
                raw = reader.read()

                # CRITICAL:
                # While EchoMind is thinking/speaking, completely
                # discard microphone audio and reset the VAD.
                if self.paused:
                    seg.reset()
                    was_paused = True
                    continue

                # We just resumed listening.
                # Give the speaker/microphone a short settling period
                # before allowing VAD to detect another command.
                if was_paused:
                    was_paused = False
                    ignore_until = (
                        time.time()
                        + 0.7
                    )

                x = hp(raw)

                if time.time() < ignore_until:
                    seg.reset()
                    continue

                n = (
                    len(x)
                    // FRAME
                    * FRAME
                )

                for utt in seg.feed(
                    x[:n].reshape(
                        -1,
                        FRAME
                    )
                ):
                    if debug:
                        print(
                            f"[vad] utterance "
                            f"{len(utt) / 16000:.1f}s, "
                            f"noise floor "
                            f"{seg.floor:.0f}",
                            flush=True
                        )

                    try:
                        self._jobs.put_nowait(
                            utt
                        )

                    except queue.Full:
                        print(
                            "[vad] busy, utterance dropped",
                            flush=True
                        )

        except Exception as e:
            print(
                f"[mic] ERROR: {e}",
                flush=True
            )

        finally:
            if gen == self._gen:
                self._running = False

            if reader is not None:
                reader.close()

    def _worker(self, gen):
        """Process recognized speech without queuing stale microphone audio."""
        debug = os.getenv("ECHOMIND_DEBUG_MIC") == "1"

        while self._running and gen == self._gen:
            try:
                utt = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._running or gen != self._gen or self.paused:
                continue

            t0 = time.time()

            try:
                text = self._stt.transcribe(prepare(utt))
            except Exception as e:
                print(f"[stt] ERROR: {e}", flush=True)
                continue

            if debug:
                print(
                    f"[stt] '{text}' ({time.time() - t0:.1f}s)",
                    flush=True
                )

            if not text:
                continue

            # Pause immediately after recognizing a command.
            # This prevents the microphone from collecting the
            # next/stale utterance while pi_main is responding.
            self.paused = True

            # Discard anything captured immediately before recognition.
            self._clear_jobs()

            try:
                self.on_text(text)
            except Exception as e:
                print(f"[audio] on_text error: {e}", flush=True)


def _speak_pipe(text):
    """espeak-ng -> paplay.
    Follows the default PipeWire/Pulse output
    (e.g. Bluetooth speaker).
    """

    if not (
        ESPEAK
        and PAPLAY
    ):
        return False

    try:
        p1 = subprocess.Popen(
            [
                ESPEAK,
                "-s",
                "160",
                "--stdout",
                text
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        p2 = subprocess.run(
            [PAPLAY],
            stdin=p1.stdout,
            stderr=subprocess.DEVNULL,
            timeout=60
        )

        p1.stdout.close()
        p1.wait(timeout=5)

        return (
            p1.returncode == 0
            and p2.returncode == 0
        )

    except Exception:
        return False


def speak(text):
    """Speak offline.
    Returns 'paplay', 'pyttsx3' (unverified fallback) or None.
    """

    if _speak_pipe(text):
        return "paplay"

    if _PYTTSX3:
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()

            return "pyttsx3"

        except Exception:
            pass

    return None

