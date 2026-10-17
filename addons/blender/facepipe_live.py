"""Blender addon: drive ARKit shape keys from FacePipe legacy text UDP."""
bl_info = {
    "name": "FacePipe Live",
    "author": "FacePipe contributors",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > FacePipe",
    "description": "Receive FacePipe facial motion on a private UDP address",
    "category": "Animation",
}

import ipaddress
import math
import socket

import bpy
from bpy.props import IntProperty, PointerProperty, StringProperty

_socket = None
_running = False


def _canonical(name):
    if name.endswith("_L"):
        return name[:-2] + "Left"
    if name.endswith("_R"):
        return name[:-2] + "Right"
    return name


def parse_frame(text):
    """Decode v1/v2 FacePipe text into blendshapes and pose components."""
    values = {}
    poses = {}
    for part in text.replace("___iFacialMocap", "").split("|"):
        part = part.strip().lstrip("=")
        if not part:
            continue
        if "#" in part:
            name, numbers = part.split("#", 1)
            try:
                poses[name.lower()] = tuple(float(item) for item in numbers.split(","))
            except ValueError:
                continue
            continue
        separator = "&" if "&" in part else "-"
        if separator not in part:
            continue
        name, number = part.split(separator, 1)
        try:
            values[_canonical(name)] = float(number) / 100.0
        except ValueError:
            continue
    return values, poses


def apply_frame(scene, text):
    mesh = scene.facepipe_mesh
    if mesh is None or mesh.type != "MESH" or mesh.data.shape_keys is None:
        return 0
    values, poses = parse_frame(text)
    keys = mesh.data.shape_keys.key_blocks
    applied = 0
    for name, value in values.items():
        key = keys.get(name)
        if key is None and name.endswith("Left"):
            key = keys.get(name[:-4] + "_L")
        elif key is None and name.endswith("Right"):
            key = keys.get(name[:-5] + "_R")
        if key is not None and math.isfinite(value):
            key.value = value
            applied += 1
    for obj, pose_name in ((scene.facepipe_head, "head"),
                           (scene.facepipe_left_eye, "lefteye"),
                           (scene.facepipe_right_eye, "righteye")):
        numbers = poses.get(pose_name)
        if obj is None or numbers is None or len(numbers) < 3:
            continue
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = tuple(math.radians(value) for value in numbers[:3])
        if pose_name == "head" and len(numbers) >= 6:
            obj.location = numbers[3:6]
    return applied


def _tick():
    if not _running or _socket is None:
        return None
    latest = None
    for _ in range(12):
        try:
            latest, _peer = _socket.recvfrom(8192)
        except BlockingIOError:
            break
        except OSError:
            return None
    if latest is not None:
        try:
            apply_frame(bpy.context.scene, latest.decode("utf-8", "replace"))
        except (AttributeError, ReferenceError):
            pass
    return 1.0 / 60.0


class FACEPIPE_OT_start(bpy.types.Operator):
    bl_idname = "facepipe.start"
    bl_label = "Start FacePipe"

    def execute(self, context):
        global _socket, _running
        if _running:
            return {"FINISHED"}
        host = context.scene.facepipe_bind
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            self.report({"ERROR"}, "Use a private IPv4 address")
            return {"CANCELLED"}
        if address.version != 4 or address.is_unspecified or not (
                address.is_private or address.is_loopback or
                address in ipaddress.ip_network("100.64.0.0/10")):
            self.report({"ERROR"}, "Use a private IPv4 address")
            return {"CANCELLED"}
        try:
            _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _socket.bind((host, context.scene.facepipe_port))
            _socket.setblocking(False)
        except OSError as error:
            if _socket:
                _socket.close()
                _socket = None
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        _running = True
        bpy.app.timers.register(_tick, first_interval=0.01)
        self.report({"INFO"}, f"Listening on {host}:{context.scene.facepipe_port}")
        return {"FINISHED"}


class FACEPIPE_OT_stop(bpy.types.Operator):
    bl_idname = "facepipe.stop"
    bl_label = "Stop FacePipe"

    def execute(self, context):
        global _socket, _running
        _running = False
        if _socket:
            _socket.close()
            _socket = None
        return {"FINISHED"}


class FACEPIPE_PT_panel(bpy.types.Panel):
    bl_label = "FacePipe Live"
    bl_idname = "FACEPIPE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FacePipe"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "facepipe_mesh")
        layout.prop(scene, "facepipe_head")
        layout.prop(scene, "facepipe_left_eye")
        layout.prop(scene, "facepipe_right_eye")
        layout.prop(scene, "facepipe_bind")
        layout.prop(scene, "facepipe_port")
        layout.operator("facepipe.stop" if _running else "facepipe.start")


_CLASSES = (FACEPIPE_OT_start, FACEPIPE_OT_stop, FACEPIPE_PT_panel)


def _mesh_poll(_self, obj):
    return obj.type == "MESH"


def register():
    for item in _CLASSES:
        bpy.utils.register_class(item)
    bpy.types.Scene.facepipe_mesh = PointerProperty(type=bpy.types.Object, poll=_mesh_poll)
    bpy.types.Scene.facepipe_head = PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.facepipe_left_eye = PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.facepipe_right_eye = PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.facepipe_bind = StringProperty(name="Bind address", default="127.0.0.1")
    bpy.types.Scene.facepipe_port = IntProperty(name="UDP port", default=49985, min=1, max=65535)


def unregister():
    FACEPIPE_OT_stop.execute(None, None)
    for name in ("facepipe_mesh", "facepipe_head", "facepipe_left_eye",
                 "facepipe_right_eye", "facepipe_bind", "facepipe_port"):
        delattr(bpy.types.Scene, name)
    for item in reversed(_CLASSES):
        bpy.utils.unregister_class(item)


if __name__ == "__main__":
    register()
