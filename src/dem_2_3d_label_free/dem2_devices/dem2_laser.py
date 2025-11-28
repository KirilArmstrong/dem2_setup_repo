"""Swept Source Laser control script."""
import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors


class Dem2Laser:
    def __init__(self, config: dict):
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED

        self.wavelength_centre = self._cfg["wavelength_center"]
        self.wavelength_min = self._cfg["wavelength_min"]
        self.wavelength_max = self._cfg["wavelength_max"]
        self.wavelength_range = self.wavelength_max - self.wavelength_min

        self._total_sweep_time = None
        self._sweep_speed = None

    def connect(self):
        """Connect to laser source."""
        if self._state != Dem2State.DISCONNECTED:
            raise Dem2Errors.LaserError("Laser source has already been connected! Disconnect first.")
        self._log.info("Connecting to the laser source...")
        # TODO connect to laser
        self._state = Dem2State.CONNECTED
        self._log.info("Connected to the laser source.")

    def initialize(self):
        """Initialize the laser source."""
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.LaserError("Laser source must be connected!")
        if self._sweep_speed is None or self._total_sweep_time is None:
            raise Dem2Errors.LaserError("total_sweep_time, and in turn sweep_speed, must be set to initialize!")
        self._log.info("Initialising the laser source...")
        # TODO Initialize
        self._state = Dem2State.INITIALIZED
        self._log.info("Initialized the laser source.")

    # Properties

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
            raise Dem2Errors.PropertyNotSetError("total_sweep_time, and in turn sweep_speed, was never set.")
        return self._sweep_speed