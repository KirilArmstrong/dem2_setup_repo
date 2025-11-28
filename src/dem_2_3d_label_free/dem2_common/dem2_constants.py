from enum import Enum

class Dem2State(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    INITIALIZED = 2
    CALIBRATED = 3
    READY = 4