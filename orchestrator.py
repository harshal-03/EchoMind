"""State machine: mute -> wake word -> LLM decision -> allowlisted tool -> answer."""
import re
import threading
import time

import netlog
from config import ALLOW_CALENDAR, ALLOW_FACT_LOOKUP, DB_PATH, FOLLOWUP_SECONDS, WAKE_VARIANTS
from llm import PERSONAL, LocalLLM
from memory_store import STOP, MemoryStore
from tools import ALLOWED_TOOLS, get_weather, web_lookup
from intents import route_docs as _route_docs

PREDICTION = re.compile(
    r"(?i)\b(stock|share price|bitcoin|crypto|nifty|sensex|lottery)\b")


def _keywords(text):
    """Only a few keywords ever leave the device, never the full sentence."""
    toks = [
    t for t in re.findall(
        r"[a-z0-9']+",
         text.lower()) if t not in STOP and len(t) > 2]
    return " ".join(toks[:6])


class Orchestrator:
    def __init__(self, log=lambda kind, msg: print(kind, msg)):
        self.log = log
        self.mem = MemoryStore(DB_PATH)
        self.llm = LocalLLM()
        self.muted = False
        self.online = False          # weather lookups blocked until enabled
        self.require_wake = True
        # follow-up window: no wake word needed shortly after "echo"
        self.awake_until = 0.0
        self.on_alert = None         # set by the UI to speak reminders

    # ---- hardware-switch equivalents -------------------------------------
    def set_muted(self, value):
        self.muted = value
        self.awake_until = 0.0
        self.log("audit", "MUTE ON: mic closed, nothing is processed" if value
                 else "MUTE OFF: listening again")

    def set_online(self, value):
        self.online = value
        self.log("audit", "ONLINE allowed: allowlisted lookups only (weather, facts)" if value
                 else "OFFLINE: all network access blocked")

    # ---- main entry -------------------------------------------------------
    def touch(self):
        """Keep the follow-up window open (called after a reply has been spoken)."""
        if FOLLOWUP_SECONDS and not self.muted:
            self.awake_until = time.time() + FOLLOWUP_SECONDS

    def handle(self, text, force_wake=False):
        reply = self._handle(text, force_wake)
        if reply is not None:
            self.touch()
        return reply

    def _handle(self, text, force_wake=False):
        if self.muted:
            self.log("audit", "Input ignored (muted)")
            return None

        text = text.strip()

        if self.require_wake and not force_wake:
            m = re.match(
                rf"(?i)^(?:(?:hey|hi|ok|okay)[\s,]+)?"
                rf"(?:{'|'.join(WAKE_VARIANTS)})"
                rf"\b[\s,:.!-]*(.*)$",
                text,
            )

            if m:
                text = m.group(1).strip()
                self.log("audit", "Wake word detected")
                self.touch()
            elif time.time() < self.awake_until:
                self.log(
                    "audit",
                    "Follow-up window open: no wake word needed"
                )
            else:
                self.log(
                    "audit",
                    "No wake word -> utterance discarded"
                )
                return None

        if not text:
            return "I'm listening."

        if PREDICTION.search(text):
            self.log(
                "audit",
                "Refused: prediction request (honest degradation)"
            )
            return (
                "I can't predict markets offline, and I wouldn't guess. "
                "Want me to save that as a note instead?"
            )

        extras_reply = None if _route_docs(text) else self._try_extras(text)
        if extras_reply is not None:
            return extras_reply

        decision, engine = self.llm.decide(text)
        self.log("audit", f"Reasoning engine: {engine}")

        if "reply" in decision and "tool" not in decision:
            return decision["reply"]

        name = decision.get("tool")
        args = decision.get("args", {})

        if name not in ALLOWED_TOOLS:
            self.log(
                "audit",
                f"BLOCKED tool not on allowlist: {name}"
            )
            return (
                "I can't do that. I only save notes, recall them, "
                "and check weather."
            )

        self.log("audit", f"Tool allowed: {name}")

        if name == "remember_note":
            self.mem.add(args.get("text", text))
            self.log(
                "audit",
                "Saved to local SQLite (no audio stored)"
            )
            return "Got it, I've saved that."

        if name == "search_notes":
            query = args.get("query", text)
            notes = self.mem.search(query) or self.mem.search(text)

            self.log(
                "audit",
                f"Local FTS search -> {len(notes)} match(es)"
            )

            if not notes:
                docs_reply = self._docs_answer(text, strict=True)
                if docs_reply is not None:
                    return docs_reply

            if (
                not notes
                and ALLOW_FACT_LOOKUP
                and not PERSONAL.search(text)
            ):
                self.log(
                    "audit",
                    "No local answer and not a personal question -> "
                    "may go online"
                )
                return self._lookup_online(
                    text,
                    _keywords(text)
                )

            return self.llm.compose(text, notes)

        if name == "web_lookup":
            if not ALLOW_FACT_LOOKUP:
                self.log(
                    "audit",
                    "Fact lookup disabled: weather is the only online use"
                )
                return (
                    "I don't know that offline. "
                    "I only go online for the weather."
                )

            return self._lookup_online(
                text,
                _keywords(args.get("query") or text)
            )

        if name == "add_task":
            self.mem.add_task(args.get("text", text))
            self.log(
                "audit",
                "Task saved to local SQLite"
            )
            return "Added to your tasks."

        if name == "list_tasks":
            tasks = self.mem.open_tasks()

            if not tasks:
                return "You have no open tasks."

            items = ". ".join(
                f"{i}, {t}"
                for i, (_, t) in enumerate(tasks, 1)
            )

            return (
                f"You have {len(tasks)} open task"
                f"{'s' if len(tasks) != 1 else ''}. "
                f"{items}."
            )

        if name == "complete_task":
            ref = args.get("ref", "").strip(" .?!")

            # Generic requests must never guess when multiple tasks are open.
            if not ref or ref.lower() in {"as", "my task", "task"}:
                tasks = self.mem.open_tasks()

                if not tasks:
                    return "You have no open tasks to complete."

                if len(tasks) > 1:
                    choices = ". ".join(
                        f"{i}, {task_text}"
                        for i, (_, task_text) in enumerate(tasks, 1)
                    )
                    return (
                        f"You have {len(tasks)} open tasks. "
                        f"Which one should I mark done? {choices}."
                    )

                ref = "1"

            done = self.mem.complete_task(ref)

            return (
                f"Marked done: {done}."
                if done
                else "I couldn't find that task. "
                     "Ask me what your tasks are."
            )

        if name == "set_reminder":
            secs = int(args.get("seconds", 0))
            what = args.get("what", "")

            t = threading.Timer(
                secs,
                self._fire_reminder,
                args=(what,)
            )
            t.daemon = True
            t.start()

            self.log(
                "audit",
                f"Reminder scheduled locally in {secs}s (no network)"
            )

            if secs % 3600 == 0:
                span = (
                    f"{secs // 3600} hour"
                    f"{'s' if secs // 3600 != 1 else ''}"
                )
            elif secs % 60 == 0:
                span = (
                    f"{secs // 60} minute"
                    f"{'s' if secs // 60 != 1 else ''}"
                )
            else:
                span = (
                    f"{secs} second"
                    f"{'s' if secs != 1 else ''}"
                )

            return (
                f"Okay, I'll remind you in {span}"
                + (f" to {what}." if what else ".")
            )

        if name == "create_calendar_event":
            if not ALLOW_CALENDAR:
                self.log("audit", "Calendar sync is switched off")
                return "Calendar sync is switched off. I keep reminders on this device."
            if not self.online:
                self.log(
                    "audit",
                    "Calendar BLOCKED (offline mode)"
                )
                return (
                    "Google Calendar needs internet. "
                    "Switch online mode on and ask again."
                )

            title = args.get("title", "").strip()
            start = args.get("start", "").strip()
            end = args.get("end", "").strip()

            if not title or not start or not end:
                self.log(
                    "audit",
                    "Calendar event rejected: missing arguments"
                )
                return "I need the event title, date, and time."

            self.log(
                "audit",
                f"Creating Google Calendar event: {title} (title and time only, no audio)"
            )

            try:
                from google_calendar import create_calendar_event

                create_calendar_event(
                    title=title,
                    start_iso=start,
                    end_iso=end,
                    description="Created by EchoMind",
                )

                self.log(
                    "audit",
                    "Google Calendar event created successfully"
                )

                return (
                    f"Done. I've added {title} "
                    "to your Google Calendar."
                )

            except Exception as e:
                self.log(
                    "audit",
                    f"Google Calendar failed: {e}"
                )
                return (
                    "I couldn't create the Google Calendar event "
                    "right now."
                )

        if name == "list_upcoming_events":
            if not ALLOW_CALENDAR:
                return "Google Calendar sync is switched off."
            if not self.online:
                return (
                    "Google Calendar needs internet. "
                    "Switch online mode on and ask again."
                )

            self.log("audit", "Reading upcoming events from Google Calendar")
            try:
                from google_calendar import list_upcoming_events

                events = list_upcoming_events()
                if not events:
                    return "You have no upcoming events on your Google Calendar."

                lines = [
                    f"{i}. {event['title']} — {event['when']}"
                    for i, event in enumerate(events, 1)
                ]
                return "Here are your upcoming Google Calendar events. " + ". ".join(lines)

            except Exception as e:
                self.log("audit", f"Google Calendar event lookup failed: {e}")
                return "I couldn't read your Google Calendar right now."

        if name == "summarize":
            self.log(
                "audit",
                "Summarizing notes and tasks with the on-device model"
            )
            return self.llm.summarize(
                self.mem.recent_notes(8),
                self.mem.open_tasks()
            )

        if name == "search_docs":
            return self._docs_answer(args.get("query") or text)

        if name == "docs_status":
            return self._docs_status(args.get("action", "list"))

        if name == "privacy_report":
            self.log(
                "audit",
                "Self-audit: reporting network activity "
                "from the local counters"
            )
            return self._privacy_report()

        if name == "get_weather":
            if not self.online:
                self.log(
                    "audit",
                    "Network BLOCKED (offline mode)"
                )
                return (
                    "Weather needs internet and online mode is off. "
                    "Switch it on and ask again."
                )

            city = args.get("city", "").strip() or "Mumbai"

            self.log(
                "audit",
                "HTTP GET api.open-meteo.com "
                "(city name only, no audio)"
            )

            try:
                return get_weather(city)
            except Exception as e:
                self.log(
                    "audit",
                    f"Weather failed: {e}"
                )
                return (
                    "I couldn't reach the weather service right now."
                )

    # --- extras hook: email + GitHub, runs BEFORE the LLM ---
    _EXTRAS_EMAIL = re.compile(r"(?i)\b(e-?mails?|inbox|gmail|unread)\b")
    _EXTRAS_GITHUB = re.compile(
        r"(?i)\bgit ?hub\b|\b(repos?|repositor(?:y|ies)|commits?|pull requests?)\b|\bissues? in\b")

    def _docs_answer(self, question, strict=False):
        """Answer from the local documents. strict=True returns None when nothing relevant is found."""
        try:
            import rag
            if strict and not rag.has_docs():
                return None
            self.log("audit", "Searching your local documents (no network)")
            return rag.ask(question, self.llm, strict=strict)
        except Exception as e:
            self.log("audit", f"Document search failed: {e}")
            return None if strict else "I couldn't search your documents right now."

    def _docs_status(self, action):
        try:
            import rag
            self.log("audit", "Reading the local documents folder (no network)")
            return rag.status(reindex=(action == "reload"))
        except Exception as e:
            self.log("audit", f"Document status failed: {e}")
            return "I couldn't read your documents folder right now."

    def _try_extras(self, text):
        import os
        import subprocess
        import sys
        if re.match(r"(?i)^\s*(remember|note|save)\b", text):
            return None
        is_mail = bool(self._EXTRAS_EMAIL.search(text))
        is_git = bool(self._EXTRAS_GITHUB.search(text))
        if not (is_mail or is_git):
            return None
        import intents
        r = intents.route(text)
        if r and ("reply" in r or r.get("tool") in
                  {"add_task", "complete_task", "set_reminder", "create_calendar_event"}):
            return None            # tasks, reminders and calendar keep priority
        name = "mail_digest" if is_mail else "github_overview"
        if name not in ALLOWED_TOOLS:
            self.log("audit", f"BLOCKED tool not on allowlist: {name}")
            return "I can't do that."
        if not self.online:
            self.log("audit", f"{name} BLOCKED (offline mode)")
            return "That needs internet and online mode is off. Switch it on and ask again."
        host = "imap.gmail.com" if is_mail else "api.github.com"
        self.log("audit", f"Tool allowed: {name} -> read-only request to {host} "
                          "(no audio; content stays on this device)")
        netlog.record(host, "external")
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            proc = subprocess.run([sys.executable, os.path.join(here, "extras.py"), text],
                                  capture_output=True, text=True, timeout=60, cwd=here)
        except Exception as e:
            self.log("audit", f"{name} failed: {e}")
            return "I couldn't reach that service right now."
        lines = [ln.strip() for ln in proc.stdout.splitlines()
                 if ln.strip() and not ln.startswith("route:")]
        out = " ".join(lines).strip()
        if not out:
            self.log("audit", f"{name} returned nothing: {proc.stderr[-200:]}")
            return "I couldn't get that right now."
        return out[:500]

    def _lookup_online(self, question, query):
        if not self.online:
            self.log("audit", "Network BLOCKED (offline mode)")
            return "I don't know that offline, and online mode is off."
        self.log("audit", f"Going online: sending ONLY keywords '{query}' to en.wikipedia.org "
                          "(no audio, no notes, no transcript)")
        try:
            info = web_lookup(query)
        except Exception as e:
            self.log("audit", f"Online lookup failed: {e}")
            return "I couldn't reach the internet, and I don't know that offline."
        if not info:
            return "I couldn't find anything about that."
        return self.llm.compose(question, [("web", info)])

    def _privacy_report(self):
        names = {"api.open-meteo.com": "the weather service", "geocoding-api.open-meteo.com": "the weather service",
                 "en.wikipedia.org": "Wikipedia", "www.googleapis.com": "Google Calendar",
                 "api.github.com": "GitHub", "imap.gmail.com": "Gmail"}
        who = sorted({names.get(h, h) for h in netlog.external_hosts()})
        n = netlog.count("external")
        sent = (f"{n} online request{'s' if n != 1 else ''} to {' and '.join(who)}, "
                "each carrying only a city, a few keywords or an event title and time") if n else "no online requests at all"
        return (f"I'm {'muted' if self.muted else 'listening'} and online mode is "
                f"{'on' if self.online else 'off'}. This session I made {sent}. "
                f"No audio has been uploaded or stored, and I keep {self.mem.count()} notes on this device.")

    def _fire_reminder(self, what):
        msg = f"Reminder: {what}." if what else "Time's up."
        self.log("audit", "Reminder fired (local timer)")
        if self.on_alert:
            self.on_alert(msg)
