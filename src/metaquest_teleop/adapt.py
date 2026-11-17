"""Your hand on the ADAPT hand: its 20 joint angles, its 13 motor angles and the wrist's pose.

    from metaquest_teleop import adapt

    joints = adapt.joint_angles(hand)  # (20,) rad, in JOINTS order, within JOINT_LIMITS
    motors = adapt.motor_angles(hand)  # (13,) rad, in MOTORS order: targets for a motor PID
    wrist = adapt.wrist_pose(hand)     # the wrist, with the ADAPT base frame's axes

Its thumb follows yours through your calibration (:data:`CALIBRATION`), and its fingers take the
pose, within its limits, that puts them closest to yours, through its forward kinematics
(:func:`joint_angles`); with :data:`FIT` False, its fingers follow your calibration too.

The ADAPT hand is a right hand: a thumb with joints CMC1, CMC2, MCP and IP, and four fingers with
joints spread, MCP, PIP and DIP. Its geometry, joint ranges, motor order and transmissions are
those of ``virtualmodelcontrol.robots.adapt``. Its base frame: +z towards the fingertips, +y on
the palm side, the thumb towards -x. Flexion is positive; a finger's spread is positive towards
the pinky.

Its own wrist stays straight, at 0, 0 (:data:`WRIST_MOTORS`): the arm moves and turns the hand,
with its base at :func:`wrist_pose`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from .fake import quaternion
from .hands import FINGERS, Hand, Pose

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

_COLUMNS = ("base", "spread", "middle", "tip")

#: Your angles that the ADAPT joints follow, as the dashboard and the 3D view show them: each
#: finger's ``base``, ``spread``, ``middle`` and ``tip`` (the thumb's too: :attr:`Hand.angles
#: <metaquest_teleop.Hand.angles>`), and the thumb's ``turn``: how far its first bone has turned
#: about the hand's long axis, from sideways towards the palm's front, as the ADAPT's CMC1 turns
#: its own. :func:`your_angles` reads them, in degrees.
YOUR_ANGLES = tuple(f"{finger} {column}" for finger in FINGERS for column in _COLUMNS) + ("thumb turn",)

#: The angles of yours (:data:`YOUR_ANGLES`) that each ADAPT joint follows: the thumb's CMC2 two,
#: its base and its spread; the middle finger's spread none (it stays at 0); the others one.
FOLLOWS = {
    "thumb_CMC1": ("thumb turn",), "thumb_CMC2": ("thumb base", "thumb spread"),
    "thumb_MCP": ("thumb middle",), "thumb_IP": ("thumb tip",),
    "index_spread": ("index spread",), "index_MCP": ("index base",), "index_PIP": ("index middle",), "index_DIP": ("index tip",),
    "middle_spread": (), "middle_MCP": ("middle base",), "middle_PIP": ("middle middle",), "middle_DIP": ("middle tip",),
    "ring_spread": ("ring spread",), "ring_MCP": ("ring base",), "ring_PIP": ("ring middle",), "ring_DIP": ("ring tip",),
    "pinky_spread": ("pinky spread",), "pinky_MCP": ("pinky base",), "pinky_PIP": ("pinky middle",), "pinky_DIP": ("pinky tip",),
}  # fmt: skip

#: The calibration: for each ADAPT joint, points of yours and the angle it takes there, in
#: degrees: ``{your angle: its angle}``; for the thumb's CMC2, ``{(your base, your spread): its
#: angle}`` (:data:`FOLLOWS`). Each joint follows the line closest to its points (for two angles
#: of yours, the plane), by least squares: through them with two points (three for a plane), their
#: best fit with more. Then within its limits (:data:`JOINT_LIMITS`). At least two points, at
#: different angles of yours (for two angles, three not on one line).
#:
#: These are the library's points. Change them at any time, in Python or in the 3D view
#: (``metaquest-teleop --calibration``, which saves each calibration to a file in
#: :data:`CALIBRATIONS`: :func:`save_calibration`, :func:`load_calibration`). A calibration becomes
#: the library's with ``scripts/set_calibration.py`` in its repository. The first ones: your open
#: hand gives all zeros (the hand's home), a power grasp about PC1 and a pinch about PC2 of
#: HumanManipulationVMC's PoseControl (Santello et al., 1998).
CALIBRATION = {
    "thumb_CMC1": {5: 0, 95: 86}, "thumb_CMC2": {(0, 30): 20, (20, 35): 0, (43, 21.6): -6, (44.3, 15): -1, (70, 20): -60},
    "thumb_MCP": {0: 0, 65: 86}, "thumb_IP": {0: 0, 44.9: 42, 45: 90},
    "index_spread": {0: 0, 20: -17}, "index_MCP": {0: 0, 90: 86}, "index_PIP": {0: 0, 90: 69}, "index_DIP": {0: 0, 60: 69},
    "middle_MCP": {0: 0, 90: 86}, "middle_PIP": {0: 0, 90: 69}, "middle_DIP": {0: 0, 60: 69},
    "ring_spread": {-15: 17, 0: 0}, "ring_MCP": {0: 0, 90: 86}, "ring_PIP": {0: 0, 90: 69}, "ring_DIP": {0: 0, 60: 69},
    "pinky_spread": {-25: 17, 0: 0}, "pinky_MCP": {0: 0, 90: 86}, "pinky_PIP": {0: 0, 90: 69}, "pinky_DIP": {0: 0, 60: 69},
}  # fmt: skip
_DEFAULT_CALIBRATION = {joint: dict(points) for joint, points in CALIBRATION.items()}

#: Where ``metaquest-teleop --calibration`` saves each calibration, a new file each time, named by
#: when it started: ``~/.config/metaquest-teleop/calibrations`` (``$XDG_CONFIG_HOME`` instead of
#: ``~/.config`` when set).
CALIBRATIONS = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "metaquest-teleop" / "calibrations"

def _model(joint: str, points: dict) -> np.ndarray:
    """The line closest to a joint's points (for two angles of yours, the plane), by least squares:
    its angle at yours all 0, then how much it turns per degree of each, (k + 1,). ValueError if
    the points cannot make one."""
    k = len(FOLLOWS[joint])
    names = ", ".join(FOLLOWS[joint])
    if k == 0:
        raise ValueError(f"{joint} follows none of your angles: it has no calibration")
    yours, its = [], []
    for key, value in points.items():
        x = np.atleast_1d(np.asarray(key, dtype=float))
        if x.shape != (k,) or not np.all(np.isfinite(x)) or not np.isfinite(float(value)):
            raise ValueError(f"{joint}: a point is {k} angle(s) of yours ({names}) and its angle, in degrees, not {key!r}: {value!r}")
        yours.append(x)
        its.append(float(value))
    a = np.c_[np.ones(len(yours)), np.array(yours, dtype=float).reshape(-1, k)]
    if np.linalg.matrix_rank(a) < k + 1:
        raise ValueError(f"{joint} needs two points or more, at different angles of yours ({names})" if k == 1
                         else f"{joint} needs {k + 1} points or more, not all on one line ({names})")
    return np.linalg.lstsq(a, np.array(its), rcond=None)[0]


_MODELS: dict = {}  # joint -> (its points, as items, when fitted; its line)


def calibrated(joint: str, *yours: float) -> float:
    """The angle of the ADAPT joint, in degrees, for these angles of yours, in degrees (its
    :data:`FOLLOWS`, in that order): the line closest to its :data:`CALIBRATION` points (the plane,
    for two angles of yours); before its limits. ``calibrated("thumb_CMC2", 20, 35)`` is the CMC2
    for your thumb's base at 20° and spread at 35°."""
    if len(yours) != len(FOLLOWS[joint]):
        raise TypeError(f"{joint} follows {len(FOLLOWS[joint])} angle(s) of yours ({', '.join(FOLLOWS[joint])}), not {len(yours)}")
    if not yours:
        return 0.0
    points = CALIBRATION[joint]
    items = tuple(points.items())
    cached = _MODELS.get(joint)
    if cached is None or cached[0] != items:
        cached = _MODELS[joint] = (items, _model(joint, points))
    line = cached[1]
    return float(line[0] + line[1:] @ np.asarray(yours, dtype=float))


