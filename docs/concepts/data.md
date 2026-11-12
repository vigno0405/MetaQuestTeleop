# The data

## Units and space

Metres, radians, and quaternions as (x, y, z, w). Every pose is in WebXR's `local-floor`
space:

- the origin is on the floor, below where the headset was when you pressed Start;
- **+y is up**;
- **−z is the direction the headset faced** at Start, and +x is to its right.

Holding the Meta button recentres the view, which moves this origin. If the headset offers
no floor level, the page falls back to the `local` space, whose origin is at the headset's
starting position instead of the floor; `quest.headset["space"]` says which one is in use.

## Frames

Each frame the headset renders gives one {py:class}`~metaquest_teleop.Frame`:

| Field | |
|---|---|
| `seq` | frame counter from the headset |
| `time` | the headset's clock, seconds: the spacing of frames as the headset rendered them |
| `received` | `time.time()` on this computer when the frame arrived: its age, and the time to log |
| `head` | the headset's {py:class}`~metaquest_teleop.Pose`, or `None` |
| `left`, `right` | a {py:class}`~metaquest_teleop.Hand`, or `None` while that hand is not tracked |

A hand is reported whole or not at all: when the headset loses one joint, the frame carries
no hand on that side.

## Joints

Each hand has 25 joints, named as in the WebXR Hand Input specification. Their order is the
order of the rows of `hand.positions` and `hand.quaternions`, and of `metaquest_teleop.JOINTS`:

| Index | Joint | Parent |
|---|---|---|
| 0 | `wrist` | |
| 1 | `thumb-metacarpal` | 0 |
| 2 | `thumb-phalanx-proximal` | 1 |
| 3 | `thumb-phalanx-distal` | 2 |
| 4 | `thumb-tip` | 3 |
| 5 | `index-finger-metacarpal` | 0 |
| 6 | `index-finger-phalanx-proximal` | 5 |
| 7 | `index-finger-phalanx-intermediate` | 6 |
| 8 | `index-finger-phalanx-distal` | 7 |
| 9 | `index-finger-tip` | 8 |
| 10 | `middle-finger-metacarpal` | 0 |
| 11 | `middle-finger-phalanx-proximal` | 10 |
| 12 | `middle-finger-phalanx-intermediate` | 11 |
| 13 | `middle-finger-phalanx-distal` | 12 |
| 14 | `middle-finger-tip` | 13 |
| 15 | `ring-finger-metacarpal` | 0 |
| 16 | `ring-finger-phalanx-proximal` | 15 |
| 17 | `ring-finger-phalanx-intermediate` | 16 |
| 18 | `ring-finger-phalanx-distal` | 17 |
| 19 | `ring-finger-tip` | 18 |
| 20 | `pinky-finger-metacarpal` | 0 |
| 21 | `pinky-finger-phalanx-proximal` | 20 |
| 22 | `pinky-finger-phalanx-intermediate` | 21 |
| 23 | `pinky-finger-phalanx-distal` | 22 |
| 24 | `pinky-finger-tip` | 23 |

The thumb has no intermediate phalanx, so it has four joints and the fingers five. The parent
column is `metaquest_teleop.hands.PARENT`.

**Joint axes.** Each joint's own axes, on both hands: **−Z along the bone towards the
fingertip, −Y out of the palm**, and +X completing a right-handed frame.

| | |
|---|---|
| `hand.positions` | (25, 3) joint positions |
| `hand.quaternions` | (25, 4) joint orientations |
| `hand.rotations` | (25, 3, 3) the same orientations as rotation matrices |
| `hand.local_quaternions` | (25, 4) each joint's rotation relative to its parent; the wrist's is absolute |
| `hand.wrist`, `hand.joint(name)` | one joint's {py:class}`~metaquest_teleop.Pose`: `position`, `quaternion`, `rotation`, `matrix` |
| `hand.pinch` | distance from the thumb tip to the index tip, m |

## Angles

`hand.angles` is a (5, 4) array in radians, one row per finger from thumb to pinky
(`metaquest_teleop.FINGERS`):

| | column 0 | column 1 | column 2 | column 3 |
|---|---|---|---|---|
| thumb | CMC flexion | CMC abduction | MCP flexion | IP flexion |
| index … pinky | MCP flexion | MCP abduction | PIP flexion | DIP flexion |

`hand.angle_dict` gives the same 20 angles by name, from `thumb_cmc_flex` to `pinky_dip_flex`
(`metaquest_teleop.ANGLE_NAMES`, in the order of `hand.angles.ravel()`).

**Signs.** Flexion is positive towards the palm; abduction is positive towards the thumb side.
Both hold on both hands, so a left and a right hand in the same posture read the same angles.

**Zero.** Each angle is the bend of a bone against its parent joint's axes. An open, flat
hand reads about 0 everywhere except the thumb's CMC, which is measured against the wrist and
is not 0 at rest. For a different convention, start from `hand.local_quaternions` or the raw
joint poses.

## Rate

The page asks the headset for its highest frame rate, 72 to 120 Hz depending on the model,
and sends every frame. Hand tracking itself may update less often than the display, so
consecutive frames can carry the same hands: `quest.rates()["changed_hz"]`, and the
dashboard's *hands changed* count, give the frames per second that carry new hand data.
