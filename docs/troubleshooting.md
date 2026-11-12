# Troubleshooting

## What the dashboard says

| The dashboard says | Do this |
|---|---|
| `adb not found` | install `adb` ([installation](installation.md#adb)) |
| `no headset on USB` | use a data cable, turn developer mode on, wake the headset; on Linux see [no permissions](#adb-devices-says-no-permissions) |
| `headset not authorised` | put the headset on and accept *Allow USB debugging* |
| `waiting for the page to connect` | open http://localhost:8012 in the headset's browser while `USB` is green |
| `page open: press Start in the headset` | press Start on the page in the headset |
| `no frames for … s` | the headset is asleep or the session ended: put it on, press Start |

The USB link is lost when the cable is unplugged or the headset sleeps. The library restores
it within two seconds while no page is connected; the page then reconnects by itself.

## What the page in the headset says

- **WebXR is not available.** Open the page as `http://localhost:8012`, through the cable,
  not by the computer's IP address: the headset allows WebXR only on `localhost` or HTTPS.
- **Hand tracking is unavailable.** Turn hand tracking on (Settings → Movement tracking) and
  put the controllers down.
- **Waiting for the computer.** Start `metaquest-teleop`, or your script. The page reconnects
  by itself.

## `adb devices` says `no permissions`

On Linux your user may have no access to the headset's USB device; the dashboard then reports
`no headset on USB`. Check with `adb devices`. If the headset is listed as `no permissions`,
install the udev rules for Android devices, then unplug and replug the headset:

```bash
sudo apt install android-sdk-platform-tools-common
```

## `Could not serve on port 8012`

Another program already serves the port, usually a second copy of `metaquest-teleop` or of
your script: only one can run at a time. Stop the other one, or use another port with
`--port 8013` (or `QuestHands(port=8013)`) and open `http://localhost:8013` in the headset.

## Import errors with ROS 2 sourced

ROS's `PYTHONPATH` comes before your environment's packages. Unset it for the command:

```bash
env -u PYTHONPATH metaquest-teleop
```

[Installation](installation.md#with-ros-2) shows how to use `rclpy` and the library together.

## No virtual environment on Ubuntu

`python3 -m venv` fails with "ensurepip is not available" until the `python3-venv` package
is installed:

```bash
sudo apt install python3-venv
```

## Hands update less often than the frame rate

The page sends every frame the headset renders, but hand tracking may update less often than
the display. The dashboard's *hands changed in …/s* counts the frames that carry new hand
data, and `quest.rates()["changed_hz"]` gives the same number in code.
