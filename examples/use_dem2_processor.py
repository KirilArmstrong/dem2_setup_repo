"""Example script on how to use the Demonstrator 2 Controller."""
import time
from pathlib import Path
from matplotlib import pyplot as plt

import numpy as np

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
    collect_h5_contents,
)
from src.dem_2_3d_label_free.dem2_common.dem2_processor import Dem2Processor
from src.dem_2_3d_label_free.__globals__ import __datapath__
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2SweepPacket

# DATA_PATH = Path(__datapath__)
# FILE_NAME = Path("filename.h5")

DATA_PATH = Path("C:/Users/ZOKARMST/OneDrive - Carl Zeiss AG/PycharmProjects/kirils_playground/data")
# FILE_NAME = Path("dem2") / "26-06-05" / "usaf.h5"
FILE_NAME = Path("dem2") / "26-06-12" / "collimated_via_eye_2.h5"

# DATA_PATH = Path("D:/Alignment/")
# FILE_NAME = Path("26-06-16") / "scotch_stairs.h5"
# FILE_NAME = Path("26-06-16") / "mirror.h5"

def prep_zernike(processor: Dem2Processor, array: np.ndarray, centre: tuple[int,int]|None=None, radius:int|None=None):
    cx = int(input("Centre X: ")) if centre is None else centre[1]
    cy = int(input("Centre Y: ")) if centre is None else centre[0]
    r = int(input("Radius: ")) if radius is None else radius
    return processor.get_zernike_coeffs(array, (cy, cx), r)


def recon_zs(log, processor, centre, w, h, z_slice):
    roi_bool = input("Roi? y/n: ")
    roi = None
    processor.set_attribute("roi", None)
    if roi_bool.lower() == "y":
        cor_bool = input("Plot reconstruction for roi? y/n: ")
        if cor_bool.lower() == "y":
            processor.reconstruct(
                centre=centre, width=w, height=h, plot=True, z_slice=z_slice
            )
        x1 = int(input("X start: "))
        x2 = int(input("X end: "))
        y1 = int(input("Y start: "))
        y2 = int(input("Y end: "))
        roi = (slice(x1, x2), slice(y1, y2))
        processor.plot_ft(roi=roi, z_index=z_slice)
        cx = int(input("Start Centre X: "))
        cy = int(input("Start Centre Y: "))
        centre = (cy, cx)
        w = int(input("Width: "))
        h = int(input("Height: "))
    processor.plot_ft(roi=roi, z_index=processor.shape[0]-1)
    cx = int(input("End Centre X: "))
    cy = int(input("End Centre Y: "))
    centre2 = (cy,cx)
    y = np.linspace(centre[0], centre2[0], processor.shape[0]-z_slice).astype(int)
    x = np.linspace(centre[1], centre2[1], processor.shape[0]-z_slice).astype(int)
    log.info("Beginning full reconstruction...")
    packet = Dem2SweepPacket(
        str(DATA_PATH / FILE_NAME)[:-3] + "_recon.h5", "1", processor.get_attributes()
    )
    packet.open_file()
    rng = processor.shape[0] - z_slice
    for i in range(rng):
        t1 = time.time()
        packet.append_frame(
            abs(
                processor.reconstruct(
                    roi=roi,
                    centre=(y[i],x[i]),
                    width=w,
                    height=h,
                    plot=False,
                    z_slice=z_slice + i,
                )
            )
        )
        dt = (time.time() - t1) * (rng - i)
        log.info(f"{i / rng * 100}%, ETA: {int(dt // 60)} mins {int(dt % 60)} s.")
    packet.close_file()
    packet.set_attributes()

