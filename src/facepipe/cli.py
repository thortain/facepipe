"""FacePipe command line.

Examples
--------
Serve a webcam as an iFacialMocap-compatible stream (FMV3 + legacy text):

    facepipe serve --source 0 --fps 30

Serve a synthetic stream so you can test a receiver without a camera:

    facepipe serve --source synthetic --fps 60

Record a webcam clip and replay it into Unity:

    facepipe record --source 0 --out session.ndjson
    facepipe replay --in session.ndjson --emit text-udp --host 127.0.0.1 --port 49983

Ingest a real iPhone running iFacialMocap and re-broadcast to VMC/OSC:

    facepipe receive --host 192.168.1.7 --transport udp --emit vmc --host-vmc 127.0.0.1
"""
from __future__ import annotations

import argparse
import sys
import time

from .blendshapes import ARKIT_52
from .calibration import Calibration
from .capture import MediaPipeFaceCapture, image_frames, synthetic_frames
from .emitters import (ConsoleEmitter, FMV3Sink, JSONFileEmitter, Relay, TextTCPEmitter,
                       TextUDPEmitter, VMCEmitter, run_capture_loop)
from .fmv3 import FMV3Receiver, FMV3Sender, MODE_FIXED52, MODE_VARIABLE
from .recorder import replay, summary
from .text_protocol import official_sample


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="facepipe", description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="capture a camera/video and serve it as a mocap stream")
    serve.add_argument("--source", default="synthetic", help="webcam index, video path, or 'synthetic'")
    serve.add_argument("--fps", type=int, default=30)
    serve.add_argument("--udp-port", type=int, default=49983)
    serve.add_argument("--tcp-port", type=int, default=49984)
    serve.add_argument("--mode", choices=["fixed52", "variable"], default="fixed52")
    serve.add_argument("--text", action="store_true", help="also send legacy iFacialMocap text frames")
    serve.add_argument("--text-host", default="127.0.0.1")
    serve.add_argument("--text-port", type=int, default=49983)
    serve.add_argument("--vmc-host", default=None, help="also send VMC/OSC to this host")
    serve.add_argument("--vmc-port", type=int, default=39539)
    serve.add_argument("--web", type=int, default=None, help="serve a live viewer on this HTTP port")
    serve.add_argument("--duration", type=float, default=None)
    serve.add_argument("--model", default="face_landmarker.task")

    record = sub.add_parser("record", help="capture to an NDJSON recording")
    record.add_argument("--source", default="0")
    record.add_argument("--out", default="session.ndjson")
    record.add_argument("--fps", type=int, default=30)
    record.add_argument("--duration", type=float, default=None)
    record.add_argument("--model", default="face_landmarker.task")

    play = sub.add_parser("replay", help="replay a recording into an emitter")
    play.add_argument("--in", dest="path", required=True)
    play.add_argument("--fps", type=int, default=60)
    play.add_argument("--loop", action="store_true")
    play.add_argument("--emit", choices=["console", "text-udp", "text-tcp", "fmv3", "json"], default="console")
    play.add_argument("--host", default="127.0.0.1")
    play.add_argument("--port", type=int, default=49983)
    play.add_argument("--duration", type=float, default=None)

    receive = sub.add_parser("receive", help="connect to an iPhone running iFacialMocap")
    receive.add_argument("--host", required=True)
    receive.add_argument("--transport", choices=["udp", "tcp"], default="udp")
    receive.add_argument("--protocol", choices=["fmv3", "text"], default="fmv3")
    receive.add_argument("--mode", choices=["fixed52", "variable"], default="fixed52")
    receive.add_argument("--port", type=int, default=49983,
                         help="port the iOS app listens on")
    receive.add_argument("--pc-port", type=int, default=None,
                        help="local port to bind (defaults to --port)")
    receive.add_argument("--duration", type=float, default=10.0)
    receive.add_argument("--out", default=None, help="also write the stream to an NDJSON file")

    calibrate = sub.add_parser("calibrate", help="capture a neutral face and save a profile")
    calibrate.add_argument("--source", default="0")
    calibrate.add_argument("--out", default="calibration.json")
    calibrate.add_argument("--samples", type=int, default=30)
    calibrate.add_argument("--model", default="face_landmarker.task")

    info = sub.add_parser("info", help="print the blendshape table and protocol notes")
    info.add_argument("--sample", action="store_true", help="show the official sample frame")

    return parser


def source_for(args):
    if args.source == "synthetic":
        return synthetic_frames(fps=args.fps, duration=args.duration or 10.0)
    if args.source.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
        capture = MediaPipeFaceCapture(model_path=args.model)
        return image_frames(args.source, capture, fps=args.fps, duration=args.duration or 5.0)
    capture = MediaPipeFaceCapture(model_path=args.model)
    try:
        source = int(args.source)
    except ValueError:
        source = args.source
    return capture.frames(source, fps=args.fps)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "info":
        print("ARKit 52 blendshapes (FMV3 fixed52 order)")
        for index, (identifier, raw) in enumerate(ARKIT_52):
            print(f"  {index:2d}  {identifier:<18} {raw}")
        if args.sample:
            print("\nOfficial iFacialMocap sample frame:")
            print(official_sample())
        return 0

    if args.command == "calibrate":
        calibration = Calibration()
        calibration.capture_neutral(source_for(args), samples=args.samples)
        calibration.save(args.out)
        print(f"saved {len(calibration.profiles)} blendshape profiles to {args.out}")
        return 0

    if args.command == "record":
        relay = Relay([JSONFileEmitter(args.out), ConsoleEmitter(every=1.0)])
        try:
            count = run_capture_loop(source_for(args), relay, fps=args.fps)
        finally:
            relay.close()
        print(f"recorded {count} frames -> {args.out}")
        print(summary(args.out)["frames"], "frames")
        return 0

    if args.command == "replay":
        if args.emit == "text-udp":
            emitters = [TextUDPEmitter(args.host, args.port)]
        elif args.emit == "text-tcp":
            emitters = [TextTCPEmitter(args.host, args.port)]
        elif args.emit == "json":
            emitters = [JSONFileEmitter(getattr(args, "out", None) or "out.ndjson")]
        elif args.emit == "fmv3":
            sender = FMV3Sender(udp_port=args.port, tcp_port=args.port + 1, fps=args.fps)
            sender.start()
            emitters = [FMV3Sink(sender), ConsoleEmitter(every=1.0)]
        else:
            emitters = [ConsoleEmitter(every=1.0)]
        relay = Relay(emitters)
        frames = replay(args.path, fps=args.fps, loop=args.loop)
        if args.duration:
            frames = itertools_islice(frames, int(args.fps * args.duration))
        try:
            count = run_capture_loop(frames, relay, fps=args.fps)
        finally:
            relay.close()
        print(f"replayed {count} frames")
        return 0

    if args.command == "receive":
        sinks = []
        if args.out:
            sinks.append(JSONFileEmitter(args.out))

        def handle(frame):
            for sink in sinks:
                sink.send(frame)
            print(f"{frame.timestamp:8.3f} tracking={frame.tracking} "
                  f"head={tuple(round(v, 2) for v in frame.head)} "
                  f"top={sorted(frame.blendshapes.items(), key=lambda kv: -kv[1])[:5]}")
        if args.protocol == "text":
            from .text_protocol import CMD_START, decode
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", args.pc_port or args.port))
            sock.sendto(CMD_START.encode(), (args.host, args.port))
            sock.settimeout(args.duration)
            count = 0
            end = time.time() + args.duration
            while time.time() < end:
                try:
                    data, _ = sock.recvfrom(8192)
                except socket.timeout:
                    break
                frame = decode(data.decode("utf-8"))
                if frame:
                    handle(frame)
                    count += 1
            print(f"received {count} frames")
            return 0
        receiver = FMV3Receiver(args.host, port=args.port, pc_port=args.pc_port,
                                transport=args.transport,
                                mode=MODE_FIXED52 if args.mode == "fixed52" else MODE_VARIABLE)
        receiver.run(handle, duration=args.duration)
        for sink in sinks:
            sink.close()
        print(f"received {receiver.frames_received} frames")
        return 0

    if args.command == "serve":
        sender = FMV3Sender(udp_port=args.udp_port, tcp_port=args.tcp_port, fps=args.fps,
                            mode=MODE_FIXED52 if args.mode == "fixed52" else MODE_VARIABLE)
        sender.start()
        relay = Relay([FMV3Sink(sender), ConsoleEmitter(every=2.0)])
        if args.web:
            from .web_server import WebViewer
            relay.add(WebViewer(port=args.web))
        if args.text:
            relay.add(TextUDPEmitter(args.text_host, args.text_port))
        if args.vmc_host:
            relay.add(VMCEmitter(args.vmc_host, args.vmc_port))
        print(f"FacePipe serving on UDP {args.udp_port} / TCP {args.tcp_port} "
            f"(mode={args.mode}, fps={args.fps}). Waiting for a receiver to HELLO...")
        try:
            run_capture_loop(source_for(args), relay, fps=args.fps)
        except KeyboardInterrupt:
            pass
        finally:
            relay.close()
            sender.stop()
        return 0

    return 1


def itertools_islice(iterable, n):
    import itertools
    return itertools.islice(iterable, n)


if __name__ == "__main__":
    raise SystemExit(main())
