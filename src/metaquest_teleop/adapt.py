"""Your hand on the ADAPT hand: its 20 joint angles, its 13 motor angles and the wrist's pose.

    from metaquest_teleop import adapt

    joints = adapt.joint_angles(hand)  # (20,) rad, in JOINTS order, within JOINT_LIMITS
    motors = adapt.motor_angles(hand)  # (13,) rad, in MOTORS order: targets for a motor PID
    wrist = adapt.wrist_pose(hand)     # the wrist, with the ADAPT base frame's axes

Its joints take the pose, within its limits, that puts the ADAPT hand closest to yours, through
its forward kinematics (:func:`joint_angles`); or, with :data:`FIT` False, follow yours joint for
joint (:data:`HUMAN_RANGES`).

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

#: The range of each joint, (low, high) in radians, as in ``virtualmodelcontrol``. The thumb's CMC2
#: goes from -70° to 30° (the real hand turned it to -73° in the experiments of
#: HumanManipulationVMC), its IP from 0° to 90°.
JOINT_LIMITS = {
    "thumb_CMC1": (0.0, 1.5), "thumb_CMC2": (float(np.radians(-70.0)), float(np.radians(30.0))), "thumb_MCP": (0.0, 1.5),
    "thumb_IP": (0.0, float(np.radians(90.0))),
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
#: goes the other way round), the thumb's CMC1 is read as the ADAPT's is built (see
#: :func:`joint_angles`). The thumb's CMC2 is not here: :data:`CMC2_POSES`.
HUMAN_RANGES = {
    "thumb_CMC1": (5, 95), "thumb_MCP": (0, 65), "thumb_IP": (0, 45),
    "index_spread": (20, 0), "index_MCP": (0, 90), "index_PIP": (0, 90), "index_DIP": (0, 60),
    "middle_spread": (0, 0), "middle_MCP": (0, 90), "middle_PIP": (0, 90), "middle_DIP": (0, 60),
    "ring_spread": (0, -15), "ring_MCP": (0, 90), "ring_PIP": (0, 90), "ring_DIP": (0, 60),
    "pinky_spread": (0, -25), "pinky_MCP": (0, 90), "pinky_PIP": (0, 90), "pinky_DIP": (0, 60),
}  # fmt: skip

#: The ADAPT thumb's CMC2, in degrees, for poses of your thumb: (base, spread) -> CMC2, your
#: thumb's base and spread in degrees as the dashboard shows them (the thumb's row of
#: :attr:`Hand.angles <metaquest_teleop.Hand.angles>`). CMC2 follows the smoothest surface through
#: them (:func:`cmc2`): exactly each pose's, and with three poses the plane through them. At least
#: three, not on one line. Change, add or remove poses at any time.
CMC2_POSES = {(20, 35): 0, (70, 20): -60, (0, 30): 20}


def _spline(r: np.ndarray) -> np.ndarray:
    """The thin-plate spline's kernel, r^2 log r (0 at r = 0)."""
    return np.where(r > 0.0, r * r * np.log(np.where(r > 0.0, r, 1.0)), 0.0)


def _cmc2_surface() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The thin-plate spline through CMC2_POSES: the poses (n, 2), their weights (n,) and the
    plane's (a, b, c)."""
    poses = np.array(list(CMC2_POSES), dtype=float).reshape(-1, 2)
    values = np.array(list(CMC2_POSES.values()), dtype=float)
    n = len(poses)
    plane = np.c_[np.ones(n), poses]
    system = np.block([[_spline(np.linalg.norm(poses[:, None] - poses[None], axis=-1)), plane],
                       [plane.T, np.zeros((3, 3))]])
    solved = np.linalg.solve(system, np.r_[values, np.zeros(3)])
    return poses, solved[:n], solved[n:]


def cmc2(base: float, spread: float) -> float:
    """The ADAPT thumb's CMC2, degrees, for your thumb's base and spread, degrees: the smoothest
    surface through :data:`CMC2_POSES` (a thin-plate spline: a plane, bent just enough to pass
    through every pose), before the joint's limits."""
    poses, weights, (a, b, c) = _cmc2_surface()
    return float(a + b * base + c * spread + weights @ _spline(np.hypot(base - poses[:, 0], spread - poses[:, 1])))


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
#: Each fingertip from its last joint, in that joint's frame [m]: along the last bone, which runs
#: along -x for the thumb (25 mm, as HumanManipulationVMC draws it) and along +z for the fingers.
TIP_OFFSETS = {"thumb": np.array([-0.025, 0.0, 0.0]),
               **{d: np.array([0.0, 0.0, 0.0175]) for d in ("index", "middle", "ring", "pinky")}}
