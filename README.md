# FacePipe

**Open-source facial motion capture that speaks the iFacialMocap protocols — from any camera, not just an iPhone.**

iFacialMocap is a $7.99 iOS app that turns a FaceID-capable iPhone into a facial
motion capture device and streams 52 ARKit blendshapes + head/eye pose to a PC,
which then drives Unity, Blender, Maya, 3ds Max, Unreal, VRChat, VTube Studio,
Warudo, VSeeFace and the whole VMC/VRM ecosystem.

FacePipe reimplements that pipeline **as a PC-side capture + protocol bridge**, so
an ordinary webcam, a video file, or a browser on a phone can feed the exact same
toolchain.

```
   webcam / video / browser  ──►  MediaPipe (52 ARKit blendshapes + pose)
                                        │
                                        ▼
                                   FacePipe core
                                        │
        ┌──────────────┬───────────────┼────────────────┬──────────────┐
        ▼              ▼               ▼                ▼              ▼
   FMV3 (binary)   iFacialMocap     VMC / OSC      NDJSON        live web viewer
   UDP + TCP       text v1/v2       (VRM avatars)  record/replay  http://localhost:8080
```

## Quick start

```bash
pip install mediapipe opencv-python numpy pillow

# 1. see the protocol tables
python -m facepipe.cli info --sample

# 2. serve a synthetic stream (no camera needed) and connect a test receiver
python -m facepipe.cli serve --source synthetic --fps 30 --duration 10
python samples/listener.py --fmv3 --port 49983 --pc-port 49983   # in another terminal

# 3. capture from a webcam and record it
python -m facepipe.cli record --source 0 --out session.ndjson

# 4. replay a recording into a Unity/Blender plugin that expects iFacialMocap
python -m facepipe.cli replay --in session.ndjson --emit text-udp --host 127.0.0.1 --port 49983

# 5. watch the stream in the browser
python -m facepipe.cli serve --source 0 --web 8080
```

Tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## What is implemented

| Module | What it does |
|---|---|
| `facepipe/blendshapes.py` | Canonical ARKit 52 table, both spellings (`eyeBlinkLeft` / `eyeBlink_L`), FMV3 fixed52 index order, name normalisation |
| `facepipe/text_protocol.py` | iFacialMocap v1/v2 text protocol: handshake commands, encoder, forgiving decoder |
| `facepipe/fmv3.py` | Face Motion v3 (contract revision 6): header, HELLO/SCHEMA/SCHEMA_ACK/FRAME/PING/PONG/STOP/ERROR, UDP fragmentation, sender **and** receiver, TCP support |
| `facepipe/capture.py` | MediaPipe FaceLandmarker → 52 blendshapes + head pose + iris-based eye pose, smoothing, webcam/video/image sources |
| `facepipe/emitters.py` | UDP/TCP text emitters, VMC/OSC emitter, NDJSON recorder, console, `Relay` fan-out |
| `facepipe/osc.py` | Minimal OSC packet writer + ARKit→VRM blendshape mapping |
| `facepipe/recorder.py` | NDJSON recording, replay, statistics |
| `facepipe/calibration.py` | Neutral-pose capture, per-blendshape gain/offset profiles |
| `facepipe/web_server.py` | Live browser viewer (landmark mesh + blendshape bars) |
| `facepipe/cli.py` | `serve`, `record`, `replay`, `receive`, `calibrate`, `info` |

## Protocol notes (reverse-engineered + documented)

### Ports

| Direction | UDP | TCP |
|---|---|---|
| iPhone app listens | 49983 | 49984 |
| PC receiver listens | 49983 | 49984 |
| Legacy TCP frame stream | — | 49986 |
| Recorded ("baked") animation | — | 49987 |

### Legacy text protocol (v1/v2)

Start streaming:

```
iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719        -> iOS:49983
iFacialMocap_UDPTCP_sahuasouryya9218sauhuiayeta91555dy3719 -> iOS:49983 (TCP on 49986)
iFacialMocap_lookForward                                   -> calibration
iFacialMocap_bakeRecordedAnimation_start                   -> recorded playback
```

Frame format:

```
mouthSmile_R-0|eyeLookOut_L-0|...|=head#rx,ry,rz,px,py,pz|rightEye#rx,ry,rz|leftEye#rx,ry,rz|
```

* values are integer percent 0..100 (v2 uses `&` instead of `-` so negatives are legal)
* angles are **degrees**, positions metres
* TCP frames are terminated with `___iFacialMocap`
* real streams contain stray `?`, empty tokens and malformed tails — the decoder tolerates all of it (see `tests/test_protocol_text.py`)

### Face Motion v3 (FMV3, revision 6)

Binary, little-endian, 40-byte header + payload:

```
magic "FMV3" | type | flags | header_size | session_id | schema_id | sequence |
source_token | total_payload_length | part_index | part_count | chunk_length
```

* **HELLO** (PC → iOS): requested fps, max UDP size, revision 6, mode (0 variable / 1 fixed52)
* **SCHEMA** (iOS → PC): start info + descriptor + (variable mode only) app name, profile, blendshape names
* **SCHEMA_ACK** (PC → iOS, UDP only) — frames do not start until it is sent
* **FRAME**: N blendshape ints (i16 or i32, percent, may be negative or >100) + 12 float32 (head rot/pos, right eye, left eye)
* **PING/PONG** every 3 s; iOS ends the session after `lease_ms` (10 s) of silence
* UDP payloads are fragmented at 536 bytes for SCHEMA and `max_udp_size - 40` for FRAME

Fixed52 mode sends exactly the 52 ARKit blendshapes in alphabetical order of the
ARKit identifier, always as Int32 — a fixed 296-byte FRAME. This is the mode
FacePipe defaults to because it is the most portable.

## Why this exists

* iFacialMocap requires an iPhone with FaceID. FacePipe works with any camera.
* The official PC bridge is closed-source, Windows/macOS only, and cannot be
  extended. FacePipe is a library you can import.
* One capture can be fanned out to Unity, Blender, Unreal, VMC/OSC and a file at
  the same time.
* Recordings are plain NDJSON — easy to inspect, diff, and re-drive.

## Roadmap

- [x] FMV3 sender + receiver (UDP + TCP)
- [x] Legacy text protocol sender + receiver
- [x] MediaPipe capture, smoothing, calibration
- [x] VMC/OSC output
- [x] NDJSON record / replay
- [x] Browser viewer
- [ ] FBX export (iFacialMocap's "export by email" feature)
- [ ] Blender / Unity / Unreal plugins that consume FacePipe directly
- [ ] Multi-client relay with device discovery
- [ ] ONNX/other face models, per-user training
- [ ] macOS/iOS native client

## License

MIT. The protocol itself is documented publicly by DevelopW LLC at
<https://www.ifacialmocap.com/for-developer/> and in the reference receiver at
<https://github.com/emoto-yasushi/iFacialMocap_Facemotion3d_udp-tcp_v3>.
