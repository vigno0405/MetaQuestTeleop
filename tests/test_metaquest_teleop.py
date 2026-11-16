"""Hand maths, the wire format, the page's packer and the server end to end, without a headset."""

import asyncio
import io
import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from importlib.resources import files

import numpy as np
import pytest

from metaquest_teleop import ANGLE_NAMES, QuestHands
from metaquest_teleop.fake import stream, synthetic_hand
from metaquest_teleop.hands import FRAME_BYTES, PARENT, Hand, Pose, decode, encode, rotations

PAGE = files("metaquest_teleop") / "client.html"
VIEW = files("metaquest_teleop") / "view.html"
MIRROR = np.diag([-1.0, 1.0, 1.0])


def _angles(rng):
    return np.stack([rng.uniform(-0.3, 1.5, 5), rng.uniform(-0.4, 0.4, 5),
                     rng.uniform(0.0, 1.6, 5), rng.uniform(0.0, 1.2, 5)], axis=1)


def _pose(rng):
    q = rng.normal(size=4)
    return Pose(rng.uniform(-1, 1, 3), q / np.linalg.norm(q))


def _free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("side", ["left", "right"])
def test_angles_read_back_what_the_hand_was_built_with(side):
    rng = np.random.default_rng(0)
    for _ in range(50):
        angles = _angles(rng)
        assert np.allclose(synthetic_hand(side, angles, _pose(rng)).angles, angles, atol=1e-9)


def test_a_mirrored_right_hand_reads_as_the_same_left_hand():
    from metaquest_teleop.fake import quaternion

    right = synthetic_hand("right", _angles(np.random.default_rng(1)), Pose(np.zeros(3), np.array([0, 0, 0, 1.0])))
    mirrored = Hand("left", right.positions @ MIRROR,
                    np.array([quaternion(MIRROR @ r @ MIRROR) for r in right.rotations]))
    assert np.allclose(mirrored.angles, right.angles, atol=1e-9)
    assert np.allclose(synthetic_hand("left", right.angles, Pose(np.zeros(3), np.array([0, 0, 0, 1.0]))).positions,
                       mirrored.positions, atol=1e-12)


def test_local_rotations_compose_back_to_the_joints():
    hand = synthetic_hand("right", _angles(np.random.default_rng(2)), _pose(np.random.default_rng(3)))
    world, local = hand.rotations, rotations(hand.local_quaternions)
    assert np.allclose(local[0], world[0])
    for joint, parent in enumerate(PARENT[1:], start=1):
        assert np.allclose(world[parent] @ local[joint], world[joint], atol=1e-9)


def test_the_wire_format_round_trips_and_marks_missing_hands():
    rng = np.random.default_rng(4)
    right, head = synthetic_hand("right", _angles(rng), _pose(rng)), _pose(rng)
    data = encode(42, 12.5, head, None, right)
    assert len(data) == FRAME_BYTES
    frame = decode(data, received=1.0)
    assert (frame.seq, frame.time, frame.received, frame.left) == (42, 12.5, 1.0, None)
    assert np.allclose(frame.head.position, head.position, atol=1e-6)
    assert np.allclose(frame.right.positions, right.positions, atol=1e-6)
    assert np.allclose(frame.right.angles, right.angles, atol=1e-4)
    assert set(json.loads(json.dumps(frame.to_dict()))["right"]["angles"]) == set(ANGLE_NAMES)
    with pytest.raises(ValueError):
        decode(data[:-4])
    with pytest.raises(ValueError):
        decode(b"XXXX" + data[4:])


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_page_packs_frames_exactly_as_python_reads_them(tmp_path):
    html = PAGE.read_text(encoding="utf-8")
    rng = np.random.default_rng(5)
    head, right = rng.normal(size=7), rng.normal(size=(25, 7))
    script = tmp_path / "pack.js"
    script.write_text(html.split("// pack-begin")[1].split("// pack-end")[0] + f"""
const head = new Float32Array({json.dumps(head.tolist())});
const right = new Float32Array({json.dumps(right.ravel().tolist())});
process.stdout.write(Buffer.from(packFrame(4294967298, 12.25, head, null, right)).toString("hex"));
""", encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
    expected = encode(4294967298, 12.25, Pose(head[:3], head[3:]), None,
                      Hand("right", right[:, :3], right[:, 3:]))
    assert bytes.fromhex(out) == expected

    page_script = tmp_path / "page.js"
    page_script.write_text(html.split("<script>")[1].split("</script>")[0], encoding="utf-8")
    subprocess.run(["node", "--check", str(page_script)], check=True)


def test_the_server_serves_the_page_and_receives_frames_from_a_headset():
    port = _free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind(("127.0.0.1", 0))
        udp.settimeout(3.0)
        received = []
        with QuestHands(port, adb=False, udp=udp.getsockname(), hands="both") as quest:
            quest.on_frame(received.append)
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read().decode()
            assert "Quest hand stream" in page
            headset = threading.Thread(target=lambda: asyncio.run(
                stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=1.0, hands=("left", "right"))))
            headset.start()
            frame = quest.wait(timeout=3.0)
            message = json.loads(udp.recv(65536))
            assert quest.headset.get("session") == "started" and quest.headset.get("fps") == 60
            headset.join(5.0)
            rates = quest.rates()
        assert frame is not None and frame.left is not None and frame.right is not None
        assert np.allclose(frame.right.angles, frame.right.angles.clip(-np.pi, np.pi))
        assert set(message["right"]["angles"]) == set(ANGLE_NAMES)
        assert len(received) == quest.frames > 40
        assert rates["changed_hz"] == rates["hz"] > 0


