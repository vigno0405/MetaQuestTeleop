"""Hand frames from the headset: 25 tracked joints per hand, the head pose, and joint angles.

Units are metres and radians; quaternions are (x, y, z, w). Everything is expressed in
WebXR's `local-floor` space: origin on the floor where the session started, +y up,
-z the direction the headset faced at the start, +x to its right. Each joint's own axes
follow the WebXR spec for both hands: -Z along the bone towards the fingertip, -Y out of
the palm.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from functools import cached_property

import numpy as np

JOINTS = (
    "wrist",
    "thumb-metacarpal", "thumb-phalanx-proximal", "thumb-phalanx-distal", "thumb-tip",
    "index-finger-metacarpal", "index-finger-phalanx-proximal",
    "index-finger-phalanx-intermediate", "index-finger-phalanx-distal", "index-finger-tip",
    "middle-finger-metacarpal", "middle-finger-phalanx-proximal",
    "middle-finger-phalanx-intermediate", "middle-finger-phalanx-distal", "middle-finger-tip",
    "ring-finger-metacarpal", "ring-finger-phalanx-proximal",
    "ring-finger-phalanx-intermediate", "ring-finger-phalanx-distal", "ring-finger-tip",
    "pinky-finger-metacarpal", "pinky-finger-phalanx-proximal",
    "pinky-finger-phalanx-intermediate", "pinky-finger-phalanx-distal", "pinky-finger-tip",
)
PARENT = (-1, 0, 1, 2, 3, 0, 5, 6, 7, 8, 0, 10, 11, 12, 13, 0, 15, 16, 17, 18, 0, 20, 21, 22, 23)

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
ANGLE_NAMES = (
    "thumb_cmc_flex", "thumb_cmc_abd", "thumb_mcp_flex", "thumb_ip_flex",
    "index_mcp_flex", "index_mcp_abd", "index_pip_flex", "index_dip_flex",
    "middle_mcp_flex", "middle_mcp_abd", "middle_pip_flex", "middle_dip_flex",
    "ring_mcp_flex", "ring_mcp_abd", "ring_pip_flex", "ring_dip_flex",
    "pinky_mcp_flex", "pinky_mcp_abd", "pinky_pip_flex", "pinky_dip_flex",
)

# (parent, child) joints of each finger's three bends.
_BENDS = np.array([
    [[0, 1], [1, 2], [2, 3]],           # thumb: CMC, MCP, IP
    [[5, 6], [6, 7], [7, 8]],           # index: MCP, PIP, DIP
    [[10, 11], [11, 12], [12, 13]],     # middle
    [[15, 16], [16, 17], [17, 18]],     # ring
    [[20, 21], [21, 22], [22, 23]],     # pinky
])

MAGIC = b"QHS1"
_HEADER = struct.Struct("<4sIdB3x")
_HAND_FLOATS = len(JOINTS) * 7
_FLOATS = 7 + 2 * _HAND_FLOATS
FRAME_BYTES = _HEADER.size + 4 * _FLOATS


def rotations(quaternions: np.ndarray) -> np.ndarray:
    """(..., 4) xyzw quaternions to (..., 3, 3) rotation matrices."""
    q = np.asarray(quaternions, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    x, y, z, w = np.moveaxis(q, -1, 0)
    m = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    return np.moveaxis(m, (0, 1), (-2, -1))


def _quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], axis=-1)


@dataclass(frozen=True, eq=False)
class Pose:
    position: np.ndarray    # (3,) metres
    quaternion: np.ndarray  # (4,) x, y, z, w

    @property
    def rotation(self) -> np.ndarray:
        """(3, 3) rotation matrix."""
        return rotations(self.quaternion)

    @property
    def matrix(self) -> np.ndarray:
        """(4, 4) homogeneous transform."""
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = self.rotation, self.position
        return m


@dataclass(frozen=True, eq=False)
class Hand:
    side: str               # "left" or "right"
    positions: np.ndarray   # (25, 3) joint positions, in JOINTS order
    quaternions: np.ndarray  # (25, 4) joint orientations

    @property
    def wrist(self) -> Pose:
        return Pose(self.positions[0], self.quaternions[0])

    def joint(self, name: str) -> Pose:
        i = JOINTS.index(name)
        return Pose(self.positions[i], self.quaternions[i])

    @cached_property
    def rotations(self) -> np.ndarray:
        """(25, 3, 3) joint rotation matrices."""
        return rotations(self.quaternions)

    @cached_property
    def angles(self) -> np.ndarray:
        """(5, 4) joint angles, radians: one row per finger, thumb to pinky.

        Fingers: MCP flexion, MCP abduction, PIP flexion, DIP flexion. Thumb: CMC flexion,
        CMC abduction (both of the metacarpal against the wrist), MCP flexion, IP flexion.
        Flexion is positive towards the palm and abduction positive towards the thumb side,
        on both hands. Each is the bend of a bone's direction against its parent joint's
        axes, so a straight finger reads 0 and the thumb's CMC is not 0 at rest.
        """
        out = np.empty((5, 4))
        for col, bend in ((0, 0), (2, 1), (3, 2)):
            parent, child = self.rotations[_BENDS[:, bend, 0]], self.rotations[_BENDS[:, bend, 1]]
            bone = -np.einsum("fji,fj->fi", parent, child[:, :, 2])
            out[:, col] = np.arctan2(-bone[:, 1], -bone[:, 2])
            if bend == 0:
                radial = -1.0 if self.side == "right" else 1.0
                out[:, 1] = np.arcsin(np.clip(radial * bone[:, 0], -1.0, 1.0))
        return out

    @property
    def angle_dict(self) -> dict[str, float]:
        """The 20 joint angles by name (ANGLE_NAMES), radians."""
        return dict(zip(ANGLE_NAMES, self.angles.ravel().tolist()))

    @cached_property
    def local_quaternions(self) -> np.ndarray:
        """(25, 4) each joint's rotation relative to its parent joint (PARENT); the wrist's is absolute."""
        q = self.quaternions / np.linalg.norm(self.quaternions, axis=-1, keepdims=True)
        parent = q[[max(p, 0) for p in PARENT]] * np.array([-1.0, -1.0, -1.0, 1.0])
        local = _quat_multiply(parent, q)
        local[0] = q[0]
        return local

    @property
    def pinch(self) -> float:
        """Thumb tip to index tip, metres."""
        return float(np.linalg.norm(self.positions[4] - self.positions[9]))

    def to_dict(self) -> dict:
        return {
            "wrist": {"position": self.positions[0].tolist(), "quaternion": self.quaternions[0].tolist()},
            "angles": self.angle_dict,
            "pinch": self.pinch,
            "joints": np.hstack([self.positions, self.quaternions]).tolist(),
        }


@dataclass(frozen=True, eq=False)
class Frame:
    seq: int                 # frame counter from the headset
    time: float              # headset clock, seconds
    received: float          # time.time() on this computer when it arrived
    head: Pose | None
    left: Hand | None
    right: Hand | None

    def hand(self, side: str) -> Hand | None:
        return self.left if side == "left" else self.right

    def to_dict(self) -> dict:
        return {
            "seq": self.seq, "time": self.time, "received": self.received,
            "head": None if self.head is None else {"position": self.head.position.tolist(),
                                                    "quaternion": self.head.quaternion.tolist()},
            "left": None if self.left is None else self.left.to_dict(),
            "right": None if self.right is None else self.right.to_dict(),
        }


def decode(data: bytes, received: float | None = None) -> Frame:
    """One binary message from the headset page to a Frame."""
    if len(data) != FRAME_BYTES:
        raise ValueError(f"expected {FRAME_BYTES} bytes, got {len(data)}")
    magic, seq, t, flags = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ValueError(f"not a hand frame (magic {magic!r})")
    values = np.frombuffer(data, dtype="<f4", offset=_HEADER.size).astype(np.float64)
    head = Pose(values[:3], values[3:7]) if flags & 1 else None
    hands = {}
    for bit, side, start in ((2, "left", 7), (4, "right", 7 + _HAND_FLOATS)):
        if flags & bit:
            block = values[start:start + _HAND_FLOATS].reshape(len(JOINTS), 7)
            hands[side] = Hand(side, block[:, :3].copy(), block[:, 3:].copy())
    return Frame(seq, t, time.time() if received is None else received, head,
                 hands.get("left"), hands.get("right"))


def encode(seq: int, t: float, head: Pose | None = None, left: Hand | None = None,
           right: Hand | None = None) -> bytes:
    """A Frame's fields to the headset's binary format; the inverse of decode."""
    values = np.zeros(_FLOATS, dtype="<f4")
    flags = 0
    if head is not None:
        values[:7] = np.r_[head.position, head.quaternion]
        flags |= 1
    for bit, hand, start in ((2, left, 7), (4, right, 7 + _HAND_FLOATS)):
        if hand is not None:
            values[start:start + _HAND_FLOATS] = np.hstack([hand.positions, hand.quaternions]).ravel()
            flags |= bit
    return _HEADER.pack(MAGIC, seq & 0xFFFFFFFF, t, flags) + values.tobytes()
