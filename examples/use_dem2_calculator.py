"""Example script on how to use the System calculator script."""

import logging
import os

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
)

from src.dem_2_3d_label_free.__globals__ import __config__
from src.dem_2_3d_label_free.dem2_components.dem2_controller import Dem2Controller


def use_dem2_calculator():
    log = logging.getLogger(os.path.basename(__file__))

    # Instantiate system calculator with config.yml.
    cont = Dem2Controller(__config__)

    # Log all system information:

    log.info(
        f"For:\nwavelength_min={cont.laser.wavelength_min} nm,\n"
        f"wavelength_max={cont.laser.wavelength_max} nm,\n"
        f"depth_max={cont.z_max} um,\n"
        f"time_exposure={cont.camera.t_exp} ms,\n"
        f"time_idle={cont.camera.t_idle} ms,\n"
        f"time_readout={cont.camera.t_read} ms,\n"
        "---------------------------------------"
    )

    log.info(
        "No. of samples (uniform k-sampling): "
        + str(
            cont.sample_no(
                cont.laser.wavelength_min, cont.laser.wavelength_max, cont.z_max
            )
        )
    )

    log.info(
        "Total time for one sample position [s]: "
        + str(cont.total_time(cont.camera.t_frame, cont.camera.samples_a_scan))
    )

    log.info(
        "Sweep speed [nm/s]: "
        + str(cont.laser.sweep_speed)
        + (" (NOTE: Min speed is 0.1 nm/s)" if cont.laser.sweep_speed < 0.1 else "")
        + (
            " (NOTE: Max speed is 10,000 nm/s)"
            if cont.laser.sweep_speed > 10000
            else ""
        )
    )

    log.info("Axial Bandwidth [um]: " + str(cont.axial_bandwidth))

    log.info(
        "Wavelength bandwidth over exposure time [nm]: "
        + str(cont.exposure_lambda_range())
    )

    log.info(
        "Total Axial Bandwidth [um]: "
        + str(cont.axial_bandwidth() + (cont.exposure_lambda_range() / 1000))
    )

    log.info("Lateral FOV [mm]: " + str(cont.lateral_fov))

    log.info("Lateral Spacing [um]: " + str(cont.lateral_spacing))

    log.info("Lateral resolution [um]: " + str(cont.lateral_resolution))


def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Running use_dem2_calculator().")

    # run the calculator
    use_dem2_calculator()


if __name__ == "__main__":
    main()
