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


# The ADAPT calibration the tests expect (the library's first): an open hand gives home, a power
# grasp PC1, a pinch PC2. The library's own may change with each calibration made its own.
TYPICAL = {
    "thumb_CMC1": {5: 0, 95: 86}, "thumb_CMC2": {(0, 30): 20, (20, 35): 0, (70, 20): -60},
    "thumb_MCP": {0: 0, 65: 86}, "thumb_IP": {0: 0, 45: 90},
    "index_spread": {0: 0, 20: -17}, "index_MCP": {0: 0, 90: 86}, "index_PIP": {0: 0, 90: 69}, "index_DIP": {0: 0, 60: 69},
    "middle_MCP": {0: 0, 90: 86}, "middle_PIP": {0: 0, 90: 69}, "middle_DIP": {0: 0, 60: 69},
    "ring_spread": {-15: 17, 0: 0}, "ring_MCP": {0: 0, 90: 86}, "ring_PIP": {0: 0, 90: 69}, "ring_DIP": {0: 0, 60: 69},
    "pinky_spread": {-25: 17, 0: 0}, "pinky_MCP": {0: 0, 90: 86}, "pinky_PIP": {0: 0, 90: 69}, "pinky_DIP": {0: 0, 60: 69},
}  # fmt: skip


@pytest.fixture(autouse=True)
def _calibration(tmp_path, monkeypatch):
    """Every test starts from the typical ADAPT calibration, and none writes where yours go."""
    from metaquest_teleop import adapt

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))  # and the commands the tests run
    monkeypatch.setattr(adapt, "CALIBRATIONS", tmp_path / "config" / "metaquest-teleop" / "calibrations")
    adapt.reset_calibration()
    adapt.CALIBRATION.update({joint: dict(points) for joint, points in TYPICAL.items()})
    yield
    adapt.reset_calibration()


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
    assert all(s["adapt"] is None for s in statuses)  # no teleoperation: no ADAPT hand to show


