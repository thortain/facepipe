"""Export an NDJSON capture as a binary FBX animation carrier using Blender."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .recorder import load


def find_blender(explicit: Optional[str] = None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raise FileNotFoundError(f"Blender executable not found: {candidate}")
    command = shutil.which("blender")
    if command:
        return Path(command).resolve()
    roots = [Path(r"C:\Program Files\Blender Foundation"),
             Path("/Applications/Blender.app/Contents/MacOS")]
    for root in roots:
        if root.is_dir():
            matches = sorted(root.glob("Blender */blender.exe"), reverse=True)
            if matches:
                return matches[0]
            candidate = root / "Blender"
            if candidate.is_file():
                return candidate
    raise FileNotFoundError("Blender is required for FBX export; supply --blender PATH")


def export_fbx(recording: str, output: str, *, fps: int = 60,
               blender: Optional[str] = None) -> Path:
    """Create a binary FBX with 52 animated shape keys and head/eye bones."""
    source = Path(recording).expanduser().resolve(strict=True)
    target = Path(output).expanduser().resolve()
    if not 1 <= fps <= 240:
        raise ValueError("fps must be between 1 and 240")
    if not load(str(source)):
        raise ValueError("recording contains no frames")
    target.parent.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name("_blender_export.py")
    command = [str(find_blender(blender)), "--background", "--factory-startup",
               "--python", str(script), "--", "--input", str(source),
               "--output", str(target), "--fps", str(fps)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        detail = (result.stderr + "\n" + result.stdout)[-5000:]
        raise RuntimeError(f"Blender FBX export failed (exit {result.returncode}):\n{detail}")
    return target
