"""Run from the repo root with PYTHONPATH=src to check browser POST -> FMV3."""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

from facepipe.fmv3 import FMV3Receiver

base = "http://127.0.0.1:51160"
command = [sys.executable, "-m", "facepipe.cli", "serve", "--source", "browser",
           "--web", "51160", "--udp-port", "51161", "--tcp-port", "51162",
           "--duration", "4"]
process = subprocess.Popen(command, env=os.environ.copy(), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
captured = []
receiver = FMV3Receiver("127.0.0.1", port=51161, pc_port=51163, fps=30)
thread = threading.Thread(target=receiver.run, args=(captured.append,),
                          kwargs={"duration": 2.5}, daemon=True)
try:
    for _ in range(30):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError("browser bridge did not start")
    thread.start()
    time.sleep(0.25)
    for index in range(40):
        frame = {"tracking": True, "blend": {"jawOpen": index / 100.0},
                 "head": [1, 2, 3, 0, 0, 0],
                 "leftEye": [0, 0, 0], "rightEye": [0, 0, 0]}
        request = urllib.request.Request(
            base + "/api/frame", data=json.dumps(frame).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=1) as response:
            assert response.status == 204
        time.sleep(0.025)
    thread.join(timeout=3)
    assert len(captured) > 10, f"only {len(captured)} FMV3 frames received"
    assert captured[-1].blendshapes["jawOpen"] > 0.1
    print(f"BROWSER_POST_TO_FMV3_OK received={len(captured)}")
finally:
    receiver.stop()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=2)
    output = process.stdout.read()
    if process.returncode != 0:
        print(output)
        raise RuntimeError(f"FacePipe exited {process.returncode}")