def test_the_dashboard_renders_with_and_without_hands():
    from rich.console import Console

    from metaquest_teleop.dashboard import render

    port = _free_port()
    with QuestHands(port, adb=False) as quest:
        console = Console(width=120, record=True, file=io.StringIO())
        console.print(render(quest, 120))
        assert "waiting for the page" in console.export_text()
        headset = threading.Thread(target=lambda: asyncio.run(
            stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=0.6, hands=("left", "right"))))
        headset.start()
        frame = quest.wait(timeout=3.0)
        console.print(render(quest, 80))
        text = console.export_text()
        headset.join(5.0)
    # The right hand only, by default, even when the headset sends both.
    assert frame.right is not None and frame.left is None
    assert "RIGHT" in text and "LEFT" not in text and "index" in text and "frames/s" in text
    assert "3D view" in text and "/view" in text


def test_malformed_text_messages_do_not_drop_the_headset_connection():
    import aiohttp

    port = _free_port()
    with QuestHands(port, adb=False) as quest:
        async def headset():
            async with aiohttp.ClientSession() as session, session.ws_connect(f"ws://127.0.0.1:{port}/ws") as ws:
                for text in ("not json", '"hello"', "[1, 2]", "42", "null"):
                    await ws.send_str(text)
                await ws.send_str(json.dumps({"hello": {"agent": "test headset"}}))
                for _ in range(50):
                    if quest.headset.get("agent") == "test headset":
                        return True
                    await asyncio.sleep(0.02)
                return False

        assert asyncio.run(headset())


def test_the_command_line_parses_udp_addresses_and_reports_its_version(capsys, monkeypatch):
    import argparse
    import sys

    from metaquest_teleop import __version__
    from metaquest_teleop.cli import _udp_address, main

    assert _udp_address("10.0.0.2:9000") == ("10.0.0.2", 9000)
    assert _udp_address(":9000") == ("127.0.0.1", 9000)
    with pytest.raises(argparse.ArgumentTypeError):
        _udp_address("localhost")
    monkeypatch.setattr(sys, "argv", ["metaquest-teleop", "--version"])
    with pytest.raises(SystemExit):
        main()
    assert __version__ in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_3d_view_draws_hands_as_python_computes_them(tmp_path):
    html = VIEW.read_text(encoding="utf-8")
    rng = np.random.default_rng(6)
    hand = synthetic_hand("right", _angles(rng), _pose(rng))
    flat = synthetic_hand("right", np.zeros((5, 4)), _pose(rng))
    quats = rng.normal(size=(5, 4))
    script = tmp_path / "view.js"
    script.write_text(html.split("// math-begin")[1].split("// math-end")[0] + f"""
const joints = {json.dumps(np.hstack([hand.positions, hand.quaternions]).tolist())};
const flat = {json.dumps(np.hstack([flat.positions, flat.quaternions]).tolist())};
const cam = camera({{yaw: 0.3, pitch: 0.4, dist: 1.2, target: [0.1, 1.0, -0.3]}}, 800, 600);
process.stdout.write(JSON.stringify({{
  mats: {json.dumps(quats.tolist())}.map(quatToMat), hand: handFrame(joints), flat: handFrame(flat),
  parent: PARENT, centre: cam.toScreen(cam.toCam([0.1, 1.0, -0.3])), eye: cam.eye}}));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)

    assert np.allclose(out["mats"], rotations(quats))
    local = (hand.positions - hand.positions[0]) @ hand.rotations[0]  # each row R_wrist^T (p - p_wrist)
    assert np.allclose(out["hand"], local[:, [0, 2, 1]] * [1.0, -1.0, 1.0])
    index_tip, thumb_tip = out["flat"][9], out["flat"][4]
    assert index_tip[1] > 0.1 and abs(index_tip[0]) < 0.03  # a flat hand's fingers point up
    assert thumb_tip[0] < 0  # and a right thumb is on the left, seen from the back of the hand
    assert out["parent"] == list(PARENT)
    assert np.allclose(out["centre"], [400, 300])
    assert np.isclose(np.linalg.norm(np.subtract(out["eye"], [0.1, 1.0, -0.3])), 1.2)

    page_script = tmp_path / "view-page.js"
    page_script.write_text(html.split("<script>")[1].split("</script>")[0], encoding="utf-8")
    subprocess.run(["node", "--check", str(page_script)], check=True)


def test_the_3d_view_receives_frames_and_status_with_only_the_right_hand():
    import aiohttp

    port = _free_port()

    async def view(seconds):
        messages = []
        async with aiohttp.ClientSession() as session, \
                session.ws_connect(f"ws://127.0.0.1:{port}/view/ws") as ws:
            headset = asyncio.ensure_future(
                stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=seconds, hands=("right",)))
            loop = asyncio.get_running_loop()
            end = loop.time() + seconds + 0.3
            while loop.time() < end:
                try:
                    msg = await ws.receive(timeout=end - loop.time())
                except asyncio.TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                messages.append(json.loads(msg.data))
            await headset
        return messages

    with QuestHands(port, adb=False) as quest:
        assert quest.view_url == f"http://localhost:{port}/view"
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/view", timeout=3).read().decode()
        assert "3D view" in page
        messages = asyncio.run(view(1.0))

    frames = [m["frame"] for m in messages if m.get("frame")]
    statuses = [m["status"] for m in messages if "status" in m]
    assert len(frames) > 20
    assert all(f["right"] is not None and f["left"] is None for f in frames)
    assert len(frames[-1]["right"]["joints"]) == 25
    assert set(frames[-1]["right"]["angles"]) == set(ANGLE_NAMES)
    assert any(s["page"] and s["session"] == "started" and s["mode"] == "fake" for s in statuses)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_3d_views_demo_makes_the_same_fake_hands_as_python(tmp_path):
    from metaquest_teleop.fake import pose_at

    html = VIEW.read_text(encoding="utf-8")
    rng = np.random.default_rng(7)
    cases = [(side, _angles(rng), _pose(rng)) for side in ("left", "right", "right")]
    times = [0.0, 0.7, 3.3, 11.9]
    script = tmp_path / "demo.js"
    script.write_text(html.split("// math-begin")[1].split("// math-end")[0] + f"""
const cases = {json.dumps([[s, a.tolist(), p.position.tolist(), p.quaternion.tolist()] for s, a, p in cases])};
const times = {json.dumps(times)};
process.stdout.write(JSON.stringify({{
  hands: cases.map(([side, a, p, q]) => fakeHand(side, a, p, q)),
  poses: times.flatMap((t) => ["left", "right"].map((side) => fakePose(t, side))),
}}));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)

    for (side, angles, pose), js in zip(cases, out["hands"]):
        hand = synthetic_hand(side, angles, pose)
        assert np.allclose(js["positions"], hand.positions, atol=1e-12)
        assert np.allclose(js["quaternions"], hand.quaternions, atol=1e-12)
    for (t, side), js in zip([(t, s) for t in times for s in ("left", "right")], out["poses"]):
        angles, wrist = pose_at(t, side)
        assert np.allclose(js["angles"], angles) and np.allclose(js["position"], wrist.position)
        assert np.allclose(js["quaternion"], wrist.quaternion)


