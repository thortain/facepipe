extends SceneTree
## Headless integration check: send a VMC packet to port 51170 while this runs.


func _initialize() -> void:
    call_deferred("_run")


func _run() -> void:
    var mesh := ArrayMesh.new()
    mesh.add_blend_shape("jawOpen")
    var base: Array = []
    base.resize(Mesh.ARRAY_MAX)
    base[Mesh.ARRAY_VERTEX] = PackedVector3Array([
        Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
    var jaw: Array = []
    jaw.resize(Mesh.ARRAY_MAX)
    jaw[Mesh.ARRAY_VERTEX] = PackedVector3Array([
        Vector3(0, -0.1, 0), Vector3.RIGHT, Vector3.UP])
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, base, [jaw])
    var face := MeshInstance3D.new()
    face.mesh = mesh
    root.add_child(face)
    var head := Node3D.new()
    root.add_child(head)
    var receiver := Node.new()
    receiver.set_script(load("res://FacePipeVMC.gd"))
    receiver.face_mesh = face
    receiver.head = head
    receiver.port = 51170
    root.add_child(receiver)
    print("VMC_BIND=", receiver._peer != null, " port=",
        receiver._peer.get_local_port() if receiver._peer != null else -1)
    await create_timer(3.0).timeout
    print("VMC_COUNTS packets=", receiver.packets_received,
        " messages=", receiver.messages_received)
    var value := face.get_blend_shape_value(0)
    if absf(value - 0.5) < 0.01 and absf(head.position.x - 0.25) < 0.01:
        print("FACEPIPE_GODOT_VMC_OK shape=", value, " head_x=", head.position.x)
        quit(0)
    else:
        push_error("FacePipe VMC data missing: shape=%s head=%s" % [value, head.position.x])
        quit(1)
