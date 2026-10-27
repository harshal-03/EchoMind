"""Seed demo notes:  python seed_demo.py   (add --reset to wipe first)"""
import sys
from config import DB_PATH
from memory_store import MemoryStore

NOTES = [
    "We decided to use JWT tokens with refresh rotation for authentication.",
    "The demo rehearsal is on Friday at 6 pm in the seminar hall.",
    "We decided to use SQLite instead of Postgres because the device is offline.",
    "Team lunch order is veg biryani and paneer wraps.",
    "Mute switch must be wired before anything else, Rahul owns the hardware.",
]

if __name__ == "__main__":
    mem = MemoryStore(DB_PATH)
    if "--reset" in sys.argv:
        mem.clear()
    if mem.count() == 0:
        for n in NOTES:
            mem.add(n)
        print(f"Seeded {len(NOTES)} notes.")
    else:
        print("Notes already exist (use --reset to re-seed).")
