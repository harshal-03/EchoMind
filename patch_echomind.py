#!/usr/bin/env python3
import os, py_compile, shutil, sys

D = os.path.expanduser("~/echomind/echomind")


def patch(fname, marker, edits):
    path = os.path.join(D, fname)
    src = open(path, encoding="utf-8").read()
    if marker in src:
        print(f"{fname}: already patched, skipping")
        return
    for old, new in edits:
        if src.count(old) != 1:
            sys.exit(f"{fname}: anchor not found exactly once:\n{old}\nNothing was changed.")
        src = src.replace(old, new)
    shutil.copy(path, path + ".bak")
    open(path, "w", encoding="utf-8").write(src)
    py_compile.compile(path, doraise=True)
    print(f"{fname}: patched (backup: {fname}.bak)")


# ---- config.py: allow the GitHub API host ----
patch("config.py", "api.github.com", [(
    '"en.wikipedia.org"}',
    '"en.wikipedia.org", "api.github.com"}',
)])

# ---- tools.py: register the new tools ----
patch("tools.py", '"github_repo"', [(
    '"create_calendar_event", "list_upcoming_events"}',
    '"create_calendar_event", "list_upcoming_events",\n'
    '                 "mail_digest", "github_overview", "github_repo"}',
)])

# ---- orchestrator.py ----
HOOK_CALL = '''        extras_reply = self._try_extras(text)
        if extras_reply is not None:
            return extras_reply

        decision, engine = self.llm.decide(text)'''

METHODS = '''    # --- extras hook: email + GitHub, runs BEFORE the LLM ---
    _EXTRAS_EMAIL = re.compile(r"(?i)\\b(e-?mails?|inbox|gmail|unread)\\b")
    _EXTRAS_GITHUB = re.compile(
        r"(?i)\\bgit ?hub\\b|\\b(repos?|repositor(?:y|ies)|commits?|pull requests?)\\b|\\bissues? in\\b")

    def _try_extras(self, text):
        import os
        import subprocess
        import sys
        if re.match(r"(?i)^\\s*(remember|note|save)\\b", text):
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

    def _lookup_online(self, question, query):'''

patch("orchestrator.py", "_try_extras", [
    ("        decision, engine = self.llm.decide(text)", HOOK_CALL),
    ("    def _lookup_online(self, question, query):", METHODS),
    ('"www.googleapis.com": "Google Calendar"}',
     '"www.googleapis.com": "Google Calendar",\n'
     '                 "api.github.com": "GitHub", "imap.gmail.com": "Gmail"}'),
])
print("Done.")
