"""The hands on ROS 2 topics, with standard messages only: ROS 2 Humble and Jazzy alike.

    from metaquest_teleop import QuestHands
    from metaquest_teleop.ros import RosPublisher

    with QuestHands() as quest:
        ros = RosPublisher(quest)  # publishes every frame until closed
        ...
        ros.close()

or ``metaquest-teleop``, which publishes whenever it finds ROS 2. Source ROS first; any Python
then works: when this one cannot load ROS 2 (a conda environment with Python 3.10, and ROS 2
Jazzy on 3.12, say), the topics go out through a small helper process with the Python ROS 2
runs on (:mod:`metaquest_teleop.ros_publish`). Topics, for each hand kept (the right one by
default):

=================================  ===========================  =====================================
``/metaquest/<side>/joint_states``  sensor_msgs/JointState       the 20 joint angles, radians
``/metaquest/<side>/wrist``         geometry_msgs/PoseStamped    the wrist, in ``metaquest_floor``
``/metaquest/<side>/joints``        geometry_msgs/PoseArray      the 25 joints, in ``metaquest_floor``
``/metaquest/<side>/pinch``         std_msgs/Float64             thumb tip to index tip, metres
=================================  ===========================  =====================================

and, from the right hand, for the ADAPT hand (``metaquest_teleop.adapt``):

==================================  ===========================  ===================================
``/metaquest/adapt/joint_states``   sensor_msgs/JointState       its 20 joint angles, within limits
``/metaquest/adapt/motors``         sensor_msgs/JointState       its 13 motor angles: PID targets
``/metaquest/adapt/wrist``          geometry_msgs/PoseStamped    your wrist, with the ADAPT axes
==================================  ===========================  ===================================

With a ``teleop`` (:class:`~metaquest_teleop.Teleop`: the other hand pauses the robot), the ADAPT
topics carry its targets, which stay still while it holds, and it adds:

==================================  ===========================  ===================================
``/metaquest/teleop/hold``          std_msgs/Bool                true: keep the robot where it is
``/metaquest/teleop/state``         std_msgs/String              ``moving``, or why it holds
``/metaquest/teleop/wrist``         geometry_msgs/PoseStamped    where the robot's wrist goes
==================================  ===========================  ===================================

While frames stop, ``hold`` and ``state`` still come, ten times a second.

``metaquest_floor`` is the room frame of the headset (x right, y up, -z forward). Messages are
stamped with the time each frame reached this computer.
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from . import adapt
from .hands import ANGLE_NAMES, Frame
from .server import QuestHands
from .teleop import Teleop

#: The frame of every pose: the headset's room (WebXR ``local-floor``).
FRAME_ID = "metaquest_floor"
_DOCS = "https://vigno0405.github.io/MetaQuestTeleop/ros.html"


class RosUnavailable(RuntimeError):
    """ROS 2 cannot publish from here: ``str()`` says why, :attr:`how` what to do."""

    def __init__(self, why: str, how: str) -> None:
        super().__init__(why)
        self.how = how


def _ros_version() -> str | None:
    """The Python version the sourced ROS 2 is for, from where rclpy is: ``"3.12"`` for Jazzy."""
    try:
        spec = importlib.util.find_spec("rclpy")
    except (ImportError, ValueError):
        return None
    found = re.search(r"python(\d+\.\d+)", (spec.origin or "") if spec is not None else "")
    return found[1] if found else None


def _ros_name() -> str:
    return " ".join(filter(None, ("ROS 2", os.environ.get("ROS_DISTRO", "").capitalize())))


def ros_python() -> str | None:
    """The Python the sourced ROS 2 runs on, when it is not this one; None otherwise."""
    version = _ros_version()
    if version is None or version == "{}.{}".format(*sys.version_info[:2]):
        return None
    for python in (f"/usr/bin/python{version}", shutil.which(f"python{version}")):
        if python and os.path.isfile(python) and os.access(python, os.X_OK):
            return python
    return None


def _unavailable(exc: BaseException) -> RosUnavailable:
    """Why this Python cannot publish on ROS 2, when no other Python can do it for it."""
    try:
        found = importlib.util.find_spec("rclpy") is not None
    except (ImportError, ValueError):
        found = False
    if not found:
        return RosUnavailable("ROS 2 not found", "To publish, source ROS first (for example "
                              f"`source /opt/ros/jazzy/setup.bash`): {_DOCS}")
    version = _ros_version()
    if version is not None and version != "{}.{}".format(*sys.version_info[:2]):
        return RosUnavailable(f"{_ros_name()} runs on Python {version}, which is not found",
                              f"To publish, install Python {version}: {_DOCS}")
    return RosUnavailable(f"ROS 2 did not load ({' '.join(str(exc).split())})", f"See {_DOCS}")


def _pose(pose) -> list[float]:
    return [*map(float, pose.position), *map(float, pose.quaternion)]


class RosPublisher:
    """Publish every frame of ``quest`` on ROS 2 topics (see the module's documentation).

    ``adapt`` also publishes the ADAPT hand's topics, and ``teleop`` (a
    :class:`~metaquest_teleop.Teleop`) the teleoperation's. ``node`` is the rclpy node to publish
    from; by default one named ``metaquest_teleop``, with ROS initialised if it is not yet.

    When this Python cannot load ROS 2, the topics go out through a helper process with the
    Python ROS 2 runs on; ``python`` names one to always do that with. :attr:`python` is the
    helper's Python, None when publishing from this one. Raises :class:`RosUnavailable` when
    ROS 2 cannot publish from here at all.
    """

    def __init__(self, quest: QuestHands, node=None, adapt: bool = True, prefix: str = "/metaquest",
                 teleop: Teleop | None = None, python: str | None = None) -> None:
        if node is not None and python is not None:
            raise ValueError("node publishes from this Python, python from a helper: give one or the other")
        self._sides =("left", "right") if quest.hands == "both" else (quest.hands,)
        self._prefix, self._adapt, self.teleop = prefix, adapt and "right" in self._sides, teleop
        topics = {}
        for side in self._sides:
            topics.update({f"{prefix}/{side}/joint_states": "joint_state", f"{prefix}/{side}/wrist": "pose",
                           f"{prefix}/{side}/joints": "poses", f"{prefix}/{side}/pinch": "float64"})
        if self._adapt:
            topics.update({f"{prefix}/adapt/joint_states": "joint_state",
                           f"{prefix}/adapt/motors": "joint_state", f"{prefix}/adapt/wrist": "pose"})
        if teleop is not None:
            topics.update({f"{prefix}/teleop/hold": "bool", f"{prefix}/teleop/state": "string",
                           f"{prefix}/teleop/wrist": "pose"})

        self.node, self.python = None, python
        if python is None:
            try:
                from .ros_publish import Publishers  # noqa: PLC0415 -- ROS 2 in this Python, if it loads
            except Exception as exc:  # noqa: BLE001 -- no ROS, or one for another Python
                self.python = ros_python() if node is None else None
                if self.python is None:
                    raise _unavailable(exc) from None
            else:
                self._out = Publishers(topics, FRAME_ID, node=node)
                self.node = self._out.node
        if self.python is not None:
            self._out = _Helper(self.python, topics, quest)
        self._open = True
        quest.on_frame(self._publish)
        if teleop is not None:  # hold, also while frames stop
            threading.Thread(target=self._watch, name="metaquest-teleop-ros", daemon=True).start()

    def _publish(self, frame: Frame) -> None:
        if not self._open:
            return
        stamp, messages = frame.received, []
        for side in self._sides:
            hand = frame.hand(side)
            if hand is None:
                continue
            topic = f"{self._prefix}/{side}"
            messages += [(f"{topic}/joint_states", stamp, (ANGLE_NAMES, hand.angles.ravel().tolist())),
                         (f"{topic}/wrist", stamp, _pose(hand.wrist)),
                         (f"{topic}/joints", stamp, np.hstack([hand.positions, hand.quaternions]).tolist()),
                         (f"{topic}/pinch", stamp, float(hand.pinch))]
        command = self.teleop.command() if self.teleop is not None else None
        if self._adapt and frame.right is not None:
            if command is None:
                joints = adapt.joint_angles(frame.right)
                motors = adapt.motor_angles(joints)
            else:
                joints, motors = command.joints, command.motors
            if joints is not None:
                messages.append((f"{self._prefix}/adapt/joint_states", stamp,
                                 (adapt.JOINTS, np.asarray(joints, float).tolist())))
            if motors is not None:
                messages.append((f"{self._prefix}/adapt/motors", stamp,
                                 (adapt.MOTORS, np.asarray(motors, float).tolist())))
            messages.append((f"{self._prefix}/adapt/wrist", stamp, _pose(adapt.wrist_pose(frame.right))))
        if command is not None:
            messages += self._teleop(command, stamp)
        self._out.publish(messages)

    def _teleop(self, command, stamp: float) -> list:
        messages = [(f"{self._prefix}/teleop/hold", stamp, bool(command.hold)),
                    (f"{self._prefix}/teleop/state", stamp, command.reason or "moving")]
        if command.wrist is not None:
            messages.append((f"{self._prefix}/teleop/wrist", stamp, _pose(command.wrist)))
        return messages

    def _watch(self) -> None:
        while self._open:
            command = self.teleop.command()
            if command.reason in ("no frames", "no frames yet"):
                try:
                    self._out.publish(self._teleop(command, time.time()))
                except Exception:  # noqa: BLE001 -- ROS shutting down
                    return
            time.sleep(0.1)

    def close(self) -> None:
        """Stop publishing: end the helper, or destroy the node and shut ROS down if this made them."""
        self._open = False
        self._out.close()


class _Helper:
    """Publishes through :mod:`metaquest_teleop.ros_publish`, run by another Python."""

    def __init__(self, python: str, topics: dict[str, str], quest: QuestHands) -> None:
        self._quest = quest
        self._errors = tempfile.TemporaryFile(mode="w+", encoding="utf-8")  # what it says if it fails
        script = Path(__file__).with_name("ros_publish.py")
        try:
            self._process = subprocess.Popen(
                [python, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._errors,
                text=True, encoding="utf-8")
        except OSError as exc:
            self._errors.close()
            raise RosUnavailable(f"{_ros_name()} did not start with {python} ({exc})", f"See {_DOCS}") from None
        answer: list[str] = []
        try:
            self._process.stdin.write(json.dumps({"name": "metaquest_teleop", "frame": FRAME_ID,
                                                  "topics": topics}) + "\n")
            self._process.stdin.flush()
        except OSError:
            pass  # it has already stopped: its errors say why
        else:
            reader = threading.Thread(target=lambda: answer.append(self._process.stdout.readline()), daemon=True)
            reader.start()
            reader.join(30.0)  # starting ROS the first time can take a while
        if not answer or answer[0].strip() != "ready":
            self._process.kill()
            self._process.wait()
            why = self._last_error() or "no answer"
            self._errors.close()
            raise RosUnavailable(f"{_ros_name()} did not start with {python} ({why})", f"See {_DOCS}")
        threading.Thread(target=self._process.stdout.read, daemon=True).start()  # never let it block
        self._alive = True
        self._queue: queue.Queue = queue.Queue(maxsize=240)  # two seconds of frames
        self._thread = threading.Thread(target=self._write, name="metaquest-teleop-ros-helper", daemon=True)
        self._thread.start()

    def _last_error(self) -> str:
        self._errors.seek(0)
        lines = [line.strip() for line in self._errors.read().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def publish(self, messages: list) -> None:
        if self._alive:
            try:
                self._queue.put_nowait(messages)
            except queue.Full:
                pass  # the helper lags: drop this frame rather than slow the stream

    def _write(self) -> None:
        while (messages := self._queue.get()) is not None:
            try:
                self._process.stdin.write(json.dumps(messages, separators=(",", ":")) + "\n")
                self._process.stdin.flush()
            except (OSError, ValueError):  # it stopped
                self._alive = False
                self._quest._event(f"ROS 2 stopped publishing ({self._last_error() or 'its helper ended'})")
                return

    def close(self) -> None:
        self._alive = False
        while True:  # the end mark, even when the queue is full
            try:
                self._queue.put_nowait(None)
                break
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
        self._thread.join(2.0)
        try:
            self._process.stdin.close()
        except OSError:
            pass
        try:
            self._process.wait(5.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._errors.close()
