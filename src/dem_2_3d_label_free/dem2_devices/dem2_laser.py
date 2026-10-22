# ruff: noqa: F405, F403
"""Swept Source Laser control script."""

import concurrent.futures
import serial
import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2LaserMode
from src.dem_2_3d_label_free.dem2_common.dem2_laser_defs import *
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    wavelength_to_hex,
    hex_to_decimal,
)


class Dem2Laser:
    """Swept Source Laser control script."""

    def __init__(self, config: dict):
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED
        self._mode = Dem2LaserMode.CW

        # Set up connection variables
        self._port = self._cfg["port"]
        self._serial_connection = None
        self._executor = concurrent.futures.ThreadPoolExecutor()

        self._wavelength_centre = self._cfg["wavelength_center"]
        self._wavelength = self._cfg["wavelength_center"]
        self._wavelength_min = self._cfg["wavelength_min"]
        self._wavelength_max = self._cfg["wavelength_max"]
        self._wavelength_base = 0

        self._total_sweep_time = None
        self._sweep_speed = None

    def check_state(
        self,
        is_in: tuple | None = None,
        isnt_in: tuple | None = None,
        fail_error: Dem2Errors.LaserError | str | None = None,
        fail_warning: str | None = None,
        force_fail: bool = False,
    ) -> bool:
        if is_in is not None:
            if self._state in is_in and not force_fail:
                return True
        if isnt_in is not None:
            if self._state not in isnt_in and not force_fail:
                return True
        if fail_warning is not None:
            self._log.warning(fail_warning)
        if fail_error is None:
            return False
        if isinstance(fail_error, str):
            raise Dem2Errors.LaserError(reason=fail_error)
        raise fail_error

    def connect(self):
        """Connect to laser source via serial."""
        self._log.info("Connecting to the laser source...")

        self.check_state(
            is_in=(Dem2State.DISCONNECTED,), fail_error=Dem2Errors.LaserError(4)
        )
        try:
            self._serial_connection = serial.Serial(
                self._port, baudrate=57600, timeout=1
            )
            self._state = Dem2State.CONNECTED
            self._log.info(
                f"Connected to the laser source. Device: {self.get_device_info()}"
            )
        except Exception as e:
            raise Dem2Errors.LaserError(0, str(e))

    def disconnect(self):
        """Disconnect the laser."""
        self._log.info("Disconnecting from the laser...")
        if self.check_state(
            isnt_in=(Dem2State.DISCONNECTED,),
            fail_warning=LS_ERROR_CODES[6] + " Continuing...",
        ):
            self.kill_emission()
            self.send_command(LS_CMD_SWP_MODE_CW)
            # self.send_command(LS_CMD_SHUTDOWN)
            self.send_command(LS_CMD_CTRL_MODE_LOCAL)
        if self._serial_connection and self._serial_connection.is_open:
            self._serial_connection.close()
            self._log.info("Disconnected from the laser.")
        self.__init__(self._cfg)

    def change_mode(self, mode: Dem2LaserMode) -> None:
        """Change Laser mode."""
        self.check_state(
            is_in=(Dem2State.DISCONNECTED, Dem2State.CONNECTED),
            fail_error=Dem2Errors.LaserError(11, 200),
        )
        self._mode = mode
        self._log.info("Changed mode to " + str(self._mode))

    def initialize(self, wake_up: bool = True):
        """Initialize the laser source.
        :param wake_up: Wake up laser after initialization. Default True."""
        self._log.info("Initialising the laser source...")
        self.check_state(
            isnt_in=(Dem2State.DISCONNECTED,),
            fail_error=Dem2Errors.LaserError(7, 12),
            force_fail=not self._serial_connection
            or not self._serial_connection.is_open,
        )

        self._wavelength_base = hex_to_decimal(self.send_command(LS_PRM_CONST_BWL)[3:])
        self.send_command(LS_CMD_CTRL_MODE_USB)  # usb control mode

        match self._mode:
            case Dem2LaserMode.CW:
                self.send_command(LS_CMD_SWP_MODE_CW)  # CW mode
                # set cw wavelength
                self.send_cw()
            case Dem2LaserMode.SINGLE:
                if self._sweep_speed is None or self._total_sweep_time is None:
                    raise Dem2Errors.LaserError(1, 205)
                self.send_command(LS_CMD_SWP_MODE_SINGLE)  # single sweep mode

                # convert wavelength into hex and send
                self.send_command(LS_PRM_USR_SINGLE_WL)
                self.send_lambda_min_max(self._wavelength_min, self._wavelength_max)
                self.send_sweep_speed(self._sweep_speed)

        self.send_command(LS_CMD_CTRL_MODE)

        self._state = Dem2State.INITIALIZED
        self._log.info("Initialized the laser source.")
        if wake_up:
            self.wake_up()

    def queue_command(self, command):
        """Queue a command to the laser device and return the response as a future object."""
        self.check_state(
            isnt_in=(Dem2State.DISCONNECTED,),
            fail_error=Dem2Errors.LaserError(
                7, LS_ERROR_CODES[201] + f" Command: {command}"
            ),
            force_fail=not self._serial_connection
            or not self._serial_connection.is_open,
        )

        def task():
            response = ""
            try:
                cmd = f"{command}\r\n"
                self._log.info(f"Sending command to laser: {cmd[:-1]}")
                self._serial_connection.write(cmd.encode())
                response = self._serial_connection.readline().decode().strip()
                self._log.info(f"Laser responded with: {response}")
                if "!" in response or response == "":
                    raise Dem2Errors.LaserError(
                        100,
                        "Response: " + (response if response != "" else "No Response."),
                    )
                return response
            except Exception as e:
                raise Dem2Errors.LaserError(3, str(e))

        future = self._executor.submit(task)
        return future

    # Commands

    def send_lambda_min_max(
        self, min_lambda, max_lambda, base_lambda=None, resolution=100
    ):
        """Send command to set min and max wavelengths."""
        base = base_lambda if base_lambda is not None else self._wavelength_base
        self._log.info(
            f"Sending wavelength min {min_lambda} wavelength max {max_lambda}  with base wavelength as {base}..."
        )
        self.send_command(
            LS_PRM_USR_START_WL, wavelength_to_hex(min_lambda, base, resolution)
        )
        self.send_command(
            LS_PRM_USR_STOP_WL, wavelength_to_hex(max_lambda, base, resolution)
        )

    def send_cw(self, wavelength=None):
        """Send command set cw."""
        if wavelength is not None:
            self.wavelength = wavelength
        self._log.info(f"Sending CW to laser: {self.wavelength}")
        self.send_command(
            LS_PRM_USR_SINGLE_WL,
            wavelength_to_hex(self.wavelength, self._wavelength_base, 100),
        )

    def send_command(self, command, parameter=""):
        """Send string command and wait for response."""
        future = self.queue_command(command + parameter)
        return future.result(timeout=1)

    def send_sweep_speed(self, sweep_speed):
        """Send command sweep speed."""
        # convert sweep speed into hex and send
        sweep_speed_hex = format(int(sweep_speed * 10), "06X")
        self._log.info(f"Sending sweep speed to laser: {sweep_speed}")
        return self.send_command(LS_PRM_USR_SWP_SPEED, str(sweep_speed_hex))

    def get_device_info(self) -> str:
        """Read operation mode [I]."""
        return self.send_command(LS_DEVICE_INFO)

    def wake_up(self):
        """
        Wake up laser.
        """
        self._log.info("Waking up laser...")
        self.check_state(
            is_in=(Dem2State.INITIALIZED,), fail_error=Dem2Errors.LaserError(8, 202)
        )
        self.send_command(LS_CMD_WAKE_UP)  # start pump source (no emission yet)
        self._state = Dem2State.READY
        self._log.info("Laser awake and ready.")

    def toggle_emission(self):
        if not self.check_state(
            is_in=(Dem2State.READY, Dem2State.RUNNING),
            fail_warning=LS_ERROR_CODES[10] + " " + LS_ERROR_CODES[203],
        ):
            return
        if self.check_state(is_in=(Dem2State.READY,)):
            self.send_command(LS_TOGGLE_EMISSION)  # toggle emission
            self._state = Dem2State.RUNNING
            return
        self.kill_emission()

    def kill_emission(self, shutdown: bool = False):
        """Kill laser emission.

        NOTE: This objects state must be set to Dem2State.RUNNING for it to work.
        :param shutdown: Shutdown swept source. Default False.
        """
        if not self.check_state(
            is_in=(Dem2State.RUNNING,),
            fail_warning=LS_ERROR_CODES[9] + " " + LS_ERROR_CODES[204],
        ):
            return
        self.send_command(LS_TOGGLE_EMISSION)  # toggle emission
        if shutdown:
            self.send_command(LS_CMD_SHUTDOWN)  # kill pump source
            self._mode = Dem2State.INITIALIZED
        self._state = Dem2State.READY

    # Properties

    @property
    def state(self) -> Dem2State:
        return self._state

    @property
    def mode(self) -> Dem2LaserMode:
        return self._mode

    @property
    def total_sweep_time(self):
        """Total time for the laser to sweep through the wavelength range in seconds."""
        return self._total_sweep_time

    @total_sweep_time.setter
    def total_sweep_time(self, value: float):
        """
        Setter for Total time for the laser to sweep through the wavelength range in seconds.

        Also updates sweep speed.
        :param value: Total time in seconds.
        """
        self.check_state(
            isnt_in=(Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED),
            fail_error=Dem2Errors.LaserError(11, 206),
        )

        self._total_sweep_time = value
        new_speed = (
            self._wavelength_max - self._wavelength_min
        ) / self._total_sweep_time
        if new_speed < 0.1:
            raise Dem2Errors.LaserError(
                101, LS_ERROR_CODES[208] + f" Min = 0.1 nm/s, calculated = {new_speed}"
            )
        self._sweep_speed = new_speed

    @property
    def wavelength_centre(self):
        """Laser wavelength centre in nm."""
        return self._wavelength_centre

    @property
    def wavelength(self):
        """Current laser wavelength in nm."""
        return self._wavelength

    @wavelength.setter
    def wavelength(self, value: float):
        """
        Setter for Total time for the laser to sweep through the wavelength range in seconds.

        Also updates sweep speed.
        :param value: Total time in seconds.
        """
        # if self._state in (Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED):
        #     raise Dem2Errors.LaserError(
        #         "wavelength can only be changed when uninitialised!"
        #     )
        if value < self._cfg["wavelength_min"] or value > self._cfg["wavelength_max"]:
            raise Dem2Errors.LaserError(101, 209)
        self._wavelength = value

    @property
    def wavelength_max(self):
        """Current laser wavelength in nm."""
        return self._wavelength_max

    @wavelength_max.setter
    def wavelength_max(self, value: float):
        """
        Setter for Total time for the laser to sweep through the wavelength range in seconds.

        Also updates sweep speed.
        :param value: Total time in seconds.
        """
        self.check_state(
            isnt_in=(Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED),
            fail_error=Dem2Errors.LaserError(11, 207),
        )
        if value < self._cfg["wavelength_min"] or value > self._cfg["wavelength_max"]:
            raise Dem2Errors.LaserError(101, 209)
        self._wavelength_max = value

    @property
    def wavelength_min(self):
        """Current laser wavelength in nm."""
        return self._wavelength_min

    @wavelength_min.setter
    def wavelength_min(self, value: float):
        """
        Setter for Total time for the laser to sweep through the wavelength range in seconds.

        Also updates sweep speed.
        :param value: Total time in seconds.
        """
        self.check_state(
            isnt_in=(Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED),
            fail_error=Dem2Errors.LaserError(11, 207),
        )
        if value < self._cfg["wavelength_min"] or value > self._cfg["wavelength_max"]:
            raise Dem2Errors.LaserError(101, 209)
        self._wavelength_min = value

    @property
    def sweep_speed(self) -> float:
        """Getter for sweep speed."""
        if self._sweep_speed is None:
            raise Dem2Errors.PropertyNotSetError(LS_ERROR_CODES[205])
        return self._sweep_speed

    @property
    def settings(self) -> dict:
        """Collect current laser settings."""
        _dict = {}
        _dict.update(self._cfg)
        if self._state == Dem2State.DISCONNECTED:
            return _dict
        _dict["mode"] = self.mode.value
        _dict["wavelength"] = self.wavelength
        _dict["wavelength_min"] = self.wavelength_min
        _dict["wavelength_max"] = self.wavelength_max
        _dict["wavelength_rng"] = self.wavelength_max - self.wavelength_min
        _dict["sweep_speed"] = self.sweep_speed
        return _dict
