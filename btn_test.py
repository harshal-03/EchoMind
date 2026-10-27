from gpiozero import Button
from time import sleep

mute = Button(17)
online = Button(24)
last = None
print("Toggle the switches. Ctrl+C to quit.")
while True:
    now = (mute.is_pressed, online.is_pressed)
    if now != last:
        print("mute =", "DOWN" if now[0] else "UP",
              "| online =", "DOWN" if now[1] else "UP")
        last = now
    sleep(0.05)
