"""Helper class to calculate basics of the system."""

import logging
import math
import numpy as np


class Dem2SystemCalculator:
    def __init__(self, config: dict):
        # Non-root logging. See dem2_helper.setup_root_logger() documentation.
        self._log = logging.getLogger(self.__class__.__name__)

        self._cfg = config

        self.lambda_0 = self._cfg["laser"]["wavelength_center"]
        self.lambda_min = self._cfg["laser"]["wavelength_min"]
        self.lambda_max = self._cfg["laser"]["wavelength_max"]
        self.lambda_range = self.lambda_max - self.lambda_min
        self.z_max = self._cfg["system"]["depth_max"]
        self.t_exp = self._cfg["camera"]["time_exposure"]
        self.t_read = self._cfg["camera"]["time_readout"]
        self.mag = self._cfg["system"]["magnification"]
        self.na = self._cfg["system"]["numerical_aperture"]
        self.cam_width = self._cfg["camera"]["lateral_size"]
        self.a_scans = self._cfg["system"]["a-scans"]

    @property
    def sample_no(self):
        """
        Calculate amount of images for lambda range.
        :return: No of images (samples).
        """
        # k-range over k-interval (satisfying Nyquist criterion)
        # um * 1000 = nm
        return (
            (2 * np.pi / self.lambda_min)
            - (2 * np.pi / self.lambda_max)
        ) / (np.pi / (self.z_max * 1000))

    @property
    def total_time(self):
        """
        Calculate total time.
        :return: Total time in seconds.
        """
        if self.t_exp < 0.1:
            raise Exception("Minimum exposure time is 100 us.")
        return (
            (self.t_exp if self.t_exp > self.t_read else self.t_read) / 1000
        ) * self.sample_no

    @property
    def sweep_speed(self):
        """
        Calculate speed to sweep at.
        :return: Sweep speed in nm/s
        """
        return self.lambda_range / self.total_time

    @property
    def axial_bandwidth(self):
        """
        Calculate axial bandwidth for specific swept source.
        :return: Axial bandwidth in um.
        """
        return ((2 * math.log(2)) * (pow(self.lambda_0 / 1000, 2))) / (
            self.lambda_range / 1000
        )

    @property
    def exposure_lambda_range(self):
        """
        Calculate the change the lambda bandwidth over the exposure time.
        :return: Lambda bandwidth over exposure time in nm.
        """
        return (self.t_exp / 1000) * self.sweep_speed

    @property
    def lateral_fov(self):
        """
        Calculate the lateral FOV.
        :return: Lateral FOV in mm.
        """
        return self.cam_width / self.mag

    @property
    def lateral_spacing(self):
        """
        Calculate amount of spacing between A-scans.
        :return: Lateral spacing in um.
        """
        return self.lateral_fov * 1000 / self.a_scans

    @property
    def lateral_resolution(self):
        """
        Calculate the lateral resolution.
        :return: Lateral resolution in um.
        """
        # for full field OCT 0.61
        constant = 0.61
        return (constant * (self.lambda_0 / 1000)) / self.na
