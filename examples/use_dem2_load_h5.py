from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt
from mkl_fft import fft2
from numpy.fft.helper import fftshift

from src.dem_2_3d_label_free.dem2_common.dem2_helper import setup_directories, setup_root_logger
from src.dem_2_3d_label_free.__globals__ import __datapath__
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2Results

DATA_PATH = Path(__datapath__)

IMG= "usaf_data.h5"

GAMMA = 0.1

SHOW_FT = True

def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Test script setup complete.")

    settings = Dem2Results(load_from_file=str(DATA_PATH/IMG))

    log.info(f"Settings: {settings.settings}")
    log.info(f"B Scan Pat: {settings.b_scan_pattern.as_dict()}")
    log.info(f"Images shape: {settings.images.shape}")

    if not SHOW_FT:
        plt.imshow(settings.images if len(settings.images.shape) == 2 else settings.images[0,:,:])
        plt.show()
        log.info("Done.")
        return

    ft_img = np.fft.fftshift(np.fft.fft2(
        settings.images if len(settings.images.shape) == 2 else settings.images[0, :, :]
    )) #ft and shift to center f image.

    plt.imshow((np.abs(ft_img) ** GAMMA).astype(np.uint8))
    plt.show()

    log.info("Done.")


if __name__ == "__main__":
    main()