"""The headset link: serves the WebXR page, sets up the USB tunnel, and receives hand frames."""

from __future__ import annotations

import asyncio
import collections
import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np
from aiohttp import WSMsgType, web

from .hands import Frame, decode

PAGE = Path(__file__).with_name("client.html")
#: The port of the page and the stream unless you choose another.
DEFAULT_PORT = 8012
_HANDS_OFFSET = 48


def adb_reverse(port: int) -> tuple[bool, str]:
    """Make the headset's localhost:port reach this computer over USB. Returns (ok, status)."""
    adb = shutil.which("adb")
    if adb is None:
        return False, "adb not found: install Android platform-tools (see README)"
    try:
        out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5).stdout
        devices = [line.split() for line in out.splitlines()[1:] if len(line.split()) > 1]
        ready = [serial for serial, state, *_ in devices if state == "device"]
        if not ready:
            if any(state == "unauthorized" for _, state, *_ in devices):
                return False, "headset not authorised: accept 'Allow USB debugging' inside the headset"
            return False, "no headset on USB: plug it in with a data cable, developer mode on"
        serial = ready[0]
        rule = f"tcp:{port} tcp:{port}"
        listed = subprocess.run([adb, "-s", serial, "reverse", "--list"],
                                capture_output=True, text=True, timeout=5).stdout
        if rule not in listed:
            subprocess.run([adb, "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"],
                           capture_output=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"adb failed: {exc}"
    return True, f"USB link ready ({serial})"


class QuestHands:
    """Hand tracking from a Meta Quest, received in background threads.

    ::

        with QuestHands() as quest:      # then open http://localhost:8012 in the Quest browser
            frame = quest.wait()         # the next frame from the headset
            frame.right.wrist.position   # metres
            frame.right.angles           # (5, 4) radians

    The server listens on 127.0.0.1 only: the headset reaches it through ``adb reverse``, and
    nothing else on the network can inject frames. Pass ``host="0.0.0.0"`` to change that.

    Parameters
    ----------
    port
        Port of the page and the stream: the headset opens ``http://localhost:<port>``.
    adb
        Keep the USB link up with ``adb reverse`` while no page is connected.
    udp
        ``(host, port)`` to also send every frame to, as one JSON datagram; None for no UDP.
    host
        The interface to listen on.

    Attributes
    ----------
    frames : int
        Frames received since the start.
    headset : dict
        What the connected page reported: ``agent``, ``mode``, ``fps``, ``space``,
        ``session`` and ``stats``; empty while no page is connected.
    usb_ok : bool
        Whether the last USB check succeeded.
    usb : str
        The USB link's status, as the dashboard shows it.
    events : collections.deque
        The last six ``(time.time(), text)`` status events.
    """

    def __init__(self, port: int = DEFAULT_PORT, adb: bool = True,
                 udp: tuple[str, int] | None = None, host: str = "127.0.0.1") -> None:
        self.port, self.host, self.udp = port, host, udp
        self.use_adb = adb
        self.usb_ok, self.usb = False, ("checking" if adb else "not managed (--no-adb)")
        self.headset: dict = {}
        self.events: collections.deque[tuple[float, str]] = collections.deque(maxlen=6)
        self.frames = 0
        self._latest: Frame | None = None
        self._cond = threading.Condition()
        self._callbacks: list[Callable[[Frame], None]] = []
        self._arrivals: collections.deque[tuple[float, bool]] = collections.deque(maxlen=2048)
        self._last_hands = b""
        self._clients: set[web.WebSocketResponse] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._error: BaseException | None = None
        self._udp: socket.socket | None = None

    # -- lifecycle --------------------------------------------------------------------------- #

    def start(self) -> QuestHands:
        """Serve the page and the stream in background threads; returns ``self``.

        Raises OSError if the port is taken, for example by another running copy.
        """
        self._thread = threading.Thread(target=self._run, name="metaquest-teleop", daemon=True)
        self._thread.start()
        self._ready.wait(10.0)
        if self._error is not None:
            raise self._error
        if self.udp is not None:
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.use_adb:
            threading.Thread(target=self._watch_usb, name="metaquest-teleop-usb", daemon=True).start()
        self._event(f"serving {self.url}")
        return self

    def stop(self) -> None:
        """Stop serving and watching USB; a pending :meth:`wait` returns None."""
        self._stopping.set()
        with self._cond:
            self._cond.notify_all()
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(5.0)
        if self._udp is not None:
            self._udp.close()

    def __enter__(self) -> QuestHands:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- data -------------------------------------------------------------------------------- #

    @property
    def url(self) -> str:
        """The address to open in the Quest browser."""
        return f"http://localhost:{self.port}"

    @property
    def connected(self) -> bool:
        """Whether a headset page is connected."""
        return bool(self._clients)

    def latest(self) -> Frame | None:
        """The most recent frame, or None before the first one."""
        with self._cond:
            return self._latest

    def wait(self, timeout: float | None = None) -> Frame | None:
        """Block until a new frame arrives and return it; None on timeout or stop."""
        with self._cond:
            seen = self.frames
            self._cond.wait_for(lambda: self.frames > seen or self._stopping.is_set(), timeout)
            return self._latest if self.frames > seen else None

    def on_frame(self, callback: Callable[[Frame], None]) -> None:
        """Call `callback(frame)` for every frame, on the receiving thread; keep it fast."""
        self._callbacks.append(callback)

    def rates(self) -> dict:
        """frames/s over the last second, of which carried changed hand data, interval p95, age."""
        now = time.perf_counter()
        with self._cond:
            arrivals = list(self._arrivals)
        last_second = [changed for t, changed in arrivals if now - t <= 1.0]
        times = np.array([t for t, _ in arrivals if now - t <= 2.0])
        gaps = np.diff(times) * 1000.0
        return {"hz": len(last_second), "changed_hz": int(sum(last_second)),
                "interval_p95_ms": float(np.percentile(gaps, 95)) if len(gaps) > 1 else None,
                "age_ms": (now - arrivals[-1][0]) * 1000.0 if arrivals else None}

    # -- server ------------------------------------------------------------------------------ #

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 -- reported to start()
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()
        self._loop.run_until_complete(self._shutdown())
        self._loop.close()

    async def _serve(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._page)
        app.router.add_get("/ws", self._socket)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()

    async def _shutdown(self) -> None:
        for ws in list(self._clients):
            await ws.close()
        if self._runner is not None:
            await self._runner.cleanup()

    async def _page(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(PAGE, headers={"Cache-Control": "no-store"})

    async def _socket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=2.0, max_msg_size=1 << 20)
        await ws.prepare(request)
        self._clients.add(ws)
        self._event("headset page connected")
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    self._receive(msg.data)
                elif msg.type == WSMsgType.TEXT:
                    self._message(msg.data)
        finally:
            self._clients.discard(ws)
            self.headset = {}
            self._event("headset page disconnected")
        return ws

    def _receive(self, data: bytes) -> None:
        try:
            frame = decode(data)
        except ValueError as exc:
            self._event(f"bad frame: {exc}")
            return
        hands = data[_HANDS_OFFSET:]
        changed = (frame.left is not None or frame.right is not None) and hands != self._last_hands
        self._last_hands = hands
        with self._cond:
            self._latest = frame
            self.frames += 1
            self._arrivals.append((time.perf_counter(), changed))
            self._cond.notify_all()
        for callback in list(self._callbacks):
            try:
                callback(frame)
            except Exception as exc:  # noqa: BLE001 -- a user callback must not stop the stream
                self._event(f"on_frame callback failed: {exc!r}")
        if self._udp is not None:
            try:
                self._udp.sendto(json.dumps(frame.to_dict(), separators=(",", ":")).encode(), self.udp)
            except OSError as exc:
                self._event(f"UDP send failed: {exc}")

    def _message(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        if "hello" in msg:
            self.headset.update(msg["hello"])
        if "session" in msg:
            state = msg.pop("session")
            self.headset.update(msg, session=state)
            if state == "started":
                self._event(f"XR session started: {msg.get('mode')}, {msg.get('fps')} Hz, "
                            f"{msg.get('space')}")
            elif state == "framerate":
                self._event(f"frame rate now {msg.get('fps')} Hz")
            else:
                self._event("XR session ended")
        if "stats" in msg:
            self.headset["stats"] = msg["stats"]
        if "error" in msg:
            self._event(f"headset: {msg['error']}")

    def _watch_usb(self) -> None:
        while not self._stopping.is_set():
            if not self._clients:
                ok, status = adb_reverse(self.port)
                if status != self.usb:
                    self._event(status)
                self.usb_ok, self.usb = ok, status
            self._stopping.wait(2.0)

    def _event(self, text: str) -> None:
        if self.events and self.events[-1][1] == text:
            self.events[-1] = (time.time(), text)
        else:
            self.events.append((time.time(), text))
