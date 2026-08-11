"""Swept Source Laser control script."""

import concurrent.futures
import serial
import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2LaserMode
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
        self._base_wavelength = 0

        self._total_sweep_time = None
        self._sweep_speed = None

    def connect(self):
        """Connect to laser source via serial."""
        self._log.info("Connecting to the laser source...")
        if self._state != Dem2State.DISCONNECTED:
            raise Dem2Errors.LaserError("Already been connected! Disconnect first.")
        try:
            self._serial_connection = serial.Serial(
                self._port, baudrate=57600, timeout=1
            )
            self._log.info(
                f"Connected to the laser source. Device: {self.get_device_info()}"
            )
            self._state = Dem2State.CONNECTED
        except serial.SerialException as e:
            raise Dem2Errors.LaserError(f"Failed to connect: {e}")

    def disconnect(self):
        """Disconnect the laser."""
        self._log.info("Disconnecting from the laser...")
        if self._state == Dem2State.DISCONNECTED:
            self._log.warning("Laser already disconnected! Continuing...")
        else:
            self.kill_emission()
            self.send_command("MT")
            # self.send_command("MO")
            self.send_command("MB")
        if self._serial_connection and self._serial_connection.is_open:
            self._serial_connection.close()
            self._log.info("Disconnected from the laser.")
        self.__init__(self._cfg)

    def change_mode(self, mode: Dem2LaserMode) -> None:
        """Change camera mode."""
        if self._state not in (Dem2State.DISCONNECTED, Dem2State.CONNECTED):
            raise Dem2Errors.CameraError(
                "Must be disconnected or uninitialize to change mode!"
            )
        self._mode = mode
        self._log.info("Changed mode to " + str(self._mode))

    def initialize(self):
        """Initialize the laser source."""
        self._log.info("Initialising the laser source...")
        if (
            (self._state != Dem2State.CONNECTED and self._state != Dem2State.READY)
            or not self._serial_connection
            or not self._serial_connection.is_open
        ):
            raise Dem2Errors.LaserError("Must be connected ande not running!")

        self._base_wavelength = hex_to_decimal(self.send_command("P04")[3:])
        self.send_command("MC")  # usb control mode

        match self._mode:
            case Dem2LaserMode.CW:
                self.send_command("MT")  # CW mode
                # set cw wavelength
                self.send_cw()
            case Dem2LaserMode.SINGLE:
                if self._sweep_speed is None or self._total_sweep_time is None:
                    raise Dem2Errors.LaserError(
                        "total_sweep_time, and in turn sweep_speed, must be set to initialize!"
                    )
                self.send_command("MY")  # single sweep mode

                # convert wavelength into hex and send
                self.send_command("P22")
                self.send_lambda_min_max(self._wavelength_min, self._wavelength_max)
                self.send_sweep_speed(self._sweep_speed)

        self.send_command("MW")  # wake pump source
        self.send_command("M")

        self._state = Dem2State.READY
        self._log.info("Initialized the laser source.")

    def queue_command(self, command):
        """Queue a command to the laser device and return the response as a future object."""
        if (
            (command != "I" and self._state == Dem2State.DISCONNECTED)
            or not self._serial_connection
            or not self._serial_connection.is_open
        ):
            raise Dem2Errors.LaserError(
                f"Must be connected to queue a command other than 'I'! Command: {command}"
            )

        def task():
            response = ""
            try:
                cmd = f"{command}\r\n"
                self._log.info(f"Sending command to laser: {cmd}")
                self._serial_connection.write(cmd.encode())
                response = self._serial_connection.readline().decode().strip()
                self._log.info(f"Laser responded with: {response}")
                if "!" in response or response == "":
                    raise Dem2Errors.LaserError(
                        f"Device responded with error: {response if response != '' else 'No Response.'}"
                    )
                return response
            except Exception as e:
                raise Dem2Errors.LaserError(f"Failed to send command: {e}")

        future = self._executor.submit(task)
        return future

    # Commands

    def send_lambda_min_max(
        self, min_lambda, max_lambda, base_lambda=None, resolution=100
    ):
        base = base_lambda if base_lambda is not None else self._base_wavelength
        self._log.info(
            f"Sending wavelength min {min_lambda} wavelength max {max_lambda}  with base wavelength as {base}..."
        )
        self.send_command(f"P22{wavelength_to_hex(min_lambda, base, resolution)}")
        self.send_command(f"P23{wavelength_to_hex(max_lambda, base, resolution)}")

    def send_cw(self, wavelength=None):
        if wavelength is not None:
            self.wavelength = wavelength
        self._log.info(f"Sending CW to laser: {wavelength}")
        self.send_command(
            f"P21{wavelength_to_hex(self.wavelength, self._base_wavelength, 100)}"
        )

    def send_command(self, command):
        """Send string command and wait for response."""
        future = self.queue_command(command)
        return future.result(timeout=1)

    def send_sweep_speed(self, sweep_speed):
        # convert sweep speed into hex and send
        sweep_speed_hex = format(int(sweep_speed * 10), "06X")
        self._log.info(f"Sending sweep speed to laser: {sweep_speed}")
        return self.send_command(f"P24{str(sweep_speed_hex)}")

    def get_device_info(self) -> str:
        """Read operation mode [I]."""
        return self.send_command("I")

    def toggle_emission(self):
        if self._state != Dem2State.READY and self._state != Dem2State.RUNNING:
            self._log.warning("Laser must be initialised to toggle emission!")
            return
        if self._state == Dem2State.READY:
            # self.send_command("MW") # start pump source (no emission yet)
            self.send_command("X")  # toggle emission
            self._state = Dem2State.RUNNING
            return
        self.kill_emission()

    def kill_emission(self):
        if self._state != Dem2State.RUNNING:
            self._log.warning("Laser must be running to kill emission!")
            return
        self.send_command("X")  # toggle emission
        # self.send_command("MO") # kill pump source
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
        if self._state in (Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED):
            raise Dem2Errors.LaserError(
                "sweep time can only be changed when uninitialised!"
            )

        self._total_sweep_time = value
        new_speed = (
            self._wavelength_max - self._wavelength_min
        ) / self._total_sweep_time
        if new_speed < 0.1:
            raise Dem2Errors.LaserError(
                f"Total sweep time is too low! Sweep speed min is 0.1 nm/s, calculated = {new_speed}"
            )
        self._sweep_speed = new_speed

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
            raise Dem2Errors.LaserError("wavelength out of configuration range!")
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
        if self._state in (Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED):
            raise Dem2Errors.LaserError(
                "wavelength can only be changed when uninitialised!"
            )
        if value < self._cfg["wavelength_min"] or value > self._cfg["wavelength_max"]:
            raise Dem2Errors.LaserError("wavelength out of configuration range!")
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
        if self._state in (Dem2State.READY, Dem2State.RUNNING, Dem2State.INITIALIZED):
            raise Dem2Errors.LaserError(
                "wavelength can only be changed when uninitialised!"
            )
        if value < self._cfg["wavelength_min"] or value > self._cfg["wavelength_max"]:
            raise Dem2Errors.LaserError("wavelength out of configuration range!")
        self._wavelength_min = value

    @property
    def sweep_speed(self) -> float:
        """Getter for sweep speed."""
        if self._sweep_speed is None:
            raise Dem2Errors.PropertyNotSetError(
                "total_sweep_time, and in turn sweep_speed, was never set."
            )
        return self._sweep_speed

    @property
    def settings(self) -> dict:
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
