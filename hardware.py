"""GPIO layer. Real hardware on a Raspberry Pi (gpiozero); mock everywhere else,
so the exact same pi_main.py runs on your laptop."""
import time

try:
    from gpiozero import LED, Button
    GPIO_IMPORTED = True
except Exception:
    GPIO_IMPORTED = False

from config import (PIN_LED_LISTEN, PIN_LED_MUTED, PIN_LISTEN_SWITCH,
                    PIN_ONLINE_SWITCH, PIN_PTT_BUTTON, SWITCH_MODE)


class PiHardware:
    """Switch closed to GND = pressed. Listen switch OPEN (or a broken wire) = MUTED,
    so any wiring fault fails safe."""

    def __init__(self, on_mute, on_online):
        self.listen_sw = Button(PIN_LISTEN_SWITCH, pull_up=True, bounce_time=0.05)
        self.online_sw = Button(PIN_ONLINE_SWITCH, pull_up=True, bounce_time=0.05)
        self.ptt = Button(PIN_PTT_BUTTON, pull_up=True, bounce_time=0.05)
        self.led_listen = LED(PIN_LED_LISTEN)
        self.led_muted = LED(PIN_LED_MUTED) if PIN_LED_MUTED is not None else None
        self.push = SWITCH_MODE == "push"
        self._muted, self._online = False, False
        self._on_mute, self._on_online = on_mute, on_online
        if self.push:                      # each press flips the state
            self.listen_sw.when_pressed = self._flip_mute
            self.online_sw.when_pressed = self._flip_online
        else:                              # real toggle switches
            self.listen_sw.when_pressed = lambda: on_mute(False)
            self.listen_sw.when_released = lambda: on_mute(True)
            self.online_sw.when_pressed = lambda: on_online(True)
            self.online_sw.when_released = lambda: on_online(False)

    def _flip_mute(self):
        self._muted = not self._muted
        self._on_mute(self._muted)

    def _flip_online(self):
        self._online = not self._online
        self._on_online(self._online)

    def is_muted(self):
        return self._muted if self.push else not self.listen_sw.is_pressed

    def is_online(self):
        return self._online if self.push else self.online_sw.is_pressed

    def ptt_held(self):
        return self.ptt.is_pressed

    def show(self, state):
        """state: 'listening' | 'thinking' | 'muted' (on()/off() cancel any blink)."""
        red = self.led_muted
        if state == "listening":
            red and red.off()
            self.led_listen.on()
        elif state == "thinking":
            red and red.off()
            self.led_listen.blink(on_time=0.15, off_time=0.15, background=True)
        else:  # muted: listening LED OFF, red LED ON (if fitted)
            self.led_listen.off()
            red and red.on()

    def close(self):
        self.led_listen.off()
        if self.led_muted:
            self.led_muted.off()
        for d in (self.listen_sw, self.online_sw, self.ptt, self.led_listen, self.led_muted):
            if d:
                d.close()


class MockHardware:
    """Laptop stand-in: same interface, prints LED state instead of driving pins."""

    def is_muted(self):
        return False

    def is_online(self):
        return False

    def ptt_held(self):
        return False

    def show(self, state):
        icon = {"listening": "GREEN LED ON", "thinking": "GREEN LED BLINKING",
                "muted": "GREEN OFF / RED ON"}[state]
        print(f"   [LED] {icon}")

    def close(self):
        pass


def create_hardware(on_mute, on_online):
    if GPIO_IMPORTED:
        try:
            hw = PiHardware(on_mute, on_online)
            print("GPIO hardware active")
            return hw
        except Exception as e:
            print(f"GPIO unavailable ({e.__class__.__name__}); using mock hardware")
    else:
        print("gpiozero not installed; using mock hardware")
    return MockHardware()
