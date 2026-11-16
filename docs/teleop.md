# Teleoperation

One hand drives the robot, the other one pauses it. By default your right hand drives and your
left hand gives the gestures:

| Your left hand | The robot |
|---|---|
| open | follows your right hand |
| pinching | holds still where it is, while your right hand moves freely |
| released | follows your right hand again, from where it stopped: it does not jump |
| not seen | holds, for safety |

It also holds while your right hand is not seen, and when frames stop coming for 0.1 s. The
dashboard's **robot** line and the [3D view](view.md) show what it does.

## With ROS 2

`metaquest-teleop` publishes it all: `/metaquest/teleop/hold` (true: keep the robot still),
`/metaquest/teleop/state` (`moving`, or why it holds), `/metaquest/teleop/wrist` (where the
robot's wrist goes), and the ADAPT hand's joints and motors, which hold still while it holds.
See [ROS 2](ros.md).

## In Python

```python
import time

from metaquest_teleop import QuestHands, Teleop

with QuestHands() as quest:
    teleop = Teleop(quest)
    while True:
        command = teleop.command()
        if command.hold:
            pass  # keep the robot where it is (command.reason says why)
        else:
            pass  # send command.wrist to the arm and command.motors to the ADAPT hand
        time.sleep(0.01)
```

| `command.` | |
|---|---|
| `hold` | true: keep the robot where it is |
| `reason` | why it holds, such as `left hand pinching`; empty while it moves |
| `wrist` | where the robot's wrist goes: it starts at your wrist, then moves as your hand moves, except while holding. Room coordinates, with the [ADAPT hand's axes](adapt.md#the-wrist) |
| `joints`, `motors` | the ADAPT hand's 20 joint and 13 motor angles, within its limits; unchanged while holding |

`Teleop(quest, pinch_on=0.02, pinch_off=0.04)` sets when the pinch closes and opens again, in
metres; the gap between the two keeps a half-open pinch from flickering.

For a robot other than the ADAPT hand, `Teleop(quest, adapt=False)` (`metaquest-teleop
--no-adapt`) gives your own joint angles in `command.joints` and your wrist's own axes in
`command.wrist`, with no motors.
