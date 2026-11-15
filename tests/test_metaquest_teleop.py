"""Hand maths, the wire format, the page's packer and the server end to end, without a headset."""

import asyncio
import io
import json
import shutil
import socket
import subprocess
import threading
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
        with QuestHands(port, adb=False, udp=udp.getsockname()) as quest:
            quest.on_frame(received.append)
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read().decode()
            assert "Quest hand stream" in page
            headset = threading.Thread(
                target=lambda: asyncio.run(stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=1.0)))
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
        headset = threading.Thread(
            target=lambda: asyncio.run(stream(f"ws://127.0.0.1:{port}/ws", hz=60, seconds=0.6)))
        headset.start()
        quest.wait(timeout=3.0)
        console.print(render(quest, 80))
        text = console.export_text()
        headset.join(5.0)
    assert "LEFT" in text and "RIGHT" in text and "index" in text and "frames/s" in text
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
