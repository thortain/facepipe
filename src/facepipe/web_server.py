"""Private live viewer and browser-camera motion bridge."""
from __future__ import annotations

import hmac
import json
import math
import ssl
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from .blendshapes import normalize_name
from .frame import Frame
from .network import require_private_bind

ASSETS = Path(__file__).with_name("web_assets")
CONTENT_TYPES = {".html": "text/html; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8",
                 ".mjs": "text/javascript; charset=utf-8",
                 ".wasm": "application/wasm", ".task": "application/octet-stream"}


def _numbers(value, count: int, limit: float = 1000.0):
    if not isinstance(value, list) or len(value) != count:
        raise ValueError("invalid pose")
    result = tuple(float(item) for item in value)
    if any(not math.isfinite(item) or abs(item) > limit for item in result):
        raise ValueError("non-finite or out-of-range pose")
    return result


def browser_frame(payload: dict) -> Frame:
    """Validate and normalize one browser-produced motion frame."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tracking"), bool):
        raise ValueError("invalid frame")
    values = payload.get("blend")
    if not isinstance(values, dict) or len(values) > 53:
        raise ValueError("invalid blendshapes")
    blend = {}
    for name, value in values.items():
        if name == "_neutral":
            continue
        canonical = normalize_name(name)
        score = float(value)
        if not math.isfinite(score) or abs(score) > 1000:
            raise ValueError("non-finite or out-of-range blendshape")
        blend[canonical] = score
    landmarks = payload.get("landmarks")
    if landmarks is not None:
        if not isinstance(landmarks, list) or len(landmarks) > 478:
            raise ValueError("invalid landmarks")
        landmarks = [_numbers(item, 2, 2.0) for item in landmarks]
    return Frame(blendshapes=blend, head=_numbers(payload.get("head"), 6),
                 right_eye=_numbers(payload.get("rightEye"), 3),
                 left_eye=_numbers(payload.get("leftEye"), 3),
                 tracking=payload["tracking"], timestamp=time.time(),
                 source="browser", landmarks=landmarks)


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Never log pairing tokens or facial data.

    @property
    def viewer(self):
        return self.server.viewer

    def _authorized(self) -> bool:
        token = self.viewer.token
        return token is None or hmac.compare_digest(
            self.headers.get("X-FacePipe-Token", ""), token)

    def _reply(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._reply(200, b"ok")
            return
        if path == "/frame.json":
            if not self._authorized():
                self._reply(403, b"pairing token required")
                return
            body = json.dumps(self.viewer.snapshot(), separators=(",", ":")).encode("utf-8")
            self._reply(200, body, "application/json")
            return
        if path in ("/", "/index.html"):
            path = "/assets/viewer.html"
        elif path == "/capture":
            path = "/assets/capture.html"
        if path.startswith("/assets/"):
            relative = path[len("/assets/"):]
            candidate = (ASSETS / relative).resolve()
            if not candidate.is_relative_to(ASSETS.resolve()) or not candidate.is_file():
                self._reply(404, b"not found")
                return
            content_type = CONTENT_TYPES.get(candidate.suffix)
            if content_type is None:
                self._reply(404, b"not found")
                return
            self._reply(200, candidate.read_bytes(), content_type)
            return
        self._reply(404, b"not found")

    def do_POST(self):
        if urlsplit(self.path).path != "/api/frame" or self.viewer.on_browser_frame is None:
            self._reply(404, b"not found")
            return
        if not self._authorized():
            self._reply(403, b"pairing token required")
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._reply(415, b"JSON required")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = 0
        if not 1 <= length <= 65536:
            self._reply(413, b"frame too large")
            return
        try:
            frame = browser_frame(json.loads(self.rfile.read(length)))
        except (ValueError, TypeError, UnicodeDecodeError, OverflowError):
            self._reply(400, b"invalid frame")
            return
        self.viewer.on_browser_frame(frame)
        self._reply(204)


class WebViewer:
    """An emitter that displays frames and optionally ingests browser capture."""

    def __init__(self, port: int = 8080, keep: int = 200, *,
                 bind_host: str = "127.0.0.1", token: Optional[str] = None,
                 tls_cert: Optional[str] = None, tls_key: Optional[str] = None,
                 on_browser_frame: Optional[Callable[[Frame], None]] = None) -> None:
        self.bind_host = require_private_bind(bind_host)
        if (tls_cert is None) != (tls_key is None):
            raise ValueError("both TLS certificate and key are required")
        if self.bind_host != "127.0.0.1" and (not token or not tls_cert):
            raise ValueError("private LAN web access requires FACEPIPE_CAPTURE_TOKEN and TLS")
        self.token = token
        self.on_browser_frame = on_browser_frame
        self.latest: Optional[Frame] = None
        self.frames = deque(maxlen=keep)
        self.count = 0
        self._lock = threading.Lock()
        context = None
        if tls_cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(tls_cert, tls_key)
        self._server = _HTTPServer((bind_host, port), _Handler)
        self._server.viewer = self
        if context:
            try:
                self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
            except Exception:
                self._server.server_close()
                raise
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        scheme = "https" if tls_cert else "http"
        print(f"viewer at {scheme}://{bind_host}:{port}")

    def send(self, frame: Frame) -> None:
        with self._lock:
            self.latest = frame
            self.frames.append(frame)
            self.count += 1

    def snapshot(self) -> dict:
        with self._lock:
            frame, count = self.latest, self.count
        if frame is None:
            return {"blend": {}, "head": [0, 0, 0, 0, 0, 0],
                    "tracking": False, "landmarks": None, "count": 0}
        return {"t": frame.timestamp, "tracking": frame.tracking,
                "head": list(frame.head), "blend": frame.blendshapes,
                "landmarks": frame.landmarks, "count": count}

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
