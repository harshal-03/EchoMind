"""EchoMind configuration. Everything runs locally except the weather lookup."""
import os
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

DB_PATH = DATA / "echomind.db"

# Local LLM (Ollama) - bound to localhost only, nothing leaves the machine
OLLAMA_BASE = "http://127.0.0.1:11434"
MODEL = os.getenv("ECHOMIND_MODEL", "llama3.2:3b")   # or "phi3:mini"

WAKE_WORD = "echo"
WAKE_VARIANTS = ["echo", "eco", "ecko"]   # speech-to-text often mishears "echo"

# Online use is limited to real-time factual lookups (weather, Wikipedia search). Set
# ECHOMIND_FACTS=0 to allow weather only.
ALLOW_FACT_LOOKUP = os.getenv("ECHOMIND_FACTS", "1") == "1"   # PS4 allows weather, search and news lookups
FOLLOWUP_SECONDS = float(os.getenv("ECHOMIND_FOLLOWUP", "10"))  # no wake word needed right after "echo"

# The ONLY hosts the orchestrator may ever contact (weather only)
ONLINE_ALLOWLIST = {"geocoding-api.open-meteo.com", "api.open-meteo.com", "en.wikipedia.org", "api.github.com"}

# Optional offline speech recognition model (Vosk)
VOSK_MODEL_DIR = Path(os.getenv("ECHOMIND_VOSK", str(BASE / "models" / "vosk-model-small-en-us-0.15")))

# ---- Raspberry Pi GPIO (BCM numbering) -------------------------------------
# "push" = momentary push buttons (press toggles) | "toggle" = real on/off switches
SWITCH_MODE = os.getenv("ECHOMIND_SWITCH_MODE", "push")
PIN_LISTEN_SWITCH = 17   # toggle switch to GND. CLOSED = listening, OPEN = muted (fail-safe)
PIN_ONLINE_SWITCH = 24   # toggle switch to GND. CLOSED = weather allowed, OPEN = fully offline
PIN_PTT_BUTTON = 23      # momentary button to GND (push-to-talk: skips wake word while held)
PIN_LED_LISTEN = 27      # green LED + 330 ohm resistor
PIN_LED_MUTED = 22       # red LED + 330 ohm resistor. Set to None if you only have ONE LED

# Optional Google Calendar sync (title and time only, needs online mode). 0 = keep reminders local.
ALLOW_CALENDAR = os.getenv("ECHOMIND_CALENDAR", "1") == "1"