TIP_OFFSET = TIP_OFFSETS["index"]  # the fingers' tip

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
    """(20,) your range stretched onto the ADAPT's, joint by joint (:data:`HUMAN_RANGES`); the
    thumb's CMC2 from your thumb's base and spread (:data:`CMC2_POSES`)."""
    yours = _yours(hand)
    low, high = np.radians(np.array([HUMAN_RANGES.get(j, (0, 0)) for j in JOINTS], dtype=float)).T  # as they are now
    span = high - low
    share = np.divide(yours - low, span, out=np.zeros(20), where=span != 0.0)
    wanted = _LOW + share * (_HIGH - _LOW)
    base, spread = np.degrees(hand.angles[0, :2])
    wanted[1] = np.radians(cmc2(base, spread))
    return wanted


def _fit(joints: np.ndarray, clip: bool) -> np.ndarray:
    motors = _FIT @ joints
    return np.clip(motors, _MOTOR_LOW, _MOTOR_HIGH) if clip else motors


#: Fit the ADAPT hand's pose to yours (True, the default of :func:`joint_angles` and
#: :func:`motor_angles`), or map it joint for joint, your range onto its range (False). Change it
#: at any time: ``metaquest-teleop --no-adapt-fit`` sets it to False.
FIT = True

# The fit: how much each matched point counts, per digit (a finger: its PIP, DIP and tip; the
# thumb's shape does not count: the thumb is held as yours); a pinch (your thumb tip near a
# fingertip); and the pull towards the joint-for-joint pose, which picks one among poses that fit
# equally well [m/rad].
_POINT_WEIGHTS = np.array([[0.0, 0.0, 0.0]] + [[0.5, 0.7, 1.0]] * 4)
_PINCH_REACH, _PINCH_WEIGHT = 0.03, 3.0  # m: a gap this small counts, up to 3x a fingertip
_PULL = 0.0005
_ITERATIONS = 24

_AXES = np.array([[np.asarray(a) / np.linalg.norm(a) for _, a in DIGIT_JOINTS[d]] for d in DIGITS])  # (5, 4, 3)
_OFFSETS = np.array([[o for o, _ in DIGIT_JOINTS[d]] for d in DIGITS], dtype=float)  # (5, 4, 3)
_BASES = PALM_ORIGIN + np.array([DIGIT_BASES[d] for d in DIGITS], dtype=float)  # (5, 3)
_TIPS = np.array([TIP_OFFSETS[d] for d in DIGITS], dtype=float)  # (5, 3)
_BEFORE = np.array([[j <= i - 2 for j in range(4)] for i in (3, 4, 5)], dtype=float)  # joint j moves point i
_YOUR_POINTS = np.array([[2, 3, 4], [7, 8, 9], [12, 13, 14], [17, 18, 19], [22, 23, 24]])  # yours <-> ADAPT points 3, 4, 5
_YOUR_KNUCKLES, _YOUR_TIPS = [6, 11, 16, 21], [9, 14, 19, 24]