# -- the ADAPT hand ---------------------------------------------------------------------------- #

def test_adapt_geometry_is_the_one_of_virtualmodelcontrol():
    vmc = pytest.importorskip("virtualmodelcontrol")
    from virtualmodelcontrol.robots import adapt as lib

    from metaquest_teleop import adapt

    assert np.allclose(adapt.COUPLING, lib.hand_coupling(), atol=1e-15)
    assert adapt.MOTORS == lib.HAND_MOTORS
    assert adapt.JOINT_LIMITS == {k: tuple(v) for k, v in lib.HAND_JOINT_LIMITS.items()}
    kin = vmc.Kinematics(lib.hand())
    for q in np.random.default_rng(8).uniform(-1, 1, (10, 13)):
        ours = adapt.positions(adapt.COUPLING @ q)
        for digit in adapt.DIGITS:
            assert np.allclose(np.ravel(kin.position(q, f"{digit}/tip")), ours[digit][-1], atol=1e-12)


def test_adapt_thumb_points_its_metacarpal_where_asked():
    from metaquest_teleop.adapt import DIGIT_JOINTS, _rotation, thumb_cmc

    (_, a1), (_, a2), (o3, _), _ = DIGIT_JOINTS["thumb"]
    rng = np.random.default_rng(9)
    for cmc1, cmc2 in zip(rng.uniform(0.0, 1.5, 100), rng.uniform(-0.5, 0.5, 100)):
        direction = _rotation(a1, cmc1) @ _rotation(a2, cmc2) @ np.array(o3)
        assert np.allclose(thumb_cmc(direction), (cmc1, cmc2), atol=1e-9)


