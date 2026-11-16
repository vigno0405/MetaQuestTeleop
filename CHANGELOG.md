# Changelog

## 0.5.1 (2026-11-16)

- `metaquest-teleop --print_joints` prints all your joint angles and, under them, the ADAPT
  hand's as the robot gets them (they hold still while the robot holds); with `--no-adapt`,
  yours only. `--print_joints adapt` is gone: plain `--print_joints` shows both.
- Docs: the title is just "metaquest-teleop", and the GitHub badge in the header no longer
  stays on an old release.

## 0.5.0 (2026-11-16)

- Teleoperation (`Teleop`): your right hand drives the robot; pinch your left hand to hold it
  still and move your right hand freely, release to go on from where it stopped. It holds when
  either hand is not seen or frames stop. The dashboard and the 3D view show it.
- ROS 2 (Humble and Jazzy): `metaquest-teleop` publishes the hand, the ADAPT hand and the
  teleoperation on `/metaquest/...` topics, with standard messages, whenever it finds ROS 2;
  `--ros` requires it, `--no-ros` turns it off. `metaquest_teleop.ros.RosPublisher` from Python.
- `--no-adapt` (`Teleop(quest, adapt=False)`): no ADAPT hand; the teleoperation gives your own
  joint angles and wrist, for any robot.
- `metaquest-teleop --print_joints` prints the joint angles, `--print_joints adapt` the ADAPT
  hand's, with the robot's state.
- `metaquest-teleop-fake` sends both hands again by default: the left one gives the gestures.
- Fix a black screen in the headset after Start: the page waited for the higher frame rate
  before drawing its first frame, and on the Quest that change only happens once frames are
  drawn. It now draws first and asks for the frame rate without waiting.
- After a frame-rate change the dashboard said "page open: press Start" while streaming: the
  session now stays "started", with the new rate.

## 0.4.0 (2026-11-16)

- The right hand only, by default: `QuestHands(hands="right")`, `metaquest-teleop` and
  `metaquest-teleop-fake`. `hands="both"` (`--hands both`) keeps both, `"left"` the left one.
- When `adb` is missing, the message says how to install it.

## 0.3.0 (2026-11-15)

- `metaquest_teleop.adapt`: your hand on the ADAPT hand. `joint_angles` gives its 20 joint
  angles, with PIP and DIP apart; `motor_angles` its 13 motor angles, the closest fit through
  the couplings (PIP and DIP averaged, one spread for all fingers); `wrist_pose` your wrist
  with the ADAPT hand's axes. Both keep every joint within the robot's limits, and the thumb's
  CMC2 is measured from a relaxed thumb (`THUMB_REST`). The geometry is that of
  `virtualmodelcontrol.robots.adapt`.
- The 3D view's ADAPT mode: your hand next to the ADAPT hand its motors would make, with its
  joint and motor angles; also in the documentation, as a live demo.

## 0.2.0 (2026-11-15)

- 3D view of the hands in a browser, at http://localhost:8012/view while the stream runs:
  a hand view and a room view, with the forearm, joint angles and pinch.
- `metaquest-teleop --view` opens it; `QuestHands.view_url` gives its address.
- `metaquest-teleop-fake --hands right` (or `left`) fakes a single hand.
- Plain labels in the dashboard: joint angles as base, spread, middle and tip.
- `view?demo` runs the 3D view with fake hands made in the browser, no server needed; the
  documentation embeds it, with sliders to bend each finger.
- Documentation at https://vigno0405.github.io/MetaQuestTeleop/.

## 0.1.0 (2026-11-12)

First release.

- `QuestHands`: hand tracking from a Meta Quest over USB, in background threads, with
  `wait()`, `latest()` and `on_frame()`; wrist poses, 25 joints and 20 joint angles per hand.
- `metaquest-teleop`: the stream with a live terminal dashboard, `--plain` output and
  `--udp` JSON forwarding.
- `metaquest-teleop-fake`: a stand-in headset with synthetic hands.
- The server listens on 127.0.0.1 only.
