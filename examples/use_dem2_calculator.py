"""Example script on how to use the System calculator script."""

import logging
import os

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
)
from src.dem_2_3d_label_free.dem2_common.dem2_calculator import Dem2SystemCalculator

from src.dem_2_3d_label_free.__globals__ import __config__


def use_dem2_calculator():
    log = logging.getLogger(os.path.basename(__file__))

    # Instantiate system calculator with config.yml.
    sys_calc = Dem2SystemCalculator(__config__)

    # Log all system information:

    log.info(
        f"For:\nwavelength_min={sys_calc.lambda_min} nm,\n"
        f"wavelength_max={sys_calc.lambda_max} nm,\n"
        f"depth_max={sys_calc.z_max} um,\n"
        f"time_exposure={sys_calc.t_exp} ms,\n"
        f"time_readout={sys_calc.t_read} ms,\n"
        "---------------------------------------"
    )

    log.info("No. of samples (uniform k-sampling): " + str(sys_calc.sample_no))

    log.info("Total time for one sample position [s]: " + str(sys_calc.total_time))

    log.info(
        "Sweep speed [nm/s]: "
        + str(sys_calc.sweep_speed)
        + (" (NOTE: Min speed is 0.1 nm/s)" if sys_calc.sweep_speed < 0.1 else "")
        + (" (NOTE: Max speed is 10,000 nm/s)" if sys_calc.sweep_speed > 10000 else "")
    )

    log.info("Axial Bandwidth [um]: " + str(sys_calc.axial_bandwidth))

    log.info(
        "Wavelength bandwidth over exposure time [nm]: "
        + str(sys_calc.exposure_lambda_range)
    )

    log.info(
        "Total Axial Bandwidth [um]: "
        + str(sys_calc.axial_bandwidth + (sys_calc.exposure_lambda_range / 1000))
    )

    log.info("Lateral FOV [mm]: " + str(sys_calc.lateral_fov))

    log.info("Lateral Spacing [um]: " + str(sys_calc.lateral_spacing))

    log.info("Lateral resolution [um]: " + str(sys_calc.lateral_resolution))


def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Running use_dem2_calculator().")

    # run the calculator
    use_dem2_calculator()


if __name__ == "__main__":
    main()
