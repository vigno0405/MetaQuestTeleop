# Receive frames in Python

{py:class}`~metaquest_teleop.QuestHands` does everything the `metaquest-teleop` command does,
in background threads of your program: it serves the page to the headset, keeps the USB link
up and decodes every frame. Your code asks it for frames.

## Start and stop

A `with` block starts the server and stops it when the block ends, even on an error:

```python
from metaquest_teleop import QuestHands

with QuestHands() as quest:
    ...  # open quest.url in the Quest browser and press Start
```

`start()` and `stop()` do the same without the block. `start()` raises `OSError` if another
program already serves the port.

| Argument | Default | |
|---|---|---|
| `port` | `8012` | port of the page and the stream: the headset opens `http://localhost:<port>` |
| `adb` | `True` | keep the USB link up with `adb reverse`; `False` if you run it yourself |
| `udp` | `None` | `(host, port)` to also send every frame to as JSON, see [UDP](udp.md) |
| `host` | `"127.0.0.1"` | the interface to listen on |

## Three ways to get frames

**`quest.wait(timeout=None)`** blocks until a new frame arrives and returns it, or `None`
after `timeout` seconds. It returns the newest frame: if your loop is slower than the
headset, the frames in between are skipped.

```python
while True:
    frame = quest.wait(timeout=1.0)
    if frame is not None and frame.right is not None:
        print(frame.right.wrist.position)
```

**`quest.latest()`** returns the newest frame at once, without waiting, or `None` before the
first. It suits a control loop that runs at its own rate, like the one in
[teleoperation](teleoperation.md). Check `frame.received` to know how old it is.

**`quest.on_frame(callback)`** calls `callback(frame)` for every frame, none skipped, on the
thread that receives them. Keep it fast: the next frame waits for it. An exception in the
callback does not stop the stream; it is reported in `quest.events`.

```python
quest.on_frame(lambda frame: print(frame.seq))
```

## What a frame holds

A {py:class}`~metaquest_teleop.Frame` has a `seq` number, two timestamps, the `head` pose and
two hands. A hand is `None` while the headset does not track it, so check before using it.

```python
hand = frame.right                     # or frame.left, or frame.hand("right")
hand.wrist.position                    # (3,) metres
hand.wrist.quaternion                  # (4,) x, y, z, w
hand.wrist.rotation                    # (3, 3) rotation matrix
hand.wrist.matrix                      # (4, 4) homogeneous transform
hand.positions                         # (25, 3) every joint
hand.joint("index-finger-tip")         # the Pose of one joint
hand.angles                            # (5, 4) joint angles, radians
hand.angle_dict["index_pip_flex"]      # one angle by name
hand.pinch                             # thumb tip to index tip, metres
```

[The data](../concepts/data.md) explains the units, the frames, the joints and the angles.

## Status

| | |
|---|---|
| `quest.connected` | whether the page in the headset is connected |
| `quest.headset` | what the page reported: `mode`, `fps`, `space`, `session` and `stats` |
| `quest.rates()` | `hz` (frames in the last second), `changed_hz` (of which carried new hand data), `interval_p95_ms`, `age_ms` (of the last frame) |
| `quest.frames` | frames received since the start |
| `quest.usb`, `quest.usb_ok` | the USB link's status |
| `quest.events` | the last six status messages, as `(time, text)` |

## Record a session

`frame.to_dict()` turns a frame into plain lists and numbers. One JSON line per frame makes a
recording that any language reads back:

```python
import json
import time

from metaquest_teleop import QuestHands

with open("session.jsonl", "w") as log, QuestHands() as quest:
    quest.on_frame(lambda frame: log.write(json.dumps(frame.to_dict()) + "\n"))
    time.sleep(30.0)  # record for 30 s
```

The file is opened first so that it closes last, after the stream has stopped.

Read it back:

```python
import json

with open("session.jsonl") as log:
    frames = [json.loads(line) for line in log]
right = [f["right"]["wrist"]["position"] for f in frames if f["right"] is not None]
```

The format is the one of [UDP](udp.md#the-format).
