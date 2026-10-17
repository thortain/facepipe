MediaPipe Tasks Vision 1.1.1 is bundled here from the official npm package
`@mediapipe/tasks-vision@1.1.1` (npm integrity
`sha512-jwntgT5tzDrKOkqg6xNDNpRcTUnGvmylZE5DFnzPXossiWOIDdZX+C81LI75hlXhsG58YZW+lGzcmjH1qrQE/Q==`).
It is licensed under Apache-2.0; see APACHE-2.0.txt. Only the JavaScript module
and SIMD/non-SIMD browser WebAssembly loaders and binaries are included.

The face landmarker task model at ../face_landmarker.task was fetched from:
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.
The MediaPipe maintainer states that its source and models are Apache-2.0
unless otherwise noted:
https://github.com/google-ai-edge/mediapipe/issues/6355
APACHE-2.0.txt accompanies these bundled assets.

The browser camera client runs inference on the device. FacePipe sends only
blendshapes, pose, and optional landmark coordinates to the private bridge.
