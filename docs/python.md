# Use it in Python

```python
from metaquest_teleop import QuestHands

with QuestHands() as quest:
    while True:
        frame = quest.wait()  # the next frame from the headset
        hand = frame.right    # None while the right hand is not tracked
        if hand is not None:
            print(hand.wrist.position, hand.pinch)
```

Run it instead of `metaquest-teleop` (both use port 8012), then press Start in the headset as
usual. The [3D view](view.md) works with it too.

## Getting frames

| | |
|---|---|
| `quest.wait()` | waits for the next frame |
| `quest.latest()` | the newest frame, without waiting: for loops at your own rate |
| `quest.on_frame(f)` | calls `f(frame)` for every frame |

## What's in a frame

```python
hand = frame.right              # or frame.left; None while not tracked
hand.wrist.position             # (3,) metres
hand.wrist.quaternion           # (4,) x, y, z, w
hand.wrist.rotation             # (3, 3) rotation matrix
hand.positions                  # (25, 3) every joint
hand.joint("index-finger-tip")  # one joint's pose
hand.angles                     # (5, 4) joint angles, radians
hand.pinch                      # thumb tip to index tip, metres
frame.received                  # time.time() when the frame arrived
```

[The data](data.md) explains the axes, the joints and the angles.

## Control a robot

The robot follows how the hand moves, not where it is, so it never jumps. When the hand
disappears or the frames stop, it holds still. The pinch drives the gripper.

```python
import time

import numpy as np
from metaquest_teleop import QuestHands

# The headset's axes (x right, y up, -z forward) in the robot's (x forward, y left, z up).
M = np.array([[0, 0, -1], [-1, 0, 0], [0, 1, 0]])


def send_to_robot(target, gripper):
    """Your robot: go to `target` (m, in its base frame); gripper from 0 closed to 1 open."""


target = np.array([0.4, 0.0, 0.3])  # the robot's target, m
anchor = None                       # the wrist and the target when the hand appeared

with QuestHands() as quest:
    while True:
        frame = quest.latest()
        fresh = frame is not None and time.time() - frame.received < 0.1
        hand = frame.right if fresh else None
        if hand is None:
            anchor = None  # no hand, or no frames for 0.1 s: hold still
        else:
            if anchor is None:
                anchor = (hand.wrist.position, target)
            wrist0, target0 = anchor
            target = target0 + M @ (hand.wrist.position - wrist0)  # follow the hand's motion
            gripper = np.interp(hand.pinch, [0.015, 0.08], [0.0, 1.0])
            send_to_robot(target, gripper)
        time.sleep(0.01)  # about 100 Hz
```

Orientation works the same way, with `hand.wrist.rotation`.

## Other programs: UDP

`metaquest-teleop --udp 127.0.0.1:9000` also sends every frame as one JSON message, which any
language can read. From Python:

```python
import json
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", 9000))
while True:
    frame = json.loads(sock.recv(65536))
    if frame["right"] is not None:
        print(frame["right"]["wrist"]["position"])
```

Each message holds one frame: `left` and `right` (each `null` while not tracked) with the
`wrist` position and orientation, the `angles` by name, the `pinch`, and the 25 `joints` as
x, y, z position and qx, qy, qz, qw orientation. It also has `received`, the time it arrived.
