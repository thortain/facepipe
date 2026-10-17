"""Canonical ARKit 52 blendshape tables and cross-framework name mapping.

Two spellings exist for the same 52 shapes:

* ARKit *identifier*  -> `eyeBlinkLeft`   (Swift enum name, used by FMV3 fixed52)
* ARKit *rawValue*    -> `eyeBlink_L`     (what ARKit returns, used by iFacialMocap v1/v2 text)

FMV3 fixed52 mode sends the 52 values in **alphabetical order of the identifier**.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# (identifier, rawValue) in FMV3 fixed52 order.
ARKIT_52: Tuple[Tuple[str, str], ...] = (
    ("browDownLeft", "browDown_L"),
    ("browDownRight", "browDown_R"),
    ("browInnerUp", "browInnerUp"),
    ("browOuterUpLeft", "browOuterUp_L"),
    ("browOuterUpRight", "browOuterUp_R"),
    ("cheekPuff", "cheekPuff"),
    ("cheekSquintLeft", "cheekSquint_L"),
    ("cheekSquintRight", "cheekSquint_R"),
    ("eyeBlinkLeft", "eyeBlink_L"),
    ("eyeBlinkRight", "eyeBlink_R"),
    ("eyeLookDownLeft", "eyeLookDown_L"),
    ("eyeLookDownRight", "eyeLookDown_R"),
    ("eyeLookInLeft", "eyeLookIn_L"),
    ("eyeLookInRight", "eyeLookIn_R"),
    ("eyeLookOutLeft", "eyeLookOut_L"),
    ("eyeLookOutRight", "eyeLookOut_R"),
    ("eyeLookUpLeft", "eyeLookUp_L"),
    ("eyeLookUpRight", "eyeLookUp_R"),
    ("eyeSquintLeft", "eyeSquint_L"),
    ("eyeSquintRight", "eyeSquint_R"),
    ("eyeWideLeft", "eyeWide_L"),
    ("eyeWideRight", "eyeWide_R"),
    ("jawForward", "jawForward"),
    ("jawLeft", "jawLeft"),
    ("jawOpen", "jawOpen"),
    ("jawRight", "jawRight"),
    ("mouthClose", "mouthClose"),
    ("mouthDimpleLeft", "mouthDimple_L"),
    ("mouthDimpleRight", "mouthDimple_R"),
    ("mouthFrownLeft", "mouthFrown_L"),
    ("mouthFrownRight", "mouthFrown_R"),
    ("mouthFunnel", "mouthFunnel"),
    ("mouthLeft", "mouthLeft"),
    ("mouthLowerDownLeft", "mouthLowerDown_L"),
    ("mouthLowerDownRight", "mouthLowerDown_R"),
    ("mouthPressLeft", "mouthPress_L"),
    ("mouthPressRight", "mouthPress_R"),
    ("mouthPucker", "mouthPucker"),
    ("mouthRight", "mouthRight"),
    ("mouthRollLower", "mouthRollLower"),
    ("mouthRollUpper", "mouthRollUpper"),
    ("mouthShrugLower", "mouthShrugLower"),
    ("mouthShrugUpper", "mouthShrugUpper"),
    ("mouthSmileLeft", "mouthSmile_L"),
    ("mouthSmileRight", "mouthSmile_R"),
    ("mouthStretchLeft", "mouthStretch_L"),
    ("mouthStretchRight", "mouthStretch_R"),
    ("mouthUpperUpLeft", "mouthUpperUp_L"),
    ("mouthUpperUpRight", "mouthUpperUp_R"),
    ("noseSneerLeft", "noseSneer_L"),
    ("noseSneerRight", "noseSneer_R"),
    ("tongueOut", "tongueOut"),
)

assert len(ARKIT_52) == 52

IDENTIFIERS: Tuple[str, ...] = tuple(name for name, _ in ARKIT_52)
RAW_VALUES: Tuple[str, ...] = tuple(raw for _, raw in ARKIT_52)

IDENTIFIER_TO_RAW: Dict[str, str] = dict(ARKIT_52)
RAW_TO_IDENTIFIER: Dict[str, str] = {raw: name for name, raw in ARKIT_52}
IDENTIFIER_INDEX: Dict[str, int] = {name: i for i, name in enumerate(IDENTIFIERS)}
RAW_INDEX: Dict[str, int] = {raw: i for i, raw in enumerate(RAW_VALUES)}
_LOWER_INDEX: Dict[str, str] = {name.lower(): name for name in IDENTIFIERS}

# The bundled FaceLandmarker model emits `_neutral` plus 51 ARKit identifiers;
# `tongueOut` is absent and is sent as zero by the wire/FBX encoders.
MEDIAPIPE_SKIP = {"_neutral"}


def normalize_name(name: str) -> str:
    """Return the ARKit identifier spelling for any of the common spellings."""
    name = name.strip()
    if name in IDENTIFIER_INDEX:
        return name
    if name in RAW_TO_IDENTIFIER:
        return RAW_TO_IDENTIFIER[name]
    lowered = name.lower()
    if lowered in _LOWER_INDEX:
        return _LOWER_INDEX[lowered]
    if lowered.endswith("_l") or lowered.endswith("_r"):
        side = "left" if lowered.endswith("_l") else "right"
        candidate = lowered[:-2] + side
        if candidate in _LOWER_INDEX:
            return _LOWER_INDEX[candidate]
    raise ValueError(f"unknown blendshape name: {name!r}")


def to_float(value) -> float:
    """Blendshape values arrive as int percent (0..100) or float 0..1."""
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 100.0 if v > 1.0 else v
    raise ValueError(f"bad blendshape value: {value!r}")
