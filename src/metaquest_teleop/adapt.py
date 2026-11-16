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

Its own wrist stays straight, at 0, 0 (:data:`WRIST_MOTORS`): the arm moves and turns the hand,
with its base at :func:`wrist_pose`.
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

#: The ADAPT hand's two wrist motors (13 and 14 on its bus), and where they stay: at 0, 0, held by
#: a PID (position control), as in ``virtualmodelcontrol``. The wrist never bends: the arm turns
#: the hand instead.
WRIST_MOTORS = ("wrist_yaw", "wrist_pitch")
WRIST_ANGLES = (0.0, 0.0)

#: The range of each joint, (low, high) in radians.
JOINT_LIMITS = {
    "thumb_CMC1": (0.0, 1.5), "thumb_CMC2": (-0.5, 0.5), "thumb_MCP": (0.0, 1.5), "thumb_IP": (0.0, 1.2),
    "index_spread": (-0.3, 0.0), "index_MCP": (0.0, 1.5), "index_PIP": (0.0, 1.2), "index_DIP": (0.0, 1.2),
    "middle_spread": (0.0, 0.0), "middle_MCP": (0.0, 1.5), "middle_PIP": (0.0, 1.2), "middle_DIP": (0.0, 1.2),
    "ring_spread": (0.0, 0.3), "ring_MCP": (0.0, 1.5), "ring_PIP": (0.0, 1.2), "ring_DIP": (0.0, 1.2),
    "pinky_spread": (0.0, 0.3), "pinky_MCP": (0.0, 1.5), "pinky_PIP": (0.0, 1.2), "pinky_DIP": (0.0, 1.2),
}  # fmt: skip

#: Your range of motion for each ADAPT joint, in degrees: the angles of yours that give the low
#: and the high end of its range (:data:`JOINT_LIMITS`); linearly in between, held at the ends
#: beyond. Each ADAPT joint follows the same joint of yours, as your hand's range stretched onto
#: the robot's. Typical ranges, set so that an open hand gives all zeros (the hand's home), a
#: power grasp about PC1 and a pinch about PC2 of HumanManipulationVMC's PoseControl (Santello
#: et al., 1998): change them to fit your hand, at any time. A spread is yours towards the thumb (so the index
#: goes the other way round), the thumb's CMC1 and CMC2 are read as the ADAPT's are built (see
#: :func:`joint_angles`).
HUMAN_RANGES = {
    "thumb_CMC1": (5, 95), "thumb_CMC2": (16, 74), "thumb_MCP": (0, 65), "thumb_IP": (0, 80),
    "index_spread": (20, 0), "index_MCP": (0, 90), "index_PIP": (0, 90), "index_DIP": (0, 60),
    "middle_spread": (0, 0), "middle_MCP": (0, 90), "middle_PIP": (0, 90), "middle_DIP": (0, 60),
    "ring_spread": (0, -15), "ring_MCP": (0, 90), "ring_PIP": (0, 90), "ring_DIP": (0, 60),
    "pinky_spread": (0, -25), "pinky_MCP": (0, 90), "pinky_PIP": (0, 90), "pinky_DIP": (0, 60),
}  # fmt: skip

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
_FIT = np.linalg.pinv(COUPLING)  # the least-squares motor angles for 20 joint angles


def _motor_ranges() -> tuple[np.ndarray, np.ndarray]:
    """For each motor, the angles that keep every joint it turns within JOINT_LIMITS."""
    low, high = np.full(13, -np.inf), np.full(13, np.inf)
    for j, row in enumerate(COUPLING):
        for m in np.flatnonzero(row):
            a, b = sorted((_LOW[j] / row[m], _HIGH[j] / row[m]))
            low[m], high[m] = max(low[m], a), min(high[m], b)
    return low, high


_MOTOR_LOW, _MOTOR_HIGH = _motor_ranges()


