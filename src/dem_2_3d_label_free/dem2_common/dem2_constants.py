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