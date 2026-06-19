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
    None,                 # 0 (unused)
    "Piston",             # 1
    "Tilt Vert.",        # 2
    "Tilt Horiz.",         # 3
    "Defocus",            # 4
    "1. Astig. Vert.",  # 5
    "1. Astig. Oblique",    # 6
    "1. Coma Horiz.",     # 7
    "1. Coma Vert.",      # 8
    "Trefoil Oblique",    # 9
    "Trefoil Vert.",      # 10
    "1. Spherical",       # 11 (primary)
    "2. Astig. Oblique",    # 12
    "2. Astig. Vert.",  # 13
    "Quadfoil Oblique",     # 14
    "Quadfoil Vert.",      # 15
]