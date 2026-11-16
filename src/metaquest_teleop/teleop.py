"""One hand drives the robot, the other one pauses it.

    from metaquest_teleop import QuestHands, Teleop

    with QuestHands() as quest:
        teleop = Teleop(quest)   # your right hand drives, your left hand pauses
        while True:
            command = teleop.command()
            if command.hold:
                ...              # keep the robot where it is
            else:
                ...              # send command.wrist (the arm) and command.motors (the hand)

- Pinch with the left hand: the robot holds still where it is, and your right hand can move
  freely.
- Release the pinch: the robot follows your right hand again, from where it stopped: it moves
  as your hand moves from there, without jumping.
- For safety the robot also holds while the left hand or the right hand is not seen, or while
  frames stop coming.

The targets are those of the ADAPT hand (``metaquest_teleop.adapt``): its joint and motor
angles, and the wrist with its axes. ``Teleop(quest, adapt=False)`` gives your own joint angles
and your wrist with its own axes instead, for any robot.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np

from . import adapt
from .fake import quaternion
from .hands import Frame, Pose
from .server import QuestHands

#: The other hand pinches when its pinch closes below this, metres...
PINCH_ON = 0.02
#: ... and releases when it opens above this.
PINCH_OFF = 0.04
#: Seconds without a frame before the robot holds.
STALE = 0.1


@dataclasses.dataclass(frozen=True)
class Command:
    """What the robot should do now."""

    #: True: keep the robot where it is.
    hold: bool
    #: Why it holds, such as ``"left hand pinching"``; empty while it moves.
    reason: str
    #: Where the robot's wrist goes: room coordinates, with the ADAPT hand's axes (with
    #: ``adapt=False``, your wrist's). It starts at your wrist and then moves as your hand moves,
    #: except while holding. None before the first move.
    wrist: Pose | None
    #: (20,) the ADAPT hand's joint angles, within limits (with ``adapt=False``, yours, in
    #: ``ANGLE_NAMES`` order); unchanged while holding.
    joints: np.ndarray | None
    #: (13,) the ADAPT hand's motor angles; unchanged while holding. None with ``adapt=False``.
    motors: np.ndarray | None
    #: ``time.time()`` when the frame it comes from arrived.
    received: float


class Teleop:
    """Drive a robot with one hand and pause it with the other (see the module's documentation).

    The driving hand is the hand ``quest`` keeps (the right one by default, also with
    ``hands="both"``); the other one gives the gestures. ``pinch_on`` and ``pinch_off`` [m] are
    when its pinch closes and opens again; ``stale`` [s] how long without a frame before holding.
    ``adapt=False`` drives any robot: your joint angles and your wrist's axes, no motors.
    """

    def __init__(self, quest: QuestHands, pinch_on: float = PINCH_ON, pinch_off: float = PINCH_OFF,
                 stale: float = STALE, adapt: bool = True) -> None:
        self.adapt = adapt
        self.drive = "left" if quest.hands == "left" else "right"
        self.gesture = "right" if self.drive == "left" else "left"
        self.pinch_on, self.pinch_off, self.stale = pinch_on, pinch_off, stale
        self._pinching = False
        self._anchor: tuple[Pose, Pose] | None = None  # your wrist and the robot's when it last started
        self._wrist: Pose | None = None
        self._joints: np.ndarray | None = None
        self._motors: np.ndarray | None = None
        self._last = Command(True, "no frames yet", None, None, None, 0.0)
        quest.teleop = self
        quest.on_frame(self.update, raw=True)

    def update(self, frame: Frame) -> Command:
        """Take a new frame, with both hands; ``quest`` calls this for every frame."""
        drive, gesture = frame.hand(self.drive), frame.hand(self.gesture)
        if gesture is None:
            self._pinching = False
        else:
            self._pinching = gesture.pinch < (self.pinch_off if self._pinching else self.pinch_on)
        reason = (f"{self.drive} hand not seen" if drive is None
                  else f"{self.gesture} hand not seen" if gesture is None
                  else f"{self.gesture} hand pinching" if self._pinching else "")
        if reason:
            self._anchor = None  # on release, follow from the hand's new place
        else:
            pose = adapt.wrist_pose(drive) if self.adapt else drive.wrist
            if self._wrist is None:
                self._wrist = pose
            if self._anchor is None:
                self._anchor = (pose, self._wrist)
            hand0, wrist0 = self._anchor
            turn = pose.rotation @ hand0.rotation.T
            self._wrist = Pose(wrist0.position + pose.position - hand0.position,
                               quaternion(turn @ wrist0.rotation))
            if self.adapt:
                self._joints = adapt.joint_angles(drive)
                self._motors = adapt.motor_angles(self._joints)
            else:
                self._joints = drive.angles.ravel().copy()
        self._last = Command(bool(reason), reason, self._wrist, self._joints, self._motors, frame.received)
        return self._last

    def command(self, now: float | None = None) -> Command:
        """The latest command; holding with ``"no frames"`` once frames stop for ``stale`` s."""
        last = self._last
        now = time.time() if now is None else now
        if last.received and now - last.received > self.stale:
            return dataclasses.replace(last, hold=True, reason="no frames")
        return last
