"""Example script on how to use the Demonstrator 2 Controller."""
from pathlib import Path

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
)
from src.dem_2_3d_label_free.dem2_common.dem2_processor import Dem2Processor
from src.dem_2_3d_label_free.__globals__ import __datapath__

DATA_PATH = Path(__datapath__)
FILE_NAME = Path("filename.h5")

def use_processor():
    """Demo script"""
    processor = Dem2Processor(FILE_NAME, DATA_PATH, "images")
    try:
        # Convert a tif file to h5:
        processor.convert_tif_to_h5()
    except: pass  # will error if not tif, so for demo purposes, it handles the error.

    # Just plot the FFT of the image. Useful to find 1st order center point.
    processor.plot_ft()

    # Reconstruct the object field and plot everything. 1st order center and width/height.
    processor.reconstruct(centre=(700,500), width=100, height=100)


def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Test script setup complete.")

    # Demo script
    use_processor()

    log.info("Done.")


if __name__ == "__main__":
    main()