"""Live terminal dashboard of the hand stream."""

from __future__ import annotations

import time

import numpy as np
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import adapt
from .hands import FINGERS, Hand
from .server import QuestHands

_BLOCKS = " ▏▎▍▌▋▊▉"
_STALE_S = 0.5


def _bar(degrees: float, width: int = 6, full: float = 100.0) -> str:
    cells = max(0.0, min(degrees / full, 1.0)) * width
    whole = int(cells)
    tail = _BLOCKS[int((cells - whole) * 8)] if whole < width else ""
    return ("█" * whole + tail).ljust(width)


def _deg(value: float, signed: bool = False) -> str:
    return f"{int(round(float(value))):{'+' if signed else ''}4d}°"


def _dot(state: bool | None) -> tuple[str, str]:
    return ("● ", "green" if state else ("yellow" if state is None else "red"))


def _yaw_pitch_roll(r: np.ndarray) -> tuple[float, float, float]:
    """Degrees: yaw about +y (up), pitch about +x (right), roll about +z, applied in that order."""
    return (float(np.degrees(np.arctan2(r[0, 2], r[2, 2]))),
            float(np.degrees(np.arcsin(np.clip(-r[1, 2], -1.0, 1.0)))),
            float(np.degrees(np.arctan2(r[1, 0], r[1, 1]))))


def _status(quest: QuestHands) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    grid.add_row("page", Text.assemble((quest.url, "bold"), ("   open in the Quest browser, press Start", "dim")))
    grid.add_row("3D view", Text.assemble((quest.view_url, "bold"), ("   open in a browser on this computer", "dim")))
    if quest.use_adb:
        grid.add_row("USB", Text.assemble(_dot(quest.usb_ok or quest.connected), quest.usb))

    info, rates = quest.headset, quest.rates()
    streaming = rates["age_ms"] is not None and rates["age_ms"] < _STALE_S * 1000
    if not quest.connected:
        headset = Text.assemble(_dot(None), "waiting for the page to connect")
    elif info.get("session") == "started":
        fps = info.get("fps")  # unknown when an older page reconnected while streaming
        headset = Text.assemble(_dot(streaming), "streaming", *((" at ", (f"{fps} Hz", "bold")) if fps else ()),
                                " (fake headset)" if info.get("mode") == "fake" else "")
    else:
        headset = Text.assemble(_dot(None), "page open: press Start in the headset")
    grid.add_row("headset", headset)

    if rates["age_ms"] is None:
        stream = Text("no frames yet", style="dim")
    elif not streaming:
        stream = Text(f"no frames for {rates['age_ms'] / 1000:.1f} s  ({quest.frames:,} received)", style="yellow")
    else:
        stream = Text.assemble((f"{rates['hz']} frames/s", "bold green"),
                               (f"   {quest.frames:,} received", "dim"))
    grid.add_row("stream", stream)
    if quest.teleop is not None:
        command = quest.teleop.command()
        if not command.hold:
            robot = Text.assemble(_dot(True), f"moving with your {quest.teleop.drive} hand",
                                  (f"   pinch your {quest.teleop.gesture} hand to hold", "dim"))
        else:
            robot = Text.assemble(_dot(None if "pinching" in command.reason else False),
                                  f"holding: {command.reason}")
        grid.add_row("robot", robot)
    if quest.udp is not None:
        grid.add_row("UDP", f"every frame as JSON to {quest.udp[0]}:{quest.udp[1]}")
    for stamp, text in list(quest.events)[-3:]:
        grid.add_row("", Text(f"{time.strftime('%H:%M:%S', time.localtime(stamp))}  {text}", style="dim"))
    return Panel(grid, title="[bold]Quest hand stream", title_align="left", border_style="blue",
                 box=box.ROUNDED)


def _hand(side: str, hand: Hand | None) -> Panel:
    if hand is None:
        return Panel(Text("not tracked", style="dim"), title=f"[bold]{side.upper()}[/]  [dim]○",
                     title_align="left", border_style="grey37", box=box.ROUNDED)
    p = hand.wrist.position
    yaw, pitch, roll = _yaw_pitch_roll(hand.wrist.rotation)
    info = Table.grid(padding=(0, 2))
    info.add_column(style="cyan")
    info.add_row("wrist", f"x {p[0]:+.3f}   y {p[1]:+.3f}   z {p[2]:+.3f}  m")
    info.add_row("", f"yaw {_deg(yaw, True)}  pitch {_deg(pitch, True)}  roll {_deg(roll, True)}")
    info.add_row("pinch", f"{hand.pinch * 1000:.0f} mm")

    angles = Table(box=None, padding=(0, 1), header_style="dim", show_edge=False,
                   caption="degrees of bend; spread is sideways at the base",
                   caption_style="dim")
    angles.add_column("")
    for name in ("base", "spread", "middle", "tip"):
        angles.add_column(name, justify="right" if name == "spread" else "left")
    for finger, row in zip(FINGERS, np.degrees(hand.angles)):
        angles.add_row(finger, f"{_bar(row[0])}{_deg(row[0])}", _deg(row[1], True),
                       f"{_bar(row[2])}{_deg(row[2])}", f"{_bar(row[3])}{_deg(row[3])}")
    return Panel(Group(info, Text(), angles), title=f"[bold]{side.upper()}[/]  [green]● tracked",
                 title_align="left", border_style="green", box=box.ROUNDED)


