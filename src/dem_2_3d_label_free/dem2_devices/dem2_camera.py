"""Camera control script."""
import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors


class Dem2Camera():
    def __init__(self, config: dict):
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED

        self.t_exp = self._cfg["time_exposure"]
        if self.t_exp < 0.1:
            raise Dem2Errors.CameraError("Minimum exposure time is 100 us.")
        self.t_read = self._cfg["time_readout"]
        self.lateral_size = self._cfg["lateral_size"]

        self.no_of_images: int|None = None

    def connect(self):
        """Connect to Camera."""
        if self._state != Dem2State.DISCONNECTED:
            raise Dem2Errors.LaserError("Camera has already been connected! Disconnect first.")
        self._log.info("Connecting to the Camera...")
        # TODO connect to laser
        self._state = Dem2State.CONNECTED
        self._log.info("Connected to the Camera.")

    def initialize(self):
        """Initialize the Camera."""
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.CameraError("Camera must be connected!")
        if self.no_of_images is None:
            raise Dem2Errors.CameraError("Number of images must be set to initialize!")
        self._log.info("Initialising the Camera...")
        # TODO Initialize
        self._state = Dem2State.INITIALIZED
        self._log.info("Initialized the Camera.")

    # Properties
    @property
    def t_frame(self):
        """Get time for 1 frame in ms."""
        return self.t_exp if self.t_exp > self.t_read else self.t_read