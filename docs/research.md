# Research notes: the iFacialMocap ecosystem

Compiled from the App Store listing, ifacialmocap.com (including the
"for-developer" page), the reference FMV3 receiver/simulator, and third-party
integrations on GitHub.

## 1. The product

| Item | Detail |
|---|---|
| App | iFacialMocap (DevelopW LLC, Japan) |
| App Store id | 1489470545 |
| Released | 2020-01-13 |
| Price | $7.99 (paid), plus a free ad-supported "iFacialMocapTr" (id 1520971310) |
| Rating | 3.38 / 5 on 58 ratings — low volume, mixed sentiment |
| Requirement | FaceID-capable device (iPhone X or later, A12+), iOS 14+ |
| Successor | FACEMOTION3D (id 1511435444), sold as a feature-tiered successor |
| PC bridge | "iFacialMocap to Software" v1.22, free, closed source, Windows/macOS |
| Webcam variant | "iFacialMocap Powered by NVIDIA Broadcast" (Microsoft Store, paid) |

What it does: ARKit face tracking on the phone → 52 blendshapes + head/eye pose
→ real-time stream to a PC → Unity / Blender / Maya / 3ds Max / Unreal, plus
FBX export and VRM avatar support.

## 2. Protocols

There are three generations in the wild:

**v1 (legacy text, UDP).** PC sends the magic string
`iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719` to the phone on UDP 49983;
the phone replies at ~60 FPS with a pipe-delimited text frame.

**v2 (text with `&` separator).** Same, with `|sendDataVersion=v2` appended to
the handshake. Introduced because Facemotion3d allows negative blendshape
values, which collide with the `-` delimiter.

**FMV3 (Face Motion v3, binary, contract revision 6).** Introduced for
iFacialMocap 1.5.3+, iFacialMocapTr 1.2.6+, Facemotion3d 1.4.6+. Ports 49983
(UDP) and 49984 (TCP). Header + typed messages, SCHEMA/ACK handshake, PING/lease
keep-alive, UDP fragmentation, two modes (variable names, or fixed52 ARKit order).

### Frame content (all generations)

* 52 ARKit blendshapes, integer percent (0-100 in v1/v2; negative and >100 legal in FMV3)
* head: euler XYZ in **degrees**, position XYZ in metres
* right eye and left eye: euler XYZ in degrees
* FMV3 additionally carries `tracking` and `playback` flags and a `source_token`

### Quirks worth knowing

* The official sample frame contains a stray `?` before `cheekSquint_R`, a
  dangling `|1|` token, and a malformed tail `34903,-1.6660284,-0.17520553`.
  Any real receiver must be forgiving.
* MediaPipe names the shapes with the ARKit *identifier* spelling
  (`eyeBlinkLeft`), iFacialMocap text uses the ARKit *rawValue* spelling
  (`eyeBlink_L`). FMV3 fixed52 uses identifiers; FMV3 variable mode uses rawValues.
* MediaPipe emits 53 entries including a `_neutral` placeholder that must be dropped.
* VRM/VMC uses a different 61-entry blendshape list; mapping is lossy
  (e.g. `browInnerUp` has no VRM slot).

## 3. Ecosystem / integration points

* **Official PC app** → Maya, Unity, Blender, 3ds Max, Unreal.
* **VMC protocol** (OSC over UDP 39539/39540) → VRM avatars in Unity/Unreal/Blender/Godot; used by Virtual Motion Capture, Waidayo, VSeeFace, MocapForAll, TDPT.
* **VRCFaceTracking** → VRChat face tracking via an iFacialMocap module.
* **VTube Studio** plugins (several) → Live2D VTubers.
* **Warudo**, **VRMocap**, **VMagicMirror**, **Luppet**, **HANA_APP**.
* Standalone relays exist because iFacialMocap only serves one receiver at a time
  (`BUSY` error in FMV3) — e.g. `ifacialmocap_proxy`, `Azumi-Facialmocap-Relay`,
  `VTuberHub`.

## 4. Competitors

| Product | Capture | Open source | Notes |
|---|---|---|---|
| iFacialMocap | iPhone ARKit | no | $7.99, iPhone only |
| Facemotion3d | iPhone ARKit | no | feature-tiered pricing |
| Face Cap | iPhone ARKit | no | 4.29/5, 139 ratings |
| NVIDIA Broadcast | webcam | no | Windows only, paid |
| Phiz | webcam/browser (MediaPipe + Mocap4face) | yes | closest analogue; browser capture, WebSocket to Unity/Unreal, OSC app |
| VTube Studio built-in tracking | iPhone | partial | Live2D only |
| Rokoko Face / Faceware / Arbor | dedicated hardware / pro | no | expensive |

**Gap:** nobody offers a free, open, *protocol-compatible* capture source that
plugs into the existing iFacialMocap toolchain. That is the niche FacePipe fills.

## 5. Design decisions for FacePipe

1. **Implement both protocols.** FMV3 is the future; the text protocol is still
   what most third-party plugins speak. Supporting both makes FacePipe a drop-in.
2. **Default to fixed52 mode.** It is the most portable and needs no name table.
3. **Be a sender *and* a receiver.** A webcam can replace the phone, and a real
   iPhone stream can be re-broadcast to VMC/OSC or recorded.
4. **Relay by design.** The single-receiver limitation is the most complained
   about behaviour in the ecosystem.
5. **Recordings as NDJSON**, not a proprietary blob — replayable, greppable,
   convertible to FBX later.
6. **Calibration matters.** Webcam blendshape estimates are noisier and
   asymmetric than ARKit's; a neutral + gain profile is the standard fix.
