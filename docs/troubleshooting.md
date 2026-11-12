# Troubleshooting

| You see | Do this |
|---|---|
| `adb not found` | install adb ([get started](start.md#1-install)) |
| `no headset on USB` | use a data cable, turn developer mode on, wake the headset |
| `headset not authorised` | put the headset on and accept *Allow USB debugging* |
| `waiting for the page` | open http://localhost:8012 in the Quest's browser |
| `page open: press Start` | press Start on the page in the headset |
| *WebXR is not available*, in the headset | open exactly `http://localhost:8012`, not the computer's address |
| *Hand tracking is unavailable*, in the headset | turn hand tracking on and put the controllers down |
| `Could not serve on port 8012` | another copy is running: stop it, or use `--port 8013` |

**Linux: `adb devices` says `no permissions`.** Run
`sudo apt install android-sdk-platform-tools-common`, then unplug and replug the headset.

**Errors with ROS 2 sourced.** Run `env -u PYTHONPATH metaquest-teleop`.
