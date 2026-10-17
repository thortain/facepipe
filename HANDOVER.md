# HANDOVER — FacePipe

**Audience:** an AI coding agent (ChatGPT Codex) continuing this project.
**Version:** 0.1.0 · **License:** MIT · **Language:** Python 3.9+

---

## 1. TL;DR

iFacialMocap is a $7.99 iOS app that streams 52 ARKit facial blendshapes + head/eye pose
from an iPhone to a PC, which then drives Unity/Blender/Maya/Unreal/VRChat/VTube Studio.

**FacePipe** is an open-source, PC-side reimplementation of that pipeline: it captures a
face from **any camera** (webcam, video file, still image, or synthetic frames) using
MediaPipe, and re-broadcasts it in every dialect the iFacialMocap ecosystem already
understands.

It is a **sender and a receiver** of the iFacialMocap protocols, not a clone of the app.

```
webcam/video/image/synthetic ─► MediaPipe ─► Frame ─► Relay ─► FMV3 (UDP+TCP)
                                              │                ├► iFacialMocap text v1/v2
                                              │                ├► VMC / OSC (VRM avatars)
                                              │                ├► NDJSON recording
                                              │                └► browser viewer :8080
```

---

## 2. Environment

* Built and tested on macOS (Apple Silicon), **Python 3.9.6**.
* Installed deps: `mediapipe 1.1.1`, `opencv-contrib-python 5.0`, `numpy 2.0.2`, `pillow 11.3`.
* **No Xcode** on this machine (CommandLineTools only) → do not attempt a native iOS app.
* **No physical camera** on this machine (`ffmpeg -f avfoundation -list_devices true -i ""`
  shows only "Capture screen 0"). Use `--source synthetic`, an image, or a video file for
  testing. Webcam index `0` will fail here but works on a normal machine.
* The MediaPipe model (`face_landmarker.task`, ~3.7 MB) is auto-downloaded by
  `capture.ensure_model()`; it is gitignored.

Run everything from the repo root with `PYTHONPATH=src`.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests      # 17 tests, ~15 s
PYTHONPATH=src python3 -m facepipe.cli info --sample
PYTHONPATH=src python3 -m facepipe.cli serve --source synthetic --fps 30 --web 8080
```

---

## 3. Repo map

```
facepipe/
  README.md                 user-facing docs + protocol notes
  docs/research.md          full research report (ecosystem, competitors, protocol quirks)
  pyproject.toml            installable package, console script `facepipe`
  Makefile                  test / demo / record / replay / viewer
  src/facepipe/
    blendshapes.py      ARKit 52 tables, identifier vs rawValue spellings, fixed52 order
    frame.py            Frame dataclass (the internal currency)
    text_protocol.py    iFacialMocap v1/v2 text protocol (encode + forgiving decode)
    fmv3.py             Face Motion v3 rev 6: header, messages, fragmentation,
                        FMV3Sender (acts like the iPhone), FMV3Receiver (acts like the PC)
    capture.py          MediaPipe FaceLandmarker wrapper, smoothing, eye pose, sources
    emitters.py         TextUDPEmitter, TextTCPEmitter, VMCEmitter, JSONFileEmitter,
                        ConsoleEmitter, FMV3Sink, Relay, run_capture_loop
    osc.py              minimal OSC packet writer + ARKit -> VRM blendshape index map
    recorder.py         NDJSON load / replay / summary
    calibration.py      neutral capture + per-blendshape gain/offset profiles (JSON)
    web_server.py       stdlib HTTP viewer (landmark mesh + blendshape bars)
    cli.py              argparse CLI: serve | record | replay | receive | calibrate | info
  tests/
    test_protocol_text.py  text protocol round-trip + official sample frame
    test_fmv3.py           header, schema, frame, fragmentation
    test_loopback.py       real UDP + TCP sender<->receiver over localhost
  samples/
    listener.py          stand-in "Unity plugin": listens for text or FMV3 frames
    demo.ndjson          38-frame synthetic recording
```

---

## 4. Core data model

`src/facepipe/frame.py`

```python
@dataclass
class Frame:
    blendshapes: dict[str, float]      # keyed by ARKit identifier, e.g. "eyeBlinkLeft"
    head: tuple[float]*6               # (rx, ry, rz) degrees, (px, py, pz) metres
    right_eye: tuple[float]*3          # degrees
    left_eye: tuple[float]*3           # degrees
    tracking: bool
    timestamp: float
    source: str
    landmarks: list[tuple[float,float]] | None   # 478 normalized MediaPipe points
