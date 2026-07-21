"""Control class for the Demonstrator 2."""

import logging
import math
import time
from datetime import datetime, timedelta
from pathlib import Path


import xiapi
from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern
from src.dem_2_3d_label_free.dem2_common.dem2_calculator import Dem2SystemCalculator
from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.dem_2_3d_label_free.dem2_common.dem2_helper import get_current_timestamp
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import (
    Dem2SweepPacket,
)
from src.dem_2_3d_label_free.dem2_components.dem2_capturer import Dem2Capturer
from src.dem_2_3d_label_free.dem2_devices.dem2_camera import Dem2Camera
from src.dem_2_3d_label_free.dem2_devices.dem2_laser import Dem2Laser
from src.dem_2_3d_label_free.dem2_devices.dem2_stage import Dem2Stage


from src.dem_2_3d_label_free.__globals__ import __datapath__


class Dem2Controller:
    """Control class for the Demonstrator 2."""

    def __init__(self, config: dict):
        """
        Demonstrator 2 Controller init function.
        :param config: Demonstrator 2 configuration.
        """
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED

        # System property setup
        self.z_max = self._cfg["system"]["depth_max"]
        self.mag: float = self._cfg["system"]["magnification"]
        self.na = self._cfg["system"]["numerical_aperture"]

        self.calculator = Dem2SystemCalculator()

        # Device setup
        self.stage = Dem2Stage(self._cfg["stage"])
        self.camera = Dem2Camera(self._cfg["camera"])
        self.cam_packet = Dem2SweepPacket(str(Path(__datapath__) / "packet.h5"))
        self.cam_capturer = Dem2Capturer(self.camera, self.cam_packet, 0)
        self.laser = Dem2Laser(self._cfg["laser"])
        self.update_burst_properties()

        self.bscan_pattern: Dem2BScanPattern | None = None
        self._buffer = xiapi.Image()

        self.capture_next_live_frame = False

    def update_burst_properties(self):
        self.camera.samples_a_scan = self.calculator.sample_no(
            self.laser.wavelength_min, self.laser.wavelength_max, self.z_max
        )
        self.laser.total_sweep_time = self.calculator.total_time(
            self.camera.t_exp,
            self.camera.samples_a_scan,
            self.camera.t_read,
        )

    def connect(self):
        """Connect all devices."""
        self._log.info("Connecting to all decides...")
        if self._state != Dem2State.DISCONNECTED:
            raise Dem2Errors.ControllerError(
                "Already been connected! Disconnect first."
            )
        self.stage.connect()
        self.camera.connect()
        self.laser.connect()
        self._state = Dem2State.CONNECTED

    def disconnect(self):
        """Disconnect all devices."""
        self._log.info("Disconnecting all devices...")
        self.camera.disconnect()
        self.laser.disconnect()
        self.stage.disconnect()
        self._log.info("Disconnected from all devices.")
        self.__init__(self._cfg)

    def initialize(self, stage_wait_time: float = 20):
        """
        Initialize all devices.
        :param stage_wait_time: Time to allow objective removal before stage calibration. Recommended: 20s. Min: 0
        """
        self._log.info("Initialising Demonstrator 2...")
        if self._state != Dem2State.CONNECTED:
            raise Dem2Errors.ControllerError("Must be connected!")
        if stage_wait_time < 0:
            raise Dem2Errors.ControllerError(
                "Stage must be calibrated for Controller to use it! Min stage_wait_time = 0"
            )
        self.laser.initialize()
        self.camera.initialize()
        self.stage.initialize(calibration_wait_time=stage_wait_time)
        self._state = Dem2State.INITIALIZED
        self._log.info("Demonstrator 2 ready! 🎉")

    def run_bscan_pattern(
        self,
        bsp: Dem2BScanPattern,
        save_to_directory_path: str = __datapath__,
        start_pos: int = 1,
    ) -> Dem2SweepPacket:
        """
        Run a bscan_pattern.
        :param bsp: scan pattern
        :param save_to_directory_path: directory to save the experiment to.
        :param start_pos: starting scan pat index. starts at 1 for scan pat index 0
        :return: experiment measurement as Dem2SweepPacket object. (it saves to h5 as it goes.)
        """
        pos = start_pos if 0 < start_pos < bsp.a_scans_b_scan + 1 else 1
        sweep_exp = Dem2SweepPacket(
            save_to_directory_path + "data_" + get_current_timestamp()
        )
        self._log.info("Running full scan pattern... ETA: TBD")

        for i in range(bsp.a_scans_b_scan):
            # allow for resuming experiment
            if i == 0 and pos != 1:
                i = pos - 1
            # time tracking
            start_time = datetime.now()
            # stage movement
            self.stage.move_stage(bsp.x_positions[i], bsp.y_positions[i])
            time_diff = start_time - datetime.now()
            self._log.info(f"Stage moved in {time_diff.total_seconds()} seconds.")
            # if time less than 1ms, wait remaining time for laser to reset.
            if time_diff < timedelta(milliseconds=1) and i != 0:
                self._log.info(
                    "Minimum 1ms pause time required for laser. waiting "
                    f"{(timedelta(milliseconds=1) - time_diff).total_seconds()} s..."
                )
                time.sleep((timedelta(milliseconds=1) - time_diff).total_seconds())
            # create new dataset for current position in scan pattern.
            sweep_exp.data_set = str(pos)
            self._log.info(f"Running sweep {i + 1} of {bsp.a_scans_b_scan + 1}...")
            self.run_single_sweep(sweep_exp)
            pos += 1
            eta = (
                (start_time - datetime.now()) * (bsp.a_scans_b_scan - i)
            ).total_seconds()
            self._log.info(
                f"Running full scan pattern... ETA: {(eta // 60):02d} min and {(eta % 60):02d} s."
            )
        return sweep_exp

    def run_single_sweep(self, packet: Dem2SweepPacket):
        """
        Run a single laser sweep (single a-scan).
        :param packet: packet to save measurements to.
        """
        self._log.info("Preparing capturer...")
        self.cam_capturer = Dem2Capturer(
            self.camera, packet, int(self.camera.samples_a_scan)
        )
        # start camera and set it to listen for laser HIGH.
        self.cam_capturer.start()
        # turn laser on.
        self.laser.toggle_emission()
        self._log.info("Laser on.")
        # wait until laser finished and camera saved everything to h5
        if self.cam_capturer.is_alive():
            self.cam_capturer.join()
        self._log.info("Capture finished.")

    def save(self, save_to_directory_path: str = ""):
        settings = self._cfg
        # todo finish this

    # Properties

    @property
    def state(self) -> Dem2State:
        return self._state

    @property
    def axial_bandwidth(self):
        """
        Calculate axial bandwidth for specific swept source.
        :return: Axial bandwidth in um.
        """
        return ((2 * math.log(2)) * (pow(self.laser._wavelength_centre / 1000, 2))) / (
            self.laser._wavelength_centre / 1000
        )

    @property
    def exposure_lambda_range(self):
        """
        Calculate the change the lambda bandwidth over the exposure time.
        :return: Lambda bandwidth over exposure time in nm.
        """
        return (self.camera.t_exp / 1000) * self.laser.sweep_speed

    @property
    def lateral_fov(self) -> tuple[float, float]:
        """
        Calculate the lateral FOV.
        :return: Lateral FOV in mm.
        """
        return self.camera.lateral_size / self.mag

    @property
    def lateral_spacing(self) -> tuple[float, float]:
        """
        Calculate amount of spacing between A-scans.
        :return: Lateral spacing in um.
        """
        if self.bscan_pattern is None:
            raise Dem2Errors.ControllerError(
                "B_scan_pattern not given to calculate lateral spacing. (no no_of_a_scans)"
            )
        if self.bscan_pattern.a_scans_b_scan == 0:
            raise Dem2Errors.ControllerError(
                "B_scan_pattern's no_of_a_scans is set to 0. Minimum 1 for lateral_spacing calculation."
            )
        return (self.lateral_fov[0] * 1000) / self.bscan_pattern.a_scans_b_scan, (
            self.lateral_fov[1] * 1000
        ) / self.bscan_pattern.a_scans_b_scan

    @property
    def lateral_resolution(self):
        """
        Calculate the lateral resolution.
        :return: Lateral resolution in um.
        """
        # for full field OCT 0.61
        constant = 0.61
        return (constant * (self.laser._wavelength_centre / 1000)) / self.na

    @property
    def settings(self) -> dict:
        _dict = {}
        _dict.update(self._cfg)
        _dict["stage"] = self.stage.settings
        _dict["camera"] = self.camera.settings
        _dict["laser"] = self.laser.settings
        return _dict
