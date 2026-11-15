"""Your hand on the ADAPT hand: its 20 joint angles, its 13 motor angles and the wrist's pose.

    from metaquest_teleop import adapt

    joints = adapt.joint_angles(hand)  # (20,) rad, in JOINTS order, within JOINT_LIMITS
    motors = adapt.motor_angles(hand)  # (13,) rad, in MOTORS order: targets for a motor PID
    wrist = adapt.wrist_pose(hand)     # the wrist, with the ADAPT base frame's axes

The ADAPT hand is a right hand: a thumb with joints CMC1, CMC2, MCP and IP, and four fingers with
joints spread, MCP, PIP and DIP. Its geometry, joint ranges, motor order and transmissions are
those of ``virtualmodelcontrol.robots.adapt``. Its base frame: +z towards the fingertips, +y on
the palm side, the thumb towards -x. Flexion is positive; a finger's spread is positive towards
the pinky.
"""

from __future__ import annotations

import numpy as np

from .fake import quaternion
from .hands import Hand, Pose

#: The ADAPT hand's 20 joints, in the order of :func:`joint_angles`.
JOINTS = (
    "thumb_CMC1", "thumb_CMC2", "thumb_MCP", "thumb_IP",
    "index_spread", "index_MCP", "index_PIP", "index_DIP",
    "middle_spread", "middle_MCP", "middle_PIP", "middle_DIP",
    "ring_spread", "ring_MCP", "ring_PIP", "ring_DIP",
    "pinky_spread", "pinky_MCP", "pinky_PIP", "pinky_DIP",
)  # fmt: skip

#: The ADAPT hand's 13 motors, in the order of :func:`motor_angles`. The two wrist motors are
#: not among them: they hold the wrist still.
MOTORS = (
    "thumb_CMC1", "thumb_CMC2", "thumb_MCP", "thumb_IP", "spread",
    "index_MCP", "index_PIP", "middle_MCP", "middle_PIP",
    "ring_MCP", "ring_PIP", "pinky_MCP", "pinky_PIP",
)  # fmt: skip

#: The range of each joint, (low, high) in radians.
JOINT_LIMITS = {
    "thumb_CMC1": (0.0, 1.5), "thumb_CMC2": (-0.5, 0.5), "thumb_MCP": (0.0, 1.5), "thumb_IP": (0.0, 1.2),
    "index_spread": (-0.3, 0.0), "index_MCP": (0.0, 1.5), "index_PIP": (0.0, 1.2), "index_DIP": (0.0, 1.2),
    "middle_spread": (0.0, 0.0), "middle_MCP": (0.0, 1.5), "middle_PIP": (0.0, 1.2), "middle_DIP": (0.0, 1.2),
    "ring_spread": (0.0, 0.3), "ring_MCP": (0.0, 1.5), "ring_PIP": (0.0, 1.2), "ring_DIP": (0.0, 1.2),
    "pinky_spread": (0.0, 0.3), "pinky_MCP": (0.0, 1.5), "pinky_PIP": (0.0, 1.2), "pinky_DIP": (0.0, 1.2),
}  # fmt: skip

#: The CMC2 angle of a relaxed thumb, 65° in radians. At zero the ADAPT thumb sticks out sideways,
#: well beyond a relaxed thumb, and its CMC2 range (±29°) cannot reach where yours is; so CMC2 is
#: measured from a relaxed thumb: yours relaxed puts the robot's in the middle of its range.
THUMB_REST = float(np.radians(65.0))

DIGITS = ("thumb", "index", "middle", "ring", "pinky")

# The geometry of virtualmodelcontrol.robots.adapt, in the hand's base frame [m]: the palm, the
# base of each digit, and each joint's origin (from the previous one, all frames aligned at zero)
# and axis.
PALM_ORIGIN = np.array([-0.017826, 0.003021, -0.027998])
DIGIT_BASES = {
    "thumb": (-0.001126, 0.011348, 0.056215),
    "index": (-0.001654, 0.040836, 0.093101),
    "middle": (0.02173, 0.039146, 0.092417),
    "ring": (0.032774, 0.039367, 0.090557),
    "pinky": (0.061943, 0.039534, 0.075302),
}
DIGIT_JOINTS = {
    "thumb": (
        ((-0.014257, 0.010829, -0.007467), (0.182125, -0.177737, -0.967078)),
        ((-0.008631, 0.00194, -0.008807), (0.0, 0.983527, -0.180761)),
        ((-0.04412, -0.000957, -0.00886), (0.168863, 0.20364, -0.964373)),
        ((-0.031464, -0.001054, -0.005732), (0.168863, 0.20364, -0.964373)),
    ),
    "index": (
        ((-0.006284, 0.000712, 0.005798), (0.140517, 0.943569, -0.299886)),
        ((-0.001682, -0.00044, 0.009499), (-0.981214, 0.092278, -0.169421)),
        ((-0.005287, 0.012722, 0.037552), (-0.981214, 0.092278, -0.169421)),
        ((-0.003966, 0.009542, 0.028164), (-0.981214, 0.092278, -0.169421)),
    ),
    "middle": (
        ((-0.005011, 0.000697, 0.006929), (0.036359, 0.936295, -0.349327)),
        ((0.000289, -0.000149, 0.009651), (-0.998268, 0.050205, 0.030661)),
        ((0.002081, 0.015643, 0.042143), (-0.998268, 0.050205, 0.030661)),
        ((0.001387, 0.010428, 0.028095), (-0.998268, 0.050205, 0.030661)),
    ),
    "ring": (
        ((0.006841, 0.000228, 0.005174), (-0.055584, 0.937022, -0.34482)),
        ((0.002501, -0.000155, 0.009326), (-0.964998, 0.038236, 0.259457)),
        ((0.010252, 0.013887, 0.036084), (-0.964998, 0.038236, 0.259457)),
        ((0.007689, 0.010415, 0.027062), (-0.964998, 0.038236, 0.259457)),
    ),
    "pinky": (
        ((-0.001073, -0.000153, 0.008511), (-0.211896, 0.947676, -0.238768)),
        ((0.004931, -0.000503, 0.008288), (-0.859324, -0.064308, 0.507372)),
        ((0.014895, 0.010006, 0.026496), (-0.859324, -0.064308, 0.507372)),
        ((0.009309, 0.006254, 0.016559), (-0.859324, -0.064308, 0.507372)),
    ),
}
TIP_OFFSET = np.array([0.0, 0.0, 0.0175])  # from the last joint, in its frame