def _points(joint: str, rows) -> dict:
    """A joint's points from rows ``[[your angle(s)..., its angle], ...]``, checked."""
    k = len(FOLLOWS.get(joint, ()))
    if k == 0:
        raise ValueError(f"{joint!r} is not an ADAPT joint that follows yours (adapt.FOLLOWS)")
    ok = isinstance(rows, list) and all(
        isinstance(row, list) and len(row) == k + 1
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in row) for row in rows)
    if not ok:
        raise ValueError(f"{joint}: expected points [[{', '.join(FOLLOWS[joint])}, its angle], ...] in degrees")
    points = dict(sorted({(row[0] if k == 1 else tuple(row[:k])): row[k] for row in rows}.items()))
    _model(joint, points)  # ValueError if it cannot follow them
    return points


def _number(v):
    v = float(v)
    return int(v) if v.is_integer() else v


def _rows(points: dict) -> list:
    """A joint's points as rows ``[[your angle(s)..., its angle], ...]``."""
    return [[*(_number(x) for x in np.atleast_1d(key)), _number(value)] for key, value in points.items()]


def load_calibration(path: str | os.PathLike) -> None:
    """Load a calibration saved by :func:`save_calibration` (or ``metaquest-teleop
    --calibration``): its joints take its points, the others the library's. OSError if there is no
    such file, ValueError if it is not a calibration; nothing changes then."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        saved = json.loads(text)
        if not isinstance(saved, dict):
            raise ValueError("expected {joint: points, ...}")
        loaded = {joint: _points(joint, rows) for joint, rows in saved.items()}
    except ValueError as exc:
        raise ValueError(f"{path} is not an ADAPT calibration: {exc}") from None
    reset_calibration()
    CALIBRATION.update(loaded)


def save_calibration(path: str | os.PathLike) -> Path:
    """Save the calibration as it is now, every joint's points, for :func:`load_calibration` and
    ``scripts/set_calibration.py``. As JSON: ``{"thumb_IP": [[0, 0], [45, 90]], ...}``, each point
    your angle(s) then its angle, in degrees. Returns where it saved."""
    path = Path(path)
    lines = [f"  {json.dumps(joint)}: {json.dumps(_rows(CALIBRATION[joint]))}" for joint in JOINTS if joint in CALIBRATION]
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    os.replace(partial, path)
    return path


def reset_calibration(joint: str | None = None) -> None:
    """Back to the library's calibration: of every joint, or of ``joint``."""
    for name in _DEFAULT_CALIBRATION if joint is None else (joint,):
        CALIBRATION[name] = dict(_DEFAULT_CALIBRATION[name])
    if joint is None:
        for extra in set(CALIBRATION) - set(_DEFAULT_CALIBRATION):
            del CALIBRATION[extra]


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


