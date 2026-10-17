# Godot 4 VMC receiver

Attach `FacePipeVMC.gd` to a Node in your scene and assign a `MeshInstance3D`
whose blend shapes use ARKit identifier names. The optional Head node receives
FacePipe pose. The receiver binds to `127.0.0.1:39539` by default.

Run `facepipe serve --source 0 --vmc-host 127.0.0.1 --vmc-port 39539 --vmc-head` on the
same PC. For a separate private LAN/VPN device, configure a specific private
IPv4 bind address in Godot and send to that address. The script accepts the
standard VMC `/VMC/Ext/Blend/Val` and `/VMC/Ext/Blend/Apply` messages. The
estimated Head bone pose is optional and depends on the avatar's coordinate
conventions.

Head orientation conventions differ between avatars; adjust the
transform mapping in the script for the target rig.
