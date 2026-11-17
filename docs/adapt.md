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

## Calibrate it to your hand

Each ADAPT joint follows one angle of yours (the thumb's CMC2 two) through **points**: at this
angle of yours, the ADAPT joint is at that angle. The library comes with its points
([below](#joints-the-calibration)), the same wherever it is installed. To make new ones:

```bash
metaquest-teleop --calibration
```

It opens the 3D view on the ADAPT hand, with a **Calibrate** panel at the bottom right. Then,
for each point:

1. **Pick the joint** in the panel, say *thumb IP*.
2. **Make the pose** with your hand and press **Space** (or **Freeze**): your hand holds still in
   the view, and you can let go of the pose. The panel shows your angles that the joint follows.
3. **Drag the ADAPT slider** until the ADAPT hand looks right: the joint moves as you drag.
4. **Add point**. The ADAPT hand follows it from now on.
5. Press **Space** again to unfreeze, and go on with the next pose.

The panel lists the joint's points: **×** removes one, **Reset joint** removes yours and puts back
the points the library comes with. A joint needs two points at least (the thumb's CMC2 three).

While you drag a slider, only that joint moves. Once you add the point, the fit places the
fingers around the new thumb, as it will on the robot: in a pinch, it brings the ADAPT's fingertip
towards its thumb tip.

Each time, the calibration goes to a new file in `~/.config/metaquest-teleop/calibrations/`,
named by when you started, say `adapt-2026-11-17-103000.json`: all of it, saved at every point.
The files stay there as backups; they are small. `metaquest-teleop` itself always uses the
library's calibration, unless you name a file:

| Command | |
|---|---|
| `metaquest-teleop --calibration` | calibrate in the 3D view, from the library's points; saved to a new file |
| `metaquest-teleop --calibration-file FILE` | the ADAPT hand with that calibration instead, to try it |
| `metaquest-teleop --calibration --calibration-file FILE` | calibrate on from that file; saved to a new file |

### Make it the library's

When a calibration is right, make it the library's. In the repository:

```bash
python scripts/set_calibration.py ~/.config/metaquest-teleop/calibrations/adapt-2026-11-17-103000.json
```

It writes the file's points in `adapt.CALIBRATION` (`src/metaquest_teleop/adapt.py`) and in the
3D view, and lists the joints that changed. Then run the tests, say so in `CHANGELOG.md`, and
release: `pip install -U metaquest-teleop` brings it to every computer.

### Some advice

- **Start with the ends of a joint's range**, open and fully bent: two points are a straight line
  through them. Add one in between only where the ADAPT joint goes wrong.
- **Keep points apart.** Two points a few degrees of yours apart, with very different ADAPT
  angles, make the joint jump between them.
- With the fit on (the default), the fit places the **fingers**, so the panel offers the thumb's
  joints. To calibrate the fingers too, use `--no-adapt-fit`, while calibrating and after.

### The file

```json
{
  "thumb_CMC1": [[5, 0], [95, 86]],
  "thumb_CMC2": [[0, 30, 20], [20, 35, 0], [45, 25, -20], [70, 20, -60]],
  "thumb_MCP": [[0, 0], [65, 86]],
  "thumb_IP": [[0, 0], [20, 30], [45, 90]]
}
```

One line per joint (here the thumb's; the fingers' follow); each point is your angle (for CMC2 your base and spread), then the ADAPT
joint's, in degrees. You can edit it by hand. A file with only some joints gives the others the
library's points.

### In Python

```python
from metaquest_teleop import adapt

adapt.CALIBRATION["thumb_IP"][30] = 50            # your IP at 30°: its IP at 50°
adapt.CALIBRATION["thumb_CMC2"][(45, 25)] = -20   # your base 45° and spread 25°: its CMC2 at -20°
adapt.save_calibration("mine.json")
adapt.load_calibration("mine.json")               # or one metaquest-teleop --calibration saved
adapt.reset_calibration()                         # back to the library's

print(adapt.your_angles(hand))                    # your angles now, by name, in degrees
print(adapt.calibrated("thumb_CMC2", 10, 40))     # its CMC2 at your base 10°, spread 40°
```

## Joints: the pose closest to yours

The ADAPT hand is not your hand: its bones have other lengths, its thumb sits elsewhere on the
palm, and its joints turn about other axes. Its **thumb** follows the calibration
([below](#joints-the-calibration)). Its **fingers** take the pose that puts them where yours
are, around that thumb, through its forward kinematics:

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
it bent the ADAPT's MCP to its limit in most grasps, whatever yours did. The catch is pinches:
unless the calibration turns CMC2 towards the fingers when you pinch, the ADAPT's thumb tip
stays short of the fingertip.

## Joints: the calibration

`adapt.joint_angles(hand, fit=False)`, `adapt.FIT = False`, or `metaquest-teleop --no-adapt-fit`
maps the whole ADAPT hand joint for joint; with the fit, the thumb only, and the fit starts from
this pose. Each ADAPT joint follows angles of yours, those the dashboard and the 3D view show
(`adapt.FOLLOWS`), through its points (`adapt.CALIBRATION`):

| ADAPT joint | Follows your | Its range (°) |
|---|---|---|
| thumb CMC1 | thumb **turn**: its first bone, turned about the hand's long axis from sideways towards the palm's front | 0 to 86 |
| thumb CMC2 | thumb **base** and **spread** | −70 to 30 |
| thumb MCP | thumb **middle** | 0 to 86 |
| thumb IP | thumb **tip** | 0 to 90 |
| each finger's MCP | its **base** | 0 to 86 |
| each finger's PIP | its **middle** | 0 to 69 |
| each finger's DIP | its **tip** | 0 to 69 |
| index spread | its **spread**, towards the thumb | −17 to 0 |
| ring spread, pinky spread | their **spread** | 0 to 17 |

The middle finger's spread follows nothing: it does not move.

With **one angle of yours**, a joint goes straight from one point to the next, and on in a
straight line beyond the first and the last: with two points, the line through them. With
**two** (the thumb's CMC2), it follows the smoothest surface through the points (a thin-plate
spline): with three, the plane through them; more bend it just enough to pass through each. A
point bends the surface around it, and further away too, the more it disagrees with the others.
Always within the joint's range.

The library's first points were typical ranges, set so that, as with the real hand's poses of
HumanManipulationVMC (Santello et al., 1998): your **open hand gives home**, all zeros; a
**power grasp gives PC1** (thumb CMC1 65°, MCP 50°; fingers 55° and 65°); a **pinch gives PC2**
(thumb 50°, MCP 35°; index 25° and 40°); and the thumb's IP turns twice as far as yours. The 3D
view of `metaquest-teleop` uses the same calibration, and fits or not as the library does.

The ADAPT thumb's CMC joints are a gimbal: CMC2 swings its first bone from sideways towards the
fingers, then CMC1 turns it about the hand's long axis towards the palm's front. Your thumb's
**turn** is read the same way, so its CMC1 follows yours.

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
| thumb IP | 0 to 90° |
| each finger's PIP and DIP | 0 to 69° |
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
