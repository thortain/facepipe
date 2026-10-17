"""Output backends. Each emitter accepts a Frame and pushes it somewhere.

The point of FacePipe is interoperability: a webcam/browser capture can be
re-broadcast in every dialect the iFacialMocap ecosystem already understands.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from typing import Iterable, List, Optional

from .blendshapes import IDENTIFIERS, RAW_VALUES
from .frame import Frame
from .fmv3 import FMV3Sender, MODE_FIXED52, MODE_VARIABLE
from .osc import ARKIT_TO_VRM, VMC_MARIONETTE_PORT, bundle
from .text_protocol import CMD_START, CMD_START_TCP, TCP_TERMINATOR, encode


class TextUDPEmitter:
    """Send iFacialMocap v1/v2 text frames to a PC receiver (Unity/Blender/UE plugin)."""

    def __init__(self, host: str, port: int = 49983, version: int = 1,
                 names: Optional[Iterable[str]] = None) -> None:
        self.host = host
        self.port = port
        self.version = version
        self.names = tuple(names) if names is not None else RAW_VALUES
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, frame: Frame) -> None:
        payload = encode(frame, version=self.version, names=self.names).encode("utf-8")
        self.sock.sendto(payload, (self.host, self.port))

    def close(self) -> None:
        self.sock.close()


class TextTCPEmitter:
    """Send iFacialMocap TCP frames (terminated with ___iFacialMocap)."""

    def __init__(self, host: str, port: int = 49986, version: int = 1) -> None:
        self.host = host
        self.port = port
        self.version = version
        self.sock = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=5)

    def send(self, frame: Frame) -> None:
        if self.sock is None:
            self.connect()
        self.sock.sendall(encode(frame, version=self.version, terminate=True).encode("utf-8"))

    def close(self) -> None:
        if self.sock:
            self.sock.close()


class VMCEmitter:
    """Send VMC/OSC facial expressions to a marionette (VRM avatar host)."""

    def __init__(self, host: str, port: int = VMC_MARIONETTE_PORT, send_head: bool = True) -> None:
        self.host = host
        self.port = port
        self.send_head = send_head
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, frame: Frame) -> None:
        messages = []
        for name, value in frame.blendshapes.items():
            index = ARKIT_TO_VRM.get(name)
            if index is not None:
                messages.append((f"/face/1/{index}", (float(value),)))
        if self.send_head:
            rx, ry, rz, px, py, pz = frame.head
            messages.append(("/base/Head/Front/rot", (float(rx), float(ry), float(rz))))
            messages.append(("/base/Head/Front/pos", (float(px), float(py), float(pz))))
        if messages:
            self.sock.sendto(bundle(messages), (self.host, self.port))

    def close(self) -> None:
        self.sock.close()


class JSONFileEmitter:
    """Append frames as NDJSON - the recording format used by the recorder/replayer."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.handle = open(path, "w", encoding="utf-8")

    def send(self, frame: Frame) -> None:
        record = {
            "t": frame.timestamp,
            "tracking": frame.tracking,
            "head": list(frame.head),
            "rightEye": list(frame.right_eye),
            "leftEye": list(frame.left_eye),
            "blend": frame.blendshapes,
        }
        self.handle.write(json.dumps(record) + "\n")

    def close(self) -> None:
        self.handle.close()


class ConsoleEmitter:
    def __init__(self, every: float = 1.0) -> None:
        self.every = every
        self.last = 0.0

    def send(self, frame: Frame) -> None:
        if time.time() - self.last < self.every:
            return
        self.last = time.time()
        top = sorted(frame.blendshapes.items(), key=lambda kv: -kv[1])[:6]
        print(f"[{frame.timestamp:8.3f}] tracking={frame.tracking} "
              f"head={tuple(round(v, 1) for v in frame.head)} " +
              " ".join(f"{k}={v:.2f}" for k, v in top))


class FMV3Sink:
    """Adapter that lets an FMV3Sender participate in a Relay."""

    def __init__(self, sender) -> None:
        self.sender = sender

    def send(self, frame: Frame) -> None:
        self.sender.push(frame)

    def close(self) -> None:
        self.sender.stop()


class Relay:
    """Fan one frame stream out to any number of emitters."""

    def __init__(self, emitters: List) -> None:
        self.emitters = emitters
        self.count = 0

    def add(self, emitter) -> None:
        self.emitters.append(emitter)

    def publish(self, frame: Frame) -> None:
        for emitter in self.emitters:
            try:
                emitter.send(frame)
            except Exception as exc:  # keep the stream alive if one sink is down
                print(f"emitter failed: {emitter.__class__.__name__}: {exc}")
        self.count += 1

    def close(self) -> None:
        for emitter in self.emitters:
            try:
                emitter.close()
            except Exception:
                pass


def run_capture_loop(source, relay: Relay, fps: int = 30) -> int:
    """Drive a frame source at a fixed rate into a relay."""
    interval = 1.0 / fps
    next_tick = time.time()
    for frame in source:
        relay.publish(frame)
        next_tick += interval
        delay = next_tick - time.time()
        if delay > 0:
            time.sleep(delay)
    return relay.count
