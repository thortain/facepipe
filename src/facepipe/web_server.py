"""A tiny HTTP viewer so you can *see* the stream without any 3D software.

    facepipe serve --source 0 --web 8080

then open http://localhost:8080
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .blendshapes import IDENTIFIERS
from .frame import Frame

VIEWER = """<!doctype html>
<html><head><meta charset="utf-8"><title>FacePipe viewer</title>
<style>
 body{font-family:system-ui;background:#111;color:#eee;margin:0;padding:16px}
 h1{font-size:18px;margin:0 0 8px}
 .grid{display:grid;grid-template-columns:320px 1fr;gap:16px}
 canvas{background:#1b1b1b;border:1px solid #333;border-radius:8px;width:100%}
 .bars{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
 .bar{background:#222;border-radius:6px;padding:6px}
 .bar b{display:block;font-size:11px;color:#999;font-weight:400}
 .bar span{display:block;height:6px;background:#3b8; border-radius:3px;margin-top:4px}
 .meta{color:#888;font-size:12px;margin-bottom:10px}
</style></head><body>
<h1>FacePipe live viewer</h1>
<div class="meta" id="meta">connecting...</div>
<div class="grid">
  <canvas id="mesh" width="320" height="320"></canvas>
  <div class="bars" id="bars"></div>
</div>
<script>
const canvas = document.getElementById('mesh');
const ctx = canvas.getContext('2d');
const bars = document.getElementById('bars');
const meta = document.getElementById('meta');
const NAMES = %NAMES%;
async function tick(){
  try{
    const r = await fetch('/frame.json');
    const f = await r.json();
    meta.textContent = 'frames: ' + (f.count||0) + '  tracking: ' + f.tracking +
       '  head: ' + f.head.map(v=>v.toFixed(1)).join(', ');
    ctx.clearRect(0,0,canvas.width,canvas.height);
    if (f.landmarks){
      ctx.fillStyle='#7de';
      f.landmarks.forEach(([x,y])=>{ ctx.fillRect(x*canvas.width-1, y*canvas.height-1, 2, 2); });
    }
    bars.innerHTML = NAMES.map(n => {
      const v = (f.blend[n]||0);
      return '<div class="bar"><b>'+n+'</b><span style="width:'+Math.max(0,Math.min(100,v*100))+'%"></span></div>';
    }).join('');
  }catch(e){ meta.textContent = 'no stream yet'; }
  setTimeout(tick, 100);
}
tick();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        server = self.server.server_ref
        if self.path == "/" or self.path == "/index.html":
            body = VIEWER.replace("%NAMES%", json.dumps(IDENTIFIERS)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/frame.json":
            body = json.dumps(server.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stream.ndjson":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            last = 0
            while True:
                if server.count > last:
                    for frame in server.frames[last:]:
                        self.wfile.write(json.dumps({
                            "t": frame.timestamp, "tracking": frame.tracking,
                            "head": list(frame.head), "blend": frame.blendshapes,
                        }).encode() + b"\n")
                    last = server.count
                time.sleep(0.2)
        else:
            self.send_response(404)
            self.end_headers()


class WebViewer:
    """An emitter that keeps the most recent frames available over HTTP."""

    def __init__(self, port: int = 8080, keep: int = 200) -> None:
        self.latest: Optional[Frame] = None
        self.frames = []
        self.keep = keep
        self.count = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self._server.server_ref = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"viewer at http://127.0.0.1:{port}")

    def send(self, frame: Frame) -> None:
        self.latest = frame
        self.frames.append(frame)
        if len(self.frames) > self.keep:
            self.frames = self.frames[-self.keep:]
        self.count += 1

    def snapshot(self) -> dict:
        if self.latest is None:
            return {"blend": {}, "head": [0, 0, 0, 0, 0, 0], "tracking": False,
                    "landmarks": None, "count": 0}
        return {
            "t": self.latest.timestamp,
            "tracking": self.latest.tracking,
            "head": list(self.latest.head),
            "blend": self.latest.blendshapes,
            "landmarks": self.latest.landmarks,
            "count": self.count,
        }

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
