"""Wiring check (do this in hour 0-2):  python hw_test.py
Flip switches / press the button and watch the events. LEDs cycle at start."""
import time
from hardware import create_hardware

hw = create_hardware(lambda m: print("listen switch ->", "MUTED" if m else "LISTENING"),
                     lambda o: print("online switch ->", "ONLINE" if o else "OFFLINE"))
for s in ("listening", "thinking", "muted", "listening"):
    print("LED state:", s)
    hw.show(s)
    time.sleep(1.5)
print("Now toggle switches / hold the button for 30 s (Ctrl+C to quit)")
try:
    t_end = time.time() + 30
    while time.time() < t_end:
        if hw.ptt_held():
            print("PTT held")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
hw.close()
