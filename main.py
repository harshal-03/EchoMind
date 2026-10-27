"""EchoMind launcher.   python main.py        -> desktop GUI (default)
                         python main.py --cli  -> terminal REPL"""
import sys
from orchestrator import Orchestrator


def run_cli():
    o = Orchestrator(log=lambda k, m: print(f"      [{k}] {m}"))
    print("EchoMind CLI. Start with 'echo, ...'  Commands: /mute /unmute /online /offline /quit")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line == "/quit":
            break
        cmds = {"/mute": lambda: o.set_muted(True), "/unmute": lambda: o.set_muted(False),
                "/online": lambda: o.set_online(True), "/offline": lambda: o.set_online(False)}
        if line in cmds:
            cmds[line]()
            continue
        reply = o.handle(line)
        if reply:
            print(f"echo> {reply}")


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        from gui import run_gui
        run_gui()
