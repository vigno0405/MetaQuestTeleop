"""Stream Meta Quest hand tracking to this computer, with a live dashboard.

    metaquest-teleop                        # then open http://localhost:8012 in the Quest browser
    metaquest-teleop --udp 127.0.0.1:9000   # also send every frame as JSON to a UDP port
    metaquest-teleop --view                 # also open the 3D view of the hands in a browser
    metaquest-teleop-fake                   # in a second terminal: a fake headset, for testing
"""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser

from . import DEFAULT_PORT, QuestHands, __version__


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
    parser.add_argument("--view", action="store_true", help="also open the 3D view of the hands in a browser")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    try:
        quest = QuestHands(args.port, adb=not args.no_adb, udp=args.udp).start()
    except OSError as exc:
        print(f"Could not serve on port {args.port}: {exc}. Is another copy already running?")
        return 1
    if args.view:
        webbrowser.open(quest.view_url)
    try:
        if args.plain or not sys.stdout.isatty():
            plain(quest)
        else:
            from .dashboard import run  # noqa: PLC0415 -- rich only for the dashboard
            run(quest)
    except KeyboardInterrupt:
        pass
    finally:
        quest.stop()
    print(f"Stopped after {quest.frames:,} frames.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
