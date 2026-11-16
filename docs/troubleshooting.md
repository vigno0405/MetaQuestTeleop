# Troubleshooting

| You see | Do this |
|---|---|
| `adb not found` | install adb ([get started](start.md#1-install)) |
| `no headset on USB` | use a data cable, turn developer mode on, wake the headset |
| `headset not authorised` | put the headset on and accept *Allow USB debugging* |
| `waiting for the page` | open http://localhost:8012 in the Quest's browser |
| `page open: press Start` | press Start on the page in the headset |
| streaming without pressing Start | normal: the headset was still streaming from before, and its page reconnects by itself |
| *WebXR is not available*, in the headset | open exactly `http://localhost:8012`, not the computer's address |
| *This site can't provide a secure connection*, in the headset | type the address with `http://`: **http://localhost:8012** |
| all black in the headset after Start | update: `pip install --upgrade metaquest-teleop` (fixed in 0.5.0) |
| *Hand tracking is unavailable*, in the headset | turn hand tracking on and put the controllers down |
| `Could not serve on port 8012` | another copy is running: stop it, or use `--port 8013` |

**No *Allow USB debugging* question in the headset.** Turn developer mode on, use a data cable,
and check that `lsusb | grep 2833` shows the headset. The question waits in the headset's
notifications; `adb kill-server` then `adb devices` asks again.

**Linux: `adb devices` says `no permissions`.** Run
`sudo apt install android-sdk-platform-tools-common`, then unplug and replug the headset.

**`ROS 2 not found`, or `ROS 2 Jazzy runs on Python 3.12, and this is Python 3.10`.** Source
ROS and run with the Python your ROS uses (3.10 for Humble, 3.12 for Jazzy), as in
[ROS 2](ros.md): a conda environment with another Python cannot load ROS. `--no-ros` hides the
message.
