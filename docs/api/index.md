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
