from audio import VoiceInput
import time

def on_text(text):
    print("\nRecognized:", text)

voice = VoiceInput(on_text)

print("Starting microphone...")
print("Speak clearly for about 10 seconds.")
print("Press Ctrl+C to stop.")

voice.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    voice.stop()
