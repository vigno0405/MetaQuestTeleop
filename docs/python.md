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
usual. It keeps the right hand only; `QuestHands(hands="both")` keeps both, and
`hands="left"` the left one. The [3D view](view.md) works with it too.

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

[Teleoperation](teleop.md) does it for you: your right hand drives the robot, a pinch of your
left hand pauses it, and it holds when a hand or the frames go missing.

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
