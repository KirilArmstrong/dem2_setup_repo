"""Helper class to calculate basics of the system."""

import logging
import math
import numpy as np

_2_LN2_OVR_PI = 2 * math.log(2) / math.pi


class Dem2SystemCalculator:
    def __init__(self):
        # Non-root logging. See dem2_helper.setup_root_logger() documentation.
        self._log = logging.getLogger(self.__class__.__name__)

    def sample_no(self, lambda_min, lambda_max, z_max):
        """
        Calculate amount of images for lambda range.
        :param lambda_min: Lambda min in nm.
        :param lambda_max: Lambda max in nm.
        :param z_max: Max depth in um.
        :return: No of images (samples).
        """
        # k-range over k-interval (satisfying Nyquist criterion)
        # um * 1000 = nm
        return ((1 / lambda_min) - (1 / lambda_max)) * 2 * (z_max * 1000)

    def total_time(self, t_frame, sample_no):
        """
        Calculate total time.
        :param t_frame: Frame time in ms.
        :param sample_no: Number of images per a scan.
        :return: Total time in seconds.
        """
        return (t_frame / 1000) * sample_no

    def sweep_speed(self, lambda_range, total_time):
        """
        Calculate speed to sweep at.
        :param lambda_range: Wavelength range in nm.
        :param total_time: Total sweep time in seconds.
        :return: Sweep speed in nm/s
        """
        return lambda_range / total_time

    def axial_bandwidth(self, lambda_0, lambda_range):
        """
        Calculate axial bandwidth for specific swept source.
        :param lambda_0: Central lambda in nm.
        :param lambda_range: Delta lambda in nm. (Full sweep range)
        :return: Axial bandwidth in um.
        """
        return (_2_LN2_OVR_PI * (pow(lambda_0 / 1000, 2))) / (lambda_range / 1000)

    def signal_roll_off_depth(self, lambda_0, lambda_instant):
        """
        Calculate signal roll off depth in um. (Coherence length / 2)
        :param lambda_0: Central lambda in nm.
        :param lambda_instant: delta lambda in nm. (Instant bandwidth or bandwidth for 1 image)
        :return: Signal roll off in um.
        """
        return (
            (_2_LN2_OVR_PI * (pow(lambda_0 / 1000, 2))) / (lambda_instant / 1000)
        ) / 2

    def exposure_lambda_range(self, t_exp, sweep_speed):
        """
        Calculate the change the lambda bandwidth over the exposure time.
        :param t_exp: Exposure time in ms.
        :param sweep_speed: Sweep speed in nm/s.
        :return: Lambda bandwidth over exposure time in nm.
        """
        return (t_exp / 1000) * sweep_speed

    def lateral_fov(self, cam_width, mag):
        """
        Calculate the lateral FOV.
        :param cam_width: Camera size in mm.
        :param mag: Magnification.
        :return: Lateral FOV in mm.
        """
        return cam_width / mag

    def lateral_spacing(self, lateral_fov, a_scans):
        """
        Calculate amount of spacing between A-scans.
        :param lateral_fov: Lateral field of view in mm.
        :param a_scans: Number of a scans per b scan.
        :return: Lateral spacing in um.
        """
        return lateral_fov * 1000 / a_scans

    def lateral_resolution(self, lambda_0, na):
        """
        Calculate the lateral resolution.
        :param lambda_0: Central wavelength in nm.
        :param na: Numerical Aperture.
        :return: Lateral resolution in um.
        """
        # for full field OCT 0.61
        constant = 0.61
        return (constant * (lambda_0 / 1000)) / na

    def lambdas_array(
        self, start_lambda: float, end_lambda: float, no_of_images: int
    ) -> np.ndarray:
        """
        Generate a array of lambdas between a start and end that is linear in k-space.
        :param start_lambda: Initial wavelength in nm. i.e. 805.0 nm.
        :param end_lambda: Last wavelength in nm. i.e. 880.0 nm.
        :param no_of_images: Number of images.
        :return: Lambda array.
        """
        k_start = 2 * np.pi / start_lambda
        k_end = 2 * np.pi / end_lambda
        array = np.linspace(k_start, k_end, no_of_images)
        return 2 * np.pi / array

    def pixel_to_um(
        self, pixel_no: float, pixel_size: float = 3.9, magnification: float = 1
    ):
        """
        Calculate the corresponding real size of a number of pixels in um.
        :param pixel_size: Size of pixel in um.
        :param pixel_no: Number of pixels.
        :param magnification: Magnification if applicable.
        :return: Distance in um.
        """
        return (pixel_no * pixel_size) / magnification
