"""Example script on how to use the Demonstrator 2 Controller."""
from pathlib import Path
from matplotlib import pyplot as plt

import numpy as np

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
)
from src.dem_2_3d_label_free.dem2_common.dem2_processor import Dem2Processor
from src.dem_2_3d_label_free.__globals__ import __datapath__

# DATA_PATH = Path(__datapath__)
# FILE_NAME = Path("filename.h5")

DATA_PATH = Path("C:/Users/ZOKARMST/OneDrive - Carl Zeiss AG/PycharmProjects/kirils_playground/data")
# FILE_NAME = Path("dem2") / "26-06-05" / "usaf.h5"
FILE_NAME = Path("dem2") / "26-06-12" / "collimated_via_eye_2.h5"

# DATA_PATH = Path("D:/Alignment/")
# FILE_NAME = Path("26-06-16") / "scotch_stairs.h5"
# FILE_NAME = Path("26-06-16") / "mirror.h5"

def prep_zernike(processor: Dem2Processor, array: np.ndarray, centre: tuple[int,int]|None=None, radius:int|None=None):
        cx = int(input("Centre X: ")) if centre is None else centre[0]
        cy = int(input("Centre Y: ")) if centre is None else centre[1]
        r = int(input("Radius: ")) if radius is None else radius
        processor.get_zernike_coeffs(array, (cy,cx), r)

def use_processor():
    """Demo script"""
    processor = Dem2Processor(FILE_NAME, DATA_PATH, "1")
    # try:
    #     # Convert a tif file to h5:
    #     processor.convert_tif_to_h5()
    # except: pass  # will error if not tif, so for demo purposes, it handles the error.

    # Just plot the FFT of the image. Useful to find 1st order center point.
    # processor.plot_ft()
    # try:
    #
    #     # Reconstruct the object field and plot everything. 1st order center and width/height.
    #     # processor.reconstruct(centre=(766,758), width=600, height=600, z_slice=45)
    # recon_arr = processor.reconstruct(height=60)
    # # prep_zernike(processor, recon_arr) # (1465,2255),r=1125
    #
    #
    # except:
    processor.plot_ft()
    plane = input("Speckle wave? y/n: ")
    if plane.lower() == "y":
        cx = int(input("Centre X: "))
        cy = int(input("Centre Y: "))
        w = int(input("Width: "))
        h = int(input("Height: "))
        half_w = w // 2
        half_h = h // 2

        roi = (
            slice(cy - half_h, cy + half_h),
            slice(cx - half_w, cx + half_w),
        )

        ft_arr = processor.ft()
        processor._prep_plot(ft_arr[roi[0],roi[1]], "FFTed Image", gamma=0.05)
        plt.show()
    cx = int(input("Centre X: "))
    cy = int(input("Centre Y: "))
    w = int(input("Width: "))
    h = int(input("Height: "))
    z = input("z slice: ")
    if not z:
        z = 1
    else:
        z = int(z)
    recon_arr = processor.reconstruct(centre=(cy,cx), width=w, height=h, z_slice=z)
    # prep_zernike(processor, recon_arr)


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