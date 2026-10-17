"""Run the Godot VMC demo against FacePipe's actual OSC emitter."""
import subprocess
import sys
import time
from pathlib import Path

from facepipe.emitters import VMCEmitter
from facepipe.frame import Frame

godot = Path(sys.argv[1])
process = subprocess.Popen(
    [str(godot), "--headless", "--path", str(Path("addons/godot").resolve()),
     "--script", "verify_vmc.gd"], stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True)
emitter = VMCEmitter("127.0.0.1", 51170, send_head=True)
try:
    startup = []
    for _ in range(20):
        line = process.stdout.readline()
        startup.append(line)
        if "VMC_BIND=true" in line:
            break
    else:
        raise RuntimeError("Godot receiver did not bind")
    for _ in range(40):
        emitter.send(Frame(blendshapes={"jawOpen": 0.5},
                           head=(0, 0, 0, 0.25, 0, 0)))
        time.sleep(0.05)
    output, _ = process.communicate(timeout=5)
    print(("".join(startup) + output).strip())
    if process.returncode != 0 or "FACEPIPE_GODOT_VMC_OK" not in output:
        raise RuntimeError("Godot did not consume the VMC frame")
finally:
    emitter.close()
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=2)