def _chains(joints: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The ADAPT hand's points, (5, 6, 3): per digit its base, four joints and tip; and its joint
    axes, (5, 4, 3); in its base frame. As :func:`positions`, all digits at once."""
    x, y, z = _AXES.reshape(20, 3).T
    c, s = np.cos(joints), np.sin(joints)
    t = 1.0 - c
    turns = np.stack([c + x * x * t, x * y * t - z * s, x * z * t + y * s,
                      y * x * t + z * s, c + y * y * t, y * z * t - x * s,
                      z * x * t - y * s, z * y * t + x * s, c + z * z * t], axis=-1).reshape(5, 4, 3, 3)
    points, axes = np.empty((5, 6, 3)), np.empty((5, 4, 3))
    p, r = _BASES, np.broadcast_to(np.eye(3), (5, 3, 3))
    points[:, 0] = p
    for k in range(4):
        p = p + np.einsum("dij,dj->di", r, _OFFSETS[:, k])
        axes[:, k] = np.einsum("dij,dj->di", r, _AXES[:, k])
        points[:, k + 1] = p
        r = r @ turns[:, k]
    points[:, 5] = p + np.einsum("dij,dj->di", r, _TIPS)
    return points, axes


_HOME, _ = _chains(np.zeros(20))
_THUMB_LENGTH = np.linalg.norm(np.diff(_HOME[0, 2:6], axis=0), axis=1).sum()  # CMC2 to the tip


def _targets(hand: Hand) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Where the ADAPT's points should be, for your hand: (5, 3, 3), per digit (the thumb's from
    its base, at the ADAPT thumb's length); the gaps from the thumb tip to each fingertip, (4, 3);
    and how much each gap counts, (4,)."""
    yours = (_FROM_WEBXR @ (hand.rotations[0].T @ (hand.positions - hand.positions[0]).T)).T
    knuckles, theirs = yours[_YOUR_KNUCKLES], _HOME[1:, 2]  # your knuckles on the ADAPT's
    mine, home = knuckles.mean(axis=0), theirs.mean(axis=0)
    scale = np.sum((knuckles - mine) * (theirs - home)) / np.sum((knuckles - mine) ** 2)
    at = home + scale * (yours - mine)
    goal = at[_YOUR_POINTS]
    goal[0] = _THUMB_LENGTH / np.linalg.norm(np.diff(at[1:5], axis=0), axis=1).sum() * (goal[0] - at[1])
    gaps = np.linalg.norm(hand.positions[_YOUR_TIPS] - hand.positions[4], axis=1)
    return goal, at[4] - at[_YOUR_TIPS], _PINCH_WEIGHT * np.exp(-((gaps / _PINCH_REACH) ** 2))


def _residuals(motors, goal, gaps, pinch, start) -> tuple[np.ndarray, np.ndarray]:
    """How far the ADAPT hand is from yours with these motors (70,), and its Jacobian (70, 13)."""
    points, axes = _chains(COUPLING @ motors)
    ours = points[:, 3:6].copy()
    ours[0] -= points[0, 2]  # the thumb's shape, from its base
    # A point moves with each joint before it: d point / d angle = axis x (point - joint).
    turn = np.cross(axes[:, None], points[:, 3:6, None] - points[:, None, 1:5]) * _BEFORE[None, :, :, None]
    tips = turn[:, 2].copy()  # (5, 4, 3): each tip, in the base frame
    turn[0, :, 0] -= np.cross(axes[0, 0], points[0, 2] - points[0, 1])  # the thumb's base turns with CMC1
    d = np.arange(5)
    shape = np.zeros((5, 3, 3, 5, 4))  # digit, point, xyz | digit, joint
    shape[d, :, :, d, :] = _POINT_WEIGHTS[..., None, None] * turn.transpose(0, 1, 3, 2)
    pinches = np.zeros((4, 3, 5, 4))  # finger, xyz | digit, joint
    pinches[:, :, 0, :] = pinch[:, None, None] * tips[0].T
    pinches[d[:4], :, d[1:], :] = -pinch[:, None, None] * tips[1:].transpose(0, 2, 1)
    r = np.concatenate([(_POINT_WEIGHTS[..., None] * (ours - goal)).ravel(),
                        (pinch[:, None] * ((points[0, 5] - points[1:, 5]) - gaps)).ravel(),
                        _PULL * (motors - start)])
    jac = np.vstack([np.vstack([shape.reshape(45, 20), pinches.reshape(12, 20)]) @ COUPLING, _PULL * np.eye(13)])
    return r, jac


def _solve(hand: Hand, clip: bool) -> np.ndarray:
    """(13,) the motor angles that put the ADAPT hand closest to yours: Levenberg-Marquardt from
    the joint-for-joint pose, within the motors' ranges if ``clip``."""
    low, high = (_MOTOR_LOW.copy(), _MOTOR_HIGH.copy()) if clip else (np.full(13, -np.inf), np.full(13, np.inf))
    goal, gaps, pinch = _targets(hand)
    m = start = _fit(_wanted(hand), clip)
    low[:4] = high[:4] = start[:4]  # the thumb stays as yours, joint for joint; the fingers fit around it
    r, jac = _residuals(m, goal, gaps, pinch, start)
    cost, damping, grow = r @ r, 1e-3, 2.0
    for _ in range(_ITERATIONS):
        g, h = jac.T @ r, jac.T @ jac
        free = ~(((m <= low) & (g > 0)) | ((m >= high) & (g < 0)))  # not held at a limit
        hf = h[np.ix_(free, free)]
        step = np.zeros(13)
        step[free] = np.linalg.solve(hf + damping * np.diag(np.diag(hf) + 1e-9), -g[free])
        trial = np.clip(m + step, low, high)
        r2, jac2 = _residuals(trial, goal, gaps, pinch, start)
        if r2 @ r2 < cost:
            moved = trial - m
            predicted = cost - np.sum((r + jac @ moved) ** 2)
            gain = (cost - r2 @ r2) / predicted if predicted > 0 else 0.0
            damping, grow = damping * max(1 / 3, 1 - (2 * gain - 1) ** 3), 2.0
            m, r, jac, cost = trial, r2, jac2, r2 @ r2
            if np.max(np.abs(moved)) < 1e-9:
                break
        else:  # no better: smaller steps
            damping, grow = damping * grow, 2 * grow
            if damping > 1e10:
                break
    return m


_LAST: dict = {}  # clip -> (hand, your ranges and CMC2 poses, motors): the last fit, for the next caller of that frame


def _fitted(hand: Hand, clip: bool) -> np.ndarray:
    ranges = (tuple(tuple(v) for v in HUMAN_RANGES.values()), tuple(CMC2_POSES.items()))
    last = _LAST.get(clip)
    if last is not None and last[0] is hand and last[1] == ranges:
        return last[2].copy()
    motors = _solve(hand, clip)
    _LAST[clip] = (hand, ranges, motors)
    return motors.copy()


def joint_angles(hand: Hand, clip: bool = True, coupled: bool = True, fit: bool | None = None) -> np.ndarray:
    """(20,) the ADAPT joint angles for your hand, radians, in :data:`JOINTS` order: a pose it can take.

    The thumb always follows yours joint for joint (below): its CMC1, MCP and IP through
    :data:`HUMAN_RANGES`, its CMC2 from your thumb's base and spread through :data:`CMC2_POSES`.

    The fit (``fit=True``, the default: :data:`FIT`): the fingers' pose that puts the ADAPT hand
    closest to yours, through its forward kinematics, around that thumb. Your knuckles on its
    knuckles (a scale and a shift), its fingers' PIP, DIP and tips on yours, and a fingertip as
    near the thumb tip as yours is, when you pinch. Only poses the hand can take: its motors
    (:data:`COUPLING`), within :data:`JOINT_LIMITS` (``clip=False``: without them).

    Joint for joint (``fit=False``): each ADAPT joint follows the same joint of yours, your range
    of motion stretched onto its range (:data:`HUMAN_RANGES`). A finger's spread, MCP, PIP and DIP
    follow yours; the thumb's MCP and IP follow yours, and its CMC1 is read off your thumb's first
    bone as the ADAPT's is built: how far it has turned about the hand's long axis, from sideways
    towards the palm's front.
    Then the pose the hand can take, as in ``virtualmodelcontrol``: a finger's DIP mimics its PIP
    (both the mean of the two), and one motor spreads the fingers (the best fit of the three). The
    fit starts from this pose.

    ``coupled=False`` gives the joint-for-joint angles before the motors, joint by joint (with or
    without ``fit``). ``clip`` keeps every joint within :data:`JOINT_LIMITS`.
    """
    if not coupled:
        wanted = _wanted(hand)
        return np.clip(wanted, _LOW, _HIGH) if clip else wanted
    motors = _fitted(hand, clip) if (FIT if fit is None else fit) else _fit(_wanted(hand), clip)
    joints = COUPLING @ motors
    return np.clip(joints, _LOW, _HIGH) if clip else joints  # only rounding to take off


def motor_angles(source, clip: bool = True, fit: bool | None = None) -> np.ndarray:
    """(13,) the ADAPT motor angles, radians, in :data:`MOTORS` order: targets for a motor PID.

    ``source`` is a :class:`~metaquest_teleop.Hand` (the motors of :func:`joint_angles`, with the
    same ``fit``) or 20 joint angles. 13 motors cannot set any 20 joints, so for joint angles this
    is the least-squares fit through :data:`COUPLING`: a finger's PIP motor takes the mean of its
    PIP and DIP, and the spread motor the best fit of the index, ring and pinky spreads. For
    :func:`joint_angles`, a pose the hand can take, it is exact. ``clip`` keeps each motor where
    every joint it turns stays within :data:`JOINT_LIMITS`.
    """
    if isinstance(source, Hand):
        return _fitted(source, clip) if (FIT if fit is None else fit) else _fit(_wanted(source), clip)
    return _fit(np.asarray(source, dtype=float), clip)


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
        points.append(p + r @ TIP_OFFSETS[digit])
        out[digit] = np.array(points)
    return out
