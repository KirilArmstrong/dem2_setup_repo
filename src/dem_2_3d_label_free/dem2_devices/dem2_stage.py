"""Stage control script."""

import logging
import time
import clr

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors

clr.AddReference(r"C:\Program Files\Carl Zeiss\ZEN 2\ZEN 2 (blue edition)\MTBApi.dll")
from ZEISS import MTB


class Dem2Stage:
    def __init__(self, config: dict, pos_settled_cb, focus_changed_cb):
        """
        Dem2Stage init function.

        To use: 1) ``connect()``, 2) ``Initialize()``, and 3) ``calibrate()``.
        :param config: Stage configuration.
        :param pos_settled_cb:
        :param focus_changed_cb:
        """
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state: Dem2State = Dem2State.DISCONNECTED
        self.pos_settled_cb = pos_settled_cb  # TODO maybe better way in control script?
        self.focus_changed_cb = (
            focus_changed_cb  # TODO maybe better way in control script?
        )
        self._m_Connection: MTB.Api.IMTBConnection | None = None
        self._mtbid: str | None = None
        self.root: MTB.Api.IMTBRoot | None = None
        self.axis = []
        self.stage = None
        self.stage_sink = None  # TODO privatable?
        self.focus_sink = None  # TODO privatable?
        self.focus = None
        self._focus_set_pos = 0.0
        self.b_focus_drift_detected = False
        self.b_pattern_acquisition = False
        self._sw_limit = [self._cfg["axis_limit_max"], self._cfg["axis_limit_min"]]
        self._pos_unit = None
        self._move_mode = None

    def _register_pos_settled_event_handler(self):
        # create an instant of the event sink class
        self.stage_sink = MTB.Api.MTBStageEventSink()
        # Create an instance of the handler type
        handler = MTB.Api.MTBStagePositionSettledHandler(self._my_pos_settled_handler)
        # Set the handler instance on the event sink handler
        self.stage_sink.MTBPositionSettledEvent += handler
        # Register the event sink handler with the device interface
        self.stage_sink.Advise(self.stage)

    def _my_pos_settled_handler(self, arg1, arg2):
        self._log.info("pos. settled event called!")
        self.pos_settled_cb([arg1, arg2])

    def _register_pos_changed_event_handler(self):
        # create an instant of the event sink class
        self.focus_sink = MTB.Api.MTBContinualEventSink()
        # Create an instance of the handler type
        handler2 = MTB.Api.MTBStagePositionSettledHandler(self._my_pos_changed_handler)
        # Set the handler instance on the event sink handler
        self.focus_sink.MTBPositionSettledEvent += handler2
        # Register the event sink handler with the device interface
        self.focus_sink.Advise(self.focus)

    def _my_pos_changed_handler(self, arg1):
        self._log.info("pos. changed event called!")
        self.focus_changed_cb(arg1)

    def connect(self):
        """Connect the Stage."""
        self._log.info("Connecting to the stage...")
        self._m_Connection = MTB.Api.MTBConnection()
        self._mtbid = self._m_Connection.Login("en")
        self.root = self._m_Connection.GetRoot(self._mtbid)
        self._state = Dem2State.CONNECTED
        self._log.info("Connected to the stage.")

    def disconnect(self):
        """Disconnect the stage."""
        self._log.info("Disconnecting from the stage...")
        if self._state == Dem2State.DISCONNECTED:
            self._log.warning("Stage already disconnected! Continuing...")
        else:
            self._m_Connection.Logout(self._mtbid)
            self._log.info("Disconnected from the stage.")
        self.__init__(self._cfg, self.pos_settled_cb, self.focus_changed_cb)

    def initialize(self, calibration_wait_time: float = -1):
        """
        Initialize the Stage. Must be Connected.
        :param calibration_wait_time: Auto calibrate after initialization with Time to wait for objective removal. Recommended min = 20s. Disable with ``-1``.
        :return:
        """
        self._log.info("Initialising the stage...")
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.StageError("Must be connected to Initialize!")
        # Initialize focus:
        self.focus = MTB.Api.IMTBAxis(self.root.GetComponent("MTBFocus"))
        # Initialize stage:
        self.stage = MTB.Api.IMTBStage(self.root.GetComponent("MTBStage"))
        self.axis.append(self.stage.XAxis)
        self.axis.append(self.stage.YAxis)
        self._pos_unit = self.axis[0].GetPositionUnit(0)
        self._move_mode = MTB.Api.MTBCmdSetModes(0)

        self._register_pos_settled_event_handler()
        self._register_pos_changed_event_handler()
        self._state = Dem2State.INITIALIZED
        if calibration_wait_time >= 0:
            self.calibrate(calibration_wait_time)
        self._log.info("Stage Initialized.")

    def calibrate(self, wait_time: float = 20):
        """
        Calibrate the Stage. Must be Initialized.
        :param wait_time: Time to wait for objective removal. Recommended min = 20s.
        """
        if wait_time > 0:
            self._log.warning(
                f"About to calibrate the stage! Please ensure no objective is in the stage!! "
                f"Proceeding in {wait_time}s..."
            )
            time.sleep(wait_time)
        self._log.info("Calibrating the stage...")
        if self._state != Dem2State.INITIALIZED:
            raise Dem2Errors.StageError("Must be Initialized to calibrate!")
        # Calibrate focus:
        if (
            int(self.focus.CalibrationMode)
            & int(MTB.Api.MTBCalibrationModes.OnLowerLimit)
            == 0
        ):
            # Axis requires calibration
            self.focus.Calibrate(
                MTB.Api.MTBCalibrationModes.OnFullRange
                | MTB.Api.MTBCalibrationModes.OnLowerLimit,
                MTB.Api.MTBCmdSetModes.Default,
                600,
            )
        self.move_focus(0.0)
        # Calibrate axis:
        for ax in self.axis:
            if (
                int(ax.CalibrationMode) & int(MTB.Api.MTBCalibrationModes.OnLowerLimit)
                == 0
            ):
                # Axis requires calibration
                ax.Calibrate(
                    MTB.Api.MTBCalibrationModes.OnFullRange
                    | MTB.Api.MTBCalibrationModes.OnLowerLimit,
                    MTB.Api.MTBCmdSetModes.Default,
                    600,
                )
        self._set_sw_limits()
        self._state = Dem2State.CALIBRATED
        self._log.info("Stage calibrated.")

    def move_focus(self, pos):
        """
        Move focus to position z. Must be calibrated.
        :param pos: position z.
        """
        if self._state != Dem2State.CALIBRATED:
            raise Dem2Errors.StageError("Must be calibrated to move focus!")
        self._log.info("moving focus to: ", pos)
        self._focus_set_pos = pos
        self.focus.SetPosition(self._focus_set_pos, self._pos_unit, self._move_mode)

    def get_focus_pos(self):
        """Get current focus position."""
        return [
            self.focus.GetPosition(self._pos_unit),
        ]

    def _check_focus_drift(self):
        """Check if focus is drifting."""
        if self.get_focus_pos() == self._focus_set_pos:
            self.b_focus_drift_detected = False
        else:
            self.b_focus_drift_detected = True
        return self.b_focus_drift_detected

    def _set_sw_limits(self):
        """Set software limits."""
        for ax in self.axis:
            ax.SetSWLimit(True, self._sw_limit[0], self._pos_unit)
            ax.SetSWLimit(False, self._sw_limit[1], self._pos_unit)
            self._sw_limit.append(
                [
                    ax.GetSWLimit(True, self._pos_unit),
                    ax.GetSWLimit(False, self._pos_unit),
                ]
            )
        self._log.info(
            "software limits: cfg_max, cfg_min, actual_max, actual_min:", self._sw_limit
        )  # TODO if cfg and actual identical, remove the get limits above

    def move_to_position(self, position, emergency: bool = False):
        """
        Move stage to position (x,y). Must be calibrated.
        :param position: position tuple.
        :param emergency: Override calibration requirement, i.e. emergency stop.
        """
        if self._state != Dem2State.CALIBRATED and not emergency:
            raise Dem2Errors.StageError("Must be calibrated to move stage!")
        self.stage.SetPosition(
            position[0], position[1], self._pos_unit, self._move_mode
        )
        self._log.info("moving to pos: ", position)

    def stop_moving(self):
        """Stop moving the stage."""
        self.move_to_position(self.get_position(), emergency=True)
        self.stage.Stop()
        self._log.info("stage stopped at: ", self.get_position())

    def get_position(self):
        """Get stage current position."""
        x = 0.0
        y = 0.0
        x,y = self.stage.GetPosition(x,y, self._pos_unit)
        return [x,y]