```

**Invariants — do not break these:**

1. Blendshape values are **floats in 0..1** internally. Wire format is integer percent
   (`value * 100`). Negative and >1 values are legal and must be preserved.
2. Angles are **degrees**, positions **metres**.
3. Internal blendshape keys are the **ARKit identifier** spelling (`eyeBlinkLeft`).
   The wire/text protocol uses the **rawValue** spelling (`eyeBlink_L`).
   Convert with `blendshapes.IDENTIFIER_TO_RAW` / `RAW_TO_IDENTIFIER`.
4. FMV3 fixed52 order = **alphabetical order of the ARKit identifier** (see
   `blendshapes.ARKIT_52`). Never sort at runtime.
5. MediaPipe emits 53 entries; **drop `_neutral`**.

---

## 5. Protocol cheat sheet

### Ports

| Side | UDP | TCP |
|---|---|---|
| iPhone app listens | 49983 | 49984 |
| PC receiver listens | 49983 | 49984 |
| Legacy TCP frame stream | — | 49986 |
| Recorded ("baked") animation | — | 49987 |
| VMC marionette / performer | 39539 / 39540 | — |

On a single machine the sender and receiver cannot both bind the same port — the tests
use `51083` (sender) and `51084` (receiver pc_port). Keep that pattern.

### Legacy text handshake

```
iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719          UDP 49983
iFacialMocap_UDPTCP_sahuasouryya9218sauhuiayeta91555dy3719   UDP 49983 -> TCP 49986
iFacialMocap_UDPTCPSTOP_sahuasouryya9218sauhuiayeta91555dy3719
iFacialMocap_lookForward                                     (calibration)
iFacialMocap_bakeRecordedAnimation_start                     (recorded playback)
```

Frame: `name-value|name-value|...|=head#rx,ry,rz,px,py,pz|rightEye#...|leftEye#...|`
v2 uses `&` instead of `-`. TCP frames end with `___iFacialMocap`.

### FMV3 (rev 6) header — 40 bytes, little-endian

```
struct "<4sBBHQIIIIHHI"
magic "FMV3" | message_type | flags | header_size=40 | session_id | schema_id |
sequence | source_token | total_payload_length | part_index | part_count | chunk_length
```

Message types: `1 HELLO, 2 SCHEMA, 3 SCHEMA_ACK, 4 FRAME, 5 GET_SCHEMA, 6 PING, 7 PONG,
8 STOP, 9 ERROR`.

* HELLO body `<HHIH`: requested_fps (1-60), max_udp_size (576-1200), revision 6, mode (0 variable / 1 fixed52)
* SCHEMA body: start info `<QHHII` (client_nonce, actual_fps, max_udp_size, lease_ms, revision)
  + descriptor `<HBBH` (mode, blend_encoding 1=i16/2=i32, schema_format_version=1, blend_count)
  + variable mode only: app (u16 len + utf8), profile (u16 len + utf8), then `blend_count` names
    each as (u8 len + utf8)
* FRAME body: `blend_count` ints (i16 or i32, percent) + 12 float32 = head(6) + rightEye(3) + leftEye(3)
* fixed52 FRAME is always **296 bytes total** (256-byte body)
* UDP fragmentation: SCHEMA capacity 536, FRAME capacity `max_udp_size - 40`; fragments may
  arrive out of order; `total_payload_length` is the **whole** payload, not the chunk
* PC must send SCHEMA_ACK (UDP only) before frames arrive, and PING every 3 s or the session
  dies after `lease_ms` (10 s)

Reference spec (public):
<https://github.com/emoto-yasushi/iFacialMocap_Facemotion3d_udp-tcp_v3> (`PROTOCOL_V3.md`)
and <https://www.ifacialmocap.com/for-developer/> for the text protocol.

---

## 6. Current status — what is verified working

| Feature | Verified by |
|---|---|
| Text protocol encode/decode incl. malformed official sample | `tests/test_protocol_text.py` |
| FMV3 header/schema/frame round-trip | `tests/test_fmv3.py` |
| UDP fragmentation + out-of-order reassembly | `tests/test_fmv3.py` |
| Sender↔receiver loopback, fixed52 and variable, UDP | `tests/test_loopback.py` |
| Sender↔receiver loopback, TCP | `tests/test_loopback.py` |
| MediaPipe capture from a still image (51 blendshapes, head pose, eye pose) | manual run |
| VMC/OSC bundle emission (`/face/1/<idx>`) | manual run |
| NDJSON record + replay into a UDP text listener | manual run |
| Browser viewer at `:8080` | manual run |

**17 tests pass.** No linting/formatting tooling is configured yet.

---

## 7. Known gaps and bugs

1. **`serve` does not implement a multi-client relay queue.** `FMV3Sender.push()` sends
   synchronously; there is no buffering or per-peer pacing.
2. **TCP sender manual-start path is incomplete.** The spec's "iOS connects to the PC"
   (manual start) is not implemented in `FMV3Sender._tcp_connection`.
