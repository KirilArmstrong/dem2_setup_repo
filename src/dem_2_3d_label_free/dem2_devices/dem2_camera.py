"""Camera control script."""

import logging
import time

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2CameraMode
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
import xiapi

import numpy as np


class Dem2Camera(xiapi.Camera):
    """Camera control script."""

    def __init__(self, config: dict):
        # Control settings
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED
        self._mode = Dem2CameraMode(self._cfg["mode"])
        xiapi.Camera.__init__(self, self._cfg["device_id"])

        # Camera ROI settings
        self._roi_offset = (
            int(self._cfg["roi_offset_y"]),
            int(self._cfg["roi_offset_x"]),
        )
        self._roi_size = (int(self._cfg["roi_height"]), int(self._cfg["roi_width"]))
        self._increments = (0, 0)  # Camera increment amount (y, x)
        self._max_res = (0, 0)  # (h, w)

        # Save config exposure time.
        self._t_exp = self._cfg["time_exposure"]
        if self._t_exp < 0.1:
            raise Dem2Errors.CameraError("Minimum exposure time is 100 us.")
        self._t_idle = self._cfg["time_idle"]
        if self._t_idle < 0:
            raise Dem2Errors.CameraError("Minimum idle time is 0 us.")
        self.t_read = self._cfg["time_readout"]
        self.lateral_size = (self._cfg["lateral_size_x"], self._cfg["lateral_size_y"])

        # Number of images per a-scan.
        self.samples_a_scan: int | None = None
        self._fps = None

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
        self.set_exposure(self._t_exp * 1000)
        self._increments = (self.get_height_increment(), self.get_width_increment())
        self._max_res = (self.get_height_maximum(), self.get_width_maximum())

    def disconnect(self):
        """Disconnect the camera."""
        self._log.info("Disconnecting from the camera...")
        if self._state == Dem2State.DISCONNECTED:
            self._log.warning("Camera already disconnected! Continuing...")
        else:
            self.close_device()
            self._log.info("Disconnected from the camera.")
        self.__init__(self._cfg)  # Reset object

    def change_mode(self, mode: Dem2CameraMode) -> None:
        """Change camera mode."""
        if self._state not in (Dem2State.DISCONNECTED, Dem2State.CONNECTED):
            raise Dem2Errors.CameraError(
                "Must be disconnected or uninitialize to change mode!"
            )
        self._mode = mode
        self._log.info("Changed mode to " + str(self._mode))

    def initialize(self):
        """
        Initialize the Camera.
        """
        self._log.info("Initialising the Camera in mode: " + str(self._mode) + "...")
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.CameraError("Must be connected to initialize!")

        # Set settings
        self.set_exposure(self._t_exp * 1000)  # convert ms to us
        self._log.info("Exposure initialized to " + str(self._t_exp * 1000) + " us.")
        self.set_imgdataformat("XI_MONO8")
        # Cam Hardware ROI
        if self._roi_offset != (0, 0) and self._roi_size != (0, 0):
            self.roi_size = self._roi_size
            self.roi_offset = self._roi_offset
            self._log.info(
                f"Camera roi settings set as: Offsets (y,x): {self.get_offsetY()}, {self.get_offsetX()}. "
                f"Size (h,w): {self.get_height()}, {self.get_width()}"
            )

        match self._mode:
            case Dem2CameraMode.MONO:  # Default Load in Mono mode. Single imaging
                self._log.info("mode: " + str(self._mode))
            case (
                Dem2CameraMode.FRAME_BURST_EXT_TRIGGER
            ):  # External triggering frame burst
                self._log.info("mode: " + str(self._mode))
                self.set_gpi_selector("XI_GPI_PORT2")  # Adjust to your actual port
                self.set_gpi_mode("XI_GPI_TRIGGER")
                self.set_trigger_source(
                    "XI_TRG_EDGE_FALLING"
                )  # trigger when laser rises
                self.set_trigger_selector(
                    "XI_TRG_SEL_FRAME_BURST_START"
                )  # when pulse high, it bursts.
                self.set_acq_frame_burst_count(int(self.samples_a_scan))
                self._log.info("Samples/a_scan: " + str(int(self.samples_a_scan)))
                self.set_acq_timing_mode("XI_ACQ_TIMING_MODE_FRAME_RATE_LIMIT")
                self._fps = 1 / (self.t_frame / 1000)
                if not 0.01 < self._fps < 10000:
                    raise Dem2Errors.CameraError(
                        f"Camera fps must be between 0.01 and 10,000 fps. Yours:{self._fps} fps."
                    )
                self.set_framerate(self._fps)
                self._log.info(f"Frame rate on. set to {self._fps} fps.")

                self.set_counter_selector("XI_CNT_SEL_API_SKIPPED_FRAMES")
                self.set_buffer_policy("XI_BP_SAFE")

        self._state = Dem2State.READY
        self._log.info("Initialized the Camera.")

    def start_acquisition(self):
        """Start camera acquisition."""
        self._log.info("Beginning acquisition...")
        if self._state != Dem2State.READY:
            raise Dem2Errors.CameraError(
                "Camera must be initialised and not already running."
            )
        self._state = Dem2State.RUNNING
        super().start_acquisition()
        self._log.info("Acquisition started.")

    def stop_acquisition(self):
        """Stop camera acquisition."""
        self._log.info("Stopping acquisition...")
        if self._state != Dem2State.RUNNING:
            raise Dem2Errors.CameraError("Camera must be running to stop acquisition!.")
        self._state = Dem2State.READY
        super().stop_acquisition()
        self._log.info("Acquisition stopped.")

    def get_image(
        self,
        image: xiapi.Image | None = None,
        timeout: int = 5000,
        return_numpy: bool = True,
    ) -> np.ndarray | None:
        """Override ``xiapi.Camera.get_image()`` to also return as numpy array.
        :param image: Image as xiapi.Image.
        :param timeout: Timeout in ms.
        :param return_numpy: Toggle converting and returning a numpy array.
        :returns: Image as numpy array."""
        super().get_image(image, timeout)
        if return_numpy:
            return image.get_image_data_numpy()
        else:
            return None

    def acquire_single_image(self, toggle_aqc: bool = True) -> np.ndarray:
        """Acquire single image and return it.
        :param toggle_aqc: Start and stop camera acquisition before and after capture. Default True.
        :returns: Image as numpy array."""
        if toggle_aqc:
            self.start_acquisition()
        # self.set_exposure(self._t_exp * 1000)
        time.sleep(((self._t_exp + self.t_read) / 1000) + 0.1)
        data = self.get_image(self.image)
        self._log.info("Acquired single Image.")
        if toggle_aqc:
            self.stop_acquisition()
        return data

    def toggle_live_images(self) -> str:
        """Acquire live images while Dem2State is RUNNING. Stop with ``stop_acquisition()``."""
        # if self._mode != Dem2CameraMode.MONO:
        #     raise Dem2Errors.CameraError("Camera must be in MONO (0) mode for live image acquisition!")
        if self._state == Dem2State.RUNNING:
            self.stop_acquisition()
            return "OFF"
        if self._state != Dem2State.RUNNING:
            self.start_acquisition()
        self._log.info("Now acquiring Images live...")
        return self.state.name

    # Properties

    @property
    def state(self) -> Dem2State:
        return self._state

    @property
    def mode(self) -> Dem2CameraMode:
        return self._mode

    @mode.setter
    def mode(self, mode: Dem2CameraMode):
        self._mode = mode

    @property
    def t_frame(self):
        """Get time for 1 frame in ms. t_epx + t_idle"""
        return (self.t_exp if self.t_exp > self.t_read else self.t_read) + self._t_idle

    @property
    def t_exp(self):
        """Get camera integration time in ms."""
        if self._state == Dem2State.DISCONNECTED:
            return self._t_exp
        return self.get_exposure() / 1000

    @property
    def t_idle(self):
        """Get camera idle time in ms."""
        return self._t_idle

    @t_exp.setter
    def t_exp(self, value: float):
        """Set camera integration time in ms."""

        if value < 0.1:
            raise Dem2Errors.CameraError(
                "Camera integration time must be more than 100 us!"
            )
        self._t_exp = value
        if self._state != Dem2State.DISCONNECTED:
            self.set_exposure(self._t_exp * 1000)

    @property
    def roi_offset(self):
        """Get camera offset in px."""
        return self._roi_offset

    @roi_offset.setter
    def roi_offset(self, offset: tuple[int, int]):
        """Set camera offset in px (y, x). Disable with (0, 0). NOTE: Must be set AFTER roi_size!"""
        self._log.info(f"Setting camera roi offset to {offset}...")
        if self._state != Dem2State.DISCONNECTED:
            if offset[1] % self._increments[1] or offset[0] % self._increments[0]:
                raise Dem2Errors.CameraError(
                    f"Offsets ({offset[0]}, {offset[1]}) must be multiples of increments "
                    f"({self._increments[0]}, {self._increments[1]})"
                )
            self.set_offsetY(offset[0])
            self.set_offsetX(offset[1])
        else:
            self._log.warning(
                "Ensure roi offset x and y are divisible by the cameras width and height increment "
                "values. To check this, connect to the camera first, then set roi_offset."
            )

        self._roi_offset = offset

    @property
    def roi_size(self):
        """Get camera offset in px."""
        return self._roi_offset

    @roi_size.setter
    def roi_size(self, size: tuple[int, int]):
        """Set camera offset in px (y, x). Disable with (0, 0). NOTE: Must be set BEFORE roi_offset as it overwrites it!"""
        self._log.info(f"Setting camera roi size to {size}...")
        if self._state != Dem2State.DISCONNECTED:
            if size[1] % self._increments[1] or size[0] % self._increments[0]:
                raise Dem2Errors.CameraError(
                    f"ROI dimensions must be divisible by increments ({self._increments[1]}, {self._increments[0]})!"
                )
            self.roi_offset = (0, 0)
            if size[0] != 0:
                self.set_height(size[0])
            else:
                self._log.info(f"Height set to 0, using max: {self._max_res[0]}")
                self.set_height(self._max_res[0])
            if size[1] != 0:
                self.set_width(size[1])
            else:
                self._log.info(f"Width set to 0, using max: {self._max_res[1]}")
                self.set_width(self._max_res[1])
        else:
            self._log.warning(
                "Ensure roi size w and h are divisible by the cameras width and height increment values. To check this, connect to the camera first, then set roi_size."
            )

        self._roi_size = size

    @property
    def get_max_res(self) -> tuple[int, int]:
        """Get camera width in px."""
        if self._max_res == (0, 0):
            self._log.warning("Camera was never connected. Max width: Unknown.")
        return self._max_res

    @property
    def get_increments(self) -> tuple[int, int]:
        """Get camera x increment in px."""
        if self._increments == (0, 0):
            self._log.warning("Camera was never connected. Increments: Unknown.")
        return self._increments

    @property
    def settings(self) -> dict:
        """Collect current camera settings."""
        _dict = {}
        _dict.update(self._cfg)
        if self._state == Dem2State.DISCONNECTED:
            return _dict
        _dict["mode"] = self.mode.value
        _dict["time_exposure"] = self.t_exp
        _dict["time_idle"] = self.t_idle
        _dict["frames"] = self.samples_a_scan
        _dict["fps"] = self._fps
        _dict["roi_offset_x"] = self._roi_offset[1]
        _dict["roi_offset_y"] = self._roi_offset[0]
        _dict["roi_width"] = self._roi_size[1]
        _dict["roi_height"] = self._roi_size[0]
        return _dict
