"""Per-user calibration.

ARKit-style blendshape estimates from a webcam are noisy and asymmetric: one
eye blinks at 40% while the other reaches 80%. A calibration profile stores a
neutral baseline and a per-blendshape gain/offset so the output is symmetric and
reaches the full 0..1 range.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from .frame import Frame


@dataclass
class BlendCalibration:
    neutral: float = 0.0
    gain: float = 1.0
    offset: float = 0.0
    min: float = 0.0
    max: float = 1.0


@dataclass
class Calibration:
    profiles: Dict[str, BlendCalibration] = field(default_factory=dict)
    name: str = "default"

    def apply(self, frame: Frame) -> Frame:
        blend = {}
        for key, value in frame.blendshapes.items():
            cal = self.profiles.get(key)
            if cal is None:
                blend[key] = value
                continue
            blend[key] = (value - cal.neutral) * cal.gain + cal.offset
        return Frame(blendshapes=blend, head=frame.head, right_eye=frame.right_eye,
                     left_eye=frame.left_eye, tracking=frame.tracking,
                     timestamp=frame.timestamp, source=frame.source)

    def capture_neutral(self, frames: Iterable[Frame], samples: int = 30) -> None:
        totals: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        for i, frame in enumerate(frames):
            if i >= samples:
                break
            for key, value in frame.blendshapes.items():
                totals[key] = totals.get(key, 0.0) + value
                counts[key] = counts.get(key, 0) + 1
        for key, total in totals.items():
            cal = self.profiles.setdefault(key, BlendCalibration())
            cal.neutral = total / counts[key]

    def auto_range(self, frames: Iterable[Frame]) -> None:
        """Set gain so each blendshape spans its observed min..max to 0..1."""
        lows: Dict[str, float] = {}
        highs: Dict[str, float] = {}
        for frame in frames:
            for key, value in frame.blendshapes.items():
                lows[key] = min(lows.get(key, value), value)
                highs[key] = max(highs.get(key, value), value)
        for key, low in lows.items():
            high = highs[key]
            cal = self.profiles.setdefault(key, BlendCalibration())
            cal.min, cal.max = low, high
            if high - low > 1e-3:
                cal.gain = 1.0 / (high - low)
                cal.neutral = low

    def save(self, path: str) -> None:
        data = {name: {"neutral": c.neutral, "gain": c.gain, "offset": c.offset,
                       "min": c.min, "max": c.max}
                for name, c in self.profiles.items()}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"name": self.name, "profiles": data}, handle, indent=2)

    @classmethod
    def load(cls, path: str) -> "Calibration":
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        calibration = cls(name=data.get("name", "default"))
        for name, values in data.get("profiles", {}).items():
            calibration.profiles[name] = BlendCalibration(**values)
        return calibration
