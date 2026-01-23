from enum import Enum


class Dem2State(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    INITIALIZED = 2
    READY = 3
    RUNNING = 4

