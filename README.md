# MetaQuestTeleop

[![CI](https://github.com/vigno0405/MetaQuestTeleop/actions/workflows/ci.yml/badge.svg)](https://github.com/vigno0405/MetaQuestTeleop/actions/workflows/ci.yml)

Stream hand tracking from a Meta Quest to Python over a USB cable, for teleoperation: both
wrist poses, all 25 joints of each hand and 20 joint angles per hand, at the highest frame
rate the headset offers, with a live dashboard in the terminal.

```text
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

The headset runs a small web page (WebXR) that sends every frame it renders to this
computer. `adb reverse` makes the headset's `localhost` reach the computer through the
cable, and a `localhost` page is allowed to use WebXR without certificates, so there is
nothing to install on the headset.

## Install

```bash
pip install metaquest-teleop
```

or the latest version straight from GitHub:

```bash
pip install git+https://github.com/vigno0405/MetaQuestTeleop
```

This installs the `metaquest_teleop` Python package and two commands, `metaquest-teleop`
(the stream with its dashboard) and `metaquest-teleop-fake` (a stand-in headset for testing).
Python 3.10 or newer.

## What you need

- A Meta Quest 2, 3, 3S or Pro.
- A USB-C **data** cable (some charging cables carry no data).
- A computer with `adb` (Linux, macOS or Windows).

## One-time setup

1. **Developer mode.** In the Meta Horizon phone app: Devices → your headset → Headset
   settings → Developer mode → on. The first time, Meta asks you to join or create a free
   developer organisation.
2. **adb.** Ubuntu or Debian: `sudo apt install adb`. macOS: `brew install --cask
   android-platform-tools`. Windows: download *SDK Platform-Tools* from
   developer.android.com and add its folder to `PATH`.
3. **Hand tracking**, on the headset: Settings → Movement tracking → Hand and body
   tracking on, and auto-switch between hands and controllers on.

## Run

1. Plug the headset into the computer and start the stream:

   ```bash
   metaquest-teleop
   ```

2. The first time, put the headset on and accept **Allow USB debugging** (tick *always
   allow*). The dashboard's `USB` line turns green.
3. In the headset, open the **Browser** and go to **http://localhost:8012**.
4. Press **Start**, accept the immersive session, put the controllers down and look at your
   hands. The dashboard fills in.

Press the Meta button to stop streaming; press Start on the page to stream again. `Ctrl-C`
stops the command.

No headset at hand? In a second terminal, `metaquest-teleop-fake` streams synthetic hands
to the running command, exactly as the headset would.

| Option | |
|---|---|
| `--port 8012` | port of the page and the stream |
| `--udp HOST:PORT` | also send every frame as JSON to a UDP address (see below) |
| `--plain` | one status line per second instead of the dashboard |
| `--no-adb` | do not set up the USB link; you run `adb reverse tcp:8012 tcp:8012` yourself |
| `--version` | print the installed version |

`python -m metaquest_teleop` is the same as `metaquest-teleop`.

## Use it in your code

```python
from metaquest_teleop import QuestHands

with QuestHands() as quest:              # serves the page and keeps the USB link up, in the background
    while True:
        frame = quest.wait()             # blocks until the next frame
        if frame.right is not None:
            print(frame.right.wrist.position, frame.right.angles)
```

[`examples/minimal.py`](examples/minimal.py) is a runnable version.

**`QuestHands(port=8012, adb=True, udp=None, host="127.0.0.1")`**: `start()` and `stop()`,
or use it in a `with` block. The server listens on the loopback interface only, so nothing
else on your network can send it frames; the headset reaches it through `adb reverse`.

| | |
|---|---|
| `quest.wait(timeout=None)` | the next frame; `None` on timeout |
| `quest.latest()` | the most recent frame without waiting; `None` before the first |
| `quest.on_frame(callback)` | `callback(frame)` for every frame, on the receiving thread (keep it fast) |
| `quest.rates()` | frames per second, interval p95 and age of the last frame |
| `quest.connected`, `quest.headset` | whether the page is connected, and what it reported (mode, frame rate) |

**`Frame`**: `seq`, `time` (headset clock, s), `received` (this computer's `time.time()`),
`head`, `left`, `right` (a `Hand`, or `None` while that hand is not tracked), `to_dict()`.

**`Hand`**: `side`, `wrist` (a `Pose`), `positions` (25, 3), `quaternions` (25, 4),
`joint(name)`, `angles` (5, 4), `angle_dict` (by name), `local_quaternions` (25, 4, each joint
relative to its parent), `pinch` (thumb tip to index tip, m), `to_dict()`.

**`Pose`**: `position` (3,), `quaternion` (4,), `rotation` (3, 3), `matrix` (4, 4).

## Other programs and languages: UDP

```bash
metaquest-teleop --udp 127.0.0.1:9000
```

sends each frame as one JSON datagram:

```json
{"seq": 1834, "time": 52.31, "received": 1762874211.42,
 "head":  {"position": [x, y, z], "quaternion": [x, y, z, w]},
 "right": {"wrist":  {"position": [x, y, z], "quaternion": [x, y, z, w]},
           "angles": {"thumb_cmc_flex": 0.31, "...": 0.0, "pinky_dip_flex": 0.62},
           "pinch":  0.041,
           "joints": [[x, y, z, qx, qy, qz, qw], "... 25 rows, in joint order"]},
 "left": null}
```

A listener in Python:

```python
import json, socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", 9000))
while True:
    frame = json.loads(sock.recv(65536))
    print(frame["right"] and frame["right"]["wrist"]["position"])
```

## The data

**Units and frame.** Metres, radians, quaternions as (x, y, z, w). Poses are in WebXR's
`local-floor` space: origin on the floor below where the headset was when you pressed
Start, **+y up**, **−z the direction the headset faced**, +x to its right. Holding the Meta
button recentres the view, which moves this origin.

**Joints.** 25 per hand, in this order (`metaquest_teleop.JOINTS`): `wrist`; thumb
`metacarpal`, `phalanx-proximal`, `phalanx-distal`, `tip`; then for index, middle, ring and
pinky `metacarpal`, `phalanx-proximal`, `phalanx-intermediate`, `phalanx-distal`, `tip`.
Each joint's own axes, on both hands: **−Z along the bone towards the fingertip, −Y out of
the palm**. A hand is reported whole or not at all.

**Angles.** `hand.angles` is (5, 4), one row per finger from thumb to pinky; names in
`metaquest_teleop.ANGLE_NAMES`:

| | column 0 | column 1 | column 2 | column 3 |
|---|---|---|---|---|
| thumb | CMC flexion | CMC abduction | MCP flexion | IP flexion |
| index … pinky | MCP flexion | MCP abduction | PIP flexion | DIP flexion |

Flexion is positive towards the palm; abduction is positive towards the thumb side, on
both hands. Each angle is the bend of a bone against its parent joint, so an open, flat
hand reads about 0 everywhere except the thumb's CMC, which is measured against the wrist.
For a different convention, use `local_quaternions` or the raw joint poses.

**Rate.** The page asks the headset for its highest frame rate (72 to 120 Hz depending on
the model) and sends every frame. Hand tracking itself may update less often than the
display; the dashboard's *hands changed* count shows how many frames per second carry new
hand data.

## Troubleshooting

| The dashboard says | Do this |
|---|---|
| `adb not found` | install adb (setup step 2) |
| `no headset on USB` | data cable, developer mode on, headset awake |
| `headset not authorised` | put the headset on and accept *Allow USB debugging* |
| `waiting for the page` | open http://localhost:8012 in the headset's browser while `USB` is green |
| `page open: press Start` | press Start on the page in the headset |
| `no frames for … s` | the headset is asleep or the session ended: put it on, press Start |

On the page in the headset:

- **WebXR is not available**: the page must be opened as `http://localhost:8012` through the
  cable, not by the computer's IP address.
- **Hand tracking is unavailable**: turn hand tracking on and put the controllers down.
- **Waiting for the computer**: start `metaquest-teleop`. The page reconnects by itself.

The USB link is lost when the cable is unplugged or the headset sleeps; the command
restores it within two seconds while no page is connected. If port 8012 is taken, use
`--port`.

## Development

```bash
git clone https://github.com/vigno0405/MetaQuestTeleop
cd MetaQuestTeleop
python -m pip install -e ".[test]"
python -m pytest
```

```text
src/metaquest_teleop/
  server.py              QuestHands: serves the page, USB link, receives and forwards frames
  hands.py               Frame, Hand, Pose, joint angles, the wire format
  client.html            the WebXR page that runs in the headset
  dashboard.py           the terminal dashboard
  cli.py                 the metaquest-teleop command: dashboard, --udp, --plain
  fake.py                a stand-in headset with synthetic hands
examples/minimal.py      the smallest use of the API
tests/                   python -m pytest
```

### Releasing

1. Bump `__version__` in `src/metaquest_teleop/__init__.py` and commit.
2. Create a GitHub release with the tag `v<version>` (for example `v0.1.1`).
3. The `publish` workflow builds the package, checks the tag matches the version, and
   uploads it to PyPI.

## License

MIT, see [LICENSE](LICENSE).
