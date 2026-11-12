# Changelog

## 0.2.0 (2026-11-12)

- 3D view of the hands in a browser, at http://localhost:8012/view while the stream runs:
  a hand view and a room view, with the forearm, joint angles and pinch.
- `metaquest-teleop --view` opens it; `QuestHands.view_url` gives its address.
- `metaquest-teleop-fake --hands right` (or `left`) fakes a single hand.
- Documentation at https://vigno0405.github.io/MetaQuestTeleop/.

## 0.1.0 (2026-11-12)

First release.

- `QuestHands`: hand tracking from a Meta Quest over USB, in background threads, with
  `wait()`, `latest()` and `on_frame()`; wrist poses, 25 joints and 20 joint angles per hand.
- `metaquest-teleop`: the stream with a live terminal dashboard, `--plain` output and
  `--udp` JSON forwarding.
- `metaquest-teleop-fake`: a stand-in headset with synthetic hands.
- The server listens on 127.0.0.1 only.