# Transmissions: joint angle per motor angle.
_FINGER_TRANSMISSIONS = {  # motor pulley, finger pulley, PIP cable constant [m]
    "index": (0.005, 0.00304, 0.0109),
    "middle": (0.005, 0.00304, 0.01127),
    "ring": (0.005, 0.00304, 0.0109),
    "pinky": (0.005, 0.00304, 0.00967),
}
_THUMB_TRANSMISSION = {"r_motor": 0.005, "CMC1_pulley": 0.01346, "CMC2_pulley": 0.00883,
                       "MCP_c": 0.00605, "IP_c": 0.00577}
_SPREAD_RATIOS = {"index": 1.0, "middle": 0.0, "ring": -1.0, "pinky": -1.5}
_SPREAD_CORRECTION = -1.0 / 30.0


def _coupling() -> np.ndarray:
    t = _THUMB_TRANSMISSION
    c = np.zeros((20, 13))
    c[0, 0] = t["r_motor"] / t["CMC1_pulley"]
    c[1, 1] = t["r_motor"] / t["CMC2_pulley"]
    c[2, 2] = -t["r_motor"] / t["MCP_c"]
    c[3, 3] = -t["r_motor"] / t["IP_c"]
    for k, finger in enumerate(DIGITS[1:]):
        row, mcp, pip = 4 + 4 * k, 5 + 2 * k, 6 + 2 * k
        r_motor, r_pulley, c_pip = _FINGER_TRANSMISSIONS[finger]
        c[row, 4] = _SPREAD_CORRECTION * _SPREAD_RATIOS[finger]
        c[row + 1, mcp] = r_pulley / r_motor
        c[row + 2, pip] = c[row + 3, pip] = -r_motor / c_pip
    return c


#: (20, 13): joint angles = COUPLING @ motor angles. Each finger's PIP motor turns its PIP and DIP
#: joints together, and one motor spreads the index, ring and pinky (the middle finger stays).
COUPLING = _coupling()

# From the axes of your wrist (WebXR: -z towards the fingers, -y out of the palm) to the ADAPT
# base frame's (+z towards the fingers, +y on the palm side): a half turn about x.
_FROM_WEBXR = np.diag([1.0, -1.0, -1.0])

_LOW = np.array([JOINT_LIMITS[j][0] for j in JOINTS])
_HIGH = np.array([JOINT_LIMITS[j][1] for j in JOINTS])


def _rotation(axis, angle: float) -> np.ndarray:
    """The rotation by ``angle`` about ``axis`` (right-hand rule)."""
    x, y, z = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    c, s, t = np.cos(angle), np.sin(angle), 1.0 - np.cos(angle)
    return np.array([[c + x * x * t, x * y * t - z * s, x * z * t + y * s],
                     [y * x * t + z * s, c + y * y * t, y * z * t - x * s],
                     [z * x * t - y * s, z * y * t + x * s, c + z * z * t]])


def _angle_about(axis: np.ndarray, p: np.ndarray, q: np.ndarray) -> float:
    """The angle about the unit ``axis`` that turns ``p`` to ``q`` (their parts across the axis)."""
    u, v = p - axis * (axis @ p), q - axis * (axis @ q)
    return float(np.arctan2(axis @ np.cross(u, v), u @ v))


