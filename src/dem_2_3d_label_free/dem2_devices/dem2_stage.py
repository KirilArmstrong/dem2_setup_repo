"""Stage control script."""

import logging
import time
import clr
from concurrent.futures import Future
from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2StageMode
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors

clr.AddReference(r"C:\Program Files\Carl Zeiss\ZEN 2\ZEN 2 (blue edition)\MTBApi.dll")
from ZEISS import MTB


class Dem2Stage:
    """Stage control script."""

    def __init__(self, config: dict):
        """
        Dem2Stage init function.

        To use: 1) ``connect()``, 2) ``Initialize()``, and 3) ``calibrate()``.
        :param config: Stage configuration.
        """
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state: Dem2State = Dem2State.DISCONNECTED
        self._mode: Dem2StageMode = Dem2StageMode.MANUAL

        self._m_Connection: MTB.Api.IMTBConnection | None = None
        self._mtbid: str | None = None
        self._root: MTB.Api.IMTBRoot | None = None

        self._pos_settled_future = Future()
        self._focus_settled_future = Future()

        self._axis = []
        self.stage = None
        self.focus = None
        self._stage_sink = None
        self._focus_sink = None
        self._focus_set_pos = self._cfg["focus_z_pos"]
        self._sw_limit = [self._cfg["axis_limit_max"], self._cfg["axis_limit_min"]]
        self._pos_unit = None
        self._move_mode = None

        self.b_focus_drift_detected = False

    # Initialization.

    def _register_stage_event_handler(self):
        # create an instant of the event sink class
        self._stage_sink = MTB.Api.MTBStageEventSink()
        # Create an instance of the handler type
        settle_handler = MTB.Api.MTBStagePositionSettledHandler(self._my_pos_settled_handler)
        # Set the handler instance on the event sink handler
        self._stage_sink.MTBPositionSettledEvent += settle_handler
        # Register the event sink handler with the device interface
        self._stage_sink.Advise(self.stage)

    def _my_pos_settled_handler(self, arg1, arg2):
        self._log.debug(
            f"settled handler called. moved to pos. {arg1}, {arg2} and settled!"
        )
        self._state = Dem2State.READY
        self._pos_settled_future.set_result((arg1, arg2))

    def _register_focus_event_handler(self):
        # create an instant of the event sink class
        self._focus_sink = MTB.Api.MTBContinualEventSink()
        # Create an instance of the handler type
        handler2 = MTB.Api.MTBContinualPositionSettledHandler(self._focus_settled_handler)
        # Set the handler instance on the event sink handler
        self._focus_sink.MTBPositionSettledEvent += handler2
        # Register the event sink handler with the device interface
        self._focus_sink.Advise(self.focus)

    def _focus_settled_handler(self, arg1):
        self._log.debug(f"focus settled event called! Set to {arg1['V']}")
        self._state = Dem2State.READY
        self._focus_settled_future.set_result(arg1)

    def _set_sw_limits(self):
        """Set software limits."""
        for ax in self._axis:
            ax.SetSWLimit(True, self._sw_limit[0], self._pos_unit)
            ax.SetSWLimit(False, self._sw_limit[1], self._pos_unit)
            self._sw_limit.append(
                [
                    ax.GetSWLimit(True, self._pos_unit),
                    ax.GetSWLimit(False, self._pos_unit),
                ]
            )
        self._log.info(
            "software limits: cfg_max, cfg_min, [x axi [actual_max, actual_min], [y axis [...]]:"
            + self._sw_limit.__str__()
        )

    # Stage control.

    def _queue_move_stage_to_pos(self, position, emergency: bool = False) -> Future:
        """
        Move stage to position (x,y). Must be calibrated.
        :param position: position tuple.
        :param emergency: Override calibration requirement, i.e. emergency stop.
        """
        if self._state != Dem2State.READY and not emergency:
            raise Dem2Errors.StageError("Must be calibrated to move stage!")
        self._pos_settled_future = Future()
        self._state = Dem2State.RUNNING
        if self.get_position() == position and not emergency:
            self._log.info("Stage Already at position " + position.__str__())
            self._pos_settled_future.set_result(self.get_position())
        else:
            self._log.info("moving to pos: " + position.__str__())
            self.stage.SetPosition(
                position[0], position[1], self._pos_unit, self._move_mode
            )
            # TODO see if i need to future.set_result for emergency stop.
        return self._pos_settled_future

    def _queue_move_focus(self, z_pos) -> Future:
        """
        Move focus to position z. Must be calibrated.
        :param z_pos: position z.
        """
        if self._state != Dem2State.READY:
            raise Dem2Errors.StageError("Must be calibrated to move focus!")
        self._focus_settled_future = Future()
        self._focus_set_pos = z_pos
        self._state = Dem2State.RUNNING
        if self.get_focus() == self._focus_set_pos:
            self._log.info("Focus already at pos " + z_pos.__str__())
            self._focus_settled_future.set_result(self.get_focus())
        else:
            self._log.info("moving focus to: " + z_pos.__str__())
            self.focus.SetPosition(self._focus_set_pos, self._pos_unit, self._move_mode)
        return self._focus_settled_future

    def _check_focus_drift(self):
        """Check if focus is drifting."""
        # TODO i think there is a focus stabiliser that does this. IMTBFocusStabilizer. Check in config
        if self.get_focus() == self._focus_set_pos:
            self.b_focus_drift_detected = False
        else:
            self.b_focus_drift_detected = True
        return self.b_focus_drift_detected

    def _calibrate_axis(self, ax) -> tuple[Future, Future]:
        """
        Calibrate the given axis (X, Y, or Focus).
        :param ax: Axis (X, Y, Focus).
        """
        self._pos_settled_future, self._focus_settled_future = Future(), Future()
        if int(ax.CalibrationMode) & int(MTB.Api.MTBCalibrationModes.OnLowerLimit) == 0:
            # Axis requires calibration
            ax.Calibrate(
                MTB.Api.MTBCalibrationModes.OnFullRange
                | MTB.Api.MTBCalibrationModes.OnLowerLimit,
                MTB.Api.MTBCmdSetModes.Default,
                600,
            )
        else:
            self._pos_settled_future.set_result("Already calibrated.")
            self._focus_settled_future.set_result("Already calibrated.")
        return self._pos_settled_future, self._focus_settled_future

    # # Functions

    def connect(self):
        """Connect the Stage."""
        self._log.info("Connecting to the stage...")
        self._m_Connection = MTB.Api.MTBConnection()
        self._mtbid = self._m_Connection.Login("en")
        self._root = self._m_Connection.GetRoot(self._mtbid)
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
        self.__init__(self._cfg)

    def initialize(self, calibration_wait_time: float = -1):
        """
        Initialize the Stage. Must be Connected.
        :param calibration_wait_time: Auto calibrate after initialization with Time to wait for objective removal. Recommended min = 20s. Disable with ``-1``.
        :return:
        """
        # todo mode check
        self._log.info("Initialising the stage...")
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.StageError("Must be connected to Initialize!")
        # Initialize focus:
        self.focus = MTB.Api.IMTBFocus(self._root.GetComponent("MTBFocus"))
        # Initialize stage:
        self.stage = MTB.Api.IMTBStage(self._root.GetComponent("MTBStage"))
        self._axis.append(self.stage.XAxis)
        self._axis.append(self.stage.YAxis)
        self._pos_unit = self._axis[0].GetPositionUnit(0)
        self._move_mode = MTB.Api.MTBCmdSetModes(0)

        self._register_stage_event_handler()
        self._register_focus_event_handler()
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
                f"Proceeding in {wait_time}s... Ctrl + C to cancel!"
            )
            time.sleep(wait_time)
        if self._state != Dem2State.INITIALIZED:
            raise Dem2Errors.StageError("Must be Initialized to calibrate!")
        self._log.info("Calibrating focus...")
        # Calibrate focus:
        self._calibrate_axis(self.focus)
        self._log.info(
            "Focus: " + self._focus_settled_future.result() if isinstance(self._focus_settled_future.result(),
                                                                          str) else "Calibrated."
        )  # wait for calibration to finish.
        # Calibrate axis:
        self._log.info("Calibrating the stage...")
        for ax in range(len(self._axis)):
            self._calibrate_axis(self._axis[ax])
            self._log.info(
                f"{ax} axis: " + self._pos_settled_future.result() if isinstance(self._pos_settled_future.result(),
                                                                                 str) else "Calibrated."
            )  # wait for calibration to finish.
        time.sleep(1)
        self._set_sw_limits()
        self._state = Dem2State.READY
        self._log.info("Stage calibrated.")
        if self._focus_set_pos is not None:
            self._queue_move_focus(self._focus_set_pos)

    def change_mode(self, mode: Dem2StageMode) -> None:
        """Change camera mode."""
        if self._state not in (Dem2State.DISCONNECTED, Dem2State.CONNECTED):
            raise Dem2Errors.CameraError("Must be disconnected or uninitialize to change mode!")
        self._mode = mode
        self._log.info("Changed mode to " + str(self._mode))

    def move_focus(self, z, relative: bool = False):
        """
        Move the stage position and wait until it settles.
        :param z: Z position.
        :param relative: Whether to move relative to current position or absolute.
        """
        current_position = self.get_focus()
        if current_position == z:
            self._log.warning(f"focus already at pos {current_position.__str__()}")
            return
        if relative and z != 0:
            z = current_position + z
        future = self._queue_move_focus(z)
        res = future.result()  # will wait until it settles.
        self._log.info(f"Focus moved and settled at new pos. {res}")

    def move_stage(self, x: float, y: float, relative: bool = False):
        """
        Move the stage position and wait until it settles.
        :param x: X position.
        :param y: Y position.
        :param relative: Whether to move relative to current position or absolute.
        """
        current_position = self.get_position()
        if current_position[0] == x and current_position[1] == y and not relative:
            self._log.warning(f"Stage already at pos {current_position.__str__()}")
            return
        if relative and not (x == 0 and y == 0):
            x = current_position[0] + x
            y = current_position[1] + y
        future = self._queue_move_stage_to_pos((x, y))
        res = future.result()  # will wait until it settles.
        self._log.info(f"Stage moved and settled at new pos {res[0]}, {res[1]}")

    def stop_moving(self):
        """Stop moving the stage."""
        # override current movement
        # self._queue_move_stage_to_pos(self.get_position(), emergency=True)
        # call stop
        self.stage.Stop()
        self._state = Dem2State.READY
        self._log.info("stage stopped at: ", self.get_position())

    # # Properties

    @property
    def state(self) -> Dem2State:
        return self._state

    @property
    def mode(self) -> Dem2StageMode:
        return self._mode

    def get_position(self):
        """Get stage current position."""
        x = 0.0
        y = 0.0
        x, y = self.stage.GetPosition(x, y, self._pos_unit)
        return x, y

    def get_focus(self):
        """Get current focus position."""
        return self.focus.GetPosition(self._pos_unit)
