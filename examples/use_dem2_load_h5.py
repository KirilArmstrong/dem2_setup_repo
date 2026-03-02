from pathlib import Path

from matplotlib import pyplot as plt

from src.dem_2_3d_label_free.dem2_common.dem2_helper import setup_directories, setup_root_logger
from src.dem_2_3d_label_free.__globals__ import __datapath__
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2Results

DATA_PATH = Path(__datapath__)

IMG= "image_2026-03-02T15-47-10.h5"

def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Test script setup complete.")

    settings = Dem2Results(load_from_file=str(DATA_PATH/IMG))

    log.info(f"Settings: {settings.settings}")
    log.info(f"B Scan Pat: {settings.b_scan_pattern.as_dict()}")
    log.info(f"Images shape: {settings.images.shape}")

    plt.imshow(settings.images if len(settings.images.shape) == 2 else settings.images[0,:,:])
    plt.show()

    log.info("Done.")


if __name__ == "__main__":
    main()