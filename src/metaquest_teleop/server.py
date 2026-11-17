"""The headset link: serves the WebXR page, sets up the USB tunnel, and receives hand frames."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import dataclasses
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
VIEW = Path(__file__).with_name("view.html")
#: The port of the page and the stream unless you choose another.
DEFAULT_PORT = 8012
_HANDS_OFFSET = 48
_KEPT = {  # the hands kept, and their part of a binary frame
    "right": (("right",), slice(_HANDS_OFFSET + 700, None)),
    "left": (("left",), slice(_HANDS_OFFSET, _HANDS_OFFSET + 700)),
    "both": (("left", "right"), slice(_HANDS_OFFSET, None)),
}
_VIEW_HZ = 60.0


def adb_reverse(port: int) -> tuple[bool, str]:
    """Make the headset's localhost:port reach this computer over USB. Returns (ok, status)."""
    adb = shutil.which("adb")
    if adb is None:
        return False, ("adb not found: install it (Ubuntu: sudo apt install adb; others: "
                       "https://vigno0405.github.io/MetaQuestTeleop/start.html)")
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

        with QuestHands() as quest:      # then press Start in the headset
            frame = quest.wait()         # the next frame from the headset
            frame.right.wrist.position   # metres
            frame.right.angles           # (5, 4) radians

    Only this computer can connect (the headset comes in through the USB cable), so nothing
    else on the network can send it frames.

    Parameters
    ----------
    port
        The port: the headset opens ``http://localhost:<port>``.
    adb
        Set up the USB link to the headset automatically, with ``adb``.
    udp
        ``(host, port)``: also send every frame there as JSON, over UDP. None for no UDP.
    host
        Who can connect: ``"127.0.0.1"`` is only this computer, ``"0.0.0.0"`` the network.
    hands
        The hands to keep: ``"right"`` (the default), ``"left"`` or ``"both"``. The others are
        reported as not tracked.

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
    calibration : pathlib.Path or None
        The file the 3D view saves the ADAPT calibration you make in it to, all of it at every point
        (``metaquest-teleop --calibration`` sets it); None, the default: the 3D view does not calibrate.
    """

    def __init__(self, port: int = DEFAULT_PORT, adb: bool = True,
                 udp: tuple[str, int] | None = None, host: str = "127.0.0.1",
                 hands: str = "right") -> None:
        if hands not in _KEPT:
            raise ValueError(f"hands must be 'right', 'left' or 'both', not {hands!r}")
        self.port, self.host, self.udp, self.hands = port, host, udp, hands
        self.use_adb = adb
        self.usb_ok, self.usb = False, ("checking" if adb else "not managed (--no-adb)")
        self.headset: dict = {}
        self.events: collections.deque[tuple[float, str]] = collections.deque(maxlen=6)
        self.frames = 0
        self._latest: Frame | None = None
        self._cond = threading.Condition()
        self._callbacks: list[Callable[[Frame], None]] = []
        self._raw_callbacks: list[Callable[[Frame], None]] = []
        self.teleop = None  # a Teleop, once one drives a robot from this stream
        self.calibration: Path | None = None
        self._arrivals: collections.deque[tuple[float, bool]] = collections.deque(maxlen=2048)
        self._last_hands = b""
        self._clients: set[web.WebSocketResponse] = set()
        self._viewers: set[web.WebSocketResponse] = set()
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
    def view_url(self) -> str:
        """The address of the 3D view of the hands, to open in a browser on this computer."""
        return f"{self.url}/view"

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

    def on_frame(self, callback: Callable[[Frame], None], raw: bool = False) -> None:
        """Call ``callback(frame)`` for every frame.

        It runs in the background thread that receives the frames, so keep it fast. ``raw``
        gives it every frame with both hands, whichever ``hands`` keeps (for gestures).
        """
        (self._raw_callbacks if raw else self._callbacks).append(callback)

    def rates(self) -> dict:
        """Statistics of the stream, as a dict.

        ``hz``: frames in the last second. ``changed_hz``: how many of them carried new hand
        data. ``interval_p95_ms``: time between frames, in ms, that 95% of frames beat.
        ``age_ms``: age of the newest frame, in ms.
        """
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
        app.router.add_get("/view", self._view_page)
        app.router.add_get("/view/ws", self._view_socket)
        app.router.add_post("/calibration", self._calibrate)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()

    async def _shutdown(self) -> None:
        for ws in list(self._clients) + list(self._viewers):
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

    # -- 3D view ----------------------------------------------------------------------------- #

    async def _view_page(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(VIEW, headers={"Cache-Control": "no-store"})

    async def _view_socket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=5.0)
        await ws.prepare(request)
        self._viewers.add(ws)
        feeder = asyncio.ensure_future(self._feed_viewer(ws))
        try:
            async for _ in ws:  # the view sends nothing; reading notices when it closes
                pass
        finally:
            feeder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await feeder
            self._viewers.discard(ws)
        return ws

    async def _feed_viewer(self, ws: web.WebSocketResponse) -> None:
        """Send a 3D view the newest frame, at most _VIEW_HZ times a second, and the status."""
        sent, status_at = -1, 0.0
        try:
            while not ws.closed:
                message: dict = {}
                if self.frames != sent:
                    sent, frame = self.frames, self.latest()
                    message["frame"] = None if frame is None else frame.to_dict()
                now = time.perf_counter()
                if now - status_at >= 0.5:
                    status_at = now
                    message["status"] = self._view_status()
                if message:
                    await ws.send_str(json.dumps(message, separators=(",", ":")))
                await asyncio.sleep(1.0 / _VIEW_HZ)
        except ConnectionError:
            return  # the view closed while a message was on its way

    @staticmethod
    def _adapt_status() -> dict:
        """The ADAPT mapping as it is now, for the 3D view to map your hand as the library does:
        whether it fits the fingers (adapt.FIT), the angles of yours each joint follows
        (adapt.FOLLOWS) and the calibration (adapt.CALIBRATION), as rows [your angle(s)..., its angle]."""
        from . import adapt  # noqa: PLC0415 -- adapt imports this module, through fake

        return {"adapt_fit": bool(adapt.FIT), "follows": {joint: list(names) for joint, names in adapt.FOLLOWS.items()},
                "calibration": {joint: adapt._rows(points) for joint, points in list(adapt.CALIBRATION.items())}}

    def _view_status(self) -> dict:
        rates = self.rates()
        return {"page": self.connected, "url": self.url, "use_adb": self.use_adb,
                "usb_ok": self.usb_ok, "usb": self.usb, "frames": self.frames,
                "hz": rates["hz"], "changed_hz": rates["changed_hz"],
                "hands": self.hands,
                "teleop": None if self.teleop is None else self.teleop.command().reason or "moving",
                "adapt": None if self.teleop is None else self.teleop.adapt,
                **self._adapt_status(),
                "calibrating": None if self.calibration is None else str(self.calibration),
                **{key: self.headset.get(key) for key in ("session", "mode", "fps", "space")}}

    async def _calibrate(self, request: web.Request) -> web.Response:
        """From the 3D view, while calibrating: ``{"joint": name, "points": rows}`` gives a joint
        these points, ``{"joint": name}`` the library's; then all go to :attr:`calibration`."""
        from . import adapt  # noqa: PLC0415 -- adapt imports this module, through fake

        if self.calibration is None:
            raise web.HTTPNotFound(text="not calibrating: start metaquest-teleop --calibration")
        if request.content_type != "application/json":  # also keeps other web pages out (CORS)
            raise web.HTTPUnsupportedMediaType(text="expected JSON")
        try:
            body = await request.json()
            joint = body["joint"]
            if not adapt.FOLLOWS.get(joint):
                raise ValueError(f"{joint!r} is not an ADAPT joint that follows yours")
            if body.get("points") is None:
                adapt.reset_calibration(joint)
            else:
                adapt.CALIBRATION[joint] = adapt._points(joint, body["points"])
        except (ValueError, KeyError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        try:
            adapt.save_calibration(self.calibration)
        except OSError as exc:
            return web.json_response({"error": f"not saved to {self.calibration}: {exc}"}, status=500)
        self._event(f"calibration: {joint} saved")
        return web.json_response({"calibration": self._adapt_status()["calibration"]})

    # -- frames from the headset ------------------------------------------------------------- #

    def _receive(self, data: bytes) -> None:
        try:
            frame = decode(data)
        except ValueError as exc:
            self._event(f"bad frame: {exc}")
            return
        if self.headset.get("session") != "started":
            # The headset was streaming before this program started (its page reconnects by
            # itself), from a page too old to say so: the frames say it.
            self.headset["session"] = "started"
            self._event("streaming: Start was already pressed in the headset")
        self._call(self._raw_callbacks, frame)  # both hands, for gestures
        sides, part = _KEPT[self.hands]
        frame = dataclasses.replace(frame, **{s: None for s in ("left", "right") if s not in sides})
        hands = data[part]
        changed = (frame.left is not None or frame.right is not None) and hands != self._last_hands
        self._last_hands = hands
        with self._cond:
            self._latest = frame
            self.frames += 1
            self._arrivals.append((time.perf_counter(), changed))
            self._cond.notify_all()
        self._call(self._callbacks, frame)
        if self._udp is not None:
            try:
                self._udp.sendto(json.dumps(frame.to_dict(), separators=(",", ":")).encode(), self.udp)
            except OSError as exc:
                self._event(f"UDP send failed: {exc}")

    def _call(self, callbacks: list[Callable[[Frame], None]], frame: Frame) -> None:
        for callback in list(callbacks):
            try:
                callback(frame)
            except Exception as exc:  # noqa: BLE001 -- a user callback must not stop the stream
                self._event(f"on_frame callback failed: {exc!r}")

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
            if state == "framerate":  # the session goes on, at a new rate
                self.headset["fps"] = msg.get("fps")
                self._event(f"frame rate now {msg.get('fps')} Hz")
            else:
                resumed = msg.pop("resumed", False)  # the page reconnected while streaming
                self.headset.update(msg, session=state)
                rate = f", {msg['fps']} Hz" if msg.get("fps") else ""
                if state != "started":
                    self._event("streaming stopped")
                elif resumed:
                    self._event(f"streaming{rate}: Start was already pressed in the headset")
                else:
                    self._event(f"streaming started{rate}")
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
