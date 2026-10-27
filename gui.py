"""Tkinter desktop UI: virtual LED + mute switch + online toggle + privacy audit log."""
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

import audio
import netlog
from orchestrator import Orchestrator

BG, PANEL, FG = "#0f172a", "#1e293b", "#e2e8f0"
GREEN, AMBER, GREY = "#22c55e", "#f59e0b", "#475569"


class App:
    def __init__(self):
        self.q = queue.Queue()
        self.orch = Orchestrator(log=lambda k, m: self.q.put((k, m)))
        self.orch.on_alert = self.on_alert
        self.voice = audio.VoiceInput(self.on_voice) if audio.VOICE_AVAILABLE else None

        self.root = tk.Tk()
        self.root.title("EchoMind - offline desk companion")
        self.root.geometry("980x640")
        self.root.configure(bg=BG)
        self._build()
        self.set_state("listening")
        self.root.after(100, self.poll)

    # ---------- layout ----------
    def _build(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=14, pady=10)
        self.led = tk.Canvas(top, width=34, height=34, bg=BG, highlightthickness=0)
        self.led_dot = self.led.create_oval(3, 3, 31, 31, fill=GREEN, outline="")
        self.led.pack(side="left")
        self.status = tk.Label(top, text="LISTENING", fg=FG, bg=BG, font=("Segoe UI", 14, "bold"))
        self.status.pack(side="left", padx=10)

        self.mute_btn = tk.Button(top, text="MUTE (mic off)", command=self.toggle_mute,
                                  bg="#b91c1c", fg="white", font=("Segoe UI", 11, "bold"), padx=12)
        self.mute_btn.pack(side="right")

        self.online_var = tk.BooleanVar(value=False)
        self.wake_var = tk.BooleanVar(value=True)
        self.mic_var = tk.BooleanVar(value=False)
        opts = tk.Frame(self.root, bg=BG)
        opts.pack(fill="x", padx=14)
        for text, var, cmd, state in [
            ("Allow online (weather only)", self.online_var, self.on_online, "normal"),
            ("Require wake word 'echo'", self.wake_var, self.on_wake, "normal"),
            ("Use microphone (Vosk)" if self.voice else "Microphone: Vosk not installed",
             self.mic_var, self.refresh_mic, "normal" if self.voice else "disabled")]:
            tk.Checkbutton(opts, text=text, variable=var, command=cmd, state=state, bg=BG, fg=FG,
                           selectcolor=PANEL, activebackground=BG, activeforeground=FG
                           ).pack(side="left", padx=8)

        self.net = tk.Label(self.root, text="", fg="#a3e635", bg="#020617", anchor="w",
                            font=("Consolas", 11, "bold"), padx=10, pady=6)
        self.net.pack(fill="x", padx=14, pady=(8, 0))
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(left, text="Conversation", fg=FG, bg=BG).pack(anchor="w")
        self.chat = scrolledtext.ScrolledText(left, bg=PANEL, fg=FG, wrap="word",
                                              font=("Segoe UI", 11), state="disabled")
        self.chat.pack(fill="both", expand=True)
        self.chat.tag_config("user", foreground="#93c5fd")
        self.chat.tag_config("bot", foreground="#86efac")

        tk.Label(right, text="Privacy / audit log (what the device is doing)", fg=FG, bg=BG).pack(anchor="w")
        self.audit = scrolledtext.ScrolledText(right, bg="#020617", fg="#a3e635", wrap="word",
                                               font=("Consolas", 10), state="disabled")
        self.audit.pack(fill="both", expand=True)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=14, pady=(0, 12))
        self.entry = tk.Entry(bottom, font=("Segoe UI", 12), bg=PANEL, fg=FG, insertbackground=FG)
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", lambda e: self.on_send())
        self.entry.focus()
        tk.Button(bottom, text="Send", command=self.on_send, padx=14).pack(side="left", padx=6)
        tk.Button(bottom, text="Push-to-talk (no wake word)", command=self.on_ptt).pack(side="left")
        self.add("bot", "Hi! Say or type: 'echo, remember that ...' or 'echo, what did we decide about ...?'")

    # ---------- helpers ----------
    def _append(self, widget, text, tag=None):
        widget.config(state="normal")
        widget.insert("end", text + "\n", tag)
        widget.see("end")
        widget.config(state="disabled")

    def add(self, who, text):
        label = {"user": "You", "bot": "Echo"}[who]
        self._append(self.chat, f"{label}: {text}\n", who)

    def set_state(self, state):
        colour, text = {"listening": (GREEN, "LISTENING"), "thinking": (AMBER, "THINKING"),
                        "muted": (GREY, "MUTED - mic closed")}[state]
        self.led.itemconfig(self.led_dot, fill=colour)
        self.status.config(text=text)

    # ---------- controls ----------
    def toggle_mute(self):
        muted = not self.orch.muted
        self.orch.set_muted(muted)
        self.set_state("muted" if muted else "listening")
        self.mute_btn.config(text="UNMUTE" if muted else "MUTE (mic off)",
                             bg="#15803d" if muted else "#b91c1c")
        self.refresh_mic()

    def on_online(self):
        self.orch.set_online(self.online_var.get())

    def on_wake(self):
        self.orch.require_wake = self.wake_var.get()

    def refresh_mic(self):
        if not self.voice:
            return
        if self.mic_var.get() and not self.orch.muted:
            self.voice.start()
            self.q.put(("audit", "Mic stream OPEN (audio stays in RAM, discarded after STT)"))
        else:
            self.voice.stop()
            self.q.put(("audit", "Mic stream CLOSED"))

    def on_send(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.submit(text)

    def on_ptt(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.submit(text, force_wake=True)

    def on_alert(self, text):
        self.q.put(("bot", text))
        if audio.TTS_AVAILABLE:
            threading.Thread(target=audio.speak, args=(text,), daemon=True).start()

    def on_voice(self, text):
        self.submit(text, shown=f"(voice) {text}")

    def submit(self, text, force_wake=False, shown=None):
        self.q.put(("user", shown or text))
        threading.Thread(target=self._work, args=(text, force_wake), daemon=True).start()

    def _work(self, text, force_wake):
        if self.voice:
            self.voice.paused = True
        if not self.orch.muted:
            self.q.put(("state", "thinking"))
        reply = self.orch.handle(text, force_wake=force_wake)
        self.q.put(("state", "muted" if self.orch.muted else "listening"))
        if reply:
            self.q.put(("bot", reply))
            if audio.TTS_AVAILABLE:
                audio.speak(reply)
            self.orch.touch()
        if self.voice:
            self.voice.paused = False

    def poll(self):
        try:
            while True:
                kind, msg = self.q.get_nowait()
                if kind in ("user", "bot"):
                    self.add(kind, msg)
                elif kind == "state":
                    self.set_state(msg)
                else:
                    self._append(self.audit, f"[{time.strftime('%H:%M:%S')}] {msg}")
        except queue.Empty:
            pass
        ext = netlog.count("external")
        hosts = ", ".join(netlog.external_hosts()) or "none"
        self.net.config(
            text=f"PROOF OF PRIVACY | External requests: {ext} ({hosts}) | "
                 f"Local LLM calls (127.0.0.1): {netlog.count('local')} | Audio uploaded: 0 bytes",
            fg="#a3e635" if ext == 0 else "#fbbf24")
        self.root.after(100, self.poll)


def run_gui():
    App().root.mainloop()
