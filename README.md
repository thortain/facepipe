# FacePipe

**Facial motion capture that speaks the iFacialMocap protocols — from a webcam, video, or browser camera.**

iFacialMocap turns a compatible iPhone into a facial
motion capture device and streams 52 ARKit blendshapes + head/eye pose to a PC,
which then drives Unity, Blender, Maya, 3ds Max, Unreal, VRChat, VTube Studio,
Warudo, VSeeFace and the whole VMC/VRM ecosystem.

FacePipe reimplements that pipeline **as a PC-side capture + protocol bridge**, so
an ordinary webcam, a video file, or a browser on a phone can feed the exact same
toolchain.

```
   webcam / video / browser  ──►  MediaPipe (51 tracked shapes + pose)
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
python -m pip install -e .

# 1. see the protocol tables
python -m facepipe.cli info --sample

# 2. serve a synthetic stream (no camera needed) and connect a test receiver
python -m facepipe.cli serve --source synthetic --fps 30 --duration 10
python samples/listener.py --fmv3 --port 49983 --pc-port 49985   # in another terminal

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

## Export an animated FBX

Blender 3.6 or newer is required for the exporter. The result is a **motion
carrier**: a small placeholder mesh with all 52 ARKit shape keys, plus animated
Head, Eye.L and Eye.R bones. Retarget those curves to your own avatar; this is
not an avatar mesh or an iFacialMocap email attachment clone.

```bash
facepipe export-fbx --in samples/demo.ndjson --out demo.fbx --fps 60
# If Blender is not on PATH, add --blender /path/to/blender
```

The original blendshape coefficients, including negative or above-one values,
are retained. Head position follows the recording's metres convention; the
MediaPipe source estimates that position rather than measuring physical depth.

## Drive Blender, Unity, or VMC directly

Install `addons/blender/facepipe_live.py` using Blender's Add-ons **Install from
Disk** action. Choose a mesh with ARKit shape keys in the FacePipe panel, then
press **Start FacePipe**. The optional head and eye object fields drive pose.
The addon listens only on `127.0.0.1` by default.

Copy `addons/unity/FacePipeReceiver.cs` into a Unity project's `Assets` folder,
attach it to a GameObject, and assign an ARKit-compatible SkinnedMeshRenderer.
The optional Transform fields receive head and eye pose. Unity's blendshape
weights are percentages, so the receiver passes the wire values through.
Run a separate UDP port per application if Blender and Unity are open together.

```bash
facepipe serve --source 0 --text-target 127.0.0.1:49985 --text-version 2
```

For a VMC Performer accepting face-only Assistant data, use
`--vmc-host 127.0.0.1 --vmc-port 39540`. FacePipe sends named ARKit
expressions using `/VMC/Ext/Blend/Val` and `/VMC/Ext/Blend/Apply`, suitable
for a PerfectSync-compatible avatar. A receiver that accepts face-only VMC
directly can instead listen on port 39539. Add `--vmc-head` to send the
estimated Head bone position and rotation; check the avatar's coordinate
conventions before using that pose. OSC bundles stay below 1400 bytes.

`addons/godot/FacePipeVMC.gd` is a Godot 4 VMC consumer. Attach it to a Node,
assign an ARKit-named MeshInstance3D, and use the same `--vmc-host` command.
The Godot project includes a headless loopback check for its VMC/OSC path.

## Browser camera capture

Browser inference runs on the camera device using the bundled MediaPipe model
and WebAssembly. Video pixels stay in that browser; FacePipe receives
blendshapes, pose, and landmark coordinates. On the **same computer**, run:

The bundled model does not report `tongueOut`; FacePipe fills that one ARKit
channel with zero when emitting a 52-shape stream or FBX.

```bash
facepipe serve --source browser --web 8080
```

Open `http://127.0.0.1:8080/capture`, use **Check model** to verify local model
loading, then **Start camera** and grant camera access. The viewer is at `/`.
The preview alone is mirrored; inference uses the original image so ARKit
left/right names follow the subject's face.

For a **phone on a private LAN or VPN**, bind to that interface's numeric
private IPv4 address. The browser requires a trusted HTTPS certificate for
camera access. The certificate must match the name or IP used in the phone's
URL. Set a long pairing token in the `FACEPIPE_CAPTURE_TOKEN` environment
variable without putting its value in shell history or a command argument;
enter the same token in the phone page. FacePipe requires both TLS files and
the token whenever web access binds beyond loopback:

```bash
facepipe serve --source browser --bind 192.168.1.20 --web 8443 \
  --tls-cert /path/to/trusted-cert.pem --tls-key /path/to/private-key.pem \
  --discover
```

Then open `https://<certificate-name>:8443/capture` on the phone. A private
VPN name with a matching trusted certificate is also suitable. An untrusted
self-signed browser warning does not meet the camera secure-context rule.
FacePipe does not create firewall, NAT, tunnel, DNS, or public reverse-proxy
rules.

## Multi-client streaming and discovery

FMV3 now queues each receiver independently, keeps only the newest frames for
a slow receiver, and expires sessions that stop sending keep-alives. Up to 32
receivers can be active at once. Network listeners bind to loopback by
default. For another device, specify the exact private LAN/VPN IPv4 interface
with `--bind`; public and wildcard addresses are rejected.

When receiving from a phone, set `--bind` to the PC's exact private LAN/VPN
IPv4 address so the phone can reply to that interface:

```bash
facepipe receive --host 192.168.1.7 --bind 192.168.1.20 --protocol fmv3
```

Discovery is opt-in with `--discover`. It uses FacePipe's small UDP
request/response on port 49982, not mDNS. A client can probe one host or a
private subnet of at most 1024 addresses:

```bash
facepipe discover --host 127.0.0.1
facepipe discover --subnet 192.168.1.0/24
```

Only private-address requests receive a response. No public network route is
configured by FacePipe.

## Verified paths and current limits

On Windows, the FMV3 relay delivered live frames to two receivers and to a
receiver bound on the PC's private LAN interface. Discovery returned that
interface and service ports. Browser motion POSTs reached an FMV3 receiver;
Chrome loaded the bundled model; a Blender UDP frame changed a shape key;
Godot consumed standard VMC expression and Head messages; and an exported FBX
reimported in Blender with its shape and rig animation. The Unity script
compiled against Unity 2022's real engine assembly, but Unity could not run
the avatar scene without an editor license here.

A physical phone camera, trusted phone HTTPS pairing, and subjective avatar
motion quality have not been verified on this machine. The bundled MediaPipe
model reports 51 ARKit-style shapes; `tongueOut` is zero-filled in the 52-shape
wire and FBX formats. A native macOS/iOS client remains conditional on access
to a Mac with full Xcode.

## What is implemented

| Module | What it does |
|---|---|
| `facepipe/blendshapes.py` | Canonical ARKit 52 table, both spellings (`eyeBlinkLeft` / `eyeBlink_L`), FMV3 fixed52 index order, name normalisation |
| `facepipe/text_protocol.py` | iFacialMocap v1/v2 text protocol: handshake commands, encoder, forgiving decoder |
| `facepipe/fmv3.py` | Face Motion v3 (contract revision 6): header, HELLO/SCHEMA/SCHEMA_ACK/FRAME/PING/PONG/STOP/ERROR, UDP fragmentation, sender **and** receiver, TCP support |
| `facepipe/capture.py` | MediaPipe FaceLandmarker → 51 measured shapes plus a zero `tongueOut`, head pose and iris-based eye pose, webcam/video/image sources |
| `facepipe/emitters.py` | UDP/TCP text emitters, VMC/OSC emitter, NDJSON recorder, console, `Relay` fan-out |
| `facepipe/osc.py` | OSC packet writer with VMC-compatible message framing and UDP-sized bundles |
| `facepipe/recorder.py` | NDJSON recording, replay, statistics |
| `facepipe/calibration.py` | Neutral-pose capture, per-blendshape gain/offset profiles |
| `facepipe/web_server.py` | Private live viewer and validated browser motion ingestion |
| `facepipe/fbx_export.py` | Blender-backed binary FBX motion carrier export |
| `facepipe/discovery.py` | Opt-in private LAN/VPN service discovery |
| `facepipe/cli.py` | `serve`, `record`, `replay`, `receive`, `calibrate`, `info`, `export-fbx`, `discover` |

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
- [x] Blender-backed FBX motion carrier export
- [x] Blender addon and Unity receiver that consume FacePipe directly
- [x] Multi-client relay with opt-in private device discovery
- [x] Browser camera capture client using MediaPipe WebAssembly
- [x] Godot 4 VMC consumer
- [ ] Unreal consumer
- [ ] ONNX/other face models, per-user training
- [ ] macOS/iOS native client

## License

FacePipe's own source does not yet have an owner-selected redistribution
license. The bundled MediaPipe JavaScript, WebAssembly, and task model are
Apache-2.0; provenance and the license text are in
`src/facepipe/web_assets/vendor/`. The protocol itself is documented publicly by DevelopW LLC at
<https://www.ifacialmocap.com/for-developer/> and in the reference receiver at
<https://github.com/emoto-yasushi/iFacialMocap_Facemotion3d_udp-tcp_v3>.
