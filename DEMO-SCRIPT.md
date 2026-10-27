# EchoMind demo script (about 4 minutes)

Set up: Pi on phone hotspot, online button OFF, red/green LEDs visible, laptop terminal showing the log.

1. (20 s) Pitch: "A desk companion that listens, thinks and remembers on the Pi. Cloud AI pins shut down or leak.
   Ours keeps all reasoning local and only goes online for factual lookups."
2. (40 s) Memory: "echo, remember that we chose SQLite because the device is offline."
   Pause. "echo, why did we choose SQLite?"  -> local model answers from the note.
3. (30 s) Productivity: "echo, add task finish the slides." "echo, what are my tasks?"
   "echo, remind me in twenty seconds to drink water." (it speaks the reminder later)
4. (30 s) Reasoning: "echo, summarize my notes and tasks."  -> 2-3 sentences from the on-device model.
5. (40 s) Online vs local: "echo, what is the weather in Pune?" -> refuses, online is OFF.
   Press the online button. Ask again -> live weather. Log shows only a city leaves the device.
6. (20 s) Honest limits: "echo, will Nifty go up tomorrow?" -> refuses, offers to save a note.
   "echo, what did we decide about the logo?" -> "I don't have a note about that yet."
7. (30 s) Privacy: Press mute -> red LED, no reply. Unmute.
   "echo, what have you sent online?" -> the device audits itself: requests, hosts, zero audio.
8. (30 s) Close: footprint = Pi 5 with 4 GB, 1B model, no cloud. Modular: swap the model, add a tool in tools.py.
