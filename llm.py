"""Local SLM via Ollama (127.0.0.1 only) + deterministic guardrail router.
A 1B model is unreliable at picking tools (it once saved questions as notes), so clear
commands are routed by rules; the local model handles open-ended requests and writes
every recall answer."""
import json
import re
import urllib.request

import intents
import netlog
from config import ALLOW_FACT_LOOKUP, MODEL, OLLAMA_BASE

# Bypass any system proxy: this must only ever talk to localhost
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

SYSTEM = """You are EchoMind, a private offline desk companion. Reply with ONE JSON object only.
Choose exactly one:
{"tool":"search_notes","args":{"query":"<3-6 keywords incl. synonyms>"}}
{"tool":"get_weather","args":{"city":"<city name>"}}
{"tool":"web_lookup","args":{"query":"<2-5 keyword search>"}}
{"reply":"<short answer>"}
Rules: questions about past decisions, plans or notes use search_notes. get_weather is only for
weather. Never save notes yourself. For stock prices or predictions, or anything you cannot
know offline, use reply and say you are not sure offline."""

REMEMBER = re.compile(
    r"(?i)^\s*(?:please\s+)?(?:remember|note|save|make a note|don'?t forget)\b"
    r"(?:\s+(?:that|this|down))?[:,]?\s+(.+)$")
PRIVACY = re.compile(r"(?i)(privacy (report|check|status|audit)|what (have|did) you (send|sent|upload)"
                     r"|did you (send|upload)|anything (go|went) online|are you (recording|spying))")
WEATHER = re.compile(r"(?i)weather\s+(?:like\s+)?(?:in|at|for)\s+([A-Za-z .-]+)")
GENERAL = re.compile(r"(?i)\b(who is|who was|capital of|population of|how many|how tall|how far)\b")
PERSONAL = re.compile(r"(?i)\b(we|our|us|my|notes?|decided|decide|chose|choose|picked|remind|recall)\b")
QUESTION = re.compile(r"(?i)^\s*(what|when|where|who|which|why|how|did|do|does|is|are|was|were|can|could)\b|\?\s*$")


def rules_route(text):
    """Deterministic router: clear commands/questions, plus the offline fallback."""
    t = text.strip()
    if PRIVACY.search(t):
        return {"tool": "privacy_report", "args": {}}
    hit = intents.route(t)
    if hit:
        return hit
    m = REMEMBER.match(t)
    if m:
        return {"tool": "remember_note", "args": {"text": m.group(1).strip()}}
    m = WEATHER.search(t)
    if m:
        return {"tool": "get_weather", "args": {"city": m.group(1).strip(" ?.")}}
    if ALLOW_FACT_LOOKUP and GENERAL.search(t) and not PERSONAL.search(t):
        return {"tool": "web_lookup", "args": {"query": t.rstrip("?. ")}}
    if PERSONAL.search(t) or QUESTION.search(t):
        return {"tool": "search_notes", "args": {"query": t}}
    return {"reply": "I'm not sure offline. I can save notes, recall them, or check the weather."}


class LocalLLM:
    def available(self):
        try:
            _opener.open(f"{OLLAMA_BASE}/api/tags", timeout=1.5)
            return True
        except Exception:
            return False

    def _chat(self, messages, json_mode=False):
        payload = {"model": MODEL, "messages": messages, "stream": False,
                   "options": {"temperature": 0.1, "num_ctx": 2048}, "keep_alive": "24h"}
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/chat",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        netlog.record("127.0.0.1", "local")
        with _opener.open(req, timeout=120) as r:
            return json.load(r)["message"]["content"]

    def warmup(self):
        """Load the model into RAM at boot so the first answer isn't slow."""
        try:
            self._chat([{"role": "user", "content": "hi"}])
        except Exception:
            pass

    def decide(self, text):
        """Returns (decision_dict, engine_name)."""
        rule = rules_route(text)
        if "tool" in rule:                          # clear case: guardrails decide
            return rule, "rules (guardrail)"
        if not self.available():
            return rule, "rules (Ollama not running)"
        try:
            raw = self._chat([{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": text}], json_mode=True)
            d = json.loads(raw)
            tool = d.get("tool")
            if tool == "remember_note":             # never save without an explicit command
                d = {"reply": "To save something, say: echo, remember that ..."}
            elif tool == "get_weather" and "weather" not in text.lower():
                d = rule
            if "tool" in d or "reply" in d:
                d.setdefault("args", {})
                return d, f"local LLM ({MODEL})"
        except Exception:
            pass
        return rule, "rules (LLM output invalid)"

    @staticmethod
    def _grounded(answer, texts):
        """Reject answers that quote timestamps or invent numbers/facts not in the notes."""
        low = answer.lower()
        if re.search(r"\d{4}-\d{2}-\d{2}", answer):
            return False
        if "no note" in low or "don't have" in low or "do not have" in low:
            return True
        body = " ".join(texts).lower()
        for num in re.findall(r"\d[\d,.]*", answer):
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
        ctx = "\n".join(f"- {t}" for t in texts)
        try:
            ans = self._chat([
                {"role": "system", "content": "Answer from the notes only. The first note is the newest; "
                                              "if notes disagree, trust the first. Reply in one short "
                                              "sentence that restates the fact with its exact numbers. "
                                              "If the notes do not answer the question, say you have no "
                                              "note about it."},
                {"role": "user", "content": f"Notes:\n{ctx}\n\nQuestion: {question}"}]).strip()
        except Exception:
            return fallback
        return ans if self._grounded(ans, texts) else fallback

    def summarize(self, notes, tasks):
        """Local-model reasoning over everything stored on the device."""
        if not notes and not tasks:
            return "There's nothing to summarize yet."
        if not self.available():
            latest = notes[0][1] if notes else "no notes"
            return f"You have {len(notes)} recent notes and {len(tasks)} open task{'s' if len(tasks) != 1 else ''}. Latest note: {latest}"
        ctx = "Notes:\n" + "\n".join(f"- {t}" for _, t in notes) + \
              "\nOpen tasks:\n" + "\n".join(f"- {t}" for _, t in tasks)
        try:
            return self._chat([
                {"role": "system", "content": "Summarize the user's notes and tasks in 2-3 short spoken "
                                              "sentences. Use ONLY the items given."},
                {"role": "user", "content": ctx}]).strip()
        except Exception:
            return f"You have {len(notes)} recent notes and {len(tasks)} open tasks."
