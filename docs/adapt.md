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

<iframe class="demo" src="_static/view.html?demo&mode=room&hand=right&robot" title="The ADAPT hand at your wrist, in the room" loading="lazy"></iframe>

In **Room**, with **Robot** on, the amber ADAPT hand is where the robot goes: at your wrist, its
own wrist straight. While `metaquest-teleop` runs it is what the robot gets, so it holds still
while you pinch your left hand. The terminal shows the same ADAPT hand, in yellow, next to yours.

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

| ADAPT joint | From your hand |
|---|---|
| each finger's MCP, PIP, DIP | your bend at the base, middle and tip joints: PIP and DIP can differ |
| each finger's spread | your sideways spread, with the opposite sign: the ADAPT hand counts towards the pinky |
| thumb MCP, IP | your thumb's bend at its middle and tip joints |
| thumb CMC1 | the angle that points the robot's thumb where your thumb's first bone points |
| thumb CMC2 | the same, measured from a relaxed thumb (below) |

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

`adapt.COUPLING @ motors` gives the joint angles the robot will actually reach.

## The thumb

At zero, the ADAPT thumb sticks straight out sideways, about 65° further from the index than a
relaxed thumb, beyond its CMC2 range of ±29°. So CMC2 is measured from a relaxed thumb: yours
relaxed puts the robot's in the middle of its range, and moving yours moves it as much.
`adapt.THUMB_REST` is that 65°; `joint_angles(hand, thumb_rest=0)` gives the exact angle.

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
