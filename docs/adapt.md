---
hide-toc: true
---

# ADAPT Hand

`metaquest_teleop.adapt` turns your hand into the ADAPT hand's 20 joint angles and 13 motor
angles, and gives the pose of your wrist. Its geometry, joint ranges and motor order are those of
`virtualmodelcontrol.robots.adapt`.

## Try it

<iframe class="demo" src="_static/view.html?demo&mode=adapt&hand=right" title="Your hand next to the ADAPT hand it drives" loading="lazy"></iframe>

Your hand is on the left; the ADAPT hand on the right is where its motors would put it. Amber
angles are outside the robot's range. While `metaquest-teleop` runs, the same view is at
**http://localhost:8012/view?mode=adapt**.

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

The 13 motors leave the ADAPT wrist out: it stays at (0, 0). Use `joints` for a controller in
joint space, such as VMC, and `motors` as targets for a PID on the motors.

## Joints: from your hand

| ADAPT joint | From your hand |
|---|---|
| each finger's MCP, PIP, DIP | your bend at the base, middle and tip joints, as they are: PIP and DIP can differ |
| each finger's spread | your sideways spread, with the opposite sign: the ADAPT hand counts towards the pinky |
| thumb MCP, IP | your thumb's bend at its middle and tip joints |
| thumb CMC1, CMC2 | the two angles that point the robot's thumb where your thumb's first bone points |

`adapt.joint_angles(hand, clip=True)` keeps every joint within its range, `adapt.JOINT_LIMITS`.

## Motors: 13 for 20 joints

The ADAPT hand has fewer motors than joints, so `adapt.motor_angles` finds the motor angles that
come closest to the joints:

- each thumb joint and each finger's MCP has its own motor, which follows it exactly;
- one motor per finger turns its PIP and DIP together: it takes their **mean**;
- one motor spreads the index, ring and pinky (the middle finger does not move): it takes the
  **best fit** of the three.

It first keeps every joint within its range (`clip=False` skips that). `adapt.COUPLING @ motors`
gives the joint angles the robot will actually reach.

## The wrist

`adapt.wrist_pose(hand)` is your wrist's position, in the room in metres, and its orientation,
with the axes of the ADAPT hand:

- **+z** towards the fingertips,
- **+y** on the palm side,
- **−x** towards the thumb.

A robot arm that puts the ADAPT hand's base there makes it face the way your hand does.

## The thumb

At zero, the ADAPT thumb sticks straight out sideways, much further from the index than a thumb
at rest. Your thumb's first bone usually needs CMC2 beyond its ±29° range, so CMC2 often sits at
its limit and shows in amber.
