# Get started

## 1. Install

```bash
pip install metaquest-teleop
```

If pip refuses (`externally-managed-environment`), install it in a conda environment:

```bash
conda create -n quest -c conda-forge --override-channels python=3.12 -y
conda activate quest
pip install metaquest-teleop
```

You also need `adb`, which carries the data over the USB cable:

| System | Install adb |
|---|---|
| Ubuntu, Debian | `sudo apt install adb` |
| macOS | `brew install --cask android-platform-tools` |
| Windows | [Platform-Tools](https://developer.android.com/tools/releases/platform-tools), unzipped and added to `PATH` |

## 2. Set up the headset (once)

1. **Developer mode.** In the Meta Horizon phone app: your headset → Headset settings →
   Developer mode → on.
2. **Hand tracking.** In the headset: Settings → Movement tracking → hand tracking on.
3. **USB debugging.** Plug the headset in with a USB-C **data** cable, put it on and accept
   **Allow USB debugging** (tick *always allow*).

## 3. Stream

```bash
metaquest-teleop
```

In the headset, open the **Browser**, go to **http://localhost:8012** (type the `http://`) and
press **Start**: you see your room. Put the controllers down: the terminal shows your hands live,
the [ADAPT hand](adapt.md) in yellow next to them, and its **robot** line whether a robot would
move ([teleoperation](teleop.md)). The Meta button
pauses, `Ctrl-C` stops. Run it again and the headset goes on streaming: no need to press Start
again.

When it finds ROS 2 it also publishes on [ROS 2](ros.md) topics; otherwise it says it is not
publishing, and works the same.

To see the hands in 3D, open **http://localhost:8012/view** on your computer, or start with
`metaquest-teleop --view`.

## No headset? Use the fake one

```bash
metaquest-teleop --no-adb    # terminal 1
metaquest-teleop-fake        # terminal 2: two hands opening and closing
```

`metaquest-teleop-fake --hands right` sends the right hand only: the robot then holds, as the
left hand is not seen ([teleoperation](teleop.md)).

## Options

| Command | |
|---|---|
| `metaquest-teleop --view` | also open the 3D view |
| `metaquest-teleop --print_joints` | print all your joint angles and the ADAPT hand's, ten times a second, instead of the dashboard |
| `metaquest-teleop --no-ros` | do not publish on [ROS 2](ros.md) (it does whenever it finds ROS) |
| `metaquest-teleop --no-adapt` | no [ADAPT hand](adapt.md): no ADAPT topics, and the teleoperation gives your own joint angles |
| `metaquest-teleop --no-adapt-fit` | map the [ADAPT hand](adapt.md#joints-your-calibration)'s fingers joint for joint, through your calibration, instead of fitting them to yours |
| `metaquest-teleop --calibration` | [calibrate the ADAPT hand](adapt.md#calibrate-it-to-your-hand) to your hand in the 3D view; it is saved, and loaded every time |
| `metaquest-teleop --calibration-file FILE` | load another ADAPT calibration (and save to it with `--calibration`) |
| `metaquest-teleop --no-calibration-file` | the default ADAPT calibration, not the one you saved |
| `metaquest-teleop --hands both` | stream both hands; the default is the right hand only |
| `metaquest-teleop --port 8013` | use another port |
| `metaquest-teleop --udp 127.0.0.1:9000` | also send every frame as JSON over UDP |
| `metaquest-teleop --plain` | one line of text per second instead of the dashboard |
| `metaquest-teleop --no-adb` | do not set up the USB link |
