"""Fix: recall answers that quote the timestamp instead of the fact.
Run once inside the project folder:  python apply_recall_fix.py"""
import re
import shutil

NEW_COMPOSE = '''    @staticmethod
    def _grounded(answer, texts):
        """Reject answers that quote timestamps or invent numbers/facts not in the notes."""
        low = answer.lower()
        if re.search(r"\\d{4}-\\d{2}-\\d{2}", answer):
            return False
        if "no note" in low or "don't have" in low or "do not have" in low:
            return True
        body = " ".join(texts).lower()
        for num in re.findall(r"\\d[\\d,.]*", answer):
            if num.strip(".,") and num.strip(".,") not in body:
                return False
        words = {w for w in re.findall(r"[a-z]{4,}", body)}
        return any(w in low for w in words)

    def compose(self, question, notes):
        """Turn retrieved notes (newest first) into a short spoken answer, never inventing details."""
        if not notes:
            return "I don't have a note about that yet."
        texts = [t for _, t in notes]
        fallback = "Here's what I have: " + texts[0]
        if not self.available():
            return fallback
        ctx = "\\n".join(f"- {t}" for t in texts)
        try:
            ans = self._chat([
                {"role": "system", "content": "Answer from the notes only. The first note is the newest; "
                                              "if notes disagree, trust the first. Reply in one short "
                                              "sentence that restates the fact with its exact numbers. "
                                              "If the notes do not answer the question, say you have no "
                                              "note about it."},
                {"role": "user", "content": f"Notes:\\n{ctx}\\n\\nQuestion: {question}"}]).strip()
        except Exception:
            return fallback
        return ans if self._grounded(ans, texts) else fallback

'''

s = open("llm.py").read()
a = s.index("    def compose(self, question, notes):")
b = s.index("    def summarize(self, notes, tasks):")
shutil.copy("llm.py", "llm.py.before_recall_fix")
open("llm.py", "w").write(s[:a] + NEW_COMPOSE + s[b:])

m = open("memory_store.py").read()
old = "                    [f\"%{t}%\" for t in tokens] + [limit]).fetchall()\n        return rows\n"
assert old in m, "memory_store.py search() not in the expected shape"
shutil.copy("memory_store.py", "memory_store.py.before_recall_fix")
open("memory_store.py", "w").write(m.replace(
    old, old.replace("        return rows\n", "        return sorted(rows, key=lambda r: r[0], reverse=True)   # newest first\n")))
print("Recall fix applied. Restart EchoMind.")
