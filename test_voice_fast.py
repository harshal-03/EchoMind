from audio import VoiceInput
import time

def on_text(text):
    print("Recognized:", text)

voice = VoiceInput(on_text)

print("Starting microphone...")
print("Speak a short sentence.")
print("Press Ctrl+C to stop.")

voice.start()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    voice.stop()
    print("\nStopped.")