def _adapt_cell(joints: np.ndarray, i: int) -> Text:
    """One ADAPT joint: bending ones with a bar across their range, sideways ones signed; yellow at a limit."""
    name = adapt.JOINTS[i]
    low, high = adapt.JOINT_LIMITS[name]
    value = float(joints[i])
    style = "bold yellow" if any(abs(value - edge) < 1e-6 and edge != 0.0 for edge in (low, high)) else ""
    if name.endswith("spread") or name == "thumb_CMC2":  # sideways, either way from straight
        return Text(_deg(np.degrees(value), True), style=style)
    return Text(f"{_bar(np.degrees(value), width=5, full=np.degrees(high))}{_deg(np.degrees(value))}", style=style)


def _adapt(teleop) -> Panel:
    """The ADAPT hand as the robot gets it: what the teleoperation commands, still while it holds."""
    command = teleop.command()
    if not command.hold:
        state = "[green]● moving"
    else:
        state = f"[{'yellow' if 'pinching' in command.reason else 'red'}]● holding: {command.reason}"
    title = f"[bold yellow]ADAPT[/]  {state}"
    if command.joints is None:
        return Panel(Text("waiting for both hands", style="dim"), title=title, title_align="left",
                     border_style="yellow", box=box.ROUNDED)
    joints = np.asarray(command.joints, dtype=float)
    info = Table.grid(padding=(0, 2))
    info.add_column(style="yellow")
    if command.wrist is not None:
        p = command.wrist.position
        info.add_row("arm", f"x {p[0]:+.3f}   y {p[1]:+.3f}   z {p[2]:+.3f}  m")
    info.add_row("wrist", Text.assemble(f"yaw {_deg(0.0)}  pitch {_deg(0.0)}", ("   fixed: a PID holds it", "dim")))
    info.add_row("", "")  # so the table starts on the same line as your hand's

    table = Table(box=None, padding=(0, 1), header_style="dim", show_edge=False,
                  caption="bars span each range; yellow: at a limit", caption_style="dim")
    table.add_column("")
    for name in ("spread", "MCP", "PIP", "DIP"):
        table.add_column(name, justify="right" if name == "spread" else "left")
    for d, digit in enumerate(adapt.DIGITS[1:], start=1):
        table.add_row(digit, *(_adapt_cell(joints, 4 * d + k) for k in range(4)))
    # The thumb in the same columns: its sideways joint (CMC2) under spread, then its bending ones.
    table.add_row("", *(Text(name, style="dim") for name in ("CMC2", "CMC1", "MCP", "IP")))
    table.add_row("thumb", *(_adapt_cell(joints, k) for k in (1, 0, 2, 3)))
    return Panel(Group(info, Text(), table), title=title, title_align="left", border_style="yellow",
                 box=box.ROUNDED)


def render(quest: QuestHands, width: int = 120) -> Group:
    """The dashboard for the current state of ``quest``, as a rich renderable ``width`` wide."""
    frame = quest.latest()
    fresh = frame is not None and time.time() - frame.received < _STALE_S
    sides = ("left", "right") if quest.hands == "both" else (quest.hands,)
    panels = [_hand(side, frame.hand(side) if fresh else None) for side in sides]
    if quest.teleop is not None and quest.teleop.adapt:  # the ADAPT hand, next to yours
        panels.append(_adapt(quest.teleop))
    columns = min(len(panels), max(1, width // 52))
    if columns > 1:
        hands = Table.grid(expand=True, padding=(0, 1))
        for _ in range(columns):
            hands.add_column(ratio=1)
        for i in range(0, len(panels), columns):
            row = panels[i:i + columns]
            hands.add_row(*row, *([""] * (columns - len(row))))
    else:
        hands = Group(*panels)
    return Group(_status(quest), hands, Text("  Ctrl-C to stop", style="dim"))


def run(quest: QuestHands, refresh_hz: float = 12.0) -> None:
    """Redraw the dashboard until Ctrl-C."""
    console = Console()
    with Live(console=console, auto_refresh=False, transient=False) as live:
        while True:
            live.update(render(quest, console.width), refresh=True)
            time.sleep(1.0 / refresh_hz)
