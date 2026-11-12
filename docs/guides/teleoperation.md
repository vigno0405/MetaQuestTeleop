# Teleoperate a robot

The library gives you the hands; what the robot does with them is up to you. This page builds
a common scheme for an arm with a gripper, piece by piece:

- a control loop at the robot's rate, which holds still when frames stop;
- the change from the headset's axes to the robot's;
- relative motion with a clutch: the robot moves only while you hold it, so you can
  reposition your hand without moving the robot;
- the gripper from the pinch.

## The whole loop

The right hand moves the robot and its pinch drives the gripper. The left hand is the
clutch: pinch it to move the robot, release to stop.

```python
import time

import numpy as np
from metaquest_teleop import QuestHands

# From the headset's axes (x right, y up, -z forward)
# to the robot base's (x forward, y left, z up).
M = np.array([[0.0, 0.0, -1.0],
              [-1.0, 0.0, 0.0],
              [0.0, 1.0, 0.0]])
RATE = 100.0     # control rate, Hz
STALE = 0.1      # s without a frame before the robot holds still
SCALE = 1.0      # robot metres per hand metre
CLUTCH = 0.02    # left pinch below this, m, engages the clutch


def send_to_robot(position, rotation, gripper):
    """Your robot's interface: a target pose in its base frame, and the gripper opening."""


target_p, target_R = np.array([0.4, 0.0, 0.3]), np.eye(3)  # the robot's current target
gripper = 1.0                                              # 0 closed, 1 open
anchor = None    # the hand and the target when the clutch engaged

with QuestHands() as quest:
    while True:
        tick = time.perf_counter()
        frame = quest.latest()
        fresh = frame is not None and time.time() - frame.received < STALE
        hand = frame.right if fresh else None
        engaged = hand is not None and frame.left is not None and frame.left.pinch < CLUTCH

        if not engaged:
            anchor = None                       # released, or a hand is lost: hold the target
        else:
            if anchor is None:
                anchor = (hand.wrist, target_p, target_R)
            start, p0, R0 = anchor
            dp = hand.wrist.position - start.position         # hand motion since engaging
            dR = hand.wrist.rotation @ start.rotation.T
            target_p = p0 + SCALE * M @ dp
            target_R = M @ dR @ M.T @ R0
        if hand is not None:
            gripper = float(np.interp(hand.pinch, [0.015, 0.08], [0.0, 1.0]))

        send_to_robot(target_p, target_R, gripper)
        time.sleep(max(0.0, 1.0 / RATE - (time.perf_counter() - tick)))
```

Run it against `metaquest-teleop-fake` first, with `send_to_robot` printing its arguments,
before you connect a robot. The fake hands never pinch closer than about 4 cm, so set
`CLUTCH = 0.05` to see the clutch engage with them, and back to 0.02 for real hands.

## A loop at the robot's rate

The headset sends 72 to 120 frames a second and your robot wants commands at its own rate.
`quest.latest()` decouples the two: the loop takes the newest frame whenever it runs.

**Stale frames.** `frame.received` is the time this computer received the frame. When frames
stop, because the headset slept, the page closed or the cable came out, `latest()` keeps
returning the last one. The loop treats a frame older than `STALE` as no frame: the clutch
disengages and the robot holds its last target. Do not drop this check.

## From the headset's axes to the robot's

Poses arrive in WebXR's `local-floor` space: +x to the right of where the headset faced at
Start, +y up, and −z forward ([the data](../concepts/data.md#units-and-space)). Robots often
use x forward, y left, z up. The rotation `M` takes a vector from the first to the second:
`M @ v` for a displacement, `M @ R @ M.T` for a rotation. Here it assumes you face the same
way as the robot; for another arrangement, change `M`.

## Relative motion and the clutch

Mapping the hand's absolute position to the robot would make the robot jump to wherever your
hand is when you start. Relative motion avoids it. When the clutch engages, the loop stores
the wrist pose and the robot's target. While it stays engaged, the target moves from the
stored one by the hand's motion since then:

- position: the stored target plus `M @ (wrist - stored wrist)`, times `SCALE`;
- orientation: the hand's rotation since then, `dR = R_wrist @ R_stored.T`, applied to the
  stored target's orientation in the robot's axes: `M @ dR @ M.T @ R_target`.

Releasing the clutch freezes the target. You can move your hand back and engage again, like
lifting a mouse off the table. `SCALE` below 1 gives finer motion, above 1 a larger reach.

## The gripper from the pinch

`hand.pinch` is the distance between the thumb tip and the index tip, in metres: about 0.01 m
when they touch, 0.08 m and more with the hand open. `np.interp` maps it to the gripper's
range and clamps it at both ends; adjust the two distances to your hand.

## Going further

- **Smoothing.** Hand tracking jitters by a few millimetres. A low-pass filter on the
  target, `smooth = smooth + a * (target - smooth)` with `a` around 0.2 at 100 Hz, trades a
  little lag for steadiness.
- **Speed limits.** Clip the change of the target per tick, so that a tracking glitch cannot
  command a jump.
- **Robot hands.** For a robot hand, the joint angles map more directly than positions:
  `hand.angles[1:, 0]` are the MCP flexions of the four fingers, `hand.angles[:, 2]` the next
  joint of each finger ([angles](../concepts/data.md#angles)).
- **Another computer.** If the robot's controller runs elsewhere, send it every frame over
  [UDP](udp.md) and run the loop there.
