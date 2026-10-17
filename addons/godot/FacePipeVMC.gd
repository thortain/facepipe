extends Node
## Godot 4 VMC/OSC receiver for FacePipe. Assign an ARKit-named MeshInstance3D.

@export var face_mesh: MeshInstance3D
@export var head: Node3D
@export var bind_address := "127.0.0.1"
@export_range(1, 65535) var port := 39539

var _peer: PacketPeerUDP
var _shape_indices := {}
var _pending_blend := {}
var packets_received := 0
var messages_received := 0


func _ready() -> void:
    if not _private_ipv4(bind_address):
        push_error("FacePipe bind address must be private IPv4")
        return
    if face_mesh != null and face_mesh.mesh != null:
        for index in range(face_mesh.mesh.get_blend_shape_count()):
            _shape_indices[String(face_mesh.mesh.get_blend_shape_name(index))] = index
    _peer = PacketPeerUDP.new()
    var error := _peer.bind(port, bind_address)
    if error != OK:
        push_error("FacePipe UDP bind failed: %s" % error)
        _peer = null


func _process(_delta: float) -> void:
    if _peer == null:
        return
    while _peer.get_available_packet_count() > 0:
        packets_received += 1
        _read_packet(_peer.get_packet())


func _exit_tree() -> void:
    if _peer != null:
        _peer.close()


func _private_ipv4(value: String) -> bool:
    if not value.is_valid_ip_address() or value.contains(":"):
        return false
    var parts := value.split(".")
    if parts.size() != 4:
        return false
    var a := int(parts[0])
    var b := int(parts[1])
    return a == 127 or a == 10 or (a == 172 and b >= 16 and b <= 31) or \
        (a == 192 and b == 168) or (a == 100 and b >= 64 and b <= 127)


func _read_u32(data: PackedByteArray, offset: int) -> int:
    return (int(data[offset]) << 24) | (int(data[offset + 1]) << 16) | \
        (int(data[offset + 2]) << 8) | int(data[offset + 3])


func _read_float(data: PackedByteArray, offset: int) -> float:
    var little := PackedByteArray([
        data[offset + 3], data[offset + 2], data[offset + 1], data[offset]])
    return little.decode_float(0)


func _read_string(data: PackedByteArray, offset: int) -> Array:
    var end := offset
    while end < data.size() and data[end] != 0:
        end += 1
    if end >= data.size():
        return ["", data.size()]
    var value := data.slice(offset, end).get_string_from_utf8()
    return [value, (end + 4) & ~3]


func _read_packet(data: PackedByteArray) -> void:
    if data.size() < 4:
        return
    var first := _read_string(data, 0)[0] as String
    if first != "#bundle":
        _read_message(data)
        return
    if data.size() < 16:
        return
    var offset := 16  # OSC immediate timetag occupies bytes 8..15.
    while offset + 4 <= data.size():
        var length := _read_u32(data, offset)
        offset += 4
        if length < 4 or offset + length > data.size():
            return
        _read_message(data.slice(offset, offset + length))
        offset += length


func _read_message(data: PackedByteArray) -> void:
    messages_received += 1
    var address_part := _read_string(data, 0)
    var address := address_part[0] as String
    var tags_part := _read_string(data, int(address_part[1]))
    var tags := tags_part[0] as String
    var offset := int(tags_part[1])
    if not tags.begins_with(","):
        return
    var values: Array = []
    for tag in tags.substr(1):
        if tag == "s":
            var parsed := _read_string(data, offset)
            values.append(parsed[0])
            offset = int(parsed[1])
        elif tag == "f" and offset + 4 <= data.size():
            values.append(_read_float(data, offset))
            offset += 4
        else:
            return
    if address == "/VMC/Ext/Blend/Val" and values.size() == 2 and face_mesh != null:
        var name := values[0] as String
        if _shape_indices.has(name):
            _pending_blend[name] = values[1]
    elif address == "/VMC/Ext/Blend/Apply" and face_mesh != null:
        for name in _pending_blend:
            face_mesh.set_blend_shape_value(_shape_indices[name], _pending_blend[name])
        _pending_blend.clear()
    elif address == "/VMC/Ext/Bone/Pos" and values.size() == 8 and head != null:
        if values[0] == "Head":
            head.position = Vector3(values[1], values[2], values[3])
            head.quaternion = Quaternion(values[4], values[5], values[6], values[7])
