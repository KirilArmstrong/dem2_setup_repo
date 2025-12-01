"""Camera control script."""

import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.ximea import xiapi


class Dem2Camera(xiapi.Camera):
    """Camera control script."""

    def __init__(self, config: dict):
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED

        super().__init__(self._cfg["id"])

        # Save config exposure time.
        self._t_exp = self._cfg["time_exposure"]
        if self._t_exp < 0.1:
            raise Dem2Errors.CameraError("Minimum exposure time is 100 us.")
        self.t_read = self._cfg["time_readout"]
        self.lateral_size = self._cfg["lateral_size"]

        # Number of images per a-scan.
        self.samples_a_scan: int | None = None

    def connect(self):
        """Connect to Camera."""
        self._log.info("Connecting to the Camera...")
        if self._state != Dem2State.DISCONNECTED:
            raise Dem2Errors.LaserError("Already been connected! Disconnect first.")
        try:
            self.open_device()
        except Exception as e:
            raise Dem2Errors.CameraError(f"Failed to connect: {e}")
        self._state = Dem2State.CONNECTED
        self._log.info("Connected to the Camera.")

    def disconnect(self):
        """Disconnect the camera."""
        self._log.info("Disconnecting from the camera...")
        if self._state == Dem2State.DISCONNECTED:
            self._log.warning("Camera already disconnected! Continuing...")
        else:
            self.close_device()
            self._log.info("Disconnected from the camera.")
        self.__init__(self._cfg)

    def initialize(self):
        """Initialize the Camera."""
        self._log.info("Initialising the Camera...")
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.CameraError("Must be connected to initialize!")
        if self.samples_a_scan is None:
            raise Dem2Errors.CameraError("Number of images must be set to initialize!")
        self.set_exposure(self._t_exp * 1000)  # convert ms to us
        self.set_imgdataformat("XI_MONO8")
        self._state = Dem2State.INITIALIZED
        self._log.info("Initialized the Camera.")

    # Properties

    @property
    def t_frame(self):
        """Get time for 1 frame in ms."""
        return self.t_exp if self.t_exp > self.t_read else self.t_read

    @property
    def t_exp(self):
        """Get camera integration time in ms."""
        if self._state == Dem2State.DISCONNECTED:
            return self._t_exp
        return self.get_exposure() / 1000