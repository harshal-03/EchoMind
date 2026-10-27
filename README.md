# EchoMind

**A privacy-first, offline AI voice assistant for Raspberry Pi 5.**

EchoMind runs a local language model (via [Ollama](https://ollama.com)) to remember notes, manage tasks, answer questions from your documents, check the weather, and more — all without sending your voice, notes, or conversations to the cloud.

## Features

- **Voice interaction** — continuous wake-word ("echo") listening with push-to-talk option
- **Local memory** — save and recall notes using SQLite full-text search
- **Task management** — add, list, and complete tasks by voice
- **Timed reminders** — "remind me in 5 minutes to drink water"
- **Document Q&A (RAG)** — drop PDFs into `documents/` and ask questions about them
- **Weather lookups** — current weather via Open-Meteo (only a city name leaves the device)
- **Wikipedia search** — factual lookups with only keywords sent online
- **Google Calendar** — create and list events (optional, needs OAuth setup)
- **Email digest & GitHub overview** — optional, read-only integrations
- **Privacy audit** — every network call is logged; ask "what have you sent online?"
- **Hardware GPIO** — physical mute switch, online toggle, push-to-talk button, LEDs on Raspberry Pi 5
- **Desktop GUI** — Tkinter interface with virtual LED, privacy panel, and chat window

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Entry Points                       │
│  main.py (GUI/CLI)  │  pi_main.py (headless Pi)     │
└────────┬────────────┴────────────┬──────────────────┘
         │                         │
         ▼                         ▼
┌─────────────────────────────────────────────────────┐
│              orchestrator.py                         │
│  Wake word → Intent routing → Tool execution → LLM  │
└──┬──────┬──────┬──────┬──────┬──────┬───────────────┘
   │      │      │      │      │      │
   ▼      ▼      ▼      ▼      ▼      ▼
 llm.py  intents memory  tools  rag.py  google_
 (Ollama) .py   _store   .py   (docs)  calendar
                 .py                    .py
```

| Module | Role |
|---|---|
| `config.py` | Central configuration, env vars, GPIO pin assignments |
| `main.py` | Desktop launcher: `python main.py` (GUI) or `python main.py --cli` |
| `pi_main.py` | Headless Pi launcher with hardware, voice I/O, LEDs |
| `orchestrator.py` | State machine: mute → wake word → LLM → allowlisted tool → answer |
| `llm.py` | Local LLM via Ollama with deterministic guardrail router |
| `intents.py` | Regex command parser for tasks, reminders, calendar, docs |
| `memory_store.py` | SQLite + FTS5 for notes and tasks (never leaves the device) |
| `tools.py` | Allowlisted actions: weather, Wikipedia lookup |
| `rag.py` | Local document Q&A (PDF/text → SQLite FTS5 → LLM answer) |
| `audio.py` | Speech-to-text (Vosk / faster-whisper), TTS (espeak-ng / pyttsx3), VAD |
| `hardware.py` | GPIO layer (real on Pi, mock on laptop) |
| `gui.py` | Tkinter desktop UI with privacy audit panel |
| `google_calendar.py` | Google Calendar integration (OAuth2) |
| `extras.py` | Optional email digest and GitHub overview |
| `netlog.py` | Proof-of-privacy: counts and logs every network call |

## Supported Platforms

| Platform | Voice | GUI | GPIO | Notes |
|---|---|---|---|---|
| **Raspberry Pi 5** (primary) | ✅ | ❌ | ✅ | Use `pi_main.py`; needs USB mic + speaker |
| **Linux laptop/desktop** | ✅ | ✅ | mock | Full experience with `main.py` |
| **Windows** | partial | ✅ | mock | GUI + typed input work; voice depends on drivers |
| **macOS** | partial | ✅ | mock | Similar to Windows |

## Quick Start (Laptop / Desktop)

### Prerequisites

- **Python 3.9+** with `tkinter` (included on most systems)
- **Ollama** — <https://ollama.com/download>

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd echomind
```

### 2. Pull the local language model

```bash
ollama pull llama3.2:3b
```

### 3. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### 4. Seed demo notes (optional)

```bash
python seed_demo.py
```

### 5. Run EchoMind

```bash
# Desktop GUI (default)
python main.py

# Terminal REPL
python main.py --cli
```

### 6. Try it out

```
echo, remember that we chose Flask for the dashboard
echo, what did we decide about the dashboard?
echo, what is the weather in Bengaluru?       (enable "Allow online" first)
echo, add task finish the slides
echo, what are my tasks?
echo, remind me in thirty seconds to drink water
echo, summarize my notes and tasks
```

## Voice Setup (Optional)

EchoMind supports two offline speech-to-text engines:

### Option A: Vosk (lightweight, good for Pi)

```bash
pip install vosk sounddevice pyttsx3
```

Download [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models) and unzip into `models/`:

```
models/
└── vosk-model-small-en-us-0.15/
    ├── conf/
    ├── graph/
    └── ...
```

### Option B: faster-whisper (best accuracy)

```bash
pip install faster-whisper pyttsx3
python fetch_stt_model.py
```

This downloads the model once (~75-150 MB). After that, speech recognition runs fully offline.

## Raspberry Pi 5 Setup

See [HARDWARE.md](HARDWARE.md) for GPIO wiring (LEDs, switches, push-to-talk) and [PI-DEPLOY.md](PI-DEPLOY.md) for deploying the LLM on the Pi.

```bash
# On the Pi
sudo apt update
sudo apt install -y python3-venv python3-gpiozero python3-lgpio libportaudio2 espeak-ng
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install vosk sounddevice pyttsx3
curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.2:3b

python hw_test.py         # verify GPIO wiring
python seed_demo.py       # seed demo notes
python pi_main.py         # run the assistant
```

Run the self-test to check everything:

```bash
python pi_selftest.py
```

## Document Q&A (RAG)

Drop PDF, text, or Markdown files into the `documents/` folder. EchoMind indexes them automatically using SQLite FTS5.

```
echo, what does the project guide say about the tech stack?
echo, list the holidays in January 2026
echo, reload my documents
```

## Google Calendar Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/), create a project, enable the Google Calendar API.
2. Create an OAuth 2.0 Client ID (Desktop application) and download `credentials.json`.
3. Place `credentials.json` in the project root (it is gitignored).
4. On first use, EchoMind will open a browser for OAuth consent and save `token.json` locally.

```
echo, schedule team standup tomorrow at 10 am
echo, what are my upcoming meetings?
```

> **Note:** Never commit `credentials.json` or `token.json` to Git.

## Email & GitHub (Optional)

Set environment variables (see `.env.example`) to enable read-only integrations:

- **Email digest:** `ECHOMIND_MAIL=1` + IMAP credentials (app password for Gmail)
- **GitHub overview:** `ECHOMIND_GITHUB=1` + GitHub username + read-only PAT

## Environment Variables

Copy `.env.example` to `.env` and edit as needed. All variables are optional — EchoMind works with sensible defaults.

Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `ECHOMIND_MODEL` | `llama3.2:3b` | Ollama model name |
| `ECHOMIND_STT` | `auto` | Speech engine: `auto`, `whisper`, `vosk` |
| `ECHOMIND_CALENDAR` | `1` | Enable Google Calendar |
| `ECHOMIND_SWITCH_MODE` | `push` | GPIO: `push` (momentary) or `toggle` |

See `.env.example` for the full list.

## Running Tests

```bash
# Pi readiness and routing self-test
python pi_selftest.py

# GPIO hardware test (Pi only)
python hw_test.py

# Microphone diagnostics
python mic_probe.py
python mic_test.py

# Google Calendar integration test (needs credentials.json)
python google_calendar_test.py
```

## Troubleshooting

| Problem | Solution |
|---|---|
| "Ollama not running" | Start Ollama: `ollama serve` (or `sudo systemctl start ollama` on Pi) |
| "No speech-to-text engine" | Install Vosk or faster-whisper (see Voice Setup above) |
| Mic too quiet / clipping | Run `python mic_level.py` to check; `bash mic_fix.sh 50` to adjust |
| Wrong microphone selected | Set `ECHOMIND_MIC=<name>` or `ECHOMIND_ALSA_DEVICE=plughw:N,0` |
| GPIO permission denied | Run with `sudo` or add your user to the `gpio` group |
| Calendar auth fails | Delete `token.json` and re-authenticate |
| Weather refuses | Enable online mode (toggle switch on Pi, or checkbox in GUI) |
| LLM too slow on Pi | Use `llama3.2:1b` instead: `ECHOMIND_MODEL=llama3.2:1b` |

## Project Structure

```
echomind/
├── main.py                 # Desktop launcher (GUI / CLI)
├── pi_main.py              # Headless Pi launcher
├── orchestrator.py         # Central state machine
├── llm.py                  # Local LLM (Ollama)
├── intents.py              # Command parser
├── memory_store.py         # Notes & tasks (SQLite)
├── rag.py                  # Document Q&A
├── tools.py                # Weather & Wikipedia
├── audio.py                # Speech I/O
├── hardware.py             # GPIO / mock
├── gui.py                  # Desktop UI
├── google_calendar.py      # Calendar integration
├── extras.py               # Email & GitHub
├── netlog.py               # Privacy audit
├── config.py               # Configuration
├── seed_demo.py            # Demo note seeder
├── fetch_stt_model.py      # Speech model downloader
├── pi_selftest.py          # Pi readiness test
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── documents/              # Drop PDFs here for RAG
├── HARDWARE.md             # GPIO wiring guide
├── PI-DEPLOY.md            # Pi deployment guide
└── DEMO-SCRIPT.md          # 4-minute demo script
```

## License

This project was developed as part of a makethon / hackathon. See the team for licensing details.
