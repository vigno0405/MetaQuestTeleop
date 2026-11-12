# Other programs and languages: UDP

Any program that reads UDP and JSON can receive the hands: a C++ controller, a simulator, a
program on another computer. Start the stream with `--udp`:

```bash
metaquest-teleop --udp 127.0.0.1:9000
```

or, from Python, `QuestHands(udp=("127.0.0.1", 9000))`. Every frame is then also sent as one
JSON datagram to that address. The address can be another computer on the network, such as
the robot's controller.

## The format

```js
{"seq": 1834, "time": 52.31, "received": 1762874211.42,
 "head":  {"position": [x, y, z], "quaternion": [x, y, z, w]},
 "right": {"wrist":  {"position": [x, y, z], "quaternion": [x, y, z, w]},
           "angles": {"thumb_cmc_flex": 0.31, "...": 0.0, "pinky_dip_flex": 0.62},
           "pinch":  0.041,
           "joints": [[x, y, z, qx, qy, qz, qw], "... 25 rows, in joint order"]},
 "left": null}
```

| Field | |
|---|---|
| `seq` | frame counter from the headset |
| `time` | the headset's clock, seconds |
| `received` | this computer's `time.time()` when the frame arrived |
| `head` | the headset's pose, or `null` |
| `left`, `right` | a hand, or `null` while it is not tracked |
| `wrist` | the wrist's position (m) and orientation (quaternion x, y, z, w) |
| `angles` | the 20 joint angles by name, radians |
| `pinch` | thumb tip to index tip, m |
| `joints` | 25 rows of position and quaternion, in the [joint order](../concepts/data.md#joints) |

Units, axes and angle conventions are those of [the data](../concepts/data.md). A datagram
with both hands is about 9 kB.

## A listener in Python

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

To listen for frames from another computer, bind to `"0.0.0.0"` instead.

UDP does not resend lost datagrams or keep their order. On a cable or a local network that
is rarely an issue; compare `seq` with the previous one to notice it.