def test_adapt_joints_take_your_angles_and_the_motors_reduce_them():
    from metaquest_teleop import adapt
    from metaquest_teleop.adapt import DIGIT_JOINTS, _rotation

    rng = np.random.default_rng(10)
    hand = synthetic_hand("right", _angles(rng), _pose(rng))
    a, joints = hand.angles, adapt.joint_angles(hand, clip=False, thumb_rest=0.0)  # the exact pairing
    for f in range(1, 5):  # fingers: spread with the ADAPT sign, then MCP, PIP and DIP as they are
        assert np.allclose(joints[4 * f:4 * f + 4], [-a[f, 1], a[f, 0], a[f, 2], a[f, 3]])
    assert np.allclose(joints[2:4], a[0, 2:4])
    (_, a1), (_, a2), (o3, _), _ = DIGIT_JOINTS["thumb"]  # the thumb's metacarpal points as yours
    robot = _rotation(a1, joints[0]) @ _rotation(a2, joints[1]) @ np.array(o3)
    yours = np.diag([1.0, -1.0, -1.0]) @ hand.rotations[0].T @ (hand.positions[2] - hand.positions[1])
    assert np.allclose(robot / np.linalg.norm(robot), yours / np.linalg.norm(yours), atol=1e-9)

    motors = adapt.motor_angles(joints, clip=False)
    back = adapt.COUPLING @ motors
    assert np.allclose(back[[0, 1, 2, 3, 5, 9, 13, 17]], joints[[0, 1, 2, 3, 5, 9, 13, 17]])
    for pip in (6, 10, 14, 18):  # each PIP motor: the mean of its PIP and DIP
        assert np.isclose(back[pip], (joints[pip] + joints[pip + 1]) / 2) and np.isclose(back[pip + 1], back[pip])
    q = rng.uniform(-1, 1, 13)  # joints the motors can make come back as those motors
    assert np.allclose(adapt.motor_angles(adapt.COUPLING @ q, clip=False), q)
    clipped = adapt.COUPLING @ adapt.motor_angles(np.full(20, 5.0))  # clip: every joint in range
    assert np.all(clipped <= np.array([adapt.JOINT_LIMITS[j][1] for j in adapt.JOINTS]) + 1e-9)
    assert np.allclose(adapt.motor_angles(hand), adapt.motor_angles(adapt.joint_angles(hand)))

    # By default: CMC2 measured from a relaxed thumb, and every joint within its limits.
    assert np.isclose(adapt.joint_angles(hand, clip=False)[1], joints[1] - adapt.THUMB_REST)
    low, high = np.array([adapt.JOINT_LIMITS[j] for j in adapt.JOINTS]).T
    held = adapt.joint_angles(hand)
    assert np.all((low <= held) & (held <= high))
    assert np.allclose(held, np.clip(adapt.joint_angles(hand, clip=False), low, high))


