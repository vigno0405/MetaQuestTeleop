---
hide-navigation: true
---

# metaquest-teleop

Stream your hands from a Meta Quest to Python, to control robots. Up to 120 times a second you
get both wrists, 25 joints and 20 joint angles per hand. Nothing to install on the headset.

<img class="diagram" src="_static/data-path.svg" alt="The Quest's browser page sends every frame over the USB cable to your computer, where your Python code, the dashboard and other programs receive it">

## In three steps

1. `pip install metaquest-teleop`
2. Plug in the headset and run `metaquest-teleop`.
3. In the Quest's browser, open **http://localhost:8012** and press **Start**.

No headset? Run `metaquest-teleop-fake` in a second terminal. [Get started](start.md) has the
details, including the one-time setup of the headset.

## See your hands in 3D

Open **http://localhost:8012/view** on your computer. More in [3D view](view.md).

![The 3D view: a right hand on its forearm, with its joint angles](_static/view-hand.png)

## Use them in Python

```python
from metaquest_teleop import QuestHands

with QuestHands() as quest:
    while True:
        frame = quest.wait()  # the next frame from the headset
        if frame.right is not None:
            print(frame.right.wrist.position, frame.right.pinch)
```

More in [Use it in Python](python.md).

Written by Gregorio Valenti. MIT license. Source on
[GitHub](https://github.com/vigno0405/MetaQuestTeleop).

```{toctree}
:hidden:
:caption: Getting started

start
view
troubleshooting
```

```{toctree}
:hidden:
:caption: Using it

python
data
```

```{toctree}
:hidden:
:caption: Reference

api/index
changelog
```
