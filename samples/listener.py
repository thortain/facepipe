#!/usr/bin/env python3
"""Tiny stand-in for a Unity/Blender/Unreal plugin: listens for iFacialMocap frames.

    python samples/listener.py            # legacy text protocol on UDP 49983
    python samples/listener.py --fmv3     # Face Motion v3 (this listener acts as the PC side)
"""
import argparse
import socket
import sys

sys.path.insert(0, "src")

from facepipe.fmv3 import FMV3Receiver, MODE_FIXED52
from facepipe.text_protocol import CMD_START, decode


def listen_text(port: int, duration: float) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    sock.settimeout(duration)
    print(f"listening for iFacialMocap text frames on UDP {port}")
    count = 0
    while True:
        try:
            data, _ = sock.recvfrom(8192)
        except socket.timeout:
            break
        frame = decode(data.decode("utf-8"))
        if not frame:
            continue
        count += 1
        top = sorted(frame.blendshapes.items(), key=lambda kv: -kv[1])[:5]
        print(f"frame {count}: " + " ".join(f"{k}={v:.2f}" for k, v in top))
    print(f"received {count} frames")


def listen_fmv3(port: int, pc_port: int, duration: float) -> None:
    receiver = FMV3Receiver("127.0.0.1", port=port, pc_port=pc_port, mode=MODE_FIXED52)
    count = [0]

    def on_frame(frame):
        count[0] += 1
        if count[0] % 30 == 1:
            top = sorted(frame.blendshapes.items(), key=lambda kv: -kv[1])[:5]
            print(f"frame {count[0]}: " + " ".join(f"{k}={v:.2f}" for k, v in top))

    receiver.run(on_frame, duration=duration)
    print(f"received {count[0]} FMV3 frames")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=49983)
    parser.add_argument("--pc-port", type=int, default=None)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--fmv3", action="store_true")
    args = parser.parse_args()
    if args.fmv3:
        listen_fmv3(args.port, args.pc_port or args.port, args.duration)
    else:
        listen_text(args.port, args.duration)