def test_adapt_wrist_pose_has_the_axes_of_the_adapt_base():
    from metaquest_teleop import adapt

    hand = synthetic_hand("right", np.zeros((5, 4)), _pose(np.random.default_rng(11)))
    pose = adapt.wrist_pose(hand)
    assert np.allclose(pose.position, hand.wrist.position)
    assert np.allclose(pose.rotation, hand.rotations[0] @ np.diag([1.0, -1.0, -1.0]))
    tip = pose.rotation.T @ (hand.positions[14] - hand.positions[0])  # a flat hand points along +z
    assert tip[2] > 0.9 * np.linalg.norm(tip)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_3d_views_adapt_hand_is_the_python_one(tmp_path):
    from metaquest_teleop import adapt

    html = VIEW.read_text(encoding="utf-8")
    rng = np.random.default_rng(12)
    hands = [synthetic_hand("right", _angles(rng), _pose(rng)) for _ in range(4)]
    script = tmp_path / "adapt.js"
    script.write_text(html.split("// math-begin")[1].split("// math-end")[0] + f"""
const hands = {json.dumps([[h.angles.tolist(), np.hstack([h.positions, h.quaternions]).tolist()] for h in hands])};
const joints = hands.map(([a, j]) => adaptJoints(a, j));
const raw = hands.map(([a, j]) => adaptJoints(a, j, false));
process.stdout.write(JSON.stringify({{
  coupling: ADAPT_COUPLING, joints, raw, exact: hands.map(([a, j]) => adaptJoints(a, j, false, 0)),
  motors: joints.map((j) => adaptMotors(j)), free: raw.map((j) => adaptMotors(j, false)),
  shapes: raw.map(adaptPositions),
}}));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)

    assert np.allclose(out["coupling"], adapt.COUPLING)
    for k, hand in enumerate(hands):
        assert np.allclose(out["joints"][k], adapt.joint_angles(hand), atol=1e-12)
        assert np.allclose(out["raw"][k], adapt.joint_angles(hand, clip=False), atol=1e-12)
        assert np.allclose(out["exact"][k], adapt.joint_angles(hand, clip=False, thumb_rest=0.0), atol=1e-12)
        assert np.allclose(out["motors"][k], adapt.motor_angles(hand), atol=1e-12)
        assert np.allclose(out["free"][k], adapt.motor_angles(hand, clip=False), atol=1e-12)
        shape = out["shapes"][k]
        for digit, points in adapt.positions(adapt.joint_angles(hand, clip=False)).items():
            assert np.allclose(shape[digit], points, atol=1e-12)


def test_hands_must_be_right_left_or_both():
    with pytest.raises(ValueError):
        QuestHands(hands="two")
    assert QuestHands().hands == "right"


def test_the_page_draws_before_asking_for_a_higher_frame_rate():
    # On the Quest a new frame rate takes effect on a later frame: waiting for it before the
    # first frame never ends, and the headset shows black.
    html = PAGE.read_text(encoding="utf-8")
    start = html.index("session.requestAnimationFrame(onFrame);")
    assert "await session.updateTargetFrameRate" not in html
    assert html.index("session.updateTargetFrameRate(") > start


def test_a_frame_rate_change_keeps_the_session_started():
    import aiohttp

    port = _free_port()
    with QuestHands(port, adb=False) as quest:
        async def headset():
            async with aiohttp.ClientSession() as session, session.ws_connect(f"ws://127.0.0.1:{port}/ws") as ws:
                await ws.send_str(json.dumps({"session": "started", "mode": "immersive-ar", "fps": None}))
                await ws.send_str(json.dumps({"session": "framerate", "fps": 120}))
                for _ in range(50):
                    if quest.headset.get("fps") == 120:
                        return dict(quest.headset), [text for _, text in quest.events]
                    await asyncio.sleep(0.02)

        info, events = asyncio.run(headset())
    assert info["session"] == "started" and info["mode"] == "immersive-ar" and info["fps"] == 120
    assert "streaming started" in events and "frame rate now 120 Hz" in events


# Stand-ins for what the headset page uses: its elements, the WebSocket to the computer, timers,
# and a WebXR session that sends no frames.
_PAGE_STANDINS = """
const testSent = [], testSockets = [], testTimers = [], testElements = {};
globalThis.WebSocket = class {
  static OPEN = 1;
  constructor(url) { this.url = url; this.readyState = 0; testSockets.push(this); }
  send(data) { testSent.push([testSockets.indexOf(this), JSON.parse(data)]); }
};
globalThis.document = {
  getElementById: (id) => (testElements[id] = testElements[id] || { style: {}, handlers: {},
    addEventListener(type, fn) { this.handlers[type] = fn; } }),
  createElement: () => ({ getContext: () => ({}) }),
};
globalThis.location = { protocol: "http:", host: "localhost:8012", port: "8012" };
globalThis.setTimeout = (fn) => testTimers.push(fn);
const testSession = {
  frameRate: 90, supportedFrameRates: [72, 90, 120],
  updateRenderState() {}, addEventListener() {},
  requestReferenceSpace: async () => ({}),
  requestAnimationFrame: () => 1,
  updateTargetFrameRate: async (rate) => { testSession.frameRate = rate; },
};
Object.defineProperty(globalThis, "navigator", { configurable: true, value: { userAgent: "test", xr: {
  isSessionSupported: async (mode) => mode === "immersive-ar", requestSession: async () => testSession } } });
globalThis.XRWebGLLayer = function () {};
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_page_tells_a_restarted_computer_it_is_still_streaming(tmp_path):
    # metaquest-teleop restarts while the headset streams: the page reconnects by itself and says
    # again that it is streaming, so the new one does not ask for Start.
    html = PAGE.read_text(encoding="utf-8")
    script = tmp_path / "reconnect.js"
    script.write_text(_PAGE_STANDINS + html.split("<script>")[1].split("</script>")[0] + """
(async () => {
  const open = (socket) => { socket.readyState = 1; socket.onopen(); };
  open(testSockets[0]);
  await new Promise((resolve) => setImmediate(resolve));  // the headset can do immersive-ar
  await testElements.start.handlers.click();              // Start
  testSockets[0].readyState = 3;
  testSockets[0].onclose();                               // metaquest-teleop stops,
  testTimers.shift()();                                   // the page tries again,
  open(testSockets[1]);                                   // and a new one answers
  process.stdout.write(JSON.stringify(testSent));
})();
""", encoding="utf-8")
    sent = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    started = [(socket, message) for socket, message in sent if message.get("session") == "started"]
    assert [socket for socket, _ in started] == [0, 1]
    first, again = started[0][1], started[1][1]
    assert first == {"session": "started", "mode": "immersive-ar", "space": "local-floor", "fps": 90,
                     "rates": [72, 90, 120]}
    assert again == {**first, "fps": 120, "resumed": True}  # the same session, at its rate now


def test_a_restarted_server_knows_the_headset_is_already_streaming():
    # Restart metaquest-teleop while the headset streams and it goes on without Start: the page
    # reconnects by itself. A newer page says so; an older one only sends frames. Neither should
    # get "press Start" on the dashboard.
    import aiohttp
    from rich.console import Console

    from metaquest_teleop.dashboard import render

    port, rng = _free_port(), np.random.default_rng(3)
    with QuestHands(port, adb=False) as quest:
        async def page(*messages):
            async with aiohttp.ClientSession() as session, session.ws_connect(f"ws://127.0.0.1:{port}/ws") as ws:
                for message in messages:
                    await (ws.send_bytes(message) if isinstance(message, bytes) else ws.send_str(json.dumps(message)))
                for _ in range(100):
                    if quest.headset.get("session") == "started":
                        break
                    await asyncio.sleep(0.02)
                console = Console(width=120, record=True, file=io.StringIO())
                console.print(render(quest, 120))
                return dict(quest.headset), [text for _, text in quest.events], console.export_text()

        older = asyncio.run(page({"hello": {"agent": "an older page"}}, encode(1, 0.5, _pose(rng), None, None)))
        for _ in range(100):  # the older page has gone
            if not quest.connected:
                break
            time.sleep(0.02)
        newer = asyncio.run(page({"hello": {"agent": "a newer page"}},
                                 {"session": "started", "mode": "immersive-ar", "space": "local-floor",
                                  "fps": 120, "rates": [72, 90, 120], "resumed": True}))
    info, events, dashboard = older
    assert info["session"] == "started" and "streaming: Start was already pressed in the headset" in events
    assert "streaming" in dashboard and "press Start in the headset" not in dashboard and "None" not in dashboard
    info, events, dashboard = newer
    assert info["session"] == "started" and info["fps"] == 120 and "resumed" not in info
    assert "streaming, 120 Hz: Start was already pressed in the headset" in events
    assert "streaming at 120 Hz" in dashboard and "press Start in the headset" not in dashboard


def test_without_ros_it_says_why_in_a_few_words(monkeypatch):
    import importlib.util
    import sys
    from types import SimpleNamespace

    from metaquest_teleop.cli import ros_unavailable

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert ros_unavailable(ImportError("No module named 'rclpy'"))[0] == "ROS 2 not found"

    # A ROS for another Python: Jazzy (3.12) from a conda environment with Python 3.10, say.
    here, other = f"3.{sys.version_info.minor}", f"3.{sys.version_info.minor + 1}"
    origin = f"/opt/ros/jazzy/lib/python{other}/site-packages/rclpy/__init__.py"
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: SimpleNamespace(origin=origin))
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    why, how = ros_unavailable(ImportError("No module named 'rclpy._rclpy_pybind11'\nThe C extension isn't present"))
    assert why == f"ROS 2 Jazzy runs on Python {other}, and this is Python {here}"
    assert how.startswith(f"To publish, run it with Python {other}")


def test_print_joints_shows_the_hands_angles_and_the_adapt_ones():
    from metaquest_teleop import adapt
    from metaquest_teleop.cli import joints_header, joints_line

    hand = synthetic_hand("right", _angles(np.random.default_rng(13)), _pose(np.random.default_rng(14)))
    line = joints_line("right", hand, "hand")
    numbers = [float(w) for w in line.replace("|", " ").split() if w.lstrip("+-").isdigit()]
    assert line.startswith("right") and "index" in line
    assert np.allclose(numbers, np.round(np.degrees(hand.angles.ravel())))
    adapt_line = joints_line("right", hand, "adapt")
    numbers = [float(w) for w in adapt_line.replace("|", " ").split() if w.lstrip("+-").isdigit()]
    assert np.allclose(numbers, np.round(np.degrees(adapt.joint_angles(hand))))
    assert "not tracked" in joints_line("right", None, "hand")
    assert "CMC1" in joints_header("adapt") and "base spread middle tip" in joints_header("hand")


def test_ros_topics_carry_the_right_hand_and_the_adapt_hand():
    rclpy = pytest.importorskip("rclpy")
    from geometry_msgs.msg import PoseArray, PoseStamped
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Bool, Float64, String

    from metaquest_teleop import adapt
    from metaquest_teleop.ros import FRAME_ID, RosPublisher

    topics = {"/metaquest/right/joint_states": JointState, "/metaquest/right/wrist": PoseStamped,
              "/metaquest/right/joints": PoseArray, "/metaquest/right/pinch": Float64,
              "/metaquest/adapt/joint_states": JointState, "/metaquest/adapt/motors": JointState,
              "/metaquest/adapt/wrist": PoseStamped, "/metaquest/teleop/hold": Bool,
              "/metaquest/teleop/state": String, "/metaquest/teleop/wrist": PoseStamped,
              "/metaquest/left/joint_states": JointState}
    port = _free_port()
    rclpy.init()
    try:
        listener = rclpy.create_node("metaquest_test_listener")
        got, first = {}, {}
        def keep(msg, topic):  # the latest message of each topic, and the first
            first.setdefault(topic, msg)
            got[topic] = msg
        for topic, kind in topics.items():
            listener.create_subscription(kind, topic, lambda msg, t=topic: keep(msg, t), 10)
        with QuestHands(port, adb=False) as quest:  # the right hand only, by default
            from metaquest_teleop import Teleop
            ros = RosPublisher(quest, teleop=Teleop(quest))
            headset = threading.Thread(target=lambda: asyncio.run(
                stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=3.0, hands=("left", "right"))))
            headset.start()
            deadline = time.monotonic() + 10.0
            while len(got) < 10 and time.monotonic() < deadline:
                rclpy.spin_once(listener, timeout_sec=0.05)
            frame = quest.latest()
            ros.close()
            headset.join(5.0)
        listener.destroy_node()
    finally:
        rclpy.shutdown()

    assert "/metaquest/left/joint_states" not in got  # the left hand is not kept
    joints = got["/metaquest/right/joint_states"]
    assert list(joints.name) == list(ANGLE_NAMES) and len(joints.position) == 20
    assert got["/metaquest/right/wrist"].header.frame_id == FRAME_ID
    assert len(got["/metaquest/right/joints"].poses) == 25
    assert 0.0 < got["/metaquest/right/pinch"].data < 0.3
    adapt_joints = got["/metaquest/adapt/joint_states"]
    assert list(adapt_joints.name) == list(adapt.JOINTS)
    low, high = np.array([adapt.JOINT_LIMITS[j] for j in adapt.JOINTS]).T
    assert np.all((low - 1e-9 <= adapt_joints.position) & (np.array(adapt_joints.position) <= high + 1e-9))
    motors = got["/metaquest/adapt/motors"]
    assert list(motors.name) == list(adapt.MOTORS)
    assert np.allclose(motors.position, adapt.motor_angles(np.array(adapt_joints.position)))
    assert frame.right is not None and frame.left is None
    assert first["/metaquest/teleop/hold"].data is True  # before the first frame: hold
    assert first["/metaquest/teleop/state"].data == "no frames yet"
    assert got["/metaquest/teleop/hold"].data is False and got["/metaquest/teleop/state"].data == "moving"
    assert got["/metaquest/teleop/wrist"].header.frame_id == FRAME_ID


