# Quickstart

## Try it without a headset

The library comes with a stand-in headset that streams two synthetic hands, opening and
closing, exactly as the Quest would. In one terminal start the stream, without the USB link:

```bash
metaquest-teleop --no-adb
```

In a second terminal start the fake headset:

```bash
metaquest-teleop-fake
```

The dashboard in the first terminal fills in: the frame rate, then both hands with their
wrist poses, pinch distances and joint angles. `Ctrl-C` stops either one.

## Stream from the headset

1. Plug the headset into the computer and start the stream:

   ```bash
   metaquest-teleop
   ```

2. The dashboard's `USB` line turns green once the link is up. The first time, put the
   headset on and accept **Allow USB debugging**.
3. In the headset, open the **Browser** and go to **http://localhost:8012**.
4. Press **Start** and accept the immersive session. Put the controllers down and look at
   your hands: the dashboard fills in.

```{code-block} text
:class: dashboard

╭─ Quest hand stream ──────────────────────────────────────────────────────────╮
│ page     http://localhost:8012   open in the Quest browser, press Start      │
│ USB      ● USB link ready (2G0YC5ZF8T0912)                                   │
│ headset  ● XR session: immersive-ar, 120 Hz, local-floor                     │
│ stream   120 frames/s   hands changed in 120/s   gap p95 8.7 ms   360 frames │
│          15:32:42  headset page connected                                    │
│          15:32:44  XR session started: immersive-ar, 120 Hz, local-floor     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ RIGHT  ● tracked ───────────────────────────────────────────────────────────╮
│ wrist  x +0.163   y +1.134   z -0.400  m                                     │
│        yaw  +17°  pitch   +0°  roll   +0°                                    │
│ pinch  104 mm                                                                │
│                                                                              │
│          flex           abd  flex         flex                               │
│  thumb   █       18°   +34°  ▋       12°  ▍        6°                        │
│  index   ▋       11°    -8°  ▋       12°  ▍        8°                        │
│  middle  █▋      27°    -9°  █▊      29°  █▏      19°                        │
│  ring    ██▋     46°    -7°  ██▉     49°  █▉      32°                        │
│  pinky   ███▋    62°    -4°  ████    67°  ██▌     43°                        │
│      thumb: CMC, MCP, IP   fingers: MCP, PIP, DIP                            │
╰──────────────────────────────────────────────────────────────────────────────╯
```

The Meta button stops streaming; Start on the page streams again. `Ctrl-C` stops the
command. If something stays yellow or red, [troubleshooting](troubleshooting.md) lists what
each message means.

## In your own code

Your program serves the page itself, so it replaces the `metaquest-teleop` command: stop the
command first, since only one program can serve port 8012. Then run:

```python
from metaquest_teleop import QuestHands

with QuestHands() as quest:
    print(f"Open {quest.url} in the Quest browser and press Start. Ctrl-C to stop.")
    while True:
        frame = quest.wait(timeout=1.0)
        if frame is None or frame.right is None:
            continue  # no frame for a second, or the right hand is not tracked
        print(frame.right.wrist.position, frame.right.pinch)
```

and open the page in the headset as before. `QuestHands` keeps the USB link up in the
background, like the command. Without a headset, `metaquest-teleop-fake` streams to your
script just as well.

[Receiving frames in Python](guides/python.md) goes further, and
[teleoperating a robot](guides/teleoperation.md) turns the hand into a robot target.