def test_the_3d_view_knows_whether_the_adapt_hand_is_on():
    import aiohttp

    from metaquest_teleop import Teleop

    async def statuses(port):
        async with aiohttp.ClientSession() as session, session.ws_connect(f"ws://127.0.0.1:{port}/view/ws") as ws:
            while True:
                message = json.loads((await ws.receive(timeout=3.0)).data)
                if "status" in message:
                    return message["status"]

    from metaquest_teleop import adapt

    seen = {}
    for use_adapt in (True, False):
        port = _free_port()
        with QuestHands(port, adb=False) as quest:
            Teleop(quest, adapt=use_adapt)
            status = asyncio.run(statuses(port))
            seen[use_adapt] = status["adapt"]
    assert seen == {True: True, False: False}
    # and your calibration as it is now, for the view to map your hand as the library does
    assert status["calibration"] == {j: adapt._rows(points) for j, points in adapt.CALIBRATION.items()}
    assert status["follows"] == {j: list(names) for j, names in adapt.FOLLOWS.items()}
    assert status["adapt_fit"] is True  # and whether it fits the ADAPT hand to yours
    assert status["calibrating"] is None  # the view calibrates only with metaquest-teleop --calibration


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_3d_views_robot_in_the_room_is_where_python_puts_it(tmp_path):
    from metaquest_teleop import adapt

    html = VIEW.read_text(encoding="utf-8")
    rng = np.random.default_rng(21)
    hands = [synthetic_hand("right", _angles(rng), _pose(rng)) for _ in range(3)]
    script = tmp_path / "robot.js"
    script.write_text(html.split("// math-begin")[1].split("// math-end")[0] + f"""
const hands = {json.dumps([np.hstack([h.positions, h.quaternions]).tolist() for h in hands])};
const joints = {json.dumps([adapt.joint_angles(h).tolist() for h in hands])};
process.stdout.write(JSON.stringify(hands.map((j, k) => adaptInRoom(adaptWrist(j[0]), joints[k]))));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    for hand, room in zip(hands, out):
        pose = adapt.wrist_pose(hand)  # the ADAPT base there, its own wrist straight
        assert np.allclose(room["wrist"], pose.position + pose.rotation @ adapt.PALM_ORIGIN, atol=1e-12)
        for digit, points in adapt.positions(adapt.joint_angles(hand)).items():
            assert np.allclose(room[digit], pose.position + points @ pose.rotation.T, atol=1e-12)


def test_the_dashboard_shows_the_adapt_hand_next_to_yours():
    from rich.console import Console

    from metaquest_teleop import Teleop
    from metaquest_teleop.dashboard import render

    texts = {}
    for use_adapt in (True, False):
        port = _free_port()
        with QuestHands(port, adb=False) as quest:
            Teleop(quest, adapt=use_adapt)
            headset = threading.Thread(target=lambda: asyncio.run(
                stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=0.8)))
            headset.start()
            quest.wait(timeout=3.0)
            time.sleep(0.2)
            console = Console(width=160, record=True, file=io.StringIO())
            console.print(render(quest, 160))
            texts[use_adapt] = console.export_text()
            headset.join(5.0)
    assert "RIGHT" in texts[True] and "ADAPT" in texts[True] and "moving" in texts[True]
    assert "CMC1" in texts[True] and "PIP" in texts[True] and "fixed: a PID holds it" in texts[True]
    assert "RIGHT" in texts[False] and "CMC1" not in texts[False] and "PID" not in texts[False]


def test_the_dashboards_adapt_hand_follows_your_hand():
    # The ADAPT panel maps your hand as it is: it does not freeze while the robot holds (when you
    # test with your right hand only, say), and it is not tracked when your hand is not.
    from rich.console import Console

    from metaquest_teleop import Teleop
    from metaquest_teleop.dashboard import render

    def screen(quest):
        console = Console(width=160, record=True, file=io.StringIO())
        console.print(render(quest, 160))
        return console.export_text()

    port = _free_port()
    with QuestHands(port, adb=False, hands="both") as quest:
        teleop = Teleop(quest)
        asyncio.run(stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=0.3, hands=("right",)))  # no left hand
        right_only, holding = screen(quest), teleop.command()
        asyncio.run(stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=0.3, hands=("left",)))  # no right hand
        left_only = screen(quest)
    assert holding.hold and holding.reason == "left hand not seen"
    assert "holding: left hand not seen" in right_only  # the robot line says it holds...
    assert "ADAPT  ● tracked" in right_only and "CMC1" in right_only  # ...the ADAPT hand follows yours
    assert "ADAPT  ○" in left_only and "CMC1" not in left_only  # no right hand, no ADAPT hand


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
    assert {k: tuple(map(float, v)) for k, v in adapt.JOINT_LIMITS.items()} == {
        k: tuple(map(float, v)) for k, v in lib.HAND_JOINT_LIMITS.items()}
    # The thumb tip along its last bone (-x), as HumanManipulationVMC draws it; the rest as is.
    kin = vmc.Kinematics(lib.hand(tip_offsets={"thumb": tuple(adapt.TIP_OFFSETS["thumb"])}))
    for q in np.random.default_rng(8).uniform(-1, 1, (10, 13)):
        ours = adapt.positions(adapt.COUPLING @ q)
        for digit in adapt.DIGITS:
            assert np.allclose(np.ravel(kin.position(q, f"{digit}/tip")), ours[digit][-1], atol=1e-12)


def test_your_calibration_can_be_changed_at_any_time():
    from metaquest_teleop import adapt

    hand = synthetic_hand("right", np.array([[0.4, 0.5, 0.3, 0.3]] + [[0.4, 0.0, 0.5, 0.3]] * 4), _pose(np.random.default_rng(2)))
    before = adapt.joint_angles(hand, fit=False)[5]  # index MCP, from your 0..90°, joint for joint
    adapt.CALIBRATION["index_MCP"] = {0: 0, 45: 86}  # your index bends half as much: the same bend is twice
    assert adapt.joint_angles(hand, fit=False)[5] == pytest.approx(min(2 * before, adapt.JOINT_LIMITS["index_MCP"][1]))


def test_each_joint_goes_through_every_point_of_yours():
    from metaquest_teleop import adapt

    # One angle of yours: straight from point to point, and on beyond the first and the last.
    adapt.CALIBRATION["thumb_IP"] = {0: 0, 20: 30, 45: 90}
    for yours, its in ((0, 0), (20, 30), (45, 90), (10, 15), (30, 54), (60, 126), (-10, -15)):
        assert adapt.calibrated("thumb_IP", yours) == pytest.approx(its, abs=1e-12)
    hand = synthetic_hand("right", np.array([[0.4, 0.5, 0.3, np.radians(60)]] + [[0.4, 0.0, 0.5, 0.3]] * 4), _pose(np.random.default_rng(3)))
    for fit in (True, False):  # then within its limits: 126° is its 90°
        assert np.degrees(adapt.joint_angles(hand, fit=fit)[3]) == pytest.approx(90)
        assert np.degrees(adapt.joint_angles(hand, fit=fit, clip=False)[3]) == pytest.approx(126)
    assert adapt.calibrated("middle_spread") == 0  # it follows none of yours
    # Not enough points, or not the angles it follows: a clear error.
    for points in ({0: 0}, {(0, 1): 0, (1, 2): 3}):
        adapt.CALIBRATION["thumb_IP"] = points
        with pytest.raises(ValueError, match="thumb_IP"):
            adapt.calibrated("thumb_IP", 10)
    adapt.CALIBRATION["thumb_CMC2"] = {(0, 0): 0, (10, 10): 5, (20, 20): 10}  # on one line: no surface
    with pytest.raises(ValueError, match="not all on one line"):
        adapt.calibrated("thumb_CMC2", 5, 5)
    with pytest.raises(TypeError):
        adapt.calibrated("thumb_CMC2", 5)  # it follows two angles of yours


def test_the_calibration_is_saved_and_loaded(tmp_path):
    from metaquest_teleop import adapt

    path = tmp_path / "calibrations" / "mine.json"
    adapt.CALIBRATION["thumb_IP"] = {0: 0, 20: 30, 45: 90}
    adapt.CALIBRATION["thumb_CMC2"][(45, 25)] = -20
    assert adapt.save_calibration(path) == path
    saved = json.loads(path.read_text())  # all of it, in degrees
    assert saved == {joint: adapt._rows(points) for joint, points in adapt.CALIBRATION.items()}
    assert saved["thumb_IP"] == [[0, 0], [20, 30], [45, 90]] and [45, 25, -20] in saved["thumb_CMC2"]
    hand = synthetic_hand("right", np.array([[0.8, 0.4, 0.3, np.radians(20)]] + [[0.4, 0.0, 0.5, 0.3]] * 4), _pose(np.random.default_rng(4)))
    mine = adapt.joint_angles(hand)
    adapt.reset_calibration()  # the library's
    assert adapt.CALIBRATION == adapt._DEFAULT_CALIBRATION
    assert not np.allclose(adapt.joint_angles(hand), mine)
    adapt.load_calibration(path)
    assert np.allclose(adapt.joint_angles(hand), mine)
    adapt.CALIBRATION["index_MCP"] = {0: 0, 45: 86}
    adapt.reset_calibration("index_MCP")  # one joint back to the library's points
    assert adapt.CALIBRATION["index_MCP"] == adapt._DEFAULT_CALIBRATION["index_MCP"]
    assert adapt.CALIBRATION["thumb_IP"] == {0: 0, 20: 30, 45: 90}
    path.write_text('{"thumb_IP": [[0, 0], [30, 90]]}')  # a file with some joints: the others are the library's
    adapt.load_calibration(path)
    assert adapt.CALIBRATION == {**adapt._DEFAULT_CALIBRATION, "thumb_IP": {0: 0, 30: 90}}
    # No file, or not a calibration: refused, and nothing changes.
    with pytest.raises(OSError):
        adapt.load_calibration(tmp_path / "none.json")
    for bad in ("nope", "[1, 2]", '{"thumb_IP": [[0, 0]]}', '{"thumb_IP": [[0, 0, 1], [1, 2, 3]]}',
                '{"wrist": [[0, 0], [1, 1]]}', '{"middle_spread": [[0, 0], [1, 1]]}', '{"thumb_IP": [[0, true], [1, 2]]}'):
        path.write_text(bad)
        with pytest.raises(ValueError, match="not an ADAPT calibration"):
            adapt.load_calibration(path)
        assert adapt.CALIBRATION["thumb_IP"] == {0: 0, 30: 90}


def test_a_calibration_becomes_the_librarys_with_its_script(tmp_path):
    import ast
    import sys
    from pathlib import Path

    from metaquest_teleop import adapt

    script = Path(__file__).resolve().parent.parent / "scripts" / "set_calibration.py"
    package = tmp_path / "repo" / "src" / "metaquest_teleop"
    package.mkdir(parents=True)
    for name in ("adapt.py", "view.html"):
        (package / name).write_text((files("metaquest_teleop") / name).read_text(encoding="utf-8"), encoding="utf-8")
    run = lambda path: subprocess.run([sys.executable, str(script), str(path), "--root", str(tmp_path / "repo")],  # noqa: E731
                                      capture_output=True, text=True)
    library = lambda: ast.literal_eval(  # noqa: E731
        (package / "adapt.py").read_text().split("\nCALIBRATION = ")[1].split("  # fmt: skip")[0])

    adapt.reset_calibration()  # the library's own: nothing changes
    adapt.save_calibration(tmp_path / "same.json")
    before = {name: (package / name).read_text() for name in ("adapt.py", "view.html")}
    assert run(tmp_path / "same.json").returncode == 0
    assert {name: (package / name).read_text() for name in before} == before
    ip = dict(adapt.CALIBRATION["thumb_IP"])  # yours, a point more: in the Python and in the 3D view
    ip[max(ip) + 7.25] = 77.5
    adapt.CALIBRATION["thumb_IP"] = ip
    adapt.CALIBRATION["thumb_CMC2"][(-33.5, 44.25)] = -20.5
    adapt.save_calibration(tmp_path / "mine.json")
    done = run(tmp_path / "mine.json")
    assert done.returncode == 0 and "thumb_IP" in done.stdout and "thumb_CMC1" not in done.stdout
    assert library() == adapt.CALIBRATION
    if shutil.which("node") is not None:
        html = (package / "view.html").read_text()
        page = tmp_path / "calibration.js"
        page.write_text(html.split("// math-begin")[1].split("// math-end")[0]
                        + "process.stdout.write(JSON.stringify(ADAPT_CALIBRATION));")
        shown = json.loads(subprocess.run(["node", str(page)], capture_output=True, text=True, check=True).stdout)
        assert shown == {joint: adapt._rows(dict(sorted(points.items()))) for joint, points in adapt.CALIBRATION.items()}
    (tmp_path / "bad.json").write_text('{"thumb_IP": [[0, 0]]}')  # not a calibration: nothing changes
    before = (package / "adapt.py").read_text()
    assert run(tmp_path / "bad.json").returncode == 1 and (package / "adapt.py").read_text() == before


def test_the_3d_view_calibrates_only_with_metaquest_teleop_calibration(tmp_path):
    import aiohttp

    from metaquest_teleop import adapt

    path = tmp_path / "calibration" / "adapt_calibration.json"

    async def post(port, body, as_json=True):
        async with aiohttp.ClientSession() as session:
            sent = {"json": body} if as_json else {"data": json.dumps(body)}
            async with session.post(f"http://127.0.0.1:{port}/calibration", **sent) as r:
                return r.status, await r.json() if r.content_type == "application/json" else await r.text()

    port = _free_port()
    with QuestHands(port, adb=False) as quest:
        status, _ = asyncio.run(post(port, {"joint": "thumb_IP", "points": [[0, 0], [30, 90]]}))
        assert status == 404 and not path.exists()  # not calibrating
        quest.calibration = path
        assert quest._view_status()["calibrating"] == str(path)
        status, answer = asyncio.run(post(port, {"joint": "thumb_IP", "points": [[30, 90], [0, 0]]}))
        assert status == 200 and answer["calibration"]["thumb_IP"] == [[0, 0], [30, 90]]  # in order
        assert adapt.CALIBRATION["thumb_IP"] == {0: 0, 30: 90}
        assert json.loads(path.read_text())["thumb_IP"] == [[0, 0], [30, 90]]  # all of it, at every point
        for bad in ({"joint": "thumb_IP", "points": [[0, 0]]}, {"joint": "middle_spread", "points": [[0, 0], [1, 1]]},
                    {"joint": "nope"}, {"points": []}, [1]):
            status, answer = asyncio.run(post(port, bad))
            assert status == 400 and answer["error"], bad
        assert adapt.CALIBRATION["thumb_IP"] == {0: 0, 30: 90}  # unchanged
        status, _ = asyncio.run(post(port, {"joint": "thumb_IP"}, as_json=False))
        assert status == 415  # not JSON: another web page cannot send it
        status, answer = asyncio.run(post(port, {"joint": "thumb_IP"}))  # back to the library's points
        assert status == 200 and adapt.CALIBRATION["thumb_IP"] == adapt._DEFAULT_CALIBRATION["thumb_IP"]
        assert json.loads(path.read_text())["thumb_IP"] == adapt._rows(adapt._DEFAULT_CALIBRATION["thumb_IP"])


def test_the_command_line_loads_a_calibration_only_when_asked(tmp_path, monkeypatch, capsys):
    import sys

    from metaquest_teleop import adapt
    from metaquest_teleop.cli import main

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["metaquest-teleop", *args])
        return main()

    for args in (["--calibration", "--no-adapt"], ["--calibration-file", "x.json", "--no-adapt"]):
        with pytest.raises(SystemExit):
            run(*args)
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    assert run("--calibration-file", str(bad), "--no-adb", "--no-ros") == 1
    assert "not an ADAPT calibration" in capsys.readouterr().out
    assert run("--calibration-file", str(tmp_path / "none.json"), "--no-adb", "--no-ros") == 1
    assert "No ADAPT calibration" in capsys.readouterr().out

    # Started, it uses the library's calibration, or the one you name.
    adapt.CALIBRATION["thumb_IP"] = {0: 0, 30: 90}
    mine = adapt.save_calibration(adapt.CALIBRATIONS / "adapt-mine.json")
    for extra, said in (([], "ADAPT calibration: the library's"), (["--calibration-file", str(mine)], f"ADAPT calibration: {mine}")):
        port = _free_port()
        process = subprocess.Popen([sys.executable, "-m", "metaquest_teleop", "--no-adb", "--no-ros", "--plain",
                                    "--port", str(port), *extra], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        guard = threading.Timer(30.0, process.kill)
        guard.start()
        try:
            lines = []
            for line in process.stdout:
                lines.append(line.rstrip("\n"))
                if line.startswith("page "):
                    break
            process.terminate()
            process.communicate(timeout=10)
        finally:
            guard.cancel()
            if process.poll() is None:
                process.kill()
        assert said in lines, lines


def test_joint_for_joint_the_adapt_hand_does_what_yours_does():
    # The real hand's own poses (HumanManipulationVMC PoseControl, after Santello et al. 1998): an
    # open hand gives home, all zeros; a power grasp about PC1; a pinch about PC2. And more of
    # yours gives more of the ADAPT's, joint by joint.
    from metaquest_teleop import adapt

    wrist = Pose(np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0]))
    hand = lambda angles: synthetic_hand("right", np.asarray(angles, float), wrist)
    pick = [0, 1, 2, 3, 5, 6, 9, 10, 13, 14]  # thumb CMC1 CMC2 MCP IP; index, middle, ring MCP and PIP
    power = [1.0, 0.0, 1.48, 0.96]
    for angles, reference in (
        ([[0.1, 0.8, 0.05, 0.05]] + [[0.0] * 4] * 4, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),  # open: home
        ([[1.0, 0.35, 0.7, 0.8]] + [power] * 4, [65, 0, 50, 40, 55, 65, 55, 65, 55, 65]),  # power grasp: PC1
        ([[0.9, 0.2, 0.44, 0.52], [0.45, 0.0, 0.87, 0.61], [0.45, 0.0, 1.0, 0.7]] + [power] * 2,
         [50, 12, 35, 25, 25, 40, 25, 50, 55, 65]),  # pinch: PC2
    ):
        got = np.degrees(adapt.joint_angles(hand(angles), fit=False)[pick])
        assert np.all(np.abs(got[4:] - reference[4:]) < 6), (got, reference)  # the fingers
        assert np.all(np.abs(got[[0, 2]] - np.array(reference)[[0, 2]]) < 20), (got, reference)  # thumb CMC1, MCP
        your_ip = np.degrees(hand(angles).angles[0, 3])  # the thumb's IP: twice yours, up to its limit
        assert got[3] == pytest.approx(np.clip(2 * your_ip, 0, 90), abs=1e-6)

    def follows(index, joint, values):  # the ADAPT joint as your angle there grows
        out = []
        for v in values:
            angles = np.array([[0.4, 0.5, 0.3, 0.3]] + [[0.4, 0.0, 0.5, 0.3]] * 4)
            angles[index] = v
            out.append(adapt.joint_angles(hand(angles), fit=False)[joint])
        return np.diff(out)

    assert np.all(follows((1, 0), 5, np.linspace(0, 1.4, 8)) > 0)  # index MCP
    assert np.all(follows((2, 2), 10, np.linspace(0, 1.4, 8)) > 0)  # middle PIP (and DIP)
    assert np.all(follows((0, 3), 3, np.linspace(0, 0.75, 8)) > 0)  # thumb IP, below your 45° that is its limit
    assert np.all(follows((0, 0), 0, np.linspace(0.2, 1.4, 8)) > 0)  # the thumb in front of the palm: CMC1


def test_the_thumbs_cmc2_follows_your_base_and_spread_through_your_poses():
    from metaquest_teleop import adapt

    # Through every pose of yours exactly: (base, spread) -> CMC2, degrees.
    for (base, spread), cmc2 in adapt.CALIBRATION["thumb_CMC2"].items():
        assert adapt.calibrated("thumb_CMC2", base, spread) == pytest.approx(cmc2, abs=1e-9)
    # Both ways, the ADAPT's CMC2 is that surface at your thumb's base and spread, within its range.
    low, high = adapt.JOINT_LIMITS["thumb_CMC2"]
    rng = np.random.default_rng(50)
    for _ in range(20):
        hand = synthetic_hand("right", _angles(rng), _pose(rng))
        base, spread = np.degrees(hand.angles[0, :2])
        want = np.clip(np.radians(adapt.calibrated("thumb_CMC2", base, spread)), low, high)
        for fit in (True, False):
            assert adapt.joint_angles(hand, fit=fit)[1] == pytest.approx(want, abs=1e-9)
    # Three poses: the plane through them.
    for base, spread in ((10, 10), (50, 40), (80, 0)):
        assert adapt.calibrated("thumb_CMC2", base, spread) == pytest.approx((100 - 12 * base + 4 * spread) / 11, abs=1e-9)
    # A fourth: through it too, and smooth between them: no jump anywhere on a fine grid.
    adapt.CALIBRATION["thumb_CMC2"][(45, 25)] = -20
    assert adapt.calibrated("thumb_CMC2", 45, 25) == pytest.approx(-20, abs=1e-9)
    grid = np.array([[adapt.calibrated("thumb_CMC2", b, s) for s in np.arange(-10, 61, 0.5)] for b in np.arange(-10, 91, 0.5)])
    assert np.abs(np.diff(grid, axis=0)).max() < 2 and np.abs(np.diff(grid, axis=1)).max() < 2
    # -60° is within reach: CMC2 goes from -70° to 30°, as in virtualmodelcontrol.
    assert np.degrees([low, high]) == pytest.approx([-70, 30])
    adapt.CALIBRATION["thumb_CMC2"] = {(0, 0): 10, (90, 0): 10, (0, 90): 10}  # always 10°
    hand = synthetic_hand("right", _angles(rng), _pose(rng))
    assert np.degrees(adapt.joint_angles(hand)[1]) == pytest.approx(10)


def _adapt_shaped_hand(joints):
    """A hand whose joints are where the ADAPT hand's are for these joint angles: the wrist at the
    ADAPT base, turned so that your wrist's axes read as the ADAPT's."""
    from metaquest_teleop import adapt
    from metaquest_teleop.hands import Hand

    pts = adapt.positions(joints)
    positions = np.zeros((25, 3))
    positions[1:5] = pts["thumb"][2:6]  # CMC (the ADAPT's CMC2), MCP, IP, tip
    for f, digit in enumerate(adapt.DIGITS[1:], start=1):
        positions[5 * f:5 * f + 5] = pts[digit][1:6]  # base, MCP, PIP, DIP, tip
    quaternions = np.tile([1.0, 0.0, 0.0, 0.0], (25, 1))  # a half turn about x: the ADAPT axes
    return Hand("right", positions, quaternions)


def _distance_to(hand, joints):
    """mm: how far the ADAPT hand is from yours, as the fit measures it: the fingers' PIP, DIP and
    tips (your knuckles on the ADAPT's), and the thumb's shape from its base."""
    from metaquest_teleop import adapt

    goal, _, _ = adapt._targets(hand)
    points, _ = adapt._chains(joints)
    ours = points[:, 3:6].copy()
    ours[0] -= points[0, 2]
    gaps = np.linalg.norm(ours - goal, axis=-1) * 1000
    return gaps[1:].mean(), gaps[0].mean()


def test_the_fit_puts_the_adapt_hand_where_yours_is():
    from dataclasses import replace

    from metaquest_teleop import adapt

    # A hand shaped as an ADAPT pose gets its fingers back (a hair off: the pull towards the
    # joint-for-joint pose, which picks one pose when several fit as well). The thumb follows
    # yours joint for joint, in the fit too.
    rng = np.random.default_rng(40)
    low, high = adapt._MOTOR_LOW, adapt._MOTOR_HIGH
    for _ in range(10):
        motors = rng.uniform(low, high)
        motors[4] = 0.0  # no spread: your knuckles are then the ADAPT's own
        joints = adapt.COUPLING @ motors
        hand = _adapt_shaped_hand(joints)
        got = adapt.joint_angles(hand)
        assert np.degrees(np.abs(got[4:] - joints[4:])).max() < 1.0
        assert np.allclose(got[:4], adapt.joint_angles(hand, fit=False)[:4], atol=1e-12)
        fingers, _ = _distance_to(hand, got)
        assert fingers < 0.5

    # Your hand: the fit is nearer to it than joint for joint is, within the same limits, as
    # the fit measures it (it starts there, and each step it takes brings the hand nearer).
    def cost(hand, joints):
        goal, gaps, pinch = adapt._targets(hand)
        motors = adapt.motor_angles(joints)
        r, _ = adapt._residuals(motors, goal, gaps, pinch, motors)  # no pull: from itself
        return r @ r

    rng = np.random.default_rng(41)
    nearer = 0
    for _ in range(20):
        hand = synthetic_hand("right", _angles(rng), _pose(rng))
        fitted, direct = cost(hand, adapt.joint_angles(hand)), cost(hand, adapt.joint_angles(hand, fit=False))
        assert fitted <= direct + 1e-12
        nearer += fitted < 0.9 * direct
    assert nearer >= 15

    # A pinch: your thumb tip on your index tip brings the ADAPT's fingertip towards its thumb tip.
    wrist = Pose(np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0]))
    for target in (9, 14):
        h = synthetic_hand("right", np.array([[0.9, 0.2, 0.44, 0.52], [0.6, 0, 0.7, 0.3], [0.6, 0, 0.7, 0.3]]
                                             + [[1.0, 0.0, 1.48, 0.96]] * 2), wrist)
        p = h.positions.copy()
        p[4] = p[target]
        h = replace(h, positions=p)
        tips = {d: points[-1] for d, points in adapt.positions(adapt.joint_angles(h)).items()}
        direct = {d: points[-1] for d, points in adapt.positions(adapt.joint_angles(h, fit=False)).items()}
        finger = adapt.DIGITS[target // 5]
        gap, before = (np.linalg.norm(t["thumb"] - t[finger]) * 1000 for t in (tips, direct))
        assert gap < 0.75 * before, (gap, before)  # the thumb held as yours: the fingers close in on it

    # More of yours, more of the ADAPT's.
    def follows(index, joint, values):
        out = []
        for v in values:
            angles = np.array([[0.4, 0.5, 0.3, 0.3]] + [[0.4, 0.0, 0.5, 0.3]] * 4)
            angles[index] = v
            out.append(adapt.joint_angles(synthetic_hand("right", angles, wrist))[joint])
        return np.diff(out)

    for index, joint in (((1, 0), 5), ((2, 2), 10)):  # index MCP; middle PIP (and DIP)
        steps = follows(index, joint, np.linspace(0, 1.4, 8))
        assert np.all(steps >= -1e-9) and steps.sum() > 0.5  # never back, from its 0 limit up


def test_adapt_joints_are_a_pose_the_adapt_hand_can_take():
    # Each finger's DIP mimics its PIP (one motor, the same angle), and one motor spreads the
    # fingers: the 20 joint angles must be a pose of the hand, within its limits.
    from metaquest_teleop import adapt

    rng = np.random.default_rng(31)
    low, high = np.array([adapt.JOINT_LIMITS[j] for j in adapt.JOINTS]).T
    kept = 0
    for k in range(200):
        hand = synthetic_hand("right", _angles(rng), _pose(rng))
        for fit in (True, False) if k < 40 else (False,):
            joints = adapt.joint_angles(hand, fit=fit)
            motors = adapt.motor_angles(joints)
            assert np.allclose(adapt.COUPLING @ motors, joints, atol=1e-12)  # the motors make exactly this pose
            assert np.all((low - 1e-12 <= joints) & (joints <= high + 1e-12))
            assert np.allclose(motors, adapt.motor_angles(hand, fit=fit), atol=1e-12)
            for f in range(1, 5):
                assert joints[4 * f + 2] == pytest.approx(joints[4 * f + 3], abs=1e-12)  # DIP mimics PIP
        joints = adapt.joint_angles(hand, fit=False)
        wanted = adapt.joint_angles(hand, clip=False, coupled=False)  # yours, one by one
        for f in range(1, 5):
            pip, dip = 4 * f + 2, 4 * f + 3
            if low[pip] < joints[pip] < high[pip]:  # joint for joint, no limit in the way: the mean of the two
                assert 2 * joints[pip] == pytest.approx(wanted[pip] + wanted[dip], abs=1e-9)
                kept += 1
    assert kept > 100


def test_adapt_joints_take_your_angles_and_the_motors_reduce_them():
    from metaquest_teleop import adapt

    rng = np.random.default_rng(10)
    hand = synthetic_hand("right", _angles(rng), _pose(rng))
    # Your angles: those of the dashboard, and your thumb's turn, read as the ADAPT's CMC1 turns.
    a, yours = np.degrees(hand.angles), adapt.your_angles(hand)
    assert list(yours) == list(adapt.YOUR_ANGLES)
    for f, finger in enumerate(("thumb", "index", "middle", "ring", "pinky")):
        for c, column in enumerate(("base", "spread", "middle", "tip")):
            assert yours[f"{finger} {column}"] == pytest.approx(a[f, c], abs=1e-12)
    bone = np.diag([1.0, -1.0, -1.0]) @ hand.rotations[0].T @ (hand.positions[2] - hand.positions[1])
    assert yours["thumb turn"] == pytest.approx(np.degrees(np.arctan2(bone[1], -bone[0])), abs=1e-12)
    # Joint by joint, before the couplings and limits: each through its calibration...
    joints = adapt.joint_angles(hand, clip=False, coupled=False)
    for i, name in enumerate(adapt.JOINTS):
        want = adapt.calibrated(name, *(yours[n] for n in adapt.FOLLOWS[name]))
        assert joints[i] == pytest.approx(np.radians(want), abs=1e-12), name
    # ... with the typical one your range stretched onto its own: the index MCP, your 0..90° its 0..86°.
    assert np.degrees(joints[5]) == pytest.approx(yours["index base"] / 90 * 86, abs=1e-9)
    assert np.degrees(joints[0]) == pytest.approx((yours["thumb turn"] - 5) / 90 * 86, abs=1e-9)
    assert np.degrees(joints[4]) == pytest.approx(yours["index spread"] / 20 * -17, abs=1e-9)

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
    assert np.allclose(adapt.motor_angles(hand, fit=False), adapt.motor_angles(joints, clip=True))

    # By default: the pose the motors make, every joint within its limits.
    low, high = np.array([adapt.JOINT_LIMITS[j] for j in adapt.JOINTS]).T
    held = adapt.joint_angles(hand)
    assert np.all((low <= held) & (held <= high))
    assert np.allclose(held, adapt.COUPLING @ adapt.motor_angles(hand))
    one_by_one = adapt.joint_angles(hand, coupled=False)
    assert np.allclose(one_by_one, np.clip(adapt.joint_angles(hand, clip=False, coupled=False), low, high))


def test_adapt_wrist_pose_has_the_axes_of_the_adapt_base():
    from metaquest_teleop import adapt

    hand = synthetic_hand("right", np.zeros((5, 4)), _pose(np.random.default_rng(11)))
    pose = adapt.wrist_pose(hand)
    assert np.allclose(pose.position, hand.wrist.position)
    assert np.allclose(pose.rotation, hand.rotations[0] @ np.diag([1.0, -1.0, -1.0]))
    tip = pose.rotation.T @ (hand.positions[14] - hand.positions[0])  # a flat hand points along +z
    assert tip[2] > 0.9 * np.linalg.norm(tip)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
@pytest.mark.parametrize("calibration", ["default", "yours"])
def test_the_3d_views_adapt_hand_is_the_python_one(tmp_path, calibration):
    from metaquest_teleop import adapt

    if calibration == "yours":  # more points, and points elsewhere: the view follows them as the library does
        adapt.CALIBRATION["thumb_IP"] = {0: 0, 20: 30, 45: 90}
        adapt.CALIBRATION["thumb_CMC2"] = {(20, 35): 0, (70, 20): -60, (0, 30): 20, (45, 25): -20}
        adapt.CALIBRATION["thumb_CMC1"] = {0: 10, 60: 50, 100: 80}
        adapt.CALIBRATION["index_MCP"] = {0: 0, 45: 86}
        adapt.CALIBRATION["ring_spread"] = {-20: 17, 5: 0, 0: 2}

    html = VIEW.read_text(encoding="utf-8")
    from dataclasses import replace

    rng = np.random.default_rng(12)
    hands = [synthetic_hand("right", _angles(rng), _pose(rng)) for _ in range(4)]
    for tip in (9, 14, 24):  # and pinching: your thumb tip on a fingertip, or 2 cm from it
        for gap in (0.0, 0.02):
            h = synthetic_hand("right", _angles(rng), _pose(rng))
            p = h.positions.copy()
            p[4] = p[tip] + (p[4] - p[tip]) / np.linalg.norm(p[4] - p[tip]) * gap
            hands.append(replace(h, positions=p))
    script = tmp_path / "adapt.js"
    script.write_text(html.split("// math-begin")[1].split("// math-end")[0] + f"""
const defaults = {{ names: ADAPT_NAMES, follows: adaptFollows, calibration: adaptCalibration }};
adaptCalibration = {json.dumps({j: adapt._rows(points) for j, points in adapt.CALIBRATION.items()})};
const hands = {json.dumps([[h.angles.tolist(), np.hstack([h.positions, h.quaternions]).tolist()] for h in hands])};
const joints = hands.map(([a, j]) => adaptJoints(a, j));
const raw = hands.map(([a, j]) => adaptJoints(a, j, false));
const direct = hands.map(([a, j]) => adaptJoints(a, j, true, true, false));
const directRaw = hands.map(([a, j]) => adaptJoints(a, j, false, true, false));
process.stdout.write(JSON.stringify({{
  coupling: ADAPT_COUPLING, joints, raw, direct, directRaw, defaults,
  yours: hands.map(([a, j]) => adaptYours(a, j)),
  motors: joints.map((j) => adaptMotors(j)), free: raw.map((j) => adaptMotors(j, false)),
  directMotors: direct.map((j) => adaptMotors(j)), directFree: directRaw.map((j) => adaptMotors(j, false)),
  shapes: raw.map(adaptPositions),
  wanted: hands.map(([a, j]) => adaptJoints(a, j, true, false)),
  wantedRaw: hands.map(([a, j]) => adaptJoints(a, j, false, false)),
}}));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)

    assert np.allclose(out["coupling"], adapt.COUPLING)
    assert out["defaults"]["names"] == list(adapt.JOINTS)
    assert out["defaults"]["follows"] == {j: list(names) for j, names in adapt.FOLLOWS.items()}
    assert out["defaults"]["calibration"] == {j: adapt._rows(p) for j, p in adapt._DEFAULT_CALIBRATION.items()}
    for k, hand in enumerate(hands):
        yours = adapt.your_angles(hand)
        assert out["yours"][k].keys() == yours.keys()
        assert np.allclose([out["yours"][k][n] for n in yours], list(yours.values()), atol=1e-9)
        # the fit: the same solver, so the same pose (to its rounding)
        assert np.allclose(out["joints"][k], adapt.joint_angles(hand), atol=1e-9)
        assert np.allclose(out["raw"][k], adapt.joint_angles(hand, clip=False), atol=1e-9)
        assert np.allclose(out["motors"][k], adapt.motor_angles(hand), atol=1e-9)
        assert np.allclose(out["free"][k], adapt.motor_angles(hand, clip=False), atol=1e-9)
        # joint for joint
        assert np.allclose(out["direct"][k], adapt.joint_angles(hand, fit=False), atol=1e-12)
        assert np.allclose(out["directRaw"][k], adapt.joint_angles(hand, clip=False, fit=False), atol=1e-12)
        assert np.allclose(out["directMotors"][k], adapt.motor_angles(hand, fit=False), atol=1e-12)
        assert np.allclose(out["directFree"][k], adapt.motor_angles(hand, clip=False, fit=False), atol=1e-12)
        assert np.allclose(out["wanted"][k], adapt.joint_angles(hand, coupled=False), atol=1e-12)
        assert np.allclose(out["wantedRaw"][k], adapt.joint_angles(hand, clip=False, coupled=False), atol=1e-12)
        shape = out["shapes"][k]
        for digit, points in adapt.positions(adapt.joint_angles(hand, clip=False)).items():
            assert np.allclose(shape[digit], points, atol=1e-9)


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


def test_without_ros_here_it_finds_the_python_ros_runs_on(monkeypatch, tmp_path):
    import importlib.util
    import os
    from types import SimpleNamespace

    from metaquest_teleop import ros

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)  # ROS not sourced
    assert ros.ros_python() is None
    assert str(ros._unavailable(ImportError("No module named 'rclpy'"))) == "ROS 2 not found"

    # ROS 2 for another Python than this one: Jazzy, on 3.12, from a conda env with 3.10, say.
    origin = "/opt/ros/jazzy/lib/python3.99/site-packages/rclpy/__init__.py"
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: SimpleNamespace(origin=origin))
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ros.ros_python() is None  # no Python 3.99 on this computer
    assert str(ros._unavailable(ImportError("..."))) == "ROS 2 Jazzy runs on Python 3.99, which is not found"
    python = tmp_path / ("python3.99.exe" if os.name == "nt" else "python3.99")
    python.write_text("")
    python.chmod(0o755)
    assert os.path.normcase(ros.ros_python()) == os.path.normcase(str(python))


