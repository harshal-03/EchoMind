# Raspberry Pi 5 hardware kit

## Wiring (BCM numbers; all inputs use the Pi's internal pull-ups)
| Part | GPIO (phys pin) | Other leg |
|---|---|---|
| Listen/Mute toggle switch | GPIO17 (pin 11) | GND (pin 9). CLOSED = listening, OPEN = muted |
| Online toggle switch | GPIO24 (pin 18) | GND (pin 14). CLOSED = weather allowed |
| Push-to-talk button | GPIO23 (pin 16) | GND (pin 14) |
| Green LED + 330 ohm | GPIO27 (pin 13) -> resistor -> LED anode | LED cathode -> GND (pin 6) |
| Red LED + 330 ohm | GPIO22 (pin 15) -> resistor -> LED anode | LED cathode -> GND (pin 6) |

Audio: USB microphone + USB/Bluetooth speaker (the Pi 5 has no 3.5 mm jack).

## Pi setup
sudo apt update
sudo apt install -y python3-venv python3-gpiozero python3-lgpio libportaudio2 espeak-ng
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install vosk sounddevice pyttsx3
curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.2:3b
python hw_test.py      # verify wiring first
python seed_demo.py
python pi_main.py
