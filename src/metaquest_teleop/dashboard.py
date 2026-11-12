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
        headset = Text.assemble(_dot(streaming), f"XR session: {info.get('mode')}, ",
                                (f"{info.get('fps')} Hz", "bold"), f", {info.get('space')}")
    else:
        headset = Text.assemble(_dot(None), "page open: press Start in the headset")
    grid.add_row("headset", headset)

    if rates["age_ms"] is None:
        stream = Text("no frames yet", style="dim")
    elif not streaming:
        stream = Text(f"no frames for {rates['age_ms'] / 1000:.1f} s  ({quest.frames:,} received)", style="yellow")
    else:
        p95 = rates["interval_p95_ms"]
        stream = Text.assemble((f"{rates['hz']} frames/s", "bold green"),
                               f"   hands changed in {rates['changed_hz']}/s",
                               f"   gap p95 {p95:.1f} ms" if p95 is not None else "",
                               (f"   {quest.frames:,} frames", "dim"))
    grid.add_row("stream", stream)
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
                   caption="thumb: CMC, MCP, IP   fingers: MCP, PIP, DIP", caption_style="dim")
    angles.add_column("")
    for name in ("flex", "abd", "flex", "flex"):
        angles.add_column(name, justify="right" if name == "abd" else "left")
    for finger, row in zip(FINGERS, np.degrees(hand.angles)):
        angles.add_row(finger, f"{_bar(row[0])}{_deg(row[0])}", _deg(row[1], True),
                       f"{_bar(row[2])}{_deg(row[2])}", f"{_bar(row[3])}{_deg(row[3])}")
    return Panel(Group(info, Text(), angles), title=f"[bold]{side.upper()}[/]  [green]● tracked",
                 title_align="left", border_style="green", box=box.ROUNDED)


def render(quest: QuestHands, width: int = 120) -> Group:
    """The dashboard for the current state of ``quest``, as a rich renderable ``width`` wide."""
    frame = quest.latest()
    fresh = frame is not None and time.time() - frame.received < _STALE_S
    left, right = (frame.left, frame.right) if fresh else (None, None)
    if width >= 104:
        hands = Table.grid(expand=True, padding=(0, 1))
        hands.add_column(ratio=1)
        hands.add_column(ratio=1)
        hands.add_row(_hand("left", left), _hand("right", right))
    else:
        hands = Group(_hand("left", left), _hand("right", right))
    return Group(_status(quest), hands, Text("  Ctrl-C to stop", style="dim"))


def run(quest: QuestHands, refresh_hz: float = 12.0) -> None:
    """Redraw the dashboard until Ctrl-C."""
    console = Console()
    with Live(console=console, auto_refresh=False, transient=False) as live:
        while True:
            live.update(render(quest, console.width), refresh=True)
            time.sleep(1.0 / refresh_hz)
