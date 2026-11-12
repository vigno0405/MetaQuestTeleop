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
""")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
    expected = encode(4294967298, 12.25, Pose(head[:3], head[3:]), None,
                      Hand("right", right[:, :3], right[:, 3:]))
    assert bytes.fromhex(out) == expected

    page_script = tmp_path / "page.js"
    page_script.write_text(html.split("<script>")[1].split("</script>")[0])
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