def thumb_cmc(direction) -> tuple[float, float]:
    """The CMC1 and CMC2 angles that point the ADAPT thumb's metacarpal along ``direction``.

    ``direction`` is in the ADAPT base frame. Of the two solutions, the one nearer the middle
    of the joints' ranges; a direction out of reach gives the nearest the two axes can do.
    """
    (_, a1), (_, a2), (o3, _), _ = DIGIT_JOINTS["thumb"]
    w1, w2 = np.asarray(a1) / np.linalg.norm(a1), np.asarray(a2) / np.linalg.norm(a2)
    p = np.asarray(o3) / np.linalg.norm(o3)  # the metacarpal, CMC2 to MCP, at zero
    q = np.asarray(direction, dtype=float) / np.linalg.norm(direction)
    # Two rotations about crossing axes (Paden-Kahan): find z = R2 p = R1^-1 q.
    c, w12 = w1 @ w2, np.cross(w1, w2)
    alpha = (c * (w2 @ p) - w1 @ q) / (c * c - 1.0)
    beta = (c * (w1 @ q) - w2 @ p) / (c * c - 1.0)
    g2 = (1.0 - alpha * alpha - beta * beta - 2.0 * alpha * beta * c) / (w12 @ w12)
    (lo1, hi1), (lo2, hi2) = JOINT_LIMITS["thumb_CMC1"], JOINT_LIMITS["thumb_CMC2"]
    best, cost = (0.0, 0.0), np.inf
    for gamma in ((np.sqrt(g2), -np.sqrt(g2)) if g2 > 0.0 else (0.0,)):
        z = alpha * w1 + beta * w2 + gamma * w12
        cmc1, cmc2 = _angle_about(w1, z, q), _angle_about(w2, p, z)
        here = ((2 * cmc1 - lo1 - hi1) / (hi1 - lo1)) ** 2 + ((2 * cmc2 - lo2 - hi2) / (hi2 - lo2)) ** 2
        if here < cost:
            best, cost = (cmc1, cmc2), here
    return best


def joint_angles(hand: Hand, clip: bool = True, thumb_rest: float = THUMB_REST) -> np.ndarray:
    """(20,) the ADAPT joint angles for your hand, radians, in :data:`JOINTS` order.

    Each finger's MCP, PIP and DIP take your angles as they are, so PIP and DIP may differ; its
    spread is your sideways spread with the sign of the ADAPT hand (positive towards the pinky).
    The thumb's MCP and IP take your angles; CMC1 and CMC2 point the thumb's metacarpal where
    yours points (:func:`thumb_cmc`), CMC2 less ``thumb_rest`` (:data:`THUMB_REST`; 0 for the
    exact angle). ``clip`` keeps each joint within :data:`JOINT_LIMITS`, as the robot can go.
    """
    a = hand.angles
    metacarpal = hand.rotations[0].T @ (hand.positions[2] - hand.positions[1])  # in your wrist's frame
    cmc1, cmc2 = thumb_cmc(_FROM_WEBXR @ metacarpal)
    out = [cmc1, cmc2 - thumb_rest, a[0, 2], a[0, 3]]
    for f in range(1, 5):
        out += [-a[f, 1], a[f, 0], a[f, 2], a[f, 3]]
    out = np.array(out)
    return np.clip(out, _LOW, _HIGH) if clip else out


def motor_angles(source, clip: bool = True) -> np.ndarray:
    """(13,) the ADAPT motor angles, radians, in :data:`MOTORS` order: targets for a motor PID.

    ``source`` is a :class:`~metaquest_teleop.Hand` or 20 joint angles. 13 motors cannot set 20
    joints, so this is the least-squares fit through :data:`COUPLING`: a finger's PIP motor
    takes the mean of its PIP and DIP angles, and the spread motor the best fit of the index,
    ring and pinky spreads. ``clip`` first keeps each joint within :data:`JOINT_LIMITS`.
    """
    joints = joint_angles(source, clip) if isinstance(source, Hand) else np.asarray(source, dtype=float)
    if clip:
        joints = np.clip(joints, _LOW, _HIGH)
    return np.linalg.lstsq(COUPLING, joints, rcond=None)[0]


def wrist_pose(hand: Hand) -> Pose:
    """Your wrist, in the room, with the axes of the ADAPT base frame: +z towards the fingers,
    +y on the palm side, the thumb towards -x. Put the ADAPT hand's base there (through your arm's
    calibration) and it faces as your hand does."""
    return Pose(hand.positions[0].copy(), quaternion(hand.rotations[0] @ _FROM_WEBXR))


def positions(joints) -> dict[str, np.ndarray]:
    """The ADAPT hand's shape for 20 joint angles: for each digit, (6, 3) points in its base frame
    [m]: the digit's base, its four joints and its tip."""
    joints = np.asarray(joints, dtype=float)
    out = {}
    for d, digit in enumerate(DIGITS):
        p = PALM_ORIGIN + np.asarray(DIGIT_BASES[digit])
        r = np.eye(3)
        points = [p]
        for k, (origin, axis) in enumerate(DIGIT_JOINTS[digit]):
            p = p + r @ np.asarray(origin)
            points.append(p)
            r = r @ _rotation(axis, joints[4 * d + k])
        points.append(p + r @ TIP_OFFSET)
        out[digit] = np.array(points)
    return out
