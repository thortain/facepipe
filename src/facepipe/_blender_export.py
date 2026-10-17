"""Blender background worker. Run via ``facepipe export-fbx``, not directly."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from facepipe.blendshapes import IDENTIFIERS, normalize_name  # noqa: E402
from facepipe.recorder import load  # noqa: E402


def build_carrier():
    vertices = []
    faces = []
    for index in range(len(IDENTIFIERS)):
        x = index * 0.025
        base = len(vertices)
        vertices.extend(((x, 0.0, 0.0), (x + 0.01, 0.0, 0.0),
                         (x, 0.01, 0.0)))
        faces.append((base, base + 1, base + 2))
    mesh = bpy.data.meshes.new("FacePipe signal mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("FacePipeCarrier", mesh)
    bpy.context.collection.objects.link(obj)
    obj.shape_key_add(name="Basis", from_mix=False)
    for index, name in enumerate(IDENTIFIERS):
        key = obj.shape_key_add(name=name, from_mix=False)
        key.data[index * 3].co.z += 0.01
    return obj


def build_rig():
    armature = bpy.data.armatures.new("FacePipe bones")
    rig = bpy.data.objects.new("FacePipeRig", armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    head = armature.edit_bones.new("Head")
    head.head, head.tail = (0, 0, 0), (0, 0.1, 0)
    for name, x in (("Eye.L", -0.03), ("Eye.R", 0.03)):
        eye = armature.edit_bones.new(name)
        eye.head, eye.tail = (x, 0.02, 0), (x, 0.06, 0)
        eye.parent = head
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.select_set(False)
    for bone in rig.pose.bones:
        bone.rotation_mode = "XYZ"
    return rig


def render(input_path: str, output_path: str, fps: int):
    frames = load(input_path)
    if not frames:
        raise ValueError("recording contains no frames")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = len(frames)
    carrier = build_carrier()
    rig = build_rig()
    keys = carrier.data.shape_keys.key_blocks
    pose = rig.pose.bones
    for number, frame in enumerate(frames, 1):
        blend = {}
        for name, value in frame.blendshapes.items():
            try:
                blend[normalize_name(name)] = float(value)
            except ValueError:
                continue
        for name in IDENTIFIERS:
            value = blend.get(name, 0.0)
            if not math.isfinite(value):
                raise ValueError(f"non-finite blendshape {name} at frame {number}")
            key = keys[name]
            key.value = value
            key.keyframe_insert(data_path="value", frame=number)
        if len(frame.head) != 6 or len(frame.left_eye) != 3 or len(frame.right_eye) != 3:
            raise ValueError(f"invalid pose at frame {number}")
        head = pose["Head"]
        head.rotation_euler = tuple(math.radians(v) for v in frame.head[:3])
        head.location = frame.head[3:6]
        head.keyframe_insert(data_path="rotation_euler", frame=number)
        head.keyframe_insert(data_path="location", frame=number)
        for bone_name, angles in (("Eye.L", frame.left_eye),
                                  ("Eye.R", frame.right_eye)):
            eye = pose[bone_name]
            eye.rotation_euler = tuple(math.radians(v) for v in angles)
            eye.keyframe_insert(data_path="rotation_euler", frame=number)
    scene.frame_set(1)
    bpy.ops.object.select_all(action="DESELECT")
    carrier.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    result = bpy.ops.export_scene.fbx(
        filepath=output_path, use_selection=True, object_types={"MESH", "ARMATURE"},
        bake_anim=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0,
        add_leaf_bones=False,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"FBX exporter returned {result}")
    print(f"FACEPIPE_FBX_EXPORTED frames={len(frames)} shapes={len(IDENTIFIERS)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fps", type=int, required=True)
    arguments = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    render(arguments.input, arguments.output, arguments.fps)
