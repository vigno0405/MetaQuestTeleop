# ROS 2

`metaquest-teleop` publishes the hands on ROS 2 topics, with standard messages only, so it works
on ROS 2 Humble and Jazzy with nothing to build.

## Run it

It needs the Python your ROS uses: 3.10 for Humble, 3.12 for Jazzy. Once:

```bash
source /opt/ros/jazzy/setup.bash          # or humble
python3 -m venv --system-site-packages ~/venvs/quest-ros
~/venvs/quest-ros/bin/pip install metaquest-teleop
```

(If `python3 -m venv` fails, `sudo apt install python3-venv` first.) Then, every time:

```bash
source /opt/ros/jazzy/setup.bash
~/venvs/quest-ros/bin/metaquest-teleop
```

It publishes whenever it finds ROS 2: `ros2 topic list` shows the `/metaquest/...` topics.
Without ROS, in a conda environment for example, it runs as usual and says it is not publishing.
`--ros` makes ROS required, `--no-ros` turns it off, and `--no-adapt` leaves out the ADAPT
hand's topics.

## Topics

| Topic | Message | |
|---|---|---|
| `/metaquest/right/joint_states` | `sensor_msgs/JointState` | your 20 joint angles, radians |
| `/metaquest/right/wrist` | `geometry_msgs/PoseStamped` | your wrist |
| `/metaquest/right/joints` | `geometry_msgs/PoseArray` | your 25 joints |
| `/metaquest/right/pinch` | `std_msgs/Float64` | thumb tip to index tip, metres |
| `/metaquest/adapt/joint_states` | `sensor_msgs/JointState` | the ADAPT hand's 20 joint angles |
| `/metaquest/adapt/motors` | `sensor_msgs/JointState` | its 13 motor angles: targets for a PID |
| `/metaquest/adapt/wrist` | `geometry_msgs/PoseStamped` | your wrist, with the ADAPT axes |
| `/metaquest/teleop/hold` | `std_msgs/Bool` | true: keep the robot still ([teleoperation](teleop.md)) |
| `/metaquest/teleop/state` | `std_msgs/String` | `moving`, or why it holds |
| `/metaquest/teleop/wrist` | `geometry_msgs/PoseStamped` | where the robot's wrist goes |

Your hand's `/metaquest/right/...` topics always come; the `/metaquest/adapt/...` ones come
with them while the ADAPT hand is on, the default, and not with `--no-adapt`. Every frame
publishes, up to 120 times a second. The ADAPT joints and motors hold still while
the robot holds; `hold` and `state` keep coming, ten times a second, while frames stop. Poses
are in the frame `metaquest_floor`, the headset's room: x right, y up, −z forward. With
`--hands both`, the left hand has its own `/metaquest/left/...` topics.

## A controller

The ADAPT motors, with the hold:

```python
import rclpy
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

rclpy.init()
node = rclpy.create_node("adapt_controller")
hold = True


def on_hold(msg):
    global hold
    hold = msg.data


def on_motors(msg):
    if not hold:
        targets = dict(zip(msg.name, msg.position))  # motor name -> angle, radians
        # your PID: drive each motor towards targets[name]


node.create_subscription(Bool, "/metaquest/teleop/hold", on_hold, 10)
node.create_subscription(JointState, "/metaquest/adapt/motors", on_motors, 10)
rclpy.spin(node)
```

## From Python

```python
from metaquest_teleop import QuestHands, Teleop
from metaquest_teleop.ros import RosPublisher

with QuestHands() as quest:
    ros = RosPublisher(quest, teleop=Teleop(quest))  # publishes every frame
    ...
    ros.close()
```
