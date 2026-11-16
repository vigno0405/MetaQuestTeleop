---
hide-toc: true
---

# ADAPT Hand

`metaquest_teleop.adapt` turns your hand into the ADAPT hand's 20 joint angles and 13 motor
angles: the pose, within the robot's limits, that puts the ADAPT hand closest to yours. It also
gives the pose of your wrist. Its geometry, joint ranges and motor order are those of
`virtualmodelcontrol.robots.adapt`.

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

## Joints: the pose closest to yours

The ADAPT hand is not your hand: its bones have other lengths, its thumb sits elsewhere on the
palm, and its joints turn about other axes. Its **thumb** follows yours joint for joint: its CMC1,
MCP and IP through your ranges ([below](#joints-joint-for-joint)), its CMC2 through your poses
([below](#the-thumbs-cmc2)). Its **fingers** take the pose that puts them where yours are, around
that thumb, through its forward kinematics:

- **your knuckles on its knuckles**: your hand, scaled and shifted so that your four knuckles
  (index to pinky) fall on the ADAPT's;
- **each finger's PIP, DIP and tip on yours**, the tip counting most;
- **a pinch closes in**: when your thumb tip comes near a fingertip, the ADAPT's fingertip goes
  towards its thumb tip, which then counts the most.

Only poses the ADAPT hand can take count: those of its 13 motors (each DIP mimics its PIP, one
motor spreads the fingers: [below](#a-pose-the-adapt-hand-can-take)), within its limits. Where a
limit stops a joint, the others make up for it as best they can.

The fit is a least-squares fit (Levenberg-Marquardt) over the finger motors. It starts from the
joint-for-joint pose (below), takes a few milliseconds, and pulls very slightly towards that
pose, which picks one pose when several fit as well. Fingers shaped exactly as an ADAPT pose get
that pose back.

The thumb is not fitted because the two thumbs differ too much to match their shapes: fitting
it bent the ADAPT's MCP to its limit in most grasps, whatever yours did. Joint for joint, its MCP
and IP follow yours. The catch is pinches: unless your poses turn CMC2 towards the fingers when
you pinch, the ADAPT's thumb tip stays short of the fingertip.

## Joints: joint for joint

`adapt.joint_angles(hand, fit=False)`, `adapt.FIT = False`, or `metaquest-teleop --no-adapt-fit`
maps the ADAPT hand joint for joint instead: each ADAPT joint follows the same joint of yours,
your range of motion stretched onto its own. The angle of yours in the first column of
`adapt.HUMAN_RANGES` gives its lowest angle, the one in the second its highest, linearly in
between. The fit starts from this pose.

| ADAPT joint | Follows | Your range (°) | Its range (°) |
|---|---|---|---|
| thumb CMC1 | your thumb's first bone, turned about the hand's long axis from sideways towards the palm's front | 5 to 95 | 0 to 86 |
| thumb CMC2 | your thumb's base and spread: [below](#the-thumbs-cmc2) | | −70 to 30 |
| thumb MCP, IP | your thumb's bend at its middle and tip joints | 0 to 65, 0 to 40 | 0 to 86, 0 to 69 |
| each finger's MCP | your bend at the base | 0 to 90 | 0 to 86 |
| each finger's PIP, DIP | your bend at the middle and tip joints | 0 to 90, 0 to 60 | 0 to 69 |
| index spread | your index spread towards the thumb | 20 to 0 | −17 to 0 |
| ring, pinky spread | your spread towards the pinky | 0 to 15, 0 to 25 | 0 to 17 |

The ranges are typical ones, set so that, as with the real hand's poses of HumanManipulationVMC
(Santello et al., 1998): your **open hand gives home**, all zeros; a **power grasp gives PC1**
(thumb CMC1 65°, MCP 50°; fingers 55° and 65°); a **pinch gives PC2** (thumb 50°, MCP 35°; index
25° and 40°). The thumb's IP turns about twice as far as yours: your 0 to 40° is all of its range.
To fit your hand, change `adapt.HUMAN_RANGES`:

```python
from metaquest_teleop import adapt

adapt.HUMAN_RANGES["thumb_MCP"] = (0, 55)  # your thumb bends 55° at most: that is its 86°
```

The 3D view of `metaquest-teleop` uses the same ranges, and fits or not as the library does.

The ADAPT thumb's CMC joints are a gimbal: CMC2 swings its first bone from sideways towards the
fingers, then CMC1 turns it about the hand's long axis towards the palm's front. Your thumb's
first bone is read the same way, so its CMC1 follows yours.

## The thumb's CMC2

The ADAPT thumb's CMC2 follows your thumb's **base** and **spread**, the two thumb angles the
dashboard shows (the thumb's row of `Hand.angles`), through poses of yours that give a CMC2:

| Your thumb's base | Your thumb's spread | ADAPT CMC2 |
|---|---|---|
| 20° | 35° | 0° |
| 70° | 20° | −60° |
| 0° | 30° | 20° |

CMC2 follows the smoothest surface through them (a thin-plate spline): a plane, bent just enough
to pass through every pose exactly, within its range of −70° to 30°. With these three poses it is
the plane through them, (100 − 12 · base + 4 · spread) / 11 degrees. It does so in the fit as well
as joint for joint. To fit your hand, change, add or remove poses, at any time (at least three,
not on one line). A pose bends the surface around it, and further away too, the more it
disagrees with the others: check your other poses after adding one.

```python
from metaquest_teleop import adapt

adapt.CMC2_POSES[(45, 25)] = -20  # base 45°, spread 25°: CMC2 -20°
print(adapt.cmc2(10, 40))          # the CMC2 you get at base 10°, spread 40°, degrees
```

The 3D view of `metaquest-teleop` follows the same poses.

## A pose the ADAPT hand can take

The ADAPT hand's joints are coupled, as in VirtualModelControl and HumanManipulationVMC:

- **each finger's DIP mimics its PIP**: one motor turns both through the same cable, by the
  same angle. So PIP and DIP are always equal. The fit puts them where your finger's joints and
  tip are best matched; joint for joint, both take the mean of yours, which keeps your
  fingertip pointing where it points (PIP + DIP is the same).
- **one motor spreads the index, ring and pinky** together, the middle finger not at all. The
  spreads take the best fit of yours.

So `adapt.joint_angles(hand)` is always a pose the robot can take: the dashboard, `--print_joints`
and `/metaquest/adapt/joint_states` show what the robot does. `joint_angles(hand, coupled=False)`
gives the joint-for-joint angles before that, joint by joint, PIP and DIP apart.

## Limits

Every joint is kept within its range, as the robot can go:

| Joint | Range |
|---|---|
| thumb CMC1, MCP; each finger's MCP | 0 to 86° |
| thumb CMC2 | −70 to 30° |
| thumb IP; each finger's PIP and DIP | 0 to 69° |
| spread: index / middle / ring and pinky | −17 to 0° / none / 0 to 17° |

`adapt.JOINT_LIMITS` has them in radians. `joint_angles(hand, clip=False)` fits without them:
the pose of the ADAPT hand closest to yours if its joints went anywhere.

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