def test_a_helper_that_cannot_load_ros_says_why():
    import importlib.util
    import sys

    if importlib.util.find_spec("rclpy") is not None:
        pytest.skip("ROS 2 is here")
    from metaquest_teleop.ros import RosPublisher, RosUnavailable

    with QuestHands(_free_port(), adb=False) as quest:
        with pytest.raises(RosUnavailable, match=r"did not start with .*rclpy"):
            RosPublisher(quest, python=sys.executable)


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


@pytest.mark.parametrize("through", ["this Python", "a helper"])
def test_ros_topics_carry_the_right_hand_and_the_adapt_hand(through):
    # From this Python, or through a helper process: what a Python that cannot load ROS 2 does
    # (a conda environment with Python 3.10, and ROS 2 Jazzy on 3.12); here with this same Python.
    import sys

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
            ros = RosPublisher(quest, teleop=Teleop(quest), python=sys.executable if through == "a helper" else None)
            assert (ros.python is None) == (through == "this Python")
            deadline = time.monotonic() + 10.0
            while "/metaquest/teleop/hold" not in first and time.monotonic() < deadline:  # holding, before frames
                rclpy.spin_once(listener, timeout_sec=0.05)
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
    assert list(motors.name) == list(adapt.MOTORS + adapt.WRIST_MOTORS)
    assert np.allclose(motors.position[:13], adapt.motor_angles(np.array(adapt_joints.position)))
    assert list(motors.position[13:]) == [0.0, 0.0]  # the wrist stays at 0, 0
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
