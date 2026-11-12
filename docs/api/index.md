# API

Scripts start with `from metaquest_teleop import QuestHands`. The classes of a frame and the
constants of the hand are importable from `metaquest_teleop` too; the modules below hold the
rest.

## The stream

```{eval-rst}
.. autoclass:: metaquest_teleop.QuestHands
   :members: start, stop, wait, latest, on_frame, rates, url, connected
```

## Frames and hands

```{eval-rst}
.. autoclass:: metaquest_teleop.Frame
   :members:

.. autoclass:: metaquest_teleop.Hand
   :members:

.. autoclass:: metaquest_teleop.Pose
   :members:
```

## Constants

All but `PARENT` are importable from `metaquest_teleop`.

```{eval-rst}
.. autodata:: metaquest_teleop.hands.JOINTS
   :no-value:

.. autodata:: metaquest_teleop.hands.PARENT
   :no-value:

.. autodata:: metaquest_teleop.hands.FINGERS
   :no-value:

.. autodata:: metaquest_teleop.hands.ANGLE_NAMES
   :no-value:

.. autodata:: metaquest_teleop.server.DEFAULT_PORT
```

## Wire format: `metaquest_teleop.hands`

```{eval-rst}
.. autofunction:: metaquest_teleop.hands.decode

.. autofunction:: metaquest_teleop.hands.encode

.. autofunction:: metaquest_teleop.hands.rotations

.. autodata:: metaquest_teleop.hands.FRAME_BYTES

.. autodata:: metaquest_teleop.hands.MAGIC
```

## USB link: `metaquest_teleop.server`

```{eval-rst}
.. autofunction:: metaquest_teleop.server.adb_reverse
```

## Fake headset: `metaquest_teleop.fake`

```{eval-rst}
.. autofunction:: metaquest_teleop.fake.stream

.. autofunction:: metaquest_teleop.fake.synthetic_hand

.. autofunction:: metaquest_teleop.fake.pose_at

.. autofunction:: metaquest_teleop.fake.quaternion
```

## Dashboard: `metaquest_teleop.dashboard`

```{eval-rst}
.. autofunction:: metaquest_teleop.dashboard.render

.. autofunction:: metaquest_teleop.dashboard.run
```
