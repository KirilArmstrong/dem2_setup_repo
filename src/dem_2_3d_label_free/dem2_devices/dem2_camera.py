"""Camera control script."""

import logging

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2CameraMode
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
import xiapi

import numpy as np

class Dem2Camera(xiapi.Camera):
    """Camera control script."""

    def __init__(self, config: dict):
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED
        self._mode = Dem2CameraMode(self._cfg["mode"])

        super().__init__(self._cfg["device_id"])

        # Save config exposure time.
        self._t_exp = self._cfg["time_exposure"]
        if self._t_exp < 0.1:
            raise Dem2Errors.CameraError("Minimum exposure time is 100 us.")
        self.t_read = self._cfg["time_readout"]
        self.lateral_size = self._cfg["lateral_size"]

        # Number of images per a-scan.
        self.samples_a_scan: int | None = None

        self._buffer_offset = None

        self.image = xiapi.Image()

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
        self._log.info("Initialising the Camera in mode: " + str(self._mode) + "...")
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.CameraError("Must be connected to initialize!")
        if self.samples_a_scan is None:
            raise Dem2Errors.CameraError("Number of images must be set to initialize!")

        self.set_exposure(self._t_exp * 1000)  # convert ms to us

        match self._mode:
            case Dem2CameraMode.MONO: # Default Load in Mono mode
                self._log.info("mode: " + str(self._mode))
                self.set_imgdataformat("XI_MONO8")
            case Dem2CameraMode.FRAME_BURST_EXT_TRIGGER: # Experiment mode
                self._log.info("mode1: " + str(self._mode))
                self.set_imgdataformat("XI_FRM_TRANSPORT_DATA")  # for image burst buffer
                self.set_gpi_mode(
                    "XI_GPI_TRIGGER"
                )  # https://www.ximea.com/support/wiki/apis/XiAPI_Python_Manual#GPIMode
                self.set_trigger_source("XI_TRG_RISING_EDGE")  # trigger when laser rises
                self.set_trigger_selector(
                    "XI_TRG_SEL_FRAME_BURST_ACTIVE"
                )  # while pulse high, it continuously exposes.
                if self.samples_a_scan is None:
                    raise Dem2Errors.CameraError("Number of samples per a scan not set.")
                self.set_concat_img_count(self.samples_a_scan)
                self.enable_concat_img_mode()  # multiple images in one buffer.
                # self._buffer_offset = self.get_concat_img_transport_img_offset()
        self._state = Dem2State.READY
        self._log.info("Initialized the Camera.")

    def start_acquisition(self):
        self._log.info("Beginning acquisition...")
        if self._state != Dem2State.READY:
            raise Dem2Errors.CameraError("Camera must be initialised and not already running.")
        self._state = Dem2State.RUNNING
        super().start_acquisition()
        self._log.info("Acquisition started.")

    def stop_acquisition(self):
        self._log.info("Stopping acquisition...")
        if self._state != Dem2State.RUNNING:
            raise Dem2Errors.CameraError("Camera must be running to stop acquisition!.")
        self._state = Dem2State.READY
        super().stop_acquisition()
        self._log.info("Acquisition stopped.")

    def acquire_image(self) -> np.ndarray :
        self.start_acquisition()
        self.get_image(self.image)
        data = self.image.get_image_data_numpy()
        self._log.info("Acquired Image.")
        self.stop_acquisition()
        return data

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