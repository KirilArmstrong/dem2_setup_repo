"""Swept Source Laser control script."""

import concurrent.futures
import serial
import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors


class Dem2Laser:
    """Swept Source Laser control script."""

    def __init__(self, config: dict):
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED

        # Set up connection variables
        self._port = self._cfg["port"]
        self._serial_connection = None
        self._executor = concurrent.futures.ThreadPoolExecutor()

        self.wavelength_centre = self._cfg["wavelength_center"]
        self.wavelength_min = self._cfg["wavelength_min"]
        self.wavelength_max = self._cfg["wavelength_max"]
        self.wavelength_range = self.wavelength_max - self.wavelength_min

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
        if self._serial_connection and self._serial_connection.is_open:
            self._serial_connection.close()
            self._log.info("Disconnected from the laser.")
        self.__init__(self._cfg)

    def initialize(self):
        """Initialize the laser source."""
        self._log.info("Initialising the laser source...")
        if (
            self._state != Dem2State.CONNECTED
            or not self._serial_connection
            or not self._serial_connection.is_open
        ):
            raise Dem2Errors.LaserError("Must be connected!")
        if self._sweep_speed is None or self._total_sweep_time is None:
            raise Dem2Errors.LaserError(
                "total_sweep_time, and in turn sweep_speed, must be set to initialize!"
            )

        # convert wavelength into hex and send
        norm_min = self.wavelength_min / 4095
        lambda_min_hex = hex(65536 * norm_min)
        norm_max = self.wavelength_max / 4095
        lambda_max_hex = hex(65536 * norm_max)
        self.send_command(f"P22{str(lambda_min_hex)}")
        self.send_command(f"P23{str(lambda_max_hex)}")

        self._state = Dem2State.READY
        self._log.info("Initialized the laser source.")

    def queue_command(self, command):
        """Queue a command to the laser device and return the response as a future object."""
        if (
            (self._state != Dem2State.CONNECTED and command != "I")
            or not self._serial_connection
            or not self._serial_connection.is_open
        ):
            raise Dem2Errors.LaserError("Must be connected to queue a command other than 'I'!")

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

    def send_command(self, command):
        """Send string command and wait for response."""
        future = self.queue_command(command)
        return future.result(timeout=1)

    def send_sweep_speed(self, sweep_speed):
        # convert sweep speed into hex and send
        sweep_speed_hex = format(int(sweep_speed * 10), "06X")
        return self.send_command(f"P24{str(sweep_speed_hex)}")

    def get_device_info(self) -> str:
        """Read operation mode [I]."""
        return self.send_command("I")

    # Properties

    @property
    def state(self) -> Dem2State:
        return self._state

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
        self._total_sweep_time = value
        self._sweep_speed = self.wavelength_range / self._total_sweep_time

    @property
    def sweep_speed(self) -> float:
        """Getter for sweep speed."""
        if self._sweep_speed is None:
            raise Dem2Errors.PropertyNotSetError(
                "total_sweep_time, and in turn sweep_speed, was never set."
            )
        return self._sweep_speed