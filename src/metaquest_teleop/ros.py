"""The hands on ROS 2 topics, with standard messages only: ROS 2 Humble and Jazzy alike.

    from metaquest_teleop import QuestHands
    from metaquest_teleop.ros import RosPublisher

    with QuestHands() as quest:
        ros = RosPublisher(quest)  # publishes every frame until closed
        ...
        ros.close()

or ``metaquest-teleop --ros``. Run it with the Python your ROS uses (3.10 for Humble, 3.12 for
Jazzy) after sourcing ROS. Topics, for each hand kept (the right one by default):

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

import threading
import time

import rclpy
from builtin_interfaces.msg import Time
from geometry_msgs.msg import Point, Pose, PoseArray, PoseStamped, Quaternion
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float64, Header, String

from . import adapt
from .hands import ANGLE_NAMES, Frame, Hand
from .server import QuestHands
from .teleop import Teleop

#: The frame of every pose: the headset's room (WebXR ``local-floor``).
FRAME_ID = "metaquest_floor"


def _init_ros() -> None:
    """Start ROS without its signal handlers: they would swallow Ctrl-C and stop requests."""
    try:
        from rclpy.signals import SignalHandlerOptions  # noqa: PLC0415

        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    except (ImportError, TypeError):  # an rclpy without the option
        rclpy.init()


def _stamp(seconds: float) -> Time:
    whole = int(seconds)
    return Time(sec=whole, nanosec=int((seconds - whole) * 1e9))


def _pose(position, quaternion) -> Pose:
    x, y, z = (float(v) for v in position)
    qx, qy, qz, qw = (float(v) for v in quaternion)
    return Pose(position=Point(x=x, y=y, z=z), orientation=Quaternion(x=qx, y=qy, z=qz, w=qw))


def _joint_state(header: Header, names, values) -> JointState:
    return JointState(header=header, name=list(names), position=[float(v) for v in values])


class RosPublisher:
    """Publish every frame of ``quest`` on ROS 2 topics (see the module's documentation).

    ``node`` is the rclpy node to publish from; by default one named ``metaquest_teleop``, with
    ROS initialised if it is not yet. ``adapt`` also publishes the ADAPT hand's topics, and
    ``teleop`` (a :class:`~metaquest_teleop.Teleop`) the teleoperation's.
    """

    def __init__(self, quest: QuestHands, node=None, adapt: bool = True, prefix: str = "/metaquest",
                 teleop: Teleop | None = None) -> None:
        self._own_init = not rclpy.ok()
        if self._own_init:
            _init_ros()
        self._own_node = node is None
        self.node = node if node is not None else rclpy.create_node("metaquest_teleop")
        sides = ("left", "right") if quest.hands == "both" else (quest.hands,)
        self._hands = {
            side: (self.node.create_publisher(JointState, f"{prefix}/{side}/joint_states", 10),
                   self.node.create_publisher(PoseStamped, f"{prefix}/{side}/wrist", 10),
                   self.node.create_publisher(PoseArray, f"{prefix}/{side}/joints", 10),
                   self.node.create_publisher(Float64, f"{prefix}/{side}/pinch", 10))
            for side in sides
        }
        self._adapt = None
        if adapt and "right" in sides:
            self._adapt = (self.node.create_publisher(JointState, f"{prefix}/adapt/joint_states", 10),
                           self.node.create_publisher(JointState, f"{prefix}/adapt/motors", 10),
                           self.node.create_publisher(PoseStamped, f"{prefix}/adapt/wrist", 10))
        self.teleop = teleop
        self._teleop = None
        if teleop is not None:
            self._teleop = (self.node.create_publisher(Bool, f"{prefix}/teleop/hold", 10),
                            self.node.create_publisher(String, f"{prefix}/teleop/state", 10),
                            self.node.create_publisher(PoseStamped, f"{prefix}/teleop/wrist", 10))
        self._open = True
        quest.on_frame(self._publish)
        if teleop is not None:  # hold, also while frames stop
            threading.Thread(target=self._watch, name="metaquest-teleop-ros", daemon=True).start()

    def _publish(self, frame: Frame) -> None:
        if not self._open:
            return
        stamp = _stamp(frame.received)
        for side, (joint_states, wrist, joints, pinch) in self._hands.items():
            hand: Hand | None = frame.hand(side)
            if hand is None:
                continue
            joint_states.publish(_joint_state(Header(stamp=stamp), ANGLE_NAMES, hand.angles.ravel()))
            room = Header(stamp=stamp, frame_id=FRAME_ID)
            wrist.publish(PoseStamped(header=room, pose=_pose(hand.wrist.position, hand.wrist.quaternion)))
            joints.publish(PoseArray(header=room, poses=[
                _pose(p, q) for p, q in zip(hand.positions, hand.quaternions)]))
            pinch.publish(Float64(data=hand.pinch))
        command = self.teleop.command() if self.teleop is not None else None
        if self._adapt is not None and frame.right is not None:
            joint_states, motors, wrist = self._adapt
            if command is None:
                joints = adapt.joint_angles(frame.right)
                values = (joints, adapt.motor_angles(joints), adapt.wrist_pose(frame.right))
            else:
                values = (command.joints, command.motors, adapt.wrist_pose(frame.right))
            if values[0] is not None:
                joint_states.publish(_joint_state(Header(stamp=stamp), adapt.JOINTS, values[0]))
                motors.publish(_joint_state(Header(stamp=stamp), adapt.MOTORS, values[1]))
            wrist.publish(PoseStamped(header=Header(stamp=stamp, frame_id=FRAME_ID),
                                      pose=_pose(values[2].position, values[2].quaternion)))
        if command is not None:
            self._publish_teleop(command, stamp)

    def _publish_teleop(self, command, stamp: Time) -> None:
        hold, state, wrist = self._teleop
        hold.publish(Bool(data=command.hold))
        state.publish(String(data=command.reason or "moving"))
        if command.wrist is not None:
            wrist.publish(PoseStamped(header=Header(stamp=stamp, frame_id=FRAME_ID),
                                      pose=_pose(command.wrist.position, command.wrist.quaternion)))

    def _watch(self) -> None:
        while self._open:
            command = self.teleop.command()
            if command.reason in ("no frames", "no frames yet"):
                try:
                    self._publish_teleop(command, _stamp(time.time()))
                except Exception:  # noqa: BLE001 -- ROS shutting down
                    return
            time.sleep(0.1)

    def close(self) -> None:
        """Stop publishing; destroy the node and shut ROS down if this publisher made them."""
        self._open = False
        if self._own_node:
            self.node.destroy_node()
        if self._own_init and rclpy.ok():
            rclpy.shutdown()
