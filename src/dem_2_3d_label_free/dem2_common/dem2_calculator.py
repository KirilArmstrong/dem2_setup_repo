"""Helper class to calculate basics of the system."""

import logging
import math
import numpy as np


class Dem2SystemCalculator:
    def __init__(self):
        # Non-root logging. See dem2_helper.setup_root_logger() documentation.
        self._log = logging.getLogger(self.__class__.__name__)
        self._ln2overpi = (2 * math.log(2) / math.pi)

    def sample_no(self,lambda_min, lambda_max, z_max):
        """
        Calculate amount of images for lambda range.
        :return: No of images (samples).
        """
        # k-range over k-interval (satisfying Nyquist criterion)
        # um * 1000 = nm
        return (
            (1 / lambda_min)
            - (1 / lambda_max)
        ) * 2 * (z_max * 1000)


    def total_time(self,t_frame,sample_no):
        """
        Calculate total time.
        :return: Total time in seconds.
        """
        return (
                t_frame / 1000
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
        :param lambda_0: Central lambda in nm.
        :param lambda_range: Delta lambda in nm. (Full sweep range)
        :return: Axial bandwidth in um.
        """
        return (self._ln2overpi * (pow(lambda_0 / 1000, 2))) / (
            lambda_range / 1000
        )


    def signal_roll_off_depth(self, lambda_0, lambda_instant):
        """
        Calculate signal roll off depth in um. (Coherence length / 2)
        :param lambda_0: Central lambda in nm.
        :param lambda_instant: delta lambda in nm. (Instant bandwidth or bandwidth for 1 image)
        :return: Signal roll off in um.
        """
        return ((self._ln2overpi * (pow(lambda_0 / 1000, 2))) / (
            lambda_instant / 1000
        )) / 2


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

    def lambdas_array(self, start_lambda: float, end_lambda: float, no_of_images: int) -> np.ndarray:
        """
        Generate a array of lambdas between a start and end that is linear in k-space.
        :param start_lambda: Initial wavelength in nm. i.e. 805.0 nm.
        :param end_lambda: Last wavelength in nm. i.e. 880.0 nm.
        :param no_of_images: Number of images.
        :return: Lambda array.
        """
        k_start = 2*np.pi/start_lambda
        k_end = 2*np.pi/end_lambda
        array = np.linspace(k_start, k_end, no_of_images)
        return 2*np.pi/array