# Changelog

## Unreleased

- Documentation at https://vigno0405.github.io/MetaQuestTeleop/.

## 0.1.0 (2026-11-12)

First release.

- `QuestHands`: hand tracking from a Meta Quest over USB, in background threads, with
  `wait()`, `latest()` and `on_frame()`; wrist poses, 25 joints and 20 joint angles per hand.
- `metaquest-teleop`: the stream with a live terminal dashboard, `--plain` output and
  `--udp` JSON forwarding.
- `metaquest-teleop-fake`: a stand-in headset with synthetic hands.
- The server listens on 127.0.0.1 only.
