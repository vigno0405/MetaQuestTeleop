# Changelog

## 0.7.0 (2026-11-16)

- The ADAPT hand follows your hand joint for joint, your range of motion stretched onto its own
  (`adapt.HUMAN_RANGES`, typical ranges you can change at any time): your open hand gives its
  home (all zeros), a power grasp about PC1 and a pinch about PC2, the real hand's poses of
  HumanManipulationVMC (Santello et al., 1998). Its thumb's CMC1 and CMC2 follow your thumb's
  first bone, read as the ADAPT's gimbal turns its own. Before, the thumb stuck out sideways.
- Removed: `adapt.THUMB_REST`, `joint_angles(..., thumb_rest=...)` and `adapt.thumb_cmc`.
- The 3D view maps your hand with the same ranges as the library, also once you change them.

## 0.6.3 (2026-11-16)

- The ADAPT hand on the dashboard, in `--print_joints` and in the 3D view's Room follows your hand
  as it is, as in the ADAPT view. It no longer freezes while the robot holds: testing with your
  right hand only, the robot always holds (left hand not seen), and the ADAPT hand stood still
  at an old pose. It is not tracked when your hand is not. Whether the robot moves or holds stays
  on the robot line, and ROS 2 still carries what the robot gets.

## 0.6.2 (2026-11-16)

- 3D view, Room: **Your hand** (the default) or **ADAPT hand**, one at a time: the ADAPT hand
  alone, where the robot goes, drawn as your hand is, with its joints and motors in the panel.
  It replaces the amber ADAPT hand drawn over yours.
- Dashboard: while the robot holds, the ADAPT panel says it holds its last pose, greyed, so it
  does not look tracked when your hand is not.

## 0.6.1 (2026-11-16)

- The ADAPT joint angles are a pose the ADAPT hand can take, as in its kinematics
  (VirtualModelControl, HumanManipulationVMC): each finger's DIP mimics its PIP, so both take the
  mean of yours, which keeps your fingertip's direction; one motor spreads the fingers, so the
  spreads take the best fit of yours. The dashboard, `--print_joints`, the 3D view and
  `/metaquest/adapt/joint_states` all show that pose. `joint_angles(hand, coupled=False)` gives
  your angles one by one, as before.
- Motor targets: each motor stays where all its joints are within their limits.
- 3D view: with one hand streamed (the default), it is the hand shown, with no hand to pick; in
  Room, a line says what the amber ADAPT hand is.

## 0.6.0 (2026-11-16)

- The dashboard shows the ADAPT hand next to yours, in yellow: its joints as the robot gets them
  (still while it holds), and its wrist, fixed at (0, 0).
- The 3D view's **Room** shows the ADAPT hand where the robot goes (**Robot**): at your wrist,
  its own wrist straight, still while the robot holds.
- The ADAPT wrist stays at (0, 0), held by a PID: `adapt.WRIST_MOTORS`, and
  `/metaquest/adapt/motors` ends with its two motors at 0. The docs say so.

## 0.5.3 (2026-11-16)

- ROS 2 from any Python: from one that cannot load ROS 2, such as a conda environment with
  Python 3.10 and ROS 2 Jazzy on 3.12, `metaquest-teleop` now publishes anyway, through a small
  helper process with the Python ROS 2 runs on. `RosPublisher` does the same; its `python`
  names the Python to publish with.

## 0.5.2 (2026-11-16)

- Restart `metaquest-teleop` while the headset streams and it goes on without pressing Start
  again. The dashboard and the 3D view used to say "press Start" then; now they say
  "streaming", and the headset page tells the new one about its session again.
- Without a ROS 2 that this Python can load, the message says why in a few words, for example
  "ROS 2 Jazzy runs on Python 3.12, and this is Python 3.10".

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
