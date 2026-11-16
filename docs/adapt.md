---
hide-toc: true
---

# ADAPT Hand

`metaquest_teleop.adapt` turns your hand into the ADAPT hand's 20 joint angles and 13 motor
angles, within the robot's limits, and gives the pose of your wrist. Its geometry, joint ranges
and motor order are those of `virtualmodelcontrol.robots.adapt`.

## Try it

<iframe class="demo" src="_static/view.html?demo&mode=adapt&hand=right" title="Your hand next to the ADAPT hand it drives" loading="lazy"></iframe>

Your hand is on the left; the ADAPT hand on the right is where its motors would put it. Amber
angles are held at the robot's limit. While `metaquest-teleop` runs, the same view is at
**http://localhost:8012/view?mode=adapt**.

<iframe class="demo" src="_static/view.html?demo&mode=room&hand=right&show=adapt" title="The ADAPT hand where the robot goes, in the room" loading="lazy"></iframe>

In **Room**, **ADAPT hand** shows the ADAPT hand instead of yours, for your hand as it is: at
your wrist, its own wrist straight. The terminal shows the same ADAPT hand, in yellow, next to
yours. Both follow your hand also while the robot holds (its **robot** line says so); on ROS 2,
`/metaquest/adapt/...` carries what the robot gets, which holds still.

## In Python

```python
from metaquest_teleop import QuestHands, adapt

with QuestHands() as quest:
    while True:
        hand = quest.wait().right
        if hand is None:
            continue
        joints = adapt.joint_angles(hand)  # (20,) rad, in adapt.JOINTS order
        motors = adapt.motor_angles(hand)  # (13,) rad, in adapt.MOTORS order
        wrist = adapt.wrist_pose(hand)     # where your wrist is, and how it faces
```

Use `joints` for a controller in joint space, such as VMC, and `motors` as targets for a PID on
the motors. The ADAPT wrist stays at (0, 0): [below](#the-wrist).

## With the gestures and ROS 2

`metaquest-teleop` publishes the ADAPT hand's joints and motors on `/metaquest/adapt/joint_states`
and `/metaquest/adapt/motors` ([ROS 2](ros.md)). They hold still while you pinch your left hand,
or while a hand is not seen ([teleoperation](teleop.md)). `--no-adapt` leaves them out.

## Joints: from your hand

Each ADAPT joint follows the same joint of yours, your range of motion stretched onto its own:
the angle of yours in the first column of `adapt.HUMAN_RANGES` gives its lowest angle, the one in
the second its highest, linearly in between.

| ADAPT joint | Follows | Your range (°) | Its range (°) |
|---|---|---|---|
| thumb CMC1 | your thumb's first bone, turned about the hand's long axis from sideways towards the palm's front | 5 to 95 | 0 to 86 |
| thumb CMC2 | your thumb's first bone, pointing along the fingers | 16 to 74 | −29 to 29 |
| thumb MCP, IP | your thumb's bend at its middle and tip joints | 0 to 65, 0 to 80 | 0 to 86, 0 to 69 |
| each finger's MCP | your bend at the base | 0 to 90 | 0 to 86 |
| each finger's PIP, DIP | your bend at the middle and tip joints | 0 to 90, 0 to 60 | 0 to 69 |
| index spread | your index spread towards the thumb | 20 to 0 | −17 to 0 |
| ring, pinky spread | your spread towards the pinky | 0 to 15, 0 to 25 | 0 to 17 |

The ranges are typical ones, set so that, as with the real hand's poses of HumanManipulationVMC
(Santello et al., 1998): your **open hand gives home**, all zeros; a **power grasp gives PC1**
(thumb CMC1 65°, MCP 50°, IP 40°; fingers 55° and 65°); a **pinch gives PC2** (thumb 50°, MCP 35°,
IP 25°; index 25° and 40°). To fit your hand, change `adapt.HUMAN_RANGES`:

```python
from metaquest_teleop import adapt

adapt.HUMAN_RANGES["thumb_MCP"] = (0, 55)  # your thumb bends 55° at most: that is its 86°
```

The 3D view of `metaquest-teleop` uses the same ranges.

The ADAPT thumb's CMC joints are a gimbal: CMC2 swings its first bone from sideways towards the
fingers, then CMC1 turns it about the hand's long axis towards the palm's front. Your thumb's
first bone is read the same way, so its CMC1 and CMC2 follow yours.

## A pose the ADAPT hand can take

The ADAPT hand's joints are coupled, as in VirtualModelControl and HumanManipulationVMC:

- **each finger's DIP mimics its PIP**: one motor turns both through the same cable, by the
  same angle. So PIP and DIP are always equal. Both take the mean of yours, which keeps your
  fingertip pointing where it points (PIP + DIP is the same).
- **one motor spreads the index, ring and pinky** together, the middle finger not at all. The
  spreads take the best fit of yours.

So `adapt.joint_angles(hand)` is always a pose the robot can take: the dashboard, `--print_joints`
and `/metaquest/adapt/joint_states` show what the robot does. `joint_angles(hand, coupled=False)`
gives the angles before that, joint by joint, PIP and DIP apart.

## Limits

Every joint is kept within its range, as the robot can go:

| Joint | Range |
|---|---|
| thumb CMC1, MCP; each finger's MCP | 0 to 86° |
| thumb CMC2 | −29 to 29° |
| thumb IP; each finger's PIP and DIP | 0 to 69° |
| spread: index / middle / ring and pinky | −17 to 0° / none / 0 to 17° |

`adapt.JOINT_LIMITS` has them in radians. `joint_angles(hand, clip=False)` gives the angles
before the limits.

## Motors: 13 for 20 joints

The ADAPT hand has fewer motors than joints, so `adapt.motor_angles` finds the motor angles that
come closest to the joints:

- each thumb joint and each finger's MCP has its own motor, which follows it exactly;
- one motor per finger turns its PIP and DIP together: it takes their **mean**;
- one motor spreads the index, ring and pinky (the middle finger does not move): it takes the
  **best fit** of the three.

Each motor then stays where all its joints are within their limits. `adapt.COUPLING @ motors`
gives the joint angles the robot will reach: exactly `adapt.joint_angles(hand)`.

## The wrist

`adapt.wrist_pose(hand)` is your wrist's position, in the room in metres, and its orientation,
with the axes of the ADAPT hand:

- **+z** towards the fingertips,
- **+y** on the palm side,
- **−x** towards the thumb.

A robot arm that puts the ADAPT hand's base there makes it face the way your hand does.

The ADAPT hand's own wrist never bends: it stays at **(0, 0)**. Its two wrist motors (13 and 14
on its bus, `adapt.WRIST_MOTORS`) hold still there, under a PID, as in VirtualModelControl; the
arm turns the hand instead. `/metaquest/adapt/motors` ends with these two motors at 0, so one
PID over every motor it lists also holds the wrist.