def use_processor(log):
    """Demo script"""


    processor = Dem2Processor(FILE_NAME, DATA_PATH, "1")
    try:
        # Convert a tif file to h5:
        processor.convert_tif_to_h5()
    except: pass  # will error if not tif, so for demo purposes, it handles the error.

    log.info(collect_h5_contents(processor.path))

    # start_pos = ()

    if OCT_RECON:
        oct_recon = processor.oct_reconstruct(processor[:,Y,:])
        # oct_recon = oct_recon[:oct_recon.shape[0]//2,:]
        processor._prep_plot(oct_recon, "OCT Recon", gamma=GAMMA)
        plt.show()
        return
    # processor.rename_dataset("images", "1")

    # Just plot the FFT of the image. Useful to find 1st order center point.
    cor_bool = input("Plot reconstruction? y/n: ")
    cor_bool = True if cor_bool.lower() == "y" else False
    recon_all_z_bool = False
    if len(processor.shape) == 3:
        recon_all_z_bool = input("reconstruct all z? y/n: ")
        recon_all_z_bool = True if recon_all_z_bool.lower() == "y" else False
    z_slice = input("z slice "+("(start)" if recon_all_z_bool else "")+": ")
    if not z_slice:
        z_slice = 1
    else:
        z_slice = int(z_slice)
    # processor.plot_ft(z_index=z_slice)
    try:
        if RAISE or input("Change centre? (y/n):").lower()=="y":
            raise "Error"
        #
        #     # Reconstruct the object field and plot everything. 1st order center and width/height.
        #     # processor.reconstruct(centre=(766,758), width=600, height=600, z_slice=45)
        centre = None
        w = None #None for off
        h = None # None for off
        # centre = (y,x)
        # w = w
        # h = h
        if centre is not None or w is not None or h is not None:
            confirm = input("Really overwrite existing reconstruction params? y/n: ")
            if confirm.lower() != "y":
                return
        if not recon_all_z_bool:
            recon_arr = processor.reconstruct(
                centre=centre, width=w, height=h, plot=cor_bool, z_slice=z_slice
            )
        else:
            recon_zs(log, processor, centre, w, h, z_slice)
            return

    # return
    # try:
    #     y=1
    #     prep_zernike(processor, recon_arr) # (1465,2255),r=1125
    except:
        processor.plot_ft(z_index=z_slice)
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
        centre = (cy,cx)
        w = int(input("Width: "))
        h = int(input("Height: "))
        if not recon_all_z_bool:
            recon_arr = processor.reconstruct(centre=centre, width=w, height=h, plot=cor_bool, z_slice=z_slice)
        else:
            recon_zs(log, processor, centre, w, h, z_slice)
            return
    # a, N = prep_zernike(processor, recon_arr, centre=(1620, 2455), radius=1550)
    # a, N = prep_zernike(processor, recon_arr, centre=(1650, 2355), radius=150)

    cor_bool = input("Correlate recon_arr? y/n: ")
    if cor_bool.lower() == "y":
        coefs = processor.determine_speckle_size((slice(2400,2600), slice(2330,2530)),recon_arr)

        plt.figure()
        plt.plot(coefs[0,:], label="X correlation coefs")
        plt.grid()
        plt.legend()
        plt.title("X correlation coefs")
        plt.figure()
        plt.plot(coefs[1,:], label="Y correlation coefs")
        plt.grid()
        plt.legend()
        plt.title("Y correlation coefs")
        plt.show()


    zer_bool = input("Zernike estimation? y/n: ")
    if zer_bool.lower() == "y":
        a, N = prep_zernike(processor, recon_arr, centre=(2070, 2410), radius=1300)
        # a, N = prep_zernike(processor, processor.ft(recon_arr), centre=(1712, 2352), radius=145)

        a_no_tdf = a.copy()
        # a_no_tdf[1] = 0.0  # Noll 2  (tilt)
        # a_no_tdf[2] = 0.0  # Noll 3  (tilt)
        # a_no_tdf[3] = 0.0  # Noll 4  (defocus)

        wave_no_tdf, inside = processor.reconstruct_from_zernikes(a_no_tdf, max_noll=len(a), N=N)

        plt.figure()
        plt.imshow(wave_no_tdf, cmap="twilight", origin="lower")
        plt.colorbar(label="Phase [rad]")
        plt.title("Wavefront Estimate")
        plt.show()


def main():
    # Root setup.
    setup_directories()
    log = setup_root_logger(__file__)
    log.info("Test script setup complete.")

    # Demo script
    use_processor(log)

    log.info("Done.")


if __name__ == "__main__":
    main()