"""OSC packet writer for VMC's blendshape and bone messages.

VMC receivers identify an expression by name, then apply a group of values
with /VMC/Ext/Blend/Apply. FacePipe sends ARKit names for PerfectSync rigs.
"""
from __future__ import annotations

import struct
from typing import Iterable, Tuple

VMC_MARIONETTE_PORT = 39539
VMC_PERFORMER_PORT = 39540

def _pad(data: bytes) -> bytes:
    remainder = len(data) % 4
    return data + b"\x00" * (4 - remainder) if remainder else data


def _osc_string(value: str) -> bytes:
    return _pad(value.encode("utf-8") + b"\x00")


def osc_message(address: str, *args) -> bytes:
    """Build one OSC message. Supports float, int and str arguments."""
    if not address.startswith("/"):
        raise ValueError("OSC address must start with /")
    packet = _osc_string(address)
    tags = ""
    values = b""
    for arg in args:
        if isinstance(arg, float):
            tags += "f"
            values += struct.pack(">f", arg)
        elif isinstance(arg, int):
            tags += "i"
            values += struct.pack(">i", arg)
        elif isinstance(arg, str):
            tags += "s"
            values += _osc_string(arg)
        else:
            raise TypeError(f"unsupported OSC argument type: {type(arg)}")
    return packet + _osc_string("," + tags) + values


def bundle(messages: Iterable[Tuple[str, tuple]]) -> bytes:
    """Build a spec-compliant OSC bundle with an immediate timetag."""
    contents = b"#bundle\x00" + struct.pack(">Q", 1)
    for address, args in messages:
        message = osc_message(address, *args)
        contents += struct.pack(">I", len(message)) + message
    return contents


def bundle_packets(messages: Iterable[Tuple[str, tuple]], max_size: int = 1400):
    """Split OSC messages into UDP-sized bundles while preserving order."""
    if max_size < 64:
        raise ValueError("OSC packet limit is too small")
    group = []
    size = 16  # bundle header and timetag
    for address, args in messages:
        encoded_size = 4 + len(osc_message(address, *args))
        if 16 + encoded_size > max_size:
            raise ValueError("one OSC message exceeds the packet limit")
        if group and size + encoded_size > max_size:
            yield bundle(group)
            group = []
            size = 16
        group.append((address, args))
        size += encoded_size
    if group:
        yield bundle(group)
