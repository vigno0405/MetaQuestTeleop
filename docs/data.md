# The data

## Units and axes

Metres, radians, and quaternions as (x, y, z, w). Positions are measured from the floor below
where the headset was when you pressed Start:

- **x** to the right,
- **y** up,
- **−z** forward, where you were looking.

## Joints

Each hand has 25 joints, in this order (`metaquest_teleop.JOINTS`):

| Joints | |
|---|---|
| 0 | wrist |
| 1–4 | thumb |
| 5–9 | index |
| 10–14 | middle |
| 15–19 | ring |
| 20–24 | pinky |

Each finger goes from its base to its tip, so the tips are 4, 9, 14, 19 and 24. Each joint
also has an orientation: its −z axis points along the bone towards the fingertip, and its −y
axis out of the palm.

## Angles

`hand.angles` has one row per finger, thumb to pinky, and four columns, in radians:

| Column | Angle |
|---|---|
| 0 | bend at the base of the finger |
| 1 | spread: how far the finger moves sideways, at its base |
| 2 | bend at the middle joint |
| 3 | bend at the joint nearest the tip |

Bending towards the palm and spreading towards the thumb are positive, on both hands. An open,
flat hand reads about 0 everywhere, except the base of the thumb.

`hand.angle_dict` gives the same angles by name, such as `index_pip_flex`. The names use the
medical terms: *flex* is bend and *abd* is spread; the joints are, from the base, CMC, MCP and
IP for the thumb, and MCP, PIP and DIP for the fingers.
