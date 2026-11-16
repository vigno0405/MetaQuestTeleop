"""Publish plain data on ROS 2 topics: the part of :mod:`metaquest_teleop.ros` that needs rclpy.

It runs inside the program when its Python can load ROS 2. Otherwise it runs as a helper process
with the Python ROS 2 runs on (a conda environment with Python 3.10 and ROS 2 Jazzy, on 3.12,
say). As a helper it reads one JSON line with the node's name, the frame of the poses and the
topics, answers ``ready``, then publishes each following line, a list of ``[topic, stamp, data]``,
until its input ends. It needs rclpy and the standard messages only: not numpy, not this package.
"""

from __future__ import annotations

if __name__ == "__main__":  # the helper: keep this package's other modules off the import path
    import os as _os
    import sys as _sys

    _here = _os.path.dirname(_os.path.abspath(__file__))
    _sys.path[:] = [p for p in _sys.path if _os.path.abspath(p or _os.curdir) != _here]

import json
import signal
import sys

import rclpy
from builtin_interfaces.msg import Time
from geometry_msgs.msg import Point, Pose, PoseArray, PoseStamped, Quaternion
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float64, Header, String


def _time(seconds: float) -> Time:
    whole = int(seconds)
    return Time(sec=whole, nanosec=int((seconds - whole) * 1e9))


def _pose(values) -> Pose:
    x, y, z, qx, qy, qz, qw = (float(v) for v in values)
    return Pose(position=Point(x=x, y=y, z=z), orientation=Quaternion(x=qx, y=qy, z=qz, w=qw))


#: Each kind of topic: its message, and how to make one from (frame, stamp, data).
KINDS = {
    "joint_state": (JointState, lambda frame, stamp, data: JointState(
        header=Header(stamp=_time(stamp)), name=list(data[0]), position=[float(v) for v in data[1]])),
    "pose": (PoseStamped, lambda frame, stamp, data: PoseStamped(
        header=Header(stamp=_time(stamp), frame_id=frame), pose=_pose(data))),
    "poses": (PoseArray, lambda frame, stamp, data: PoseArray(
        header=Header(stamp=_time(stamp), frame_id=frame), poses=[_pose(p) for p in data])),
    "float64": (Float64, lambda frame, stamp, data: Float64(data=float(data))),
    "bool": (Bool, lambda frame, stamp, data: Bool(data=bool(data))),
    "string": (String, lambda frame, stamp, data: String(data=str(data))),
}


def _init_ros() -> None:
    """Start ROS without its signal handlers: they would swallow Ctrl-C and stop requests."""
    try:
        from rclpy.signals import SignalHandlerOptions  # noqa: PLC0415

        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    except (ImportError, TypeError):  # an rclpy without the option
        rclpy.init()


class Publishers:
    """A publisher on ``node`` for each of ``topics`` (name: kind, one of :data:`KINDS`).

    Without a ``node``, one named ``name``, with ROS initialised if it is not yet.
    """

    def __init__(self, topics: dict[str, str], frame: str, node=None, name: str = "metaquest_teleop") -> None:
        self._own_init = not rclpy.ok()
        if self._own_init:
            _init_ros()
        self._own_node = node is None
        self.node = node if node is not None else rclpy.create_node(name)
        self.frame = frame
        self._topics = {topic: (self.node.create_publisher(KINDS[kind][0], topic, 10), KINDS[kind][1])
                        for topic, kind in topics.items()}

    def publish(self, messages) -> None:
        """Publish each ``(topic, stamp, data)``; stamps are seconds since 1970."""
        for topic, stamp, data in messages:
            publisher, make = self._topics[topic]
            publisher.publish(make(self.frame, stamp, data))

    def close(self) -> None:
        """Destroy the node and shut ROS down, if these publishers made them."""
        if self._own_node:
            self.node.destroy_node()
        if self._own_init and rclpy.ok():
            rclpy.shutdown()


def main() -> None:
    """The helper: publish what comes on standard input, until it ends."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl-C stops the program, and so this
    setup = json.loads(sys.stdin.readline())
    publishers = Publishers(setup["topics"], setup["frame"], name=setup["name"])
    print("ready", flush=True)
    try:
        for line in sys.stdin:
            publishers.publish(json.loads(line))
    finally:
        publishers.close()


if __name__ == "__main__":
    main()
