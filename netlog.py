"""Proof-of-privacy counters: every network call in the app is recorded here."""
import threading
import time

_lock = threading.Lock()
EVENTS = []   # (timestamp, host, scope) scope = "external" | "local"


def record(host, scope):
    with _lock:
        EVENTS.append((time.strftime("%H:%M:%S"), host, scope))


def count(scope):
    with _lock:
        return sum(1 for e in EVENTS if e[2] == scope)


def external_hosts():
    with _lock:
        return sorted({e[1] for e in EVENTS if e[2] == "external"})
