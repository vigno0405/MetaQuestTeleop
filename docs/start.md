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

In the headset, open the **Browser**, go to **http://localhost:8012** and press **Start**. Put
the controllers down: the terminal shows your hands live. The Meta button pauses, `Ctrl-C`
stops.

To see the hands in 3D, open **http://localhost:8012/view** on your computer, or start with
`metaquest-teleop --view`.

## No headset? Use the fake one

```bash
metaquest-teleop --no-adb    # terminal 1
metaquest-teleop-fake        # terminal 2: two hands opening and closing
```

`metaquest-teleop-fake --hands right` sends only the right hand.

## Options

| Command | |
|---|---|
| `metaquest-teleop --view` | also open the 3D view |
| `metaquest-teleop --port 8013` | use another port |
| `metaquest-teleop --udp 127.0.0.1:9000` | also send every frame as JSON over UDP |
| `metaquest-teleop --plain` | one line of text per second instead of the dashboard |
| `metaquest-teleop --no-adb` | do not set up the USB link |
