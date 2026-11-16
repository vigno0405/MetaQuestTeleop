# API

Everything you need is in `metaquest_teleop`. Start with `QuestHands`; each frame it gives you
is a `Frame`, which holds up to two `Hand`s, whose joints are `Pose`s.

Below, *method* is something you call with `()`, like `quest.wait()`; *property* and
*attribute* are values you read, like `hand.pinch`.

## QuestHands: the stream

```{eval-rst}
.. autoclass:: metaquest_teleop.QuestHands
   :members: wait, latest, on_frame, start, stop, url, view_url, connected, rates
```

## Teleop: one hand drives, the other pauses

```{eval-rst}
.. autoclass:: metaquest_teleop.Teleop
   :members: command, update

.. autoclass:: metaquest_teleop.Command
   :members:
```

## Frame: one moment

```{eval-rst}
.. autoclass:: metaquest_teleop.Frame
   :members:
```

## Hand: one hand

```{eval-rst}
.. autoclass:: metaquest_teleop.Hand
   :members:
```

## Pose: a position and an orientation

```{eval-rst}
.. autoclass:: metaquest_teleop.Pose
   :members:
```

## ADAPT Hand: `metaquest_teleop.adapt`

```{eval-rst}
.. autofunction:: metaquest_teleop.adapt.joint_angles

.. autofunction:: metaquest_teleop.adapt.motor_angles

.. autofunction:: metaquest_teleop.adapt.wrist_pose

.. autofunction:: metaquest_teleop.adapt.thumb_cmc

.. autofunction:: metaquest_teleop.adapt.positions

.. autodata:: metaquest_teleop.adapt.JOINTS
   :no-value:

.. autodata:: metaquest_teleop.adapt.MOTORS
   :no-value:

.. autodata:: metaquest_teleop.adapt.JOINT_LIMITS
   :no-value:

.. autodata:: metaquest_teleop.adapt.COUPLING
   :no-value:

.. autodata:: metaquest_teleop.adapt.THUMB_REST
   :no-value:
```

## Names

```{eval-rst}
.. autodata:: metaquest_teleop.hands.JOINTS
   :no-value:

.. autodata:: metaquest_teleop.hands.ANGLE_NAMES
   :no-value:

.. autodata:: metaquest_teleop.hands.FINGERS
   :no-value:

.. autodata:: metaquest_teleop.server.DEFAULT_PORT
```
