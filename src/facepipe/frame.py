"""The internal representation of one captured face frame.

All blendshape values are stored as floats in the 0.0 .. 1.0 range (values
outside that range are legal and preserved - negative and >1 values are used by
some rigs). Head rotation is in degrees, head position in metres, matching the
iFacialMocap / FMV3 convention.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

ZERO6 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
ZERO3 = (0.0, 0.0, 0.0)


@dataclass
class Frame:
    blendshapes: Dict[str, float] = field(default_factory=dict)
    head: Tuple[float, float, float, float, float, float] = ZERO6
    right_eye: Tuple[float, float, float] = ZERO3
    left_eye: Tuple[float, float, float] = ZERO3
    tracking: bool = True
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"
    landmarks: Optional[list] = None

    def value(self, name: str, default: float = 0.0) -> float:
        return self.blendshapes.get(name, default)

    def is_empty(self) -> bool:
        return not any(self.blendshapes.values())
