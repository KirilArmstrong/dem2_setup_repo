"""Example script on how to use the Demonstrator 2 Controller."""
import time

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
    load_config_file,
)
from src.dem_2_3d_label_free.dem2_components.dem2_controller import Dem2Controller
from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern
from src.dem_2_3d_label_free.__globals__ import __config__


CONFIG = __config__  # default config.yml file in ~/config.
# CONFIG = load_config_file("path to config yml file here")

B_SCAN_PATTERN_FILEPATH = "line_bsp.yml"


def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Test script setup complete.")

    # Setup controller with config/configs.yml.
    controller = Dem2Controller(CONFIG)
    log.info(
        "Demonstrator 2 Controller instantiated. Settings loaded:\n"
        f"no_of_images={controller.camera.samples_a_scan},\n"
        f"sweep_speed={controller.laser.sweep_speed} nm/s,\n"
        f"sweep_time={controller.laser.total_sweep_time} s,\n"
        f"wavelength_min={controller.laser._wavelength_min} nm,\n"
        f"wavelength_max={controller.laser._wavelength_min} nm,\n"
        f"depth_max={controller.z_max} um,\n"
        f"time_exposure={controller.camera.t_exp} ms,\n"
        f"time_readout={controller.camera.t_read} ms,\n"
        "---------------------------------------"
    )
    controller.stage.connect()
    controller.stage.initialize(1)
    log.info("Stage initialized and calibrated.")
    time.sleep(5)
    log.info("Running scan pattern...")
    bsp = Dem2BScanPattern()
    bsp.generate_line(0,9000,0,9000,100)
    bsp.as_file(B_SCAN_PATTERN_FILEPATH)
    controller.stage.b_scan_pattern = bsp
    controller.stage.run_b_scan_pattern()
    log.info("Finished scan pattern, shutting down...")
    time.sleep(1)
    controller.stage.disconnect()

    log.info("Done.")


if __name__ == "__main__":
    main()