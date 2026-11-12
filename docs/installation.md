# Installation

The library needs Python 3.10 or newer and runs on Linux, macOS and Windows. pip installs
everything it uses: aiohttp (the server), numpy and rich (the dashboard). To reach the
headset you also need `adb`, and the headset needs a one-time setup.

## With pip

```bash
pip install metaquest-teleop
metaquest-teleop --version
```

The second line prints the installed version.

On a recent Ubuntu or Debian, pip refuses to install into the system Python and stops with
`error: externally-managed-environment`. That is not a fault of the library: use a virtual
environment, as in the next section.

## In a virtual environment

A virtual environment keeps the library and its dependencies apart from the rest of your
system. Create it once, then activate it in every new terminal where you use the library.
On Linux and macOS:

```bash
python3 -m venv ~/venvs/quest           # once
source ~/venvs/quest/bin/activate       # in every new terminal
pip install metaquest-teleop            # once
metaquest-teleop --version
```

While the environment is active, your prompt starts with `(quest)` and the
`metaquest-teleop` command and `import metaquest_teleop` both work. `deactivate` leaves it.

On Ubuntu, `python3 -m venv` needs the `python3-venv` package. Install it once:

```bash
sudo apt install python3-venv
```

On Windows, in PowerShell:

```powershell
py -m venv $HOME\venvs\quest
& $HOME\venvs\quest\Scripts\Activate.ps1
pip install metaquest-teleop
metaquest-teleop --version
```

## With conda

```bash
conda create -n quest -c conda-forge --override-channels python=3.12 -y
conda activate quest
pip install metaquest-teleop
metaquest-teleop --version
```

The channel is conda-forge on purpose: on a new installation, conda's default channels refuse
to create an environment (`CondaToSNonInteractiveError`) until you accept Anaconda's terms of
service, and conda-forge asks for nothing.

## With ROS 2

Sourcing ROS 2 puts ROS's own Python packages on `PYTHONPATH`. The library does not use them
and normally runs unaffected. If an import fails while ROS is sourced, unset the variable for
that command:

```bash
env -u PYTHONPATH metaquest-teleop
```

To publish frames to ROS topics from the same script, `rclpy` must import too. Build the
environment from the Python your ROS distribution uses (3.12 for Jazzy), with access to the
system's packages, and source ROS before you activate it:

```bash
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages ~/venvs/quest-ros
source ~/venvs/quest-ros/bin/activate
pip install metaquest-teleop
python -c "import rclpy, metaquest_teleop"
```

## adb

`adb` (Android Debug Bridge) carries the stream over the USB cable. Install it once:

| System | Command |
|---|---|
| Ubuntu, Debian | `sudo apt install adb` |
| macOS | `brew install --cask android-platform-tools` |
| Windows | download [SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools), unzip it and add its folder to `PATH` |

`adb version` checks it. The library finds `adb` on your `PATH` and sets up the link by
itself; you never run `adb` by hand.

## Set up the headset

Once per headset (a Quest 2, 3, 3S or Pro):

1. **Developer mode.** In the Meta Horizon phone app: Devices → your headset → Headset
   settings → Developer mode → on. The first time, Meta asks you to join or create a free
   developer organisation.
2. **Hand tracking.** In the headset: Settings → Movement tracking → Hand and body tracking
   on, and auto-switch between hands and controllers on.
3. **USB debugging.** Plug the headset into the computer with a USB-C **data** cable (some
   charging cables carry no data), put it on and accept **Allow USB debugging**. Tick
   *always allow* so it does not ask again.

The [quickstart](quickstart.md) takes it from there.

## Update

```bash
pip install --upgrade metaquest-teleop
```

The newest code, from GitHub, before it is released:

```bash
pip install git+https://github.com/vigno0405/MetaQuestTeleop
```
