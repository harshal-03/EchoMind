#!/usr/bin/env bash
# Restore microphone settings (they reset when the SD card is re-flashed).
#   bash mic_fix.sh        sets capture volume to 35 percent
#   bash mic_fix.sh 25     sets another percentage (lower = less clipping, higher = louder)
GAIN=${1:-35}
CARD=$(arecord -l 2>/dev/null | grep -i -m1 -E "usb|pnp|c-media" | sed -E 's/^card ([0-9]+):.*/\1/')
if [ -z "$CARD" ]; then
  echo "No USB microphone found. Check the plug and adapter, then run:  lsusb ; arecord -l"
  exit 1
fi
echo "== USB microphone is ALSA card $CARD =="
arecord -l | grep "^card $CARD"

echo; echo "== Sample rates and formats the microphone supports =="
arecord -D hw:$CARD,0 --dump-hw-params -d 1 /dev/null 2>&1 | grep -E "RATE|CHANNELS|FORMAT" \
  || echo "(could not read: another program may be using the microphone. Stop pi_main.py and retry)"

echo; echo "== Capture controls (before) =="
amixer -c "$CARD" scontents 2>/dev/null | grep -E "^Simple|Capture|Playback|dB|%" | head -24

echo; echo "== Setting capture volume to ${GAIN} percent and turning automatic gain off =="
amixer -c "$CARD" scontrols 2>/dev/null | sed -n "s/.*'\(.*\)',.*/\1/p" | while read -r NAME; do
  case "$NAME" in
    *"Auto Gain"*) amixer -c "$CARD" sset "$NAME" off >/dev/null 2>&1 && echo "  $NAME -> off" ;;
    Mic|*Capture*|*Microphone*) amixer -c "$CARD" sset "$NAME" "${GAIN}%" cap unmute >/dev/null 2>&1 && echo "  $NAME -> ${GAIN}%" ;;
  esac
done
sudo alsactl store >/dev/null 2>&1 && echo "  saved so it survives a reboot"

echo; echo "== USB power setting (lost when the card is re-flashed) =="
if grep -q '^usb_max_current_enable=1' /boot/firmware/config.txt 2>/dev/null; then
  echo "  already set"
else
  echo 'usb_max_current_enable=1' | sudo tee -a /boot/firmware/config.txt >/dev/null && echo "  added. A reboot is needed:  sudo reboot"
fi
vcgencmd get_throttled 2>/dev/null

echo; echo "== Add these to ~/.bashrc if missing =="
echo "  export ECHOMIND_MODEL=llama3.2:1b"
echo "  export ECHOMIND_ALSA_DEVICE=plughw:$CARD,0"
echo; echo "Next:  python mic_level.py   (once in silence, once talking)   then   python mic_test.py"
