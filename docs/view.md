---
hide-toc: true
---

# 3D view

A live 3D picture of the hands, in a browser on your computer, to check that everything works.
While `metaquest-teleop` (or your script) runs, open **http://localhost:8012/view**.

## Try it here

This is the real page, with the fake hands of `metaquest-teleop-fake` made in your browser:
no headset needed.

<iframe class="demo" src="_static/view.html?demo&mode=hand&hand=right" title="The 3D view, with a fake right hand you can move" loading="lazy"></iframe>

Some things to try:

- **Pause**, pick **index**, and move **middle**: only the middle joint of the index bends, and
  the *middle* column of the table follows. That is what `hand.angles[1, 2]` gives you.
- Move **spread**: the finger moves sideways.
- Click **Room** to see the hands where they are, over the floor.

<a href="_static/view.html?demo&mode=hand&hand=right" target="_blank">Open it in its own tab</a>.

## How it works

1. **The headset** tracks your hands, and its browser sends every frame through the USB cable.
2. **`metaquest-teleop`** on your computer receives the frames and passes the newest one to
   the 3D view, about 60 times a second.
3. **The 3D view** draws the 25 joints of each hand, the bones between them, and a grey sleeve
   for the forearm.

## How to read it

- **Hand** keeps the hand still in the middle and moves only the fingers. **Room** shows the
  hands where they are, seen from about where your eyes are.
- The grey **sleeve** is the start of the forearm; its blue side is the palm side.
- Fingers: thumb red, index yellow, middle green, ring blue, pinky violet.
- Axes: x red, y green, z blue.
- The dashed line is the pinch: thumb tip to index tip, in millimetres.
- The table gives each finger's angles: the bend at its base, middle and tip joints, and its
  spread sideways. See [the data](data.md#angles).
- While `metaquest-teleop` runs, the **robot** line says whether a robot would move or hold
  ([teleoperation](teleop.md)).

## Controls

| | |
|---|---|
| Drag | rotate |
| Shift-drag or right-drag | move |
| Scroll | zoom (Ctrl + scroll in the demo above) |
| Double-click | reset the view |
