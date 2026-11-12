"""The smallest use of the stream: print the right wrist and index finger, ten times a second.

    pip install metaquest-teleop
    python examples/minimal.py      # then open http://localhost:8012 in the Quest browser
"""

import time

import numpy as np

from metaquest_teleop import QuestHands

with QuestHands() as quest:
    print(f"Open {quest.url} in the Quest browser and press Start. Ctrl-C to stop.")
    try:
        while True:
            frame = quest.wait(timeout=1.0)
            if frame is None or frame.right is None:
                print("waiting for the right hand...")
                continue
            wrist = frame.right.wrist
            index = np.degrees(frame.right.angles[1])
            print(f"wrist {np.round(wrist.position, 3)} m   quaternion {np.round(wrist.quaternion, 3)}   "
                  f"index MCP {index[0]:4.0f}°  PIP {index[2]:4.0f}°  DIP {index[3]:4.0f}°")
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
