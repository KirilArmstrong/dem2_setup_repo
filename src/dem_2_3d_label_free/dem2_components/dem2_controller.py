"""Control class for the Demonstrator 2."""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

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


class Dem2Controller(Dem2SystemCalculator):
    """Control class for the Demonstrator 2."""

    def __init__(self, config: dict):
        """
        Demonstrator 2 Controller init function.
        :param config: Demonstrator 2 configuration.
        """
        super().__init__()
        self._cfg = config
        self._log = logging.getLogger(self.__class__.__name__)
        self._state = Dem2State.DISCONNECTED

        # System property setup
        self.z_max = self._cfg["system"]["depth_max"]
        self.mag: float = self._cfg["system"]["magnification"]
        self.na = self._cfg["system"]["numerical_aperture"]

        # Device setup
        self.stage = Dem2Stage(self._cfg["stage"])
        self.camera = Dem2Camera(self._cfg["camera"])
        self.cam_packet = Dem2SweepPacket(str(Path(__datapath__) / "packet.h5"))
        self.cam_capturer = Dem2Capturer(self.camera, self.cam_packet, 0)
        self.laser = Dem2Laser(self._cfg["laser"])
        self.update_burst_properties()

        self.bscan_pattern: Dem2BScanPattern | None = None

        self.capture_next_live_frame = False

    def update_burst_properties(self):
        self.camera.samples_a_scan = self.sample_no(
            self.laser.wavelength_min, self.laser.wavelength_max, self.z_max
        )
        self._log.info(f"update_burst_properties: Frames: {self.camera.samples_a_scan}")
        self.laser.total_sweep_time = self.total_time(
            self.camera.t_frame,
            self.camera.samples_a_scan,
        )
        self._log.info(
            f"update_burst_properties: total_sweep_time: {self.laser.total_sweep_time} for t_frame: {self.camera.t_frame}"
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
        self.stage.initialize(calibration_wait_time=stage_wait_time)
        self.camera.initialize()  # First camera to set laser sweep time!
        self.laser.initialize()
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
            self.run_single_sweep(packet=sweep_exp)
            sweep_exp.set_attributes(self.settings)
            pos += 1
            eta = (
                (start_time - datetime.now()) * (bsp.a_scans_b_scan - i)
            ).total_seconds()
            self._log.info(
                f"Running full scan pattern... ETA: {(eta // 60):02d} min and {(eta % 60):02d} s."
            )
        return sweep_exp

    def run_single_sweep(
        self, filename: str = "", packet: Dem2SweepPacket | None = None
    ) -> Dem2SweepPacket | np.ndarray:
        """
        Run a single laser sweep (single a-scan).
        :param filename: packet filename to save too. Set empty to get back an array.
        :param packet: packet to save too. Set None to get back an array.
        """
        self._log.info("Preparing capturer...")
        self.cam_capturer = Dem2Capturer(
            self.camera,
            packet
            if packet is not None
            else (Dem2SweepPacket(filename) if filename else None),
            int(self.camera.samples_a_scan),
        )
        # start camera and set it to listen for laser HIGH.
        self.cam_capturer.start()
        # wait until camera is ready.
        while not self.cam_capturer.waiting:
            continue
        # turn laser on.
        self.laser.toggle_emission()
        # wait until laser finished and camera saved everything to h5
        if self.cam_capturer.is_alive():
            self.cam_capturer.join()
        self._log.info("Capture finished.")
        return self.cam_capturer.packet if filename else self.cam_capturer.array_stack

    def run_multiple_lambdas(
        self,
        filename,
        lambdas: np.ndarray,
        increment_data_set: bool = True,
        data_set_start: int = 1,
    ) -> Dem2SweepPacket:
        """
        Capture single images at multiple CW wavelengths.
        :param filename: File to save data to.
        :param lambdas: Wavelength list in nm.
        :param increment_data_set: Increment the data set for each wavelength.
        :param data_set_start: Starting index of the data sets. Min 1
        :return: Data packet.
        """
        self._log.info(
            f"Running multiple lambdas... increment_data_set={increment_data_set}"
        )
        packet = Dem2SweepPacket(filename)
        for i in range(lambdas.size):
            self._log.info(
                f"Running lambda {lambdas[i]} ({i + 1} of {lambdas.size})..."
            )
            if increment_data_set or i == 0:
                if not increment_data_set:
                    self.camera.start_acquisition()
                packet.data_set = str(i + data_set_start)
                packet.open_file()
            self.laser.send_cw(lambdas[i])
            self.laser.toggle_emission()
            packet.append_frame(self.camera.acquire_single_image(increment_data_set))
            self.laser.kill_emission()
            if increment_data_set or i == lambdas.size - 1:
                packet.close_file()
                attrs = self.settings
                if not increment_data_set:
                    self.camera.stop_acquisition()
                    packet.set_attribute("lambdas", lambdas)
                    attrs.update(packet.get_attributes())
                packet.set_attributes(attrs)
        self._log.info(f"Finished and saved to {filename}.")
        return packet

    def axial_bandwidth(self, lambda_0=None, lambda_range=None) -> float:
        """
        Calculate axial bandwidth for specific swept source.
        :return: Axial bandwidth in um.
        """
        return super().axial_bandwidth(
            self.laser.wavelength_centre if lambda_0 is None else lambda_0,
            (self.laser.wavelength_max - self.laser.wavelength_min)
            if lambda_range is None
            else lambda_range,
        )

    def exposure_lambda_range(self, t_exp=None, sweep_speed=None):
        """
        Calculate the change the lambda bandwidth over the exposure time.
        :return: Lambda bandwidth over exposure time in nm.
        """
        try:
            return super().exposure_lambda_range(
                self.camera.t_exp if t_exp is None else t_exp,
                self.laser.sweep_speed if sweep_speed is None else sweep_speed,
            )
        except Dem2Errors.PropertyNotSetError:
            self._log.warning(
                "Property sweep_speed not set in camera, exposure_lambda_range incalculable."
            )
            return None

    def lateral_resolution(self, lambda_0=None, na=None) -> float:
        """
        Calculate the lateral resolution.
        :return: Lateral resolution in um.
        """
        return super().lateral_resolution(
            self.laser.wavelength_centre if lambda_0 is None else lambda_0,
            self.na if na is None else na,
        )

    def speckle_size(self, pixel_no_x: float, pixel_no_y: float) -> tuple[float, float]:
        """
        Calculate speckle size based on no. of pixels for each speckle in um.
        :param pixel_no_x: Number of pixels in X.
        :param pixel_no_y: Number of pixels in Y.
        :return: tuple of speckle size in um as (x, y).
        """
        x = self.pixel_to_um(pixel_no_x, self.camera.pixel_size[0], self.mag)
        y = self.pixel_to_um(pixel_no_y, self.camera.pixel_size[1], self.mag)
        return x, y

    # Properties

    @property
    def state(self) -> Dem2State:
        return self._state

    @property
    def lateral_fov_as_tuple(self) -> tuple[float, float]:
        """
        Calculate the lateral FOV.
        :return: Lateral FOV in mm.
        """
        return super().lateral_fov(
            self.camera.lateral_size[0], self.mag
        ), super().lateral_fov(self.camera.lateral_size[1], self.mag)

    @property
    def lateral_spacing_as_tuple(self) -> tuple[float, float]:
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
        lat_fov = self.lateral_fov_as_tuple
        return super().lateral_spacing(
            lat_fov[0], self.bscan_pattern.a_scans_b_scan
        ), super().lateral_spacing(lat_fov[1], self.bscan_pattern.a_scans_b_scan)

    @property
    def settings(self) -> dict:
        _dict = {}
        _dict.update(self._cfg)

        _dict["system"]["depth_max"] = self.z_max
        _dict["system"]["magnification"] = self.mag
        _dict["system"]["numerical_aperture"] = self.na
        _dict["stage"] = self.stage.settings
        _dict["camera"] = self.camera.settings
        _dict["laser"] = self.laser.settings
        return _dict