def _rotation(axis, angle: float) -> np.ndarray:
    """The rotation by ``angle`` about ``axis`` (right-hand rule)."""
    x, y, z = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    c, s, t = np.cos(angle), np.sin(angle), 1.0 - np.cos(angle)
    return np.array([[c + x * x * t, x * y * t - z * s, x * z * t + y * s],
                     [y * x * t + z * s, c + y * y * t, y * z * t - x * s],
                     [z * x * t - y * s, z * y * t + x * s, c + z * z * t]])


def _yours(hand: Hand) -> np.ndarray:
    """(20,) your angle at each ADAPT joint, radians, measured as the ADAPT's is."""
    a = hand.angles
    # Your thumb's first bone, in the ADAPT axes, read as the ADAPT's CMC joints turn theirs: CMC2
    # swings it from sideways towards the fingers, then CMC1 turns it about the hand's long axis,
    # from sideways towards the palm's front.
    d = _FROM_WEBXR @ (hand.rotations[0].T @ (hand.positions[2] - hand.positions[1]))
    d = d / np.linalg.norm(d)
    out = [np.arctan2(d[1], -d[0]), np.arcsin(np.clip(d[2], -1.0, 1.0)), a[0, 2], a[0, 3]]
    for f in range(1, 5):
        out += [a[f, 1], a[f, 0], a[f, 2], a[f, 3]]
    return np.array(out)


def _wanted(hand: Hand) -> np.ndarray:
    """(20,) your range stretched onto the ADAPT's, joint by joint (:data:`HUMAN_RANGES`)."""
    yours = _yours(hand)
    low, high = np.radians(np.array([HUMAN_RANGES[j] for j in JOINTS], dtype=float)).T  # as they are now
    span = high - low
    share = np.divide(yours - low, span, out=np.zeros(20), where=span != 0.0)
    return _LOW + share * (_HIGH - _LOW)


def _fit(joints: np.ndarray, clip: bool) -> np.ndarray:
    motors = _FIT @ joints
    return np.clip(motors, _MOTOR_LOW, _MOTOR_HIGH) if clip else motors


def joint_angles(hand: Hand, clip: bool = True, coupled: bool = True) -> np.ndarray:
    """(20,) the ADAPT joint angles for your hand, radians, in :data:`JOINTS` order: a pose it can take.

    Each ADAPT joint follows the same joint of yours, your range of motion stretched onto its
    range (:data:`HUMAN_RANGES`). A finger's spread, MCP, PIP and DIP follow yours. The thumb's
    MCP and IP follow yours, and its CMC1 and CMC2 are read off your thumb's first bone as the
    ADAPT's are built: CMC2 how far it points along the fingers, CMC1 how far it has turned about
    the hand's long axis, from sideways towards the palm's front.

    Then the pose the ADAPT hand can take, as in ``virtualmodelcontrol``: a finger's DIP mimics its
    PIP (both the mean of the two), and one motor spreads the fingers (the best fit of the three).
    ``coupled=False`` gives the angles before that, joint by joint. ``clip`` keeps every joint
    within :data:`JOINT_LIMITS`.
    """
    wanted = _wanted(hand)
    joints = COUPLING @ _fit(wanted, clip) if coupled else wanted
    return np.clip(joints, _LOW, _HIGH) if clip else joints  # coupled: only rounding to take off


def motor_angles(source, clip: bool = True) -> np.ndarray:
    """(13,) the ADAPT motor angles, radians, in :data:`MOTORS` order: targets for a motor PID.

    ``source`` is a :class:`~metaquest_teleop.Hand` or 20 joint angles. 13 motors cannot set any
    20 joints, so this is the least-squares fit through :data:`COUPLING`: a finger's PIP motor
    takes the mean of its PIP and DIP, and the spread motor the best fit of the index, ring and
    pinky spreads. For :func:`joint_angles`, a pose the hand can take, it is exact. ``clip`` keeps
    each motor where every joint it turns stays within :data:`JOINT_LIMITS`.
    """
    joints = _wanted(source) if isinstance(source, Hand) else np.asarray(source, dtype=float)
    return _fit(joints, clip)


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
