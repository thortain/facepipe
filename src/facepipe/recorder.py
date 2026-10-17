"""Record and replay captured frames.

Recording format is NDJSON: one JSON object per frame, written by JSONFileEmitter.
Replaying produces Frame objects at the recorded rate, which lets a capture be
fed into the FMV3 sender or the text emitter as if it were live.
"""
from __future__ import annotations

import json
import time
from typing import Iterator, List

from .frame import Frame


def load(path: str) -> List[Frame]:
    frames = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith("___iFacialMocap"):
                continue
            record = json.loads(line)
            frames.append(Frame(
                blendshapes=record.get("blend", {}),
                head=tuple(record.get("head", (0, 0, 0, 0, 0, 0))),
                right_eye=tuple(record.get("rightEye", (0, 0, 0))),
                left_eye=tuple(record.get("leftEye", (0, 0, 0))),
                tracking=record.get("tracking", True),
                timestamp=record.get("t", 0.0),
                source="recording",
            ))
    return frames


def replay(path: str, fps: int = 60, loop: bool = False) -> Iterator[Frame]:
    frames = load(path)
    if not frames:
        return
    interval = 1.0 / fps
    while True:
        for frame in frames:
            yield frame
            time.sleep(interval)
        if not loop:
            break


def summary(path: str) -> dict:
    frames = load(path)
    if not frames:
        return {"frames": 0}
    names = {}
    for frame in frames:
        for name, value in frame.blendshapes.items():
            stats = names.setdefault(name, [0.0, 0.0, 0.0, 0])
            stats[0] = min(stats[0], value)
            stats[1] = max(stats[1], value)
            stats[2] += value
            stats[3] += 1
    return {
        "frames": len(frames),
        "duration_s": frames[-1].timestamp - frames[0].timestamp,
        "blendshapes": {name: {"min": lo, "max": hi, "mean": total / count}
                        for name, (lo, hi, total, count) in sorted(names.items())},
    }
