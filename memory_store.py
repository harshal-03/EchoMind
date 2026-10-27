"""SQLite + FTS5 memory. Notes never leave the device."""
import re
import sqlite3
import threading
from datetime import datetime

from intents import words_to_int

STOP = {"the", "what", "did", "we", "about", "when", "where", "who", "which", "was",
        "were", "and", "for", "are", "you", "can", "tell", "me", "our", "have", "has",
        "that", "this", "with", "remind", "recall", "does", "do", "how", "any", "from"}


class MemoryStore:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, ts TEXT, text TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, ts TEXT, text TEXT, done INTEGER DEFAULT 0)")
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(text, tokenize='porter')")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        self.conn.commit()

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    def add(self, text):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO notes(ts, text) VALUES (?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M"), text.strip()))
            if self.fts:
                self.conn.execute("INSERT INTO notes_fts(rowid, text) VALUES (?, ?)",
                                  (cur.lastrowid, text.strip()))
            self.conn.commit()
            return cur.lastrowid

    def search(self, query, limit=3):
        tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower())
                  if t not in STOP and len(t) > 2]
        if not tokens:
            return []
        with self.lock:
            if self.fts:
                match = " OR ".join(f'"{t}"' for t in tokens)
                rows = self.conn.execute(
                    "SELECT n.ts, n.text FROM notes_fts f JOIN notes n ON n.id = f.rowid "
                    "WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?", (match, limit)).fetchall()
            else:
                like = " OR ".join(["text LIKE ?"] * len(tokens))
                rows = self.conn.execute(
                    f"SELECT ts, text FROM notes WHERE {like} ORDER BY id DESC LIMIT ?",
                    [f"%{t}%" for t in tokens] + [limit]).fetchall()
        return sorted(rows, key=lambda r: r[0], reverse=True)   # newest first

    def clear(self):
        with self.lock:
            self.conn.execute("DELETE FROM tasks")
            self.conn.execute("DELETE FROM notes")
            if self.fts:
                self.conn.execute("DELETE FROM notes_fts")
            self.conn.commit()

    # ---- productivity: tasks ----
    def add_task(self, text):
        with self.lock:
            self.conn.execute("INSERT INTO tasks(ts, text) VALUES (?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), text.strip()))
            self.conn.commit()

    def open_tasks(self):
        with self.lock:
            return self.conn.execute("SELECT id, text FROM tasks WHERE done = 0 ORDER BY id").fetchall()

    def complete_task(self, ref):
        tasks = self.open_tasks()
        chosen = None
        n = words_to_int(ref)
        if n and 1 <= n <= len(tasks):
            chosen = tasks[n - 1]
        else:
            toks = [t for t in re.findall(r"[a-z0-9]+", ref.lower()) if t not in STOP and len(t) > 2]
            scored = [(sum(t in task[1].lower() for t in toks), task) for task in tasks]
            scored = [s for s in scored if s[0] > 0]
            if toks and scored:
                chosen = max(scored, key=lambda s: s[0])[1]
        if not chosen:
            return None
        with self.lock:
            self.conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (chosen[0],))
            self.conn.commit()
        return chosen[1]

    def recent_notes(self, n=8):
        with self.lock:
            return self.conn.execute("SELECT ts, text FROM notes ORDER BY id DESC LIMIT ?", (n,)).fetchall()
