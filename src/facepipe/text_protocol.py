"""iFacialMocap v1/v2 text protocol (the "legacy" protocol).

Wire format (one UDP datagram or one TCP chunk per frame):

    mouthSmile_R-0|eyeLookOut_L-0|...|=head#-21.48,-6.03,-6.60,-0.03,-0.10,-0.65|
    rightEye#6.02,2.44,0.25|leftEye#6.03,-1.66,-0.17|

* blendshape token: ``<name>-<int percent>``  (v1)
* blendshape token: ``<name>&<int percent>``  (v2, allows negative values)
* head token:       ``head#rx,ry,rz,px,py,pz``  (degrees, metres)
* eye tokens:       ``rightEye#rx,ry,rz`` / ``leftEye#rx,ry,rz``
* TCP frames are terminated with ``___iFacialMocap``

Real-world streams contain stray ``?`` characters, empty tokens and malformed
tail segments, so the parser here is deliberately forgiving.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from .blendshapes import RAW_TO_IDENTIFIER, RAW_VALUES, normalize_name
from .frame import Frame

# --- handshake commands the iOS app understands -----------------------------
CMD_START = "iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719"
CMD_START_TCP = "iFacialMocap_UDPTCP_sahuasouryya9218sauhuiayeta91555dy3719"
CMD_STOP_TCP = "iFacialMocap_UDPTCPSTOP_sahuasouryya9218sauhuiayeta91555dy3719"
CMD_LOOK_FORWARD = "iFacialMocap_lookForward"
CMD_BAKE_START = "iFacialMocap_bakeRecordedAnimation_start"
TCP_TERMINATOR = "___iFacialMocap"

IOS_UDP_PORT = 49983
IOS_TCP_PORT = 49986
RECORDED_TCP_PORT = 49987

_TOKEN_SPLIT = re.compile(r"[|?]+")
_NAME_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*([-&])\s*(-?\d+(?:\.\d+)?)$")
_POSE = re.compile(r"^([A-Za-z]+)\s*#\s*(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*)$")


def _percent(value: float) -> int:
    return int(round(value * 100))


def encode(frame: Frame, version: int = 1, names: Optional[Iterable[str]] = None,
           terminate: bool = False) -> str:
    """Serialise a Frame into an iFacialMocap text frame."""
    order = list(names) if names is not None else list(frame.blendshapes.keys())
    sep = "&" if version == 2 else "-"
    parts: List[str] = []
    for name in order:
        identifier = RAW_TO_IDENTIFIER.get(name, name)
        value = frame.blendshapes.get(name, frame.blendshapes.get(identifier, 0.0))
        parts.append(f"{name}{sep}{_percent(value)}")
    parts.append("head#" + ",".join(f"{v:.6f}" for v in frame.head))
    parts.append("rightEye#" + ",".join(f"{v:.6f}" for v in frame.right_eye))
    parts.append("leftEye#" + ",".join(f"{v:.6f}" for v in frame.left_eye))
    out = "|".join(parts) + "|"
    if terminate:
        out += TCP_TERMINATOR
    return out


def decode(text: str) -> Optional[Frame]:
    """Parse a text frame. Returns None when the payload contains no usable data."""
    text = text.replace(TCP_TERMINATOR, "")
    frame = Frame()
    found = False
    for token in _TOKEN_SPLIT.split(text):
        token = token.strip().lstrip("=")
        if not token:
            continue
        pose = _POSE.match(token)
        if pose:
            key = pose.group(1).lower()
            nums = [float(x) for x in pose.group(2).split(",")]
            if key == "head" and len(nums) >= 3:
                frame.head = tuple(nums[:6]) if len(nums) >= 6 else tuple(nums[:3]) + (0.0, 0.0, 0.0)
                found = True
            elif key == "righteye" and len(nums) >= 3:
                frame.right_eye = tuple(nums[:3])
                found = True
            elif key == "lefteye" and len(nums) >= 3:
                frame.left_eye = tuple(nums[:3])
                found = True
            continue
        match = _NAME_VALUE.match(token)
        if not match:
            continue
        try:
            frame.blendshapes[normalize_name(match.group(1))] = float(match.group(3)) / 100.0
        except ValueError:
            continue
        found = True
    return frame if found else None


def split_frames(chunk: str) -> List[str]:
    """TCP delivers concatenated frames; split on the terminator."""
    return [p for p in chunk.split(TCP_TERMINATOR) if p.strip()]


def official_sample() -> str:
    """The sample frame published on ifacialmocap.com/for-developer/ (with its quirks)."""
    return (
        "mouthSmile_R-0|eyeLookOut_L-0|mouthUpperUp_L-11|eyeWide_R-0|mouthClose-8|"
        "mouthPucker-4|mouthRollLower-9|eyeBlink_R-7|eyeLookDown_L-1|?cheekSquint_R-11|"
        "eyeBlink_L-7|tongueOut-0|jawRight-0|eyeLookIn_R-9|cheekSquint_L-11|"
        "mouthDimple_L-10|mouthPress_L-4|eyeSquint_L-11|mouthRight-0|mouthShrugLower-0|"
        "eyeLookUp_R-0|eyeLookOut_R-0|mouthPress_R-5|cheekPuff-2|jawForward-1|1|"
        "mouthLowerDown_L-9|mouthFrown_L-6|mouthShrugUpper-26|browOuterUp_L-4|"
        "browInnerUp-20|mouthDimple_R-10|browDown_R-0|mouthUpperUp_R-10|mouthRollUpper-8|"
        "mouthFunnel-12|mouthStretch_R-21|mouthFrown_R-13|eyeLookDown_R-17|jawOpen-12|"
        "jawLeft-0|browDown_L-0|mouthSmile_L-0|noseSneer_R-18|mouthLowerDown_R-8|"
        "noseSneer_L-21|eyeWide_L-0|mouthStretch_L-21|browOuterUp_R-4|eyeLookIn_L-4|"
        "eyeSquint_R-11|eyeLookUp_L-0|mouthLeft-0|=head#-21.488958,-6.038993,-6.6019735,"
        "-0.030653415,-0.10287084,-0.6584072|rightEye#6.0297494,2.4403017,0.25649446|"
        "leftEye#6.034903,-1.6660284,-0.17520553|34903,-1.6660284,-0.17520553|"
    )


__all__ = [
    "CMD_START", "CMD_START_TCP", "CMD_STOP_TCP", "CMD_LOOK_FORWARD", "CMD_BAKE_START",
    "TCP_TERMINATOR", "IOS_UDP_PORT", "IOS_TCP_PORT", "RECORDED_TCP_PORT",
    "encode", "decode", "split_frames", "official_sample", "RAW_VALUES",
]
