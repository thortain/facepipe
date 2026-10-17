"""FacePipe - open-source facial motion capture that speaks the iFacialMocap protocols."""
from __future__ import annotations

from .blendshapes import ARKIT_52, IDENTIFIERS, RAW_VALUES, normalize_name
from .calibration import Calibration
from .frame import Frame
from .fmv3 import FMV3Receiver, FMV3Sender
from .text_protocol import decode, encode

__version__ = "0.1.0"

__all__ = [
    "Frame", "ARKIT_52", "IDENTIFIERS", "RAW_VALUES", "normalize_name",
    "encode", "decode", "FMV3Sender", "FMV3Receiver", "Calibration", "__version__",
]
