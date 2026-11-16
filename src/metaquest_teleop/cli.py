"""Stream Meta Quest hand tracking to this computer, with a live dashboard.

    metaquest-teleop                        # then open http://localhost:8012 in the Quest browser
    metaquest-teleop --view                 # also open the 3D view of the hands in a browser
    metaquest-teleop --print_joints         # print your joint angles and the ADAPT hand's
    metaquest-teleop --no-adapt             # no ADAPT hand: no ADAPT topics, no ADAPT joints
    metaquest-teleop --no-ros               # not on ROS 2 (the default publishes when ROS is found)
    metaquest-teleop --udp 127.0.0.1:9000   # also send every frame as JSON to a UDP port
    metaquest-teleop-fake                   # in a second terminal: a fake headset, for testing
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import time
import webbrowser

import numpy as np

from . import DEFAULT_PORT, QuestHands, __version__, adapt
from .hands import FINGERS, Hand
from .teleop import Teleop

PRINT_HZ = 10.0  # lines per second with --print_joints


def plain(quest: QuestHands) -> None:
    """One status line per second, for logs and terminals without the dashboard."""
    print(f"page {quest.url}   3D view {quest.view_url}", flush=True)
    while True:
        time.sleep(1.0)
        frame, rates = quest.latest(), quest.rates()
        hands = [f"{side} wrist {hand.wrist.position.round(3).tolist()}"
                 for side, hand in (("left", frame and frame.left), ("right", frame and frame.right)) if hand]
        print(f"{time.strftime('%H:%M:%S')}  {rates['hz']:3d} frames/s  usb: {quest.usb}  "
              + ("  ".join(hands) or "no hands"), flush=True)


def joints_header(which: str) -> str:
    """The first line of ``--print_joints``: what the numbers are."""
    if which == "adapt":
        return ("ADAPT joints, degrees, within their limits: thumb CMC1 CMC2 MCP IP | "
                "each finger spread MCP PIP DIP")
    return "joint angles, degrees: each finger base spread middle tip"


def _angles_line(label: str, degrees: np.ndarray, names) -> str:
    return f"{label:5s}  " + " | ".join(
        f"{name} " + " ".join(f"{v:+4.0f}" for v in row) for name, row in zip(names, degrees))


def joints_line(side: str, hand: Hand | None, which: str) -> str:
    """One line of ``--print_joints``: the hand's joint angles, or the ADAPT hand's, in degrees."""
    if hand is None:
        return f"{side:5s}  not tracked"
    if which == "adapt":
        return _angles_line(side, np.degrees(adapt.joint_angles(hand)).reshape(5, 4), adapt.DIGITS)
    return _angles_line(side, np.degrees(hand.angles), FINGERS)


def adapt_line(teleop: Teleop) -> str:
    """The ADAPT hand's line of ``--print_joints``: its joints as the robot gets them, which hold
    still while the robot holds (as on ``/metaquest/adapt/joint_states``)."""
    joints = teleop.command().joints
    if joints is None:
        return "ADAPT  waiting for both hands"
    return _angles_line("ADAPT", np.degrees(joints).reshape(5, 4), adapt.DIGITS)


def robot_state(teleop: Teleop) -> str:
    """The end of a ``--print_joints`` line: whether the robot moves, or why it holds."""
    command = teleop.command()
    return "robot moving" if not command.hold else f"robot HOLD ({command.reason})"


def print_joints(quest: QuestHands, teleop: Teleop) -> None:
    """Print, ``PRINT_HZ`` times a second until Ctrl-C, all the joint angles of the kept hands and,
    when the teleoperation drives the ADAPT hand, the ADAPT hand's joints, with the robot's state."""
    print(f"page {quest.url}   3D view {quest.view_url}", flush=True)
    print(joints_header("hand"), flush=True)
    if teleop.adapt:
        print(joints_header("adapt"), flush=True)
    sides = ("left", "right") if quest.hands == "both" else (quest.hands,)
    while True:
        frame = quest.wait(timeout=1.0)
        now = time.strftime("%H:%M:%S")
        if frame is None:
            print(f"{now}  no frames: open {quest.url} in the headset and press Start"
                  f"  | {robot_state(teleop)}", flush=True)
            continue
        lines = [joints_line(side, frame.hand(side), "hand") for side in sides]
        if teleop.adapt:
            lines.append(adapt_line(teleop))
        lines[-1] += f"  | {robot_state(teleop)}"
        for line in lines:
            print(f"{now}  {line}", flush=True)
        time.sleep(1.0 / PRINT_HZ)


ROS_DOCS = "https://vigno0405.github.io/MetaQuestTeleop/ros.html"


def ros_unavailable(exc: Exception) -> tuple[str, str]:
    """Why this Python cannot publish on ROS 2, and what to do about it, in a few words each."""
    here = "{}.{}".format(*sys.version_info[:2])
    try:
        spec = importlib.util.find_spec("rclpy")
    except (ImportError, ValueError):
        spec = None
    if spec is None:
        return "ROS 2 not found", ("To publish, source ROS (for example `source /opt/ros/jazzy/setup.bash`) "
                                   f"and run with the Python ROS uses: {ROS_DOCS}")
    ros = re.search(r"python(\d+\.\d+)", spec.origin or "")
    if ros and ros[1] != here:  # for example ROS Jazzy (Python 3.12) from a conda env with 3.10
        name = " ".join(filter(None, ("ROS 2", os.environ.get("ROS_DISTRO", "").capitalize())))
        return (f"{name} runs on Python {ros[1]}, and this is Python {here}",
                f"To publish, run it with Python {ros[1]}: {ROS_DOCS}")
    return f"ROS 2 did not load ({' '.join(str(exc).split())})", f"See {ROS_DOCS}"


def _udp_address(text: str) -> tuple[str, int]:
    host, _, port = text.rpartition(":")
    try:
        return host or "127.0.0.1", int(port)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected HOST:PORT, got {text!r}") from None


def main() -> int:
    parser = argparse.ArgumentParser(prog="metaquest-teleop", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port of the page and the stream (default {DEFAULT_PORT})")
    parser.add_argument("--udp", metavar="HOST:PORT", type=_udp_address,
                        help="also send every frame as JSON to this UDP address")
    parser.add_argument("--no-adb", action="store_true", help="do not set up the USB link (adb reverse) automatically")
    parser.add_argument("--plain", action="store_true", help="one status line per second instead of the dashboard")
    parser.add_argument("--print_joints", "--print-joints", action="store_true",
                        help="print your joint angles and the ADAPT hand's instead of the dashboard")
    parser.add_argument("--view", action="store_true", help="also open the 3D view of the hands in a browser")
    parser.add_argument("--ros", dest="ros", action="store_const", const="on", default="auto",
                        help="publish on ROS 2 topics (/metaquest/...); the default when ROS 2 is found")
    parser.add_argument("--no-ros", dest="ros", action="store_const", const="off",
                        help="do not publish on ROS 2")
    parser.add_argument("--no-adapt", action="store_true",
                        help="no ADAPT hand: no ADAPT topics or printed ADAPT joints; the teleoperation gives your own joint angles")
    parser.add_argument("--hands", choices=("right", "left", "both"), default="right",
                        help="the hands to stream (default right)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    RosPublisher = None  # noqa: N806
    if args.ros != "off":
        try:
            from .ros import RosPublisher  # noqa: PLC0415 -- ROS only when there is ROS
        except Exception as exc:  # noqa: BLE001 -- no ROS, or one for another Python
            why, how = ros_unavailable(exc)
            if args.ros == "on":
                print(f"{why}: cannot publish. {how}")
                return 1
            print(f"{why}: not publishing (--no-ros hides this). {how}")
    try:
        quest = QuestHands(args.port, adb=not args.no_adb, udp=args.udp, hands=args.hands).start()
    except OSError as exc:
        print(f"Could not serve on port {args.port}: {exc}. Is another copy already running?")
        return 1
    teleop = Teleop(quest, adapt=not args.no_adapt)  # the other hand pauses the robot
    ros = RosPublisher(quest, adapt=not args.no_adapt, teleop=teleop) if RosPublisher is not None else None
    if ros is not None:
        print("publishing on ROS 2: /metaquest/... (ros2 topic list)", flush=True)
    if args.view:
        webbrowser.open(quest.view_url)
    try:
        if args.print_joints:
            print_joints(quest, teleop)
        elif args.plain or not sys.stdout.isatty():
            plain(quest)
        else:
            from .dashboard import run  # noqa: PLC0415 -- rich only for the dashboard
            run(quest)
    except KeyboardInterrupt:
        pass
    finally:
        if ros is not None:
            ros.close()
        quest.stop()
    print(f"Stopped after {quest.frames:,} frames.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
