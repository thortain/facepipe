"""Minimal OSC (Open Sound Control) packet writer - enough for the VMC protocol.

VMC (Virtual Motion Capture Protocol) is OSC over UDP, commonly on port 39539
(marionette) and 39540 (performer <- assistant). Facial expressions are sent as
`/face/1/<blendshape_index>` with a single float argument in the VRM blendshape
order.
"""
from __future__ import annotations

import struct
from typing import Iterable, Tuple

VMC_MARIONETTE_PORT = 39539
VMC_PERFORMER_PORT = 39540

# ARKit name -> VRM 1.0 blendshape index
ARKIT_TO_VRM = {
    "eyeBlinkLeft": 0, "eyeBlinkRight": 1,
    "eyeLookUpLeft": 2, "eyeLookUpRight": 3,
    "eyeLookDownLeft": 4, "eyeLookDownRight": 5,
    "eyeLookInLeft": 6, "eyeLookInRight": 7,
    "eyeLookOutLeft": 8, "eyeLookOutRight": 9,
    "mouthSmileLeft": 10, "mouthSmileRight": 11,
    "browOuterUpLeft": 12, "browOuterUpRight": 13,
    "browDownLeft": 14, "browDownRight": 15,
    "cheekSquintLeft": 16, "cheekSquintRight": 17,
    "jawOpen": 18, "jawForward": 30, "jawLeft": 31, "jawRight": 32,
    "mouthLeft": 19, "mouthRight": 20,
    "mouthPucker": 21, "mouthFunnel": 22,
    "noseSneerLeft": 23, "noseSneerRight": 24,
    "tongueOut": 25,
    "mouthClose": 33,
    "mouthDimpleLeft": 34, "mouthDimpleRight": 35,
    "mouthFrownLeft": 37, "mouthFrownRight": 38,
    "mouthLowerDownLeft": 39, "mouthLowerDownRight": 40,
    "mouthPressLeft": 41, "mouthPressRight": 42,
    "mouthStretchLeft": 45, "mouthStretchRight": 46,
    "mouthUpperUpLeft": 47, "mouthUpperUpRight": 48,
    "mouthRollLower": 51, "mouthRollUpper": 52,
    "mouthShrugLower": 53, "mouthShrugUpper": 55,
}


def _pad(data: bytes) -> bytes:
    remainder = len(data) % 4
    return data + b"\x00" * (4 - remainder) if remainder else data


def osc_message(address: str, *args) -> bytes:
    """Build one OSC message. Supports float, int and str arguments."""
    packet = address.encode("utf-8")
    tags = ""
    for arg in args:
        if isinstance(arg, float):
            tags += "f"
        elif isinstance(arg, int):
            tags += "i"
        elif isinstance(arg, str):
            tags += "s"
        else:
            raise TypeError(f"unsupported OSC argument type: {type(arg)}")
    packet += b"," + tags.encode("utf-8")
    for arg in args:
        if isinstance(arg, float):
            packet += struct.pack(">f", arg)
        elif isinstance(arg, int):
            packet += struct.pack(">i", arg)
        else:
            packet += arg.encode("utf-8") + b"\x00"
    return _pad(packet)


def bundle(messages: Iterable[Tuple[str, tuple]]) -> bytes:
    """Build an OSC bundle from (address, args) pairs - VMC allows bundled packets."""
    contents = b""
    for address, args in messages:
        contents += osc_message(address, *args)
    return _pad(b"#bundle\x00" + contents)
