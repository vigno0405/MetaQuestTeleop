# The command line

The package installs two commands: `metaquest-teleop`, the stream with its dashboard, and
`metaquest-teleop-fake`, a stand-in headset.

## metaquest-teleop

```bash
metaquest-teleop                         # then open http://localhost:8012 in the Quest browser
metaquest-teleop --udp 127.0.0.1:9000    # also send every frame as JSON to a UDP port
metaquest-teleop --plain                 # one status line per second instead of the dashboard
```

| Option | |
|---|---|
| `--port 8012` | port of the page and the stream |
| `--udp HOST:PORT` | also send every frame as JSON to this UDP address ([UDP](udp.md)) |
| `--plain` | one status line per second instead of the dashboard |
| `--no-adb` | do not set up the USB link; you run `adb reverse tcp:8012 tcp:8012` yourself |
| `--version` | print the installed version |

`python -m metaquest_teleop` is the same command. `Ctrl-C` stops it.

### The dashboard

The top panel shows the link, from the computer to your hands:

| Line | |
|---|---|
| `page` | the address to open in the Quest browser |
| `USB` | the USB link: green when `adb reverse` is set up, red with the reason otherwise |
| `headset` | whether the page is connected and an immersive session runs, with its mode, frame rate and space |
| `stream` | frames per second, how many carried new hand data, the 95th percentile of the interval between frames, and the total |
| `UDP` | where frames are sent, with `--udp` |

The last three status messages follow. Below, one panel per hand gives the wrist position in
metres, its yaw, pitch and roll in degrees, the pinch distance and the 20 joint angles, with
a bar for each flexion. A hand that is not tracked, or whose last frame is older than half a
second, shows *not tracked*.

### Plain output

With `--plain`, or when the output is not a terminal (a pipe or a log file), the command
prints one line per second instead:

```text
17:16:19   90 frames/s  usb: USB link ready (2G0YC5ZF8T0912)  left wrist [-0.19, 1.149, -0.4]  right wrist [0.21, 1.149, -0.4]
```

## metaquest-teleop-fake

A stand-in headset with two synthetic hands that open and close while the wrists circle,
sent to a running `metaquest-teleop` (or your script) exactly as the Quest sends them. Use it
to develop and test without the headset.

```bash
metaquest-teleop-fake                       # 90 frames/s until Ctrl-C
metaquest-teleop-fake --hz 120 --seconds 10
```

| Option | |
|---|---|
| `--port 8012` | port of the running stream |
| `--hz 90` | frames per second |
| `--seconds` | stop after this long; without it, run until `Ctrl-C` |

`python -m metaquest_teleop.fake` is the same command.
