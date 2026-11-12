"""A stand-in headset: synthetic moving hands, sent to the server exactly as the Quest would.

    metaquest-teleop-fake                    # streams to the default port at 90 Hz until Ctrl-C
    metaquest-teleop-fake --hz 120 --seconds 10
    python -m metaquest_teleop.fake          # the same
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import numpy as np

from .hands import Hand, Pose, encode, rotations
from .server import DEFAULT_PORT

# Bone lengths, metres: thumb metacarpal, proximal, distal; fingers metacarpal, proximal,
# intermediate, distal. Bases sit across the wrist, measured towards the thumb side.
_LENGTHS = ((0.045, 0.035, 0.03), (0.07, 0.045, 0.025, 0.02), (0.068, 0.05, 0.03, 0.02),
            (0.064, 0.045, 0.028, 0.02), (0.06, 0.035, 0.022, 0.018))
_BASES = ((0.025, -0.012, -0.01), (0.02, 0.0, -0.01), (0.0, 0.0, -0.01),
          (-0.018, 0.0, -0.01), (-0.035, 0.0, -0.012))
_SPREAD = (0.0, 0.06, 0.0, -0.05, -0.12)


def _rx(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _bend(flex: float, abd: float, radial: float) -> np.ndarray:
    """Child joint axes in the parent's, for a bend that Hand.angles reads back as (flex, abd)."""
    return _rx(-flex) @ _ry(-radial * abd)


def quaternion(m: np.ndarray) -> np.ndarray:
    """(3, 3) rotation matrix to an (x, y, z, w) quaternion."""
    t = np.trace(m)
    if t > 0:
        s = 2.0 * np.sqrt(1.0 + t)
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4]
    else:
        i = int(np.argmax(np.diag(m)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = 2.0 * np.sqrt(1.0 + m[i, i] - m[j, j] - m[k, k])
        q = [0.0, 0.0, 0.0, (m[k, j] - m[j, k]) / s]
        q[i], q[j], q[k] = s / 4, (m[j, i] + m[i, j]) / s, (m[k, i] + m[i, k]) / s
    return np.asarray(q) / np.linalg.norm(q)


def synthetic_hand(side: str, angles: np.ndarray, wrist: Pose) -> Hand:
    """A hand whose joints read back exactly the given (5, 4) angles (see Hand.angles)."""
    radial = -1.0 if side == "right" else 1.0
    r_wrist, p_wrist = wrist.rotation, np.asarray(wrist.position, dtype=np.float64)
    positions, frames = [p_wrist], [r_wrist]
    for f, (lengths, base, spread, a) in enumerate(zip(_LENGTHS, _BASES, _SPREAD, angles)):
        offset = np.array([radial * base[0], base[1], base[2]])
        r = r_wrist @ (_bend(a[0], a[1], radial) if f == 0 else _bend(0.0, spread, radial))
        p = p_wrist + r_wrist @ offset
        bends = [_bend(a[2], 0.0, radial), _bend(a[3], 0.0, radial)] if f == 0 else \
            [_bend(a[0], a[1], radial), _bend(a[2], 0.0, radial), _bend(a[3], 0.0, radial)]
        for length, bend in zip(lengths, bends + [np.eye(3)]):
            positions.append(p)
            frames.append(r)
            p = p + r @ np.array([0.0, 0.0, -length])
            r = r @ bend
        positions.append(p)
        frames.append(frames[-1])
    return Hand(side, np.array(positions), np.array([quaternion(m) for m in frames]))


def pose_at(t: float, side: str) -> tuple[np.ndarray, Pose]:
    """Angles and wrist pose of a hand opening and closing, the wrist circling slowly."""
    phase = np.arange(5) * 0.5 + (0.0 if side == "right" else 1.3)
    close = 0.5 - 0.5 * np.cos(2 * np.pi * 0.35 * t + phase)
    angles = np.stack([0.3 + 0.4 * close, 0.6 - 0.3 * close, 0.2 + 0.6 * close, 0.1 + 0.5 * close], axis=1)
    angles[1:] = np.stack([1.3 * close[1:], 0.15 * np.sin(2 * np.pi * 0.2 * t + phase[1:]),
                           1.4 * close[1:], 0.9 * close[1:]], axis=1)
    x = 0.2 if side == "right" else -0.2
    position = np.array([x + 0.05 * np.cos(0.8 * t), 1.1 + 0.05 * np.sin(0.8 * t), -0.4])
    yaw = 0.3 * np.sin(0.5 * t)
    return angles, Pose(position, np.array([0.0, np.sin(yaw / 2), 0.0, np.cos(yaw / 2)]))


async def stream(url: str, hz: float = 90.0, seconds: float | None = None) -> int:
    """Send synthetic frames to a running server; returns how many were sent."""
    import aiohttp  # noqa: PLC0415

    async with aiohttp.ClientSession() as session, session.ws_connect(url) as ws:
        await ws.send_str(json.dumps({"hello": {"agent": "metaquest-teleop fake headset"}}))
        await ws.send_str(json.dumps({"session": "started", "mode": "fake", "space": "local-floor",
                                      "fps": hz, "rates": [hz]}))
        start, seq = time.perf_counter(), 0
        while seconds is None or time.perf_counter() - start < seconds:
            t = time.perf_counter() - start
            hands = {side: synthetic_hand(side, *pose_at(t, side)) for side in ("left", "right")}
            head = Pose(np.array([0.0, 1.6, 0.0]), np.array([0.0, 0.0, 0.0, 1.0]))
            await ws.send_bytes(encode(seq, t, head, hands["left"], hands["right"]))
            seq += 1
            await asyncio.sleep(max(0.0, start + seq / hz - time.perf_counter()))
        await ws.send_str(json.dumps({"session": "ended"}))
    return seq


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port of the running metaquest-teleop (default {DEFAULT_PORT})")
    parser.add_argument("--hz", type=float, default=90.0, help="frames per second")
    parser.add_argument("--seconds", type=float, default=None, help="stop after this long")
    args = parser.parse_args()
    url = f"ws://localhost:{args.port}/ws"
    print(f"fake headset streaming to {url} at {args.hz:g} Hz (Ctrl-C to stop)")
    try:
        sent = asyncio.run(stream(url, args.hz, args.seconds))
        print(f"sent {sent} frames")
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"could not reach {url}: {exc}. Is metaquest-teleop running?")


if __name__ == "__main__":
    main()
