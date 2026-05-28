"""Control class for the Demonstrator 2."""

import logging
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import xiapi
from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern
from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import (
    Dem2SweepPacket,
    Dem2SweepExperiment,
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
        self.mag = self._cfg["system"]["magnification"]
        self.na = self._cfg["system"]["numerical_aperture"]

        # Device setup
        self.stage = Dem2Stage(
            self._cfg["stage"]
        )
        self.camera = Dem2Camera(self._cfg["camera"])
        self.cam_packet = Dem2SweepPacket(str(Path(__datapath__) / "packet.h5"))
        self.cam_capturer = Dem2Capturer(self.camera, self.cam_packet)
        self.laser = Dem2Laser(self._cfg["laser"])

        self.camera.samples_a_scan = math.floor(
            (
                (2 * np.pi / self.laser._wavelength_min)
                - (2 * np.pi / self.laser._wavelength_max)
            )
            / (np.pi / (self.z_max * 1000))
        )
        self.laser.total_sweep_time = (
            self.camera.t_frame / 1000
        ) * self.camera.samples_a_scan

        self.bscan_pattern: Dem2BScanPattern | None = None
        self._buffer = xiapi.Image()

        self.capture_next_live_frame = False

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
        self.camera.initialize()
        self.laser.initialize()
        self.stage.initialize(calibration_wait_time=stage_wait_time)
        self._state = Dem2State.INITIALIZED
        self._log.info("Demonstrator 2 ready! 🎉")

    def run_bscan_pattern(
        self, bsp: Dem2BScanPattern, save_to_directory_path: str = __datapath__
    ) -> Dem2SweepExperiment:
        """Run a bscan_pattern."""
        sweep_exp = Dem2SweepExperiment()
        for i in range(bsp.a_scans_b_scan):
            start_time = datetime.now()
            self.stage.move_stage(bsp.x_positions[i], bsp.y_positions[i])
            time_diff = start_time - datetime.now()
            self._log.info(f"Stage moved in {time_diff.total_seconds()} seconds.")
            # if time less than 1ms, wait remaining time for laser to chill out.
            if time_diff < timedelta(milliseconds=1) and i != 0:
                self._log.info(
                    "Minimum 1ms pause time required for laser. waiting "
                    f"{(timedelta(milliseconds=1) - time_diff).total_seconds()} s..."
                )
                time.sleep((timedelta(milliseconds=1) - time_diff).total_seconds())
            sweep_exp.packets.append(self.run_single_sweep(os.path.join(save_to_directory_path, f"packet_sample{i}")))
        if save_to_directory_path:
            sweep_exp.save(os.path.join(save_to_directory_path, "sweep_exp"))
        return sweep_exp

    def run_single_sweep(self, save_to_directory_path: str = "") -> Dem2SweepPacket:
        """Run a single laser sweep (single a-scan)."""
        self.camera.start_acquisition()
        # start the laser sweep
        self.camera.get_image(
            self._buffer, timeout=(self.laser.total_sweep_time + 5) * 1000
        )
        packet = Dem2SweepPacket()
        # beep boop, do the laser.
        # save to save_to_directory_path
        # return Dem2SweepPacket
        return packet

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
    def lateral_fov(self):
        """
        Calculate the lateral FOV.
        :return: Lateral FOV in mm.
        """
        return self.camera.lateral_size / self.mag

    @property
    def lateral_spacing(self):
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
        return self.lateral_fov * 1000 / self.bscan_pattern.a_scans_b_scan

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