# -- teleoperation: the right hand drives, the left hand pauses ---------------------------------- #

def _yaw(angle):
    return np.array([0.0, np.sin(angle / 2), 0.0, np.cos(angle / 2)])


def _teleop_frame(t, right_at=None, right_yaw=0.0, left_pinch=None, angles=None):
    """A frame at time t: the right hand at `right_at` (None: not seen), the left with that pinch."""
    from metaquest_teleop.hands import Frame

    right = None if right_at is None else synthetic_hand(
        "right", np.zeros((5, 4)) if angles is None else angles, Pose(np.asarray(right_at, float), _yaw(right_yaw)))
    left = None
    if left_pinch is not None:
        left = synthetic_hand("left", np.zeros((5, 4)), Pose(np.array([-0.2, 1.1, -0.4]), _yaw(0.0)))
        positions = left.positions.copy()
        positions[9] = positions[4] + np.array([left_pinch, 0.0, 0.0])  # index tip that far from the thumb
        left = Hand("left", positions, left.quaternions)
    return Frame(int(t * 100), t, 1000.0 + t, None, left, right)


def test_the_left_pinch_holds_the_robot_and_releasing_it_resumes_without_a_jump():
    from metaquest_teleop import Teleop, adapt

    teleop = Teleop(QuestHands())
    assert teleop.command().hold and teleop.command().reason == "no frames yet"

    start = teleop.update(_teleop_frame(0.0, [0.2, 1.1, -0.4], left_pinch=0.08))
    assert not start.hold and start.reason == ""
    assert np.allclose(start.wrist.position, [0.2, 1.1, -0.4])  # it starts at your wrist
    assert np.allclose(start.wrist.rotation, adapt.wrist_pose(_teleop_frame(0.0, [0.2, 1.1, -0.4], left_pinch=0.08).right).rotation)
    moved = teleop.update(_teleop_frame(0.1, [0.3, 1.1, -0.4], left_pinch=0.08))
    assert np.allclose(moved.wrist.position, [0.3, 1.1, -0.4])  # and follows it

    bent = np.full((5, 4), 0.5)
    held = teleop.update(_teleop_frame(0.2, [0.5, 1.2, -0.4], left_pinch=0.01, angles=bent))
    assert held.hold and held.reason == "left hand pinching"
    assert np.allclose(held.wrist.position, moved.wrist.position)  # the robot stays
    assert np.allclose(held.joints, moved.joints) and np.allclose(held.motors, moved.motors)
    still = teleop.update(_teleop_frame(0.3, [0.6, 1.2, -0.4], left_pinch=0.03))  # half open: still pinching
    assert still.hold and np.allclose(still.wrist.position, moved.wrist.position)

    released = teleop.update(_teleop_frame(0.4, [0.6, 1.2, -0.4], left_pinch=0.06, angles=bent))
    assert not released.hold
    assert np.allclose(released.wrist.position, moved.wrist.position)  # no jump on release
    assert np.allclose(released.joints, adapt.joint_angles(_teleop_frame(0.4, [0.6, 1.2, -0.4], angles=bent).right))
    again = teleop.update(_teleop_frame(0.5, [0.65, 1.2, -0.45], right_yaw=0.3, left_pinch=0.06))
    assert np.allclose(again.wrist.position, moved.wrist.position + [0.05, 0.0, -0.05])  # it moves as you move
    turn = again.wrist.rotation @ released.wrist.rotation.T
    assert np.isclose(np.arctan2(turn[0, 2], turn[2, 2]), 0.3)  # and turns as you turn

    assert teleop.update(_teleop_frame(0.6, [0.65, 1.2, -0.45])).reason == "left hand not seen"
    assert teleop.update(_teleop_frame(0.7, None, left_pinch=0.08)).reason == "right hand not seen"
    last = teleop.update(_teleop_frame(0.8, [0.65, 1.2, -0.45], left_pinch=0.08))
    assert not teleop.command(now=last.received + 0.05).hold
    assert teleop.command(now=last.received + 0.5).reason == "no frames"  # frames stopped


def test_the_teleop_sees_the_left_hand_that_the_stream_leaves_out():
    from metaquest_teleop import Teleop

    port = _free_port()
    with QuestHands(port, adb=False) as quest:  # the right hand only
        teleop = Teleop(quest)
        headset = threading.Thread(target=lambda: asyncio.run(stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=0.8)))
        headset.start()
        frame = quest.wait(timeout=3.0)
        time.sleep(0.2)
        command = teleop.command()
        headset.join(5.0)
    assert frame.left is None and frame.right is not None
    assert not command.hold and command.motors is not None  # the fake left hand never pinches


