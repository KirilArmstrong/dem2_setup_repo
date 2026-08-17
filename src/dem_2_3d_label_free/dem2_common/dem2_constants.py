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

# # Laser parameter definitions

# Laser
LS_DEVICE_INFO = "I"
LS_TOGGLE_EMISSION = "X"

# Laser Modes
LS_CMD_CTRL_MODE = "M"
LS_CMD_CTRL_MODE_LOCAL = "MB"
LS_CMD_CTRL_MODE_REMOTE = "ME"
LS_CMD_CTRL_MODE_USB = "MC"
LS_CMD_SWP_MODE_CW = "MT"
LS_CMD_SWP_MODE_CONT = "MZ"
LS_CMD_SWP_MODE_SINGLE = "MY"
LS_CMD_SHUTDOWN = "MO"
LS_CMD_WAKE_UP = "MW"

# Constants - Read Only
LS_PRM_CONST_VERSION = "P01"
LS_PRM_CONST_BFR = "P02"
LS_PRM_CONST_MWL = "P03"
LS_PRM_CONST_BWL = "P04"
LS_PRM_CONST_CTS = "P05"
LS_PRM_CONST_CSS = "P06"
LS_PRM_CONST_MSR = "P07"

# Factory Data - Read/Write
LS_PRM_FAC_SN = "P10"
LS_PRM_FAC_MIN_WL = "P11"
LS_PRM_FAC_MAX_WL = "P12"
LS_PRM_FAC_AOTF_THERM_VAL = "P13"
LS_PRM_FAC_SLD_THERM_VAL = "P14"
LS_PRM_FAC_SLD_CURR_VAL = "P15"
LS_PRM_FAC_SLD_PD_CURR_VAL = "P16"
LS_PRM_FAC_RF_GAIN = "P17"
LS_PRM_FAC_APC_DELAY = "P18"
LS_PRM_FAC_SWP_DELAY = "P19"

# User Data - Read/Write
LS_PRM_USR_OFF_MODE_DATA = "P20"
LS_PRM_USR_SINGLE_WL = "P21"
LS_PRM_USR_START_WL = "P22"
LS_PRM_USR_STOP_WL = "P23"
LS_PRM_USR_SWP_SPEED = "P24"
LS_PRM_USR_PAUSE_TIME = "P25"
LS_PRM_USR_SWP_TIME = "P26"
LS_PRM_USR_TRIG_MODE = "P27"
LS_PRM_USR_CHNG_SWP_DIR = "P2D"

# Variable Data - Read Only
LS_PRM_VAR_SINGLE_FREQ = "P31"
LS_PRM_VAR_START_FREQ = "P32"
LS_PRM_VAR_STOP_FREQ = "P33"
LS_PRM_VAR_SRR_DRIVER = "P34"
LS_PRM_VAR_SRR = "P35"
LS_PRM_VAR_RDW = "P36"
LS_PRM_VAR_FDW = "P37"
LS_PRM_VAR_SWP_SPEED_FREQ = "P38"

# ADC Data - Read Only
LS_PRM_ADC_AOTF_THERM_SET_VAL = "PA1"
LS_PRM_ADC_AOTF_THERM_REAL_VAL = "PA2"
LS_PRM_ADC_SLD_THERM_SET_VAL = "PA3"
LS_PRM_ADC_SLD_THERM_REAL_VAL = "PA4"
LS_PRM_ADC_AOTF_TEC_CURR = "PA5"
LS_PRM_ADC_SLD_TEC_CURR = "PA6"
LS_PRM_ADC_SLD_CURR_SET_VAL = "PA7"
LS_PRM_ADC_SLD_CURR_REAL_VAL = "PA8"
LS_PRM_ADC_PD_CURR_SET_VAL = "PA9"
LS_PRM_ADC_PD_CURR_REAL_VAL = "PAA"
LS_PRM_ADC_TEMP_SENSOR_VAL = "PAE"

# Data storage in EEPROM
LS_EEPROM_STORE_USR_DATA = "SD"
LS_EEPROM_STORE_FAC_DATA = "FD"
LS_EEPROM_STORE_CAL_DATA = "CD"


def LS_CALIBRATION_DATA(cal_point: int) -> str:
    """
    Get hex code for respective calibration point. Supported values: 0-63.
    :param cal_point: Calibration point. Supported values: 0-63.
    :return: calibration point hex. C0-FF
    """
    if not isinstance(cal_point, int) or not 0 <= cal_point <= 63:
        raise ValueError("cal_point must be an integer between 0 and 63")

    return f"{0xC0 + cal_point:02X}"