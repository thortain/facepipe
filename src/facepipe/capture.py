"""Face capture backends.

The default backend is MediaPipe's FaceLandmarker, which outputs the 52 ARKit
blendshapes plus a 4x4 facial transformation matrix. That means FacePipe can
produce an iFacialMocap-compatible stream from an ordinary webcam, a video
file, or a screen capture - no iPhone required.
"""
from __future__ import annotations

import math
import time
from typing import Iterable, Iterator, Optional

import numpy as np

from .blendshapes import IDENTIFIERS
from .frame import Frame

try:  # pragma: no cover - optional heavy dependency
    import cv2
    from mediapipe import Image as MPImage
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _MEDIAPIPE_AVAILABLE = True
except Exception:  # pragma: no cover
    _MEDIAPIPE_AVAILABLE = False
    _SRGB = None
else:
    import mediapipe as _mp
    _SRGB = _mp.ImageFormat.SRGB

DEFAULT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

# MediaPipe 478-landmark iris indices (subject's left eye first).
LEFT_IRIS = list(range(468, 473))
RIGHT_IRIS = list(range(473, 478))


def _euler_xyz(matrix: np.ndarray):
    """Extract (rx, ry, rz) in degrees from a 4x4 transformation matrix."""
    r = matrix[:3, :3]
    sy = -r[2, 0]
    sy = max(-1.0, min(1.0, sy))
    pitch = math.asin(sy)
    roll = math.atan2(r[2, 1], r[2, 2])
    yaw = math.atan2(r[1, 0], r[0, 0])
    return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


def _eye_pose(landmarks, iris_idx):
    iris = [landmarks[i] for i in iris_idx]
    cx = sum(p.x for p in iris) / len(iris)
    cy = sum(p.y for p in iris) / len(iris)
    # the eyelid contour is the set of landmarks close to the iris
    nearby = [p for p in landmarks if (p.x - cx) ** 2 + (p.y - cy) ** 2 < 0.025 ** 2]
    if not nearby:
        return (0.0, 0.0, 0.0)
    ex = sum(p.x for p in nearby) / len(nearby)
    ey = sum(p.y for p in nearby) / len(nearby)
    dx = cx - ex
    dy = cy - ey
    span = 0.02  # typical iris travel before the gaze hits the edge of the eye
    yaw = max(-35.0, min(35.0, math.degrees(math.atan2(dx, span))))
    pitch = max(-35.0, min(35.0, -math.degrees(math.atan2(dy, span))))
    return (yaw, pitch, 0.0)


class Smoother:
    """Exponential smoothing so blendshape values do not flicker frame to frame."""

    def __init__(self, alpha: float = 0.35) -> None:
        self.alpha = alpha
        self.state = {}

    def update(self, values: dict) -> dict:
        out = {}
        for key, value in values.items():
            previous = self.state.get(key)
            if previous is None:
                out[key] = value
            else:
                out[key] = previous + self.alpha * (value - previous)
            self.state[key] = out[key]
        return out


class MediaPipeFaceCapture:
    def __init__(self, model_path: str = "face_landmarker.task", num_faces: int = 1,
                 smoothing: float = 0.35) -> None:
        if not _MEDIAPIPE_AVAILABLE:
            raise RuntimeError("mediapipe is not installed: pip install mediapipe")
        model_path = ensure_model(model_path)
        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=num_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self.landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        self.smoother = Smoother(smoothing)
        self._t0 = time.monotonic()

    def process(self, rgb: np.ndarray) -> Frame:
        mp_image = MPImage(image_format=_SRGB, data=rgb)
        timestamp_ms = int((time.monotonic() - self._t0) * 1000)
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
        if not result.face_blendshapes:
            return Frame(tracking=False, timestamp=time.time())
        blend = {}
        for entry in result.face_blendshapes[0]:
            if entry.category_name == "_neutral":
                continue
            blend[entry.category_name] = float(entry.score)
        blend = self.smoother.update(blend)
        head = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        if result.facial_transformation_matrixes:
            matrix = result.facial_transformation_matrixes[0]
            rx, ry, rz = _euler_xyz(matrix)
            tx, ty, tz = matrix[0, 3], matrix[1, 3], matrix[2, 3]
            head = (float(rx), float(ry), float(rz),
                    float(tx) * 0.01, float(ty) * 0.01, float(tz) * 0.01)
        left_eye = right_eye = (0.0, 0.0, 0.0)
        landmarks = result.face_landmarks[0]
        if len(landmarks) >= 478:
            left_eye = _eye_pose(landmarks, LEFT_IRIS)
            right_eye = _eye_pose(landmarks, RIGHT_IRIS)
        landmarks = [(float(p.x), float(p.y)) for p in result.face_landmarks[0]]
        return Frame(blendshapes=blend, head=head, right_eye=right_eye,
                     left_eye=left_eye, tracking=True, timestamp=time.time(),
                     source="mediapipe", landmarks=landmarks)

    def frames(self, source: str, fps: int = 30, max_frames: Optional[int] = None) -> Iterator[Frame]:
        """Yield frames from a webcam index (int) or a video file path."""
        capture = cv2.VideoCapture(source)
        if not capture.is_open():
            raise RuntimeError(f"could not open video source: {source}")
        count = 0
        try:
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                yield self.process(rgb)
                count += 1
                if max_frames and count >= max_frames:
                    break
        finally:
            capture.close()



def synthetic_frames(fps: int = 30, duration: float = 10.0) -> Iterator[Frame]:
    """A deterministic animated face - useful for testing the pipeline without a camera."""
    interval = 1.0 / fps
    now = time.time()
    end = now + duration
    i = 0
    while now < end:
        t = i / fps
        blend = {
            "jawOpen": 0.5 + 0.5 * math.sin(t * 2.0),
            "mouthSmileLeft": 0.4 + 0.4 * math.sin(t * 1.3),
            "mouthSmileRight": 0.4 + 0.4 * math.sin(t * 1.3),
            "eyeBlinkLeft": 0.5 + 0.5 * math.sin(t * 0.7),
            "eyeBlinkRight": 0.5 + 0.5 * math.sin(t * 0.7),
            "browInnerUp": 0.3 + 0.3 * math.sin(t * 0.9),
        }
        yield Frame(blendshapes=blend,
                    head=(10.0 * math.sin(t), 5.0 * math.cos(t), 3.0 * math.sin(t * 0.5), 0, 0, 0),
                    right_eye=(20.0 * math.sin(t * 1.1), 0.0, 0.0),
                    left_eye=(20.0 * math.sin(t * 1.1), 0.0, 0.0),
                    tracking=True, timestamp=time.time(), source="synthetic")
        i += 1
        now = time.time()
        time.sleep(interval)


def ensure_model(path: str = "face_landmarker.task") -> str:
    """Download the MediaPipe face landmarker model if it is not already present."""
    import os
    import urllib.request
    if os.path.exists(path):
        return path
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    print(f"downloading face landmark model to {path} ...")
    urllib.request.urlretrieve(DEFAULT_MODEL_URL, path)
    return path


def image_frame(path: str, capture: Optional[MediaPipeFaceCapture] = None) -> Frame:
    from PIL import Image
    capture = capture or MediaPipeFaceCapture()
    image = Image.open(path).convert("RGB")
    return capture.process(np.asarray(image))


def image_frames(path: str, capture: MediaPipeFaceCapture, fps: int = 30,
                 duration: float = 5.0) -> Iterator[Frame]:
    """Feed a still image through the pipeline for `duration` seconds."""
    frame = image_frame(path, capture)
    for _ in range(max(1, int(fps * duration))):
        yield frame
