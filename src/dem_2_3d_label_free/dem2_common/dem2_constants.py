from enum import Enum


class Dem2State(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    INITIALIZED = 2
    READY = 3
    RUNNING = 4


class Dem2CameraMode(Enum):
    MONO = 0
    FRAME_BURST_EXT_TRIGGER = 1


class Dem2LaserMode(Enum):
    CW = 0
    SINGLE = 1
    CONTINUOUS = 2


class Dem2StageMode(Enum):
    MANUAL = 0
    PATTERN = 1


ZERNIKE_NOLLS = [
    None,  # 0 (unused)
    "Piston",
    "Tilt Horiz.",
    "Tilt Vert.",
    "Defocus",
    "1. Astig. Oblique",
    "1. Astig. Vert.",
    "1. Coma Vert.",
    "1. Coma Horiz.",
    "Trefoil Vert.",
    "Trefoil Oblique",
    "1. Spherical",
    "2. Astig. Vert.",
    "2. Astig. Oblique",
    "Quadfoil Vert.",
    "Quadfoil Oblique",
]

STATUS_MAP = {
    0: ("DISCONNECTED", "red"),
    1: ("CONNECTED", "yellow"),
    2: ("INITIALISED", "blue"),
    3: ("READY", "green"),
    4: ("RUNNING", "cyan"),
    99: ("WAITING...", "gray"),
}

MODES = {
    "camera": ["MONO", "BURST"],
    "laser": ["CW", "SINGLE", "CONTINUOUS"],
    "stage": ["MANUAL", "PATTERN"],
}
