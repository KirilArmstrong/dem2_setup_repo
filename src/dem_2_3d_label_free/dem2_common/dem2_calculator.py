"""Helper class to calculate basics of the system."""

import logging
import math
import numpy as np


class Dem2SystemCalculator:
    def __init__(self):
        # Non-root logging. See dem2_helper.setup_root_logger() documentation.
        self._log = logging.getLogger(self.__class__.__name__)

    def sample_no(self,lambda_min, lambda_max, z_max):
        """
        Calculate amount of images for lambda range.
        :return: No of images (samples).
        """
        # k-range over k-interval (satisfying Nyquist criterion)
        # um * 1000 = nm
        return (
            (2 * np.pi / lambda_min)
            - (2 * np.pi / lambda_max)
        ) / (np.pi / (z_max * 1000))


    def total_time(self,t_exp,sample_no,t_read=3.02):
        """
        Calculate total time.
        :return: Total time in seconds.
        """
        if t_exp < 0.1:
            raise Exception("Minimum exposure time is 100 us.")
        return (
            (t_exp if t_exp > t_read else t_read) / 1000
        ) * sample_no


    def sweep_speed(self,lambda_range,total_time):
        """
        Calculate speed to sweep at.
        :return: Sweep speed in nm/s
        """
        return lambda_range / total_time


    def axial_bandwidth(self,lambda_0,lambda_range):
        """
        Calculate axial bandwidth for specific swept source.
        :return: Axial bandwidth in um.
        """
        return ((2 * math.log(2)) * (pow(lambda_0 / 1000, 2))) / (
            lambda_range / 1000
        )


    def exposure_lambda_range(self, t_exp, sweep_speed):
        """
        Calculate the change the lambda bandwidth over the exposure time.
        :return: Lambda bandwidth over exposure time in nm.
        """
        return (t_exp / 1000) * sweep_speed


    def lateral_fov(self, cam_width, mag):
        """
        Calculate the lateral FOV.
        :return: Lateral FOV in mm.
        """
        return cam_width / mag


    def lateral_spacing(self, lateral_fov, a_scans):
        """
        Calculate amount of spacing between A-scans.
        :return: Lateral spacing in um.
        """
        return lateral_fov * 1000 / a_scans


    def lateral_resolution(self, lambda_0, na):
        """
        Calculate the lateral resolution.
        :return: Lateral resolution in um.
        """
        # for full field OCT 0.61
        constant = 0.61
        return (constant * (lambda_0 / 1000)) / na
