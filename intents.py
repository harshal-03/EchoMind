"""Plain-language command parsing for tasks, reminders and summaries.
Runs locally; spoken numbers ("thirty", "two") are converted because the speech model
returns words, not digits."""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19, "a": 1, "an": 1}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
CALENDAR_TZ = ZoneInfo("Asia/Kolkata")


def _parse_calendar_datetime(day_text, time_text):
    """Convert a day + clock time into an Asia/Kolkata datetime."""

    now = datetime.now(CALENDAR_TZ)
    day = day_text.lower().strip()

    if day == "today":
        target = now
    elif day == "tomorrow":
        target = now + timedelta(days=1)
    else:
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        if day not in weekdays:
            return None

        days_ahead = (weekdays[day] - now.weekday()) % 7

        if days_ahead == 0:
            days_ahead = 7

        target = now + timedelta(days=days_ahead)

    match = re.match(
        r"(?i)^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*$",
        time_text.strip()
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3).lower()

    if hour < 1 or hour > 12:
        return None

    if ampm == "am":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12

    return target.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

def words_to_int(text):
    t = text.lower().replace("-", " ").strip()
    if t.isdigit():
        return int(t)
    total, seen = 0, False
    for w in t.split():
        if w in _TENS:
            total += _TENS[w]
            seen = True
        elif w in _UNITS:
            total += _UNITS[w]
            seen = True
        elif w != "and":
            return None
    return total if seen else None


_N = r"(?P<n>\d+|[a-z]+(?:[ -][a-z]+)?)"
_U = r"(?P<u>second|minute|hour)s?"
CALENDAR_REMINDER = re.compile(
    r"(?i)^\s*"
    r"(?:please\s+)?"
    r"remind me\s+"
    r"(?:on\s+)?"
    r"(?P<day>today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\s+(?:at|for)\s+"
    r"(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))"
    r"\s+(?:to\s+|that\s+|about\s+)?"
    r"(?P<what>.+?)"
    r"\s*$"
)
CALENDAR_SCHEDULE = re.compile(
    r"(?i)^\s*"
    r"(?:please\s+)?"
    r"(?:schedule|calendar|add to my calendar|create a calendar event)"
    r"\s+(?P<what>.+?)"
    r"\s+(?:on\s+)?"
    r"(?P<day>today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\s+at\s+"
    r"(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))"
    r"\s*$"
)
REM_C = re.compile(rf"(?i)\b(?:set|create|start)\s+(?:a\s+)?(?:reminder|timer|alarm)\s+(?:for|in)\s+{_N}\s+{_U}\b[,]?\s*(?:to\s+|that\s+|about\s+)?(?P<what>.*)$")
REM_B = re.compile(rf"(?i)\bremind me in\s+{_N}\s+{_U}\b[,]?\s*(?:to\s+|that\s+|about\s+)?(?P<what>.+)$")
REM_A = re.compile(rf"(?i)\bremind me\s+(?:to\s+|that\s+|about\s+)?(?P<what>.+?)\s+in\s+{_N}\s+{_U}\s*$")
ADD_TASK = [re.compile(r"(?i)^\s*(?:add|create|new)\s+(?:a\s+)?(?:task|to[- ]?do)\b[:,]?\s*(?:to\s+)?(?P<t>.+)$"),
            re.compile(r"(?i)^\s*add\s+(?P<t>.+?)\s+to\s+(?:my\s+)?(?:task|to[- ]?do)s?(?:\s+list)?\s*$")]
LIST_TASKS = re.compile(r"(?i)\b(what are my tasks|my tasks|list (?:my |the )?tasks|to[- ]?do list|"
                        r"what do i have to do|what'?s on my list|open tasks)\b")
DONE_TASK = [
    # Generic completion request: resolve safely in the orchestrator.
    re.compile(r"(?i)^\s*(?:mark|set)\s+(?:my\s+)?task\s+as\s+(?:done|complete|completed|finished)[?.!]*\s*(?P<r>)$"),
    re.compile(r"(?i)^\s*mark\s+(?:my\s+)?(?:task\s+)?(?P<r>.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)\s*$"),
    re.compile(r"(?i)^\s*(?:complete|finish|close)\s+(?:my\s+)?task\s+(?P<r>.+?)\s*$"),
    re.compile(r"(?i)^\s*task\s+(?P<r>.+?)\s+(?:is\s+)?(?:done|complete|completed|finished)\s*$"),
    re.compile(r"(?i)^\s*(?:mark|set)\s+(?:my\s+)?task\s+as\s+(?:done|complete|completed|finished)\s*$"),
    re.compile(r"(?i)^\s*i(?:'ve| have)\s+(?:finished|completed)\s+(?:the\s+)?(?P<r>.+?)\s*$"),
]
SUMMARY = re.compile(r"(?i)\b(summar(?:y|ise|ize)|catch me up|recap|brief me)\b")


