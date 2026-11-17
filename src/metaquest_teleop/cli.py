"""Stream Meta Quest hand tracking to this computer, with a live dashboard.

    metaquest-teleop                        # then open http://localhost:8012 in the Quest browser
    metaquest-teleop --view                 # also open the 3D view of the hands in a browser
    metaquest-teleop --print_joints         # print your joint angles and the ADAPT hand's
    metaquest-teleop --no-adapt             # no ADAPT hand: no ADAPT topics, no ADAPT joints
    metaquest-teleop --no-adapt-fit         # the ADAPT hand joint for joint, not fitted to yours
    metaquest-teleop --calibration          # calibrate the ADAPT hand in the 3D view; it is saved
    metaquest-teleop --no-ros               # not on ROS 2 (the default publishes when ROS is found)
    metaquest-teleop --udp 127.0.0.1:9000   # also send every frame as JSON to a UDP port
    metaquest-teleop-fake                   # in a second terminal: a fake headset, for testing
"""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

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


def adapt_line(hand: Hand | None) -> str:
    """The ADAPT hand's line of ``--print_joints``: its joints for your hand as it is, the pose it
    can take. (The robot's state ends the line; what it gets is on ``/metaquest/adapt/...``.)"""
    if hand is None:
        return "ADAPT  not tracked"
    return _angles_line("ADAPT", np.degrees(adapt.joint_angles(hand)).reshape(5, 4), adapt.DIGITS)


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
            lines.append(adapt_line(frame.hand(teleop.drive)))
        lines[-1] += f"  | {robot_state(teleop)}"
        for line in lines:
            print(f"{now}  {line}", flush=True)
        time.sleep(1.0 / PRINT_HZ)


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
    parser.add_argument("--no-adapt-fit", action="store_true",
                        help="the ADAPT fingers joint for joint, through your calibration, instead of fitted to yours")
    parser.add_argument("--calibration", action="store_true",
                        help="calibrate the ADAPT hand in the 3D view, which opens: your points are saved to the calibration file")
    files = parser.add_mutually_exclusive_group()
    files.add_argument("--calibration-file", metavar="FILE", type=Path,
                       help=f"the ADAPT calibration to load, and to save to with --calibration (default {adapt.CALIBRATION_FILE})")
    files.add_argument("--no-calibration-file", action="store_true",
                       help="do not load the saved ADAPT calibration: the default one")
    parser.add_argument("--hands", choices=("right", "left", "both"), default="right",
                        help="the hands to stream (default right)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()
    if args.calibration and args.no_adapt:
        parser.error("--calibration calibrates the ADAPT hand: leave out --no-adapt")
    if args.calibration and args.no_calibration_file:
        parser.error("--calibration saves to the calibration file: leave out --no-calibration-file")
    if args.no_adapt_fit:
        adapt.FIT = False
    calibration = None if args.no_calibration_file else args.calibration_file or adapt.CALIBRATION_FILE
    if not args.no_adapt:
        try:
            loaded = calibration is not None and adapt.load_calibration(calibration)
        except ValueError as exc:
            print(exc)
            return 1
        if loaded:
            print(f"ADAPT calibration: {calibration}", flush=True)
        elif args.calibration_file is not None and not args.calibration:
            print(f"No ADAPT calibration in {calibration}: make one with --calibration, or leave out --calibration-file")
            return 1
        else:
            print("ADAPT calibration: the default one" + (f" (yours will go to {calibration})" if args.calibration else ""), flush=True)

    try:
        quest = QuestHands(args.port, adb=not args.no_adb, udp=args.udp, hands=args.hands).start()
    except OSError as exc:
        print(f"Could not serve on port {args.port}: {exc}. Is another copy already running?")
        return 1
    teleop = Teleop(quest, adapt=not args.no_adapt)  # the other hand pauses the robot
    ros = None
    if args.ros != "off":
        from .ros import RosPublisher, RosUnavailable  # noqa: PLC0415

        try:
            ros = RosPublisher(quest, adapt=not args.no_adapt, teleop=teleop)
        except RosUnavailable as exc:
            if args.ros == "on":
                print(f"{exc}: cannot publish. {exc.how}")
                quest.stop()
                return 1
            print(f"{exc}: not publishing (--no-ros hides this). {exc.how}")
        else:
            through = f" through {ros.python}, the Python ROS 2 runs on" if ros.python else ""
            print(f"publishing on ROS 2{through}: /metaquest/... (ros2 topic list)", flush=True)
    if args.calibration:
        quest.calibration = calibration
        print(f"Calibrate the ADAPT hand in the 3D view: {quest.view_url}?mode=adapt", flush=True)
        webbrowser.open(f"{quest.view_url}?mode=adapt")
    elif args.view:
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