def test_the_teleop_without_the_adapt_hand_gives_your_own_angles_and_wrist():
    from metaquest_teleop import Teleop

    teleop = Teleop(QuestHands(), adapt=False)
    frame = _teleop_frame(0.0, [0.2, 1.1, -0.4], right_yaw=0.4, left_pinch=0.08, angles=np.full((5, 4), 0.3))
    command = teleop.update(frame)
    assert not command.hold and command.motors is None
    assert np.allclose(command.joints, frame.right.angles.ravel())
    assert np.allclose(command.wrist.rotation, frame.right.wrist.rotation)


@pytest.mark.parametrize("stop", ["SIGINT", "SIGTERM"])
def test_the_command_stops_on_ctrl_c_and_on_request_with_ros(stop):
    pytest.importorskip("rclpy")
    import signal
    import sys

    port = _free_port()
    command = subprocess.Popen([sys.executable, "-m", "metaquest_teleop", "--no-adb", "--port", str(port),
                                "--plain", "--ros"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    guard = threading.Timer(60.0, command.kill)  # never hang the tests
    guard.start()
    try:
        seen = []
        for line in command.stdout:  # until it runs: importing ROS the first time takes a while
            seen.append(line)
            if "publishing on ROS 2" in line:
                break
        time.sleep(0.5)
        command.send_signal(getattr(signal, stop))
        rest, _ = command.communicate(timeout=10)  # it must end, not hang
        output = "".join(seen) + rest
    finally:
        guard.cancel()
        if command.poll() is None:
            command.kill()
    assert "publishing on ROS 2" in output
    if stop == "SIGINT":
        assert command.returncode == 0 and "Stopped after" in output


@pytest.mark.parametrize("no_adapt", [False, True])
def test_print_joints_prints_all_your_joints_and_the_adapt_ones_unless_turned_off(no_adapt):
    import sys

    port = _free_port()
    command = [sys.executable, "-m", "metaquest_teleop", "--no-adb", "--no-ros", "--port", str(port), "--print_joints"]
    process = subprocess.Popen(command + (["--no-adapt"] if no_adapt else []),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    guard = threading.Timer(30.0, process.kill)
    guard.start()
    try:
        for _ in range(100):  # wait until it serves
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        headset = threading.Thread(target=lambda: asyncio.run(
            stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=1.5)))
        headset.start()
        lines = []
        for line in process.stdout:
            lines.append(line.rstrip("\n"))
            if sum(" right " in f" {line} " for line in lines) >= 5:
                break
        headset.join(5.0)  # let the fake headset finish before stopping the command
        process.terminate()  # the lines are in; terminate works everywhere, Ctrl-C not on Windows
        process.communicate(timeout=10)
    finally:
        guard.cancel()
        if process.poll() is None:
            process.kill()
    yours = [line for line in lines if "  right  thumb" in line]
    adapt_lines = [line for line in lines if "  ADAPT  thumb" in line]
    assert yours and all(line.count("|") >= 4 for line in yours)  # all five fingers
    assert any("joint angles, degrees" in line for line in lines)
    if no_adapt:
        assert not adapt_lines and not any("ADAPT joints" in line for line in lines)
        assert all("robot moving" in line for line in yours[1:])  # the state ends your line
    else:
        assert adapt_lines and any("ADAPT joints" in line for line in lines)
        assert all("robot moving" in line for line in adapt_lines[1:])  # ... or the ADAPT line


def test_ros_without_adapt_publishes_all_your_joints_but_no_adapt_topics():
    rclpy = pytest.importorskip("rclpy")
    from geometry_msgs.msg import PoseArray
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Bool

    from metaquest_teleop import Teleop
    from metaquest_teleop.ros import RosPublisher

    topics = {"/metaquest/right/joint_states": JointState, "/metaquest/right/joints": PoseArray,
              "/metaquest/teleop/hold": Bool, "/metaquest/adapt/joint_states": JointState,
              "/metaquest/adapt/motors": JointState}
    port = _free_port()
    rclpy.init()
    try:
        listener = rclpy.create_node("metaquest_test_no_adapt")
        got, holds = {}, []
        def keep(msg, topic):
            got[topic] = msg
            if topic == "/metaquest/teleop/hold":
                holds.append(msg.data)
        for topic, kind in topics.items():
            listener.create_subscription(kind, topic, lambda msg, t=topic: keep(msg, t), 10)
        with QuestHands(port, adb=False) as quest:
            ros = RosPublisher(quest, adapt=False, teleop=Teleop(quest, adapt=False))
            headset = threading.Thread(target=lambda: asyncio.run(
                stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=2.0)))
            headset.start()
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:  # long enough for any ADAPT topic to show up
                rclpy.spin_once(listener, timeout_sec=0.05)
            ros.close()
            headset.join(5.0)
        listener.destroy_node()
    finally:
        rclpy.shutdown()
    assert len(got["/metaquest/right/joint_states"].position) == 20
    assert len(got["/metaquest/right/joints"].poses) == 25
    assert False in holds and holds[-1] is True  # moving while frames came, holding once they stopped
    assert "/metaquest/adapt/joint_states" not in got and "/metaquest/adapt/motors" not in got
