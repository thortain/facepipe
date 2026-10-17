"""Run with Blender --background --factory-startup --python this_file.py."""
import importlib.util
import socket
from pathlib import Path

import bpy

path = Path(__file__).resolve().parents[1] / "addons" / "blender" / "facepipe_live.py"
spec = importlib.util.spec_from_file_location("facepipe_live", path)
addon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(addon)
addon.register()
try:
    bpy.ops.mesh.primitive_cube_add()
    mesh = bpy.context.object
    mesh.shape_key_add(name="Basis")
    mesh.shape_key_add(name="eyeBlinkLeft")
    mesh.shape_key_add(name="mouthSmile_R")
    scene = bpy.context.scene
    scene.facepipe_mesh = mesh
    scene.facepipe_bind = "127.0.0.1"
    scene.facepipe_port = 51150
    assert bpy.ops.facepipe.start() == {"FINISHED"}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(b"eyeBlink_L&67|mouthSmile_R&42|head#0,0,0,0,0,0|",
                      ("127.0.0.1", 51150))
    addon._tick()
    assert abs(mesh.data.shape_keys.key_blocks["eyeBlinkLeft"].value - 0.67) < 0.001
    assert abs(mesh.data.shape_keys.key_blocks["mouthSmile_R"].value - 0.42) < 0.001
    assert bpy.ops.facepipe.stop() == {"FINISHED"}
    print("FACEPIPE_BLENDER_ADDON_UDP_OK")
finally:
    addon.unregister()
