"""ONE-TIME download of the speech model (needs internet). After this, EchoMind never
touches the network for speech:   python fetch_stt_model.py
Choose size with ECHOMIND_STT_MODEL=tiny.en (fastest) or base.en (default, more accurate)."""
import os

os.environ.pop("HF_HUB_OFFLINE", None)
from faster_whisper import WhisperModel

name = os.getenv("ECHOMIND_STT_MODEL", "base.en")
print(f"Downloading speech model '{name}' (about 75-150 MB)...")
WhisperModel(name, device="cpu", compute_type="int8")
print("Done. Speech recognition now runs fully offline.")
