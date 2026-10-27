"""Optional fixes for the calendar feature in the OLD code. Run once inside the project folder:
    python apply_calendar_fixes.py
Safe to run twice: it skips anything already applied. Backups are saved as *.before_calendar_fix"""
import shutil

changes = {
 "tools.py": [
  ("from google_calendar import create_calendar_event\n", ""),
 ],
 "config.py": [
  (None, '\n# Optional Google Calendar sync (title and time only, needs online mode). 0 = keep reminders local.\n'
         'ALLOW_CALENDAR = os.getenv("ECHOMIND_CALENDAR", "1") == "1"\n'),
 ],
 "orchestrator.py": [
  ("from config import ALLOW_FACT_LOOKUP, DB_PATH, FOLLOWUP_SECONDS, WAKE_VARIANTS",
   "from config import ALLOW_CALENDAR, ALLOW_FACT_LOOKUP, DB_PATH, FOLLOWUP_SECONDS, WAKE_VARIANTS"),
  ('        if name == "create_calendar_event":\n',
   '        if name == "create_calendar_event":\n            if not ALLOW_CALENDAR:\n'
   '                self.log("audit", "Calendar sync is switched off")\n'
   '                return "Calendar sync is switched off. I keep reminders on this device."\n'),
  ('f"Creating Google Calendar event: {title}"',
   'f"Creating Google Calendar event: {title} (title and time only, no audio)"'),
  ('"en.wikipedia.org": "Wikipedia"}', '"en.wikipedia.org": "Wikipedia", "www.googleapis.com": "Google Calendar"}'),
  ('"each carrying only a city or a few keywords")',
   '"each carrying only a city, a few keywords or an event title and time")'),
 ],
 "google_calendar.py": [
  ("import os\n", "import os\n\nimport netlog\n"),
  ("def create_calendar_event(title, start_iso, end_iso, description=None):\n",
   'def create_calendar_event(title, start_iso, end_iso, description=None):\n'
   '    netlog.record("www.googleapis.com", "external")   # counted in the privacy report\n'),
 ],
 "intents.py": [
  ('    """Return a tool decision for productivity commands, or None."""\n',
   '    """Return a tool decision for productivity commands, or None."""\n'
   '    t = re.sub(r"(?i)\\b([ap])\\.?\\s?m\\b\\.?", r"\\1m", t)   # "5 p.m." -> "5 pm"\n'),
  ("            end = start + timedelta(minutes=15)\n",
   '            if start <= datetime.now(CALENDAR_TZ):\n'
   '                return {"reply": "That time has already passed. Try tomorrow or a later time."}\n\n'
   "            end = start + timedelta(minutes=15)\n"),
 ],
}

problems = []
for path, edits in changes.items():
    s = open(path).read()
    original = s
    for old, new in edits:
        if old is None:                                   # append block
            if "ALLOW_CALENDAR" not in s:
                s += new
            continue
        if old not in s:
            if new == "" or new in s:
                continue                                  # already applied
            problems.append(f"{path}: could not find: {old[:50]!r}")
            continue
        if new and new in s and old in new:
            continue                                      # already applied (old text is part of new)
        s = s.replace(old, new, 1)
    if s != original:
        shutil.copy(path, path + ".before_calendar_fix")
        open(path, "w").write(s)
        print("patched", path)
    else:
        print("no change", path)
print("PROBLEMS:" if problems else "All calendar fixes applied. Restart EchoMind.")
for p in problems:
    print(" -", p)
