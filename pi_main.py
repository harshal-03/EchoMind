"""Headless EchoMind for Raspberry Pi (also runs on a laptop with mock hardware).
   python pi_main.py"""
import threading
import time

import audio
import netlog
from hardware import create_hardware
from orchestrator import Orchestrator


class Companion:
    def __init__(self):
        self.orch = Orchestrator(log=lambda k, m: print(f"   [{time.strftime('%H:%M:%S')}] {m}"))
        self.orch.on_alert = self.alert
        self.voice = audio.VoiceInput(self.process) if audio.VOICE_AVAILABLE else None
        self.busy = threading.Lock()
        threading.Thread(target=self.orch.llm.warmup, daemon=True).start()
        self.hw = create_hardware(self.set_muted, self.set_online)
        self.set_online(self.hw.is_online())
        self.set_muted(self.hw.is_muted())          # honour switch position at boot

    # ---- switch handlers ----
    def set_muted(self, muted):
        self.orch.set_muted(muted)
        if self.voice:
            self.voice.stop() if muted else self.voice.start()   # mic stream really closes
        self.hw.show("muted" if muted else "listening")

    def set_online(self, online):
        self.orch.set_online(online)

    # ---- one utterance ----
    def process(self, text):
        if self.orch.muted:
            return
        with self.busy:
            if self.voice:
                self.voice.paused = True
            self.hw.show("thinking")
            print(f"You: {text}")
            reply = self.orch.handle(text, force_wake=self.hw.ptt_held())
            self.hw.show("muted" if self.orch.muted else "listening")
            if reply and not self.orch.muted:     # muted mid-answer -> stay silent
                print(f"Echo: {reply}")
                audio.speak(reply)
                self.orch.touch()
            if self.voice:
                self.voice.paused = False

    def alert(self, text):
        with self.busy:
            self.announce(text)

    def announce(self, text):
        if self.voice:
            self.voice.paused = True
        print(f"Echo: {text}")
        audio.speak(text)
        if self.voice:
            self.voice.paused = False

    def run(self):
        print("EchoMind running. Ctrl+C to stop.")
        if not self.orch.muted:
            self.announce("EchoMind is ready. Say echo, then your question.")
        try:
            if self.voice:
                threading.Event().wait()
            else:                                  # no mic model: typed dev loop
                print("Voice model not found -> typed mode. Commands: /mute /unmute /online /offline /quit")
                while True:
                    line = input("you> ").strip()
                    cmds = {"/mute": lambda: self.set_muted(True), "/unmute": lambda: self.set_muted(False),
                            "/online": lambda: self.set_online(True), "/offline": lambda: self.set_online(False)}
                    if line == "/quit":
                        break
                    if line in cmds:
                        cmds[line]()
                    elif line:
                        self.process(line)
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            print(f"\nNetwork summary: {netlog.count('external')} external request(s) "
                  f"-> {', '.join(netlog.external_hosts()) or 'none'}; "
                  f"{netlog.count('local')} local LLM call(s); audio uploaded: 0 bytes")
            if self.voice:
                self.voice.stop()
            self.hw.close()


if __name__ == "__main__":
    Companion().run()
