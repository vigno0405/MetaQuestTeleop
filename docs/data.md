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

Each finger goes from its base to its tip, so the tips are 4, 9, 14, 19 and 24. Each joint's own
axes: −z along the bone towards the fingertip, −y out of the palm.

## Angles

`hand.angles` has one row per finger, thumb to pinky, and four columns, in radians:

| | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| thumb | CMC flexion | CMC abduction | MCP flexion | IP flexion |
| fingers | MCP flexion | MCP abduction | PIP flexion | DIP flexion |

Flexion is positive when bending towards the palm, abduction when moving towards the thumb.
An open, flat hand reads about 0, except the thumb's CMC. `hand.angle_dict` gives the same
angles by name, such as `index_pip_flex`.