def your_angles(hand: Hand) -> dict[str, float]:
    """Your angles that the ADAPT joints follow (:data:`YOUR_ANGLES`), in degrees, by name."""
    a = np.degrees(hand.angles)
    out = {f"{finger} {column}": float(a[f, c]) for f, finger in enumerate(FINGERS) for c, column in enumerate(_COLUMNS)}
    # Your thumb's first bone, in the ADAPT axes, read as the ADAPT's CMC1 turns its own: about the
    # hand's long axis, from sideways towards the palm's front.
    d = _FROM_WEBXR @ (hand.rotations[0].T @ (hand.positions[2] - hand.positions[1]))
    out["thumb turn"] = float(np.degrees(np.arctan2(d[1], -d[0])))
    return out


def _wanted(hand: Hand) -> np.ndarray:
    """(20,) each ADAPT joint through its calibration (:data:`CALIBRATION`), radians, before its limits."""
    yours = your_angles(hand)
    return np.radians([calibrated(j, *(yours[name] for name in FOLLOWS[j])) for j in JOINTS])


def _calibration_key() -> tuple:
    """The calibration as it is now, to know when it changed."""
    return tuple((FOLLOWS[j], tuple(CALIBRATION[j].items()) if j in CALIBRATION else ()) for j in JOINTS)


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


_LAST: dict = {}  # clip -> (hand, the calibration, motors): the last fit, for the next caller of that frame


def _fitted(hand: Hand, clip: bool) -> np.ndarray:
    ranges = _calibration_key()
    last = _LAST.get(clip)
    if last is not None and last[0] is hand and last[1] == ranges:
        return last[2].copy()
    motors = _solve(hand, clip)
    _LAST[clip] = (hand, ranges, motors)
    return motors.copy()


def joint_angles(hand: Hand, clip: bool = True, coupled: bool = True, fit: bool | None = None) -> np.ndarray:
    """(20,) the ADAPT joint angles for your hand, radians, in :data:`JOINTS` order: a pose it can take.

    The thumb always follows your calibration (:data:`CALIBRATION`): each of its joints the angles
    of yours it follows (:data:`FOLLOWS`), through your points.

    The fit (``fit=True``, the default: :data:`FIT`): the fingers' pose that puts the ADAPT hand
    closest to yours, through its forward kinematics, around that thumb. Your knuckles on its
    knuckles (a scale and a shift), its fingers' PIP, DIP and tips on yours, and a fingertip as
    near the thumb tip as yours is, when you pinch. Only poses the hand can take: its motors
    (:data:`COUPLING`), within :data:`JOINT_LIMITS` (``clip=False``: without them).

    Joint for joint (``fit=False``): every joint follows your calibration, the fingers' too: a
    finger's spread, MCP, PIP and DIP follow your spread, base, middle and tip. Then the pose the
    hand can take, as in ``virtualmodelcontrol``: a finger's DIP mimics its PIP (both the mean of
    the two), and one motor spreads the fingers (the best fit of the three). The fit starts from
    this pose.

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