def _clean(what):
    what = what.strip(" ?.,!")
    return re.sub(r"(?i)\bmy\b", "your", what)

DOCS_STATUS = re.compile(r"(?i)\b(?:reload|refresh|re-?index|update)\s+(?:my\s+|the\s+|our\s+)?(?:documents?|docs|files|pdfs?)\b|\b(?:what|which|list|show)\b.{0,30}\b(?:documents?|docs|files|pdfs?)\b.{0,30}\b(?:do you have|have you|are loaded|are indexed|loaded|indexed)\b|\blist\s+(?:my\s+|the\s+|our\s+)?(?:documents?|docs|files|pdfs?)\b")
DOCS_ASK = re.compile(r"(?i)\b(?:search|check|look(?:\s+up)?|find|ask|read|consult)\b.{0,25}?\b(?:documents?|docs|files|pdfs?|handbook|project\s+guide|policy|policies)\b|\b(?:according\s+to|from|in|per|using)\s+(?:the\s+|my\s+|our\s+)?(?:project\s+|team\s+|company\s+|uploaded\s+)?(?:documents?|docs|files|pdfs?|handbook|guide|policy|policies|holiday\s+calendar|timeline)\b|\b(?:leave|holiday|travel|expense|hr)\s+polic(?:y|ies)\b|\b(?:team\s+handbook|project\s+guide|holiday\s+calendar|project\s+timeline|project\s+documents?)\b")


def route_docs(t):
    """Questions about the user's own documents (RAG)."""
    if DOCS_STATUS.search(t):
        return {"tool": "docs_status", "args": {"action": "reload" if re.search(r"(?i)reload|refresh|re-?index|update", t) else "list"}}
    if DOCS_ASK.search(t):
        return {"tool": "search_docs", "args": {"query": t}}
    return None


def route(t):
    """Return a tool decision for productivity commands, or None."""
    docs_hit = route_docs(t)
    if docs_hit:
        return docs_hit
    t = re.sub(r"(?i)\b([ap])\.?\s?m\b\.?", r"\1m", t)   # "5 p.m." -> "5 pm"

    # Google Calendar reminders.
    for rx in (CALENDAR_REMINDER, CALENDAR_SCHEDULE):
        m = rx.match(t)

        if m:
            start = _parse_calendar_datetime(
                m.group("day"),
                m.group("time")
            )

            if start is None:
                return {
                    "reply": "I couldn't understand that date or time."
                }

            if start <= datetime.now(CALENDAR_TZ):
                return {"reply": "That time has already passed. Try tomorrow or a later time."}

            end = start + timedelta(minutes=15)

            return {
                "tool": "create_calendar_event",
                "args": {
                    "title": _clean(m.group("what")),
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }
            }

    # Existing relative reminders.
    for rx in (REM_C, REM_B, REM_A):
        m = rx.search(t)

        if m:
            n = words_to_int(m.group("n"))
            unit = {
                "second": 1,
                "minute": 60,
                "hour": 3600
            }[m.group("u").lower()]

            if n is None or not 1 <= n * unit <= 86400:
                return {
                    "reply": (
                        "How long should I wait? Try: "
                        "remind me in two minutes to drink water."
                    )
                }

            return {
                "tool": "set_reminder",
                "args": {
                    "seconds": n * unit,
                    "what": _clean(m.group("what"))
                }
            }

    # Tasks.
    for rx in ADD_TASK:
        m = rx.match(t)

        if m:
            return {
                "tool": "add_task",
                "args": {
                    "text": m.group("t").strip(" .")
                }
            }

    if LIST_TASKS.search(t):
        return {
            "tool": "list_tasks",
            "args": {}
        }

    for rx in DONE_TASK:
        m = rx.match(t)

        if m:
            return {
                "tool": "complete_task",
                "args": {
                    "ref": m.group("r").strip(" .")
                }
            }

    # Upcoming Google Calendar meetings
    if re.search(
        r"(?i)\b(upcoming|future|next)\b.*\b(meetings?|events?|appointments?)\b"
        r"|\b(meetings?|events?|appointments?)\b.*\b(upcoming|future)\b",
        t
    ):
        return {"tool": "list_upcoming_events", "args": {}}

    # Summaries of notes and tasks
    if SUMMARY.search(t):
        return {
            "tool": "summarize",
            "args": {}
        }

    return None