3. **No lease/timeout enforcement on the sender side** (`last_seen` is tracked but never used).
4. **Head position units are approximate.** MediaPipe's transformation matrix is not in
   metres; we scale by 0.01. Documented as approximate. If you need real metres, derive it
   from a known inter-ocular distance.
5. **Eye pose is heuristic** (iris centre vs. nearby contour centroid, clamped to ±35°).
6. **`receive --protocol text`** does not implement the TCP or bake-record commands.
7. **No FBX export** — iFacialMocap's headline feature.
8. **No logging** — everything uses `print`.
9. **No packaging/entry-point test** — `pip install -e .` then `facepipe info` is untested.
10. **Python 3.9 compatibility must be preserved** (no `secrets.rand64`, no `match`,
    no `X | Y` annotations without `from __future__ import annotations`).

---

## 8. Prioritized task list

### P0 — correctness & robustness
- [ ] Add a `logging` module and replace `print` in library code (CLI may print).
- [ ] Sender-side lease: drop peers whose `last_seen` exceeds `lease_ms`.
- [ ] Validate FMV3 message fields per the spec's "Limits and validation" table
      (type range, body lengths, finite floats). Add tests for invalid input.
- [ ] Add a `queue`-based pacing loop in `FMV3Sender` so `serve` can drive many peers.
- [ ] Unit test for `calibration.Calibration.apply()` round-trip.

### P1 — parity with iFacialMocap
- [ ] **FBX export** from an NDJSON recording (52 shape keys, 60 FPS, head/eye bones).
      Suggested approach: write ASCII FBX directly (no external lib) or use `pyfbx`.
- [ ] `facepipe receive --protocol text --tcp` (port 49986, `___iFacialMocap` framing).
- [ ] `lookForward` calibration command support in the CLI.
- [ ] Blendshape remapping profile (like `LauraRozier/Config-IFacialMocap-Blend-Shapes`)
      so a custom avatar's shape names map to ARKit names.

### P2 — ecosystem
- [ ] Blender addon (Python, socket-based) that consumes FacePipe directly.
- [ ] Unity C# receiver script (mirror of `samples/listener.py`).
- [ ] Godot 4 VMC marionette demo (Godot is installed on this machine).
- [ ] Browser capture client (MediaPipe WASM) → WebSocket → FacePipe relay.

### P3 — polish
- [ ] `pip install -e .` + `facepipe` entry point test.
- [ ] CI (GitHub Actions): run tests on Python 3.9–3.12.
- [ ] Type checking with `mypy` / `ruff`.
- [ ] README GIF/demo.

---

## 9. Conventions

* Keep the code **stdlib-only** except for `mediapipe`, `opencv`, `numpy`, `pillow`.
* Every new protocol feature needs a test in `tests/`.
* Do not clamp blendshape values to 0..1 in the wire layer.
* Never change `ARKIT_52` order — it is the FMV3 fixed52 contract.
* New emitters must implement `send(frame)` and `close()` so they can be dropped into `Relay`.
* Ports in tests must not collide with the real 49983/49984 defaults.

---

## 10. Suggested first Codex prompt

> Work in `facepipe/`. Implement P0 item "sender-side lease + validation" in
> `src/facepipe/fmv3.py`: enforce the FMV3 rev-6 validation table (header fields, body
> lengths, finite floats), drop peers whose `last_seen` exceeds `lease_ms`, and add tests
> in `tests/test_fmv3.py` covering a malformed SCHEMA, a truncated FRAME, and a peer that
> stops PINGing. Run `PYTHONPATH=src python3 -m unittest discover -s tests` and make sure
> all tests pass. Do not change the public API.

---

## 11. Quick reference commands

```bash
# tests
PYTHONPATH=src python3 -m unittest discover -s tests

# protocol tables + official sample frame
PYTHONPATH=src python3 -m facepipe.cli info --sample

# serve synthetic frames as FMV3 and watch in a browser
PYTHONPATH=src python3 -m facepipe.cli serve --source synthetic --fps 30 --web 8080

# serve + also emit legacy text to a Unity-style plugin
PYTHONPATH=src python3 -m facepipe.cli serve --source synthetic --text --text-port 49983

# record and replay
PYTHONPATH=src python3 -m facepipe.cli record --source synthetic --out session.ndjson
PYTHONPATH=src python3 -m facepipe.cli replay --in session.ndjson --emit text-udp --port 49983

# connect to a real iPhone running iFacialMocap
PYTHONPATH=src python3 -m facepipe.cli receive --host 192.168.1.7 --protocol fmv3 --duration 10

# test receiver
PYTHONPATH=src python3 samples/listener.py --fmv3 --port 49983
```
