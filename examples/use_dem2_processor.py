"""Example script on how to use the Demonstrator 2 Controller."""

import time
from pathlib import Path
from matplotlib import pyplot as plt

import numpy as np
import cupy as cp

from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_directories,
    setup_root_logger,
    collect_h5_contents,
    oct_reconstruct,
)
from src.dem_2_3d_label_free.dem2_common.dem2_processor import Dem2Processor
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


SEE_ZS = None # [0, 45, 99, 140, 340, 400, 422]

def determine_properties(processor, centre, w, h, z_slice):
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
    processor.plot_ft(roi=roi, z_index=processor.shape[0] - 1)
    cx = int(input("End Centre X: "))
    cy = int(input("End Centre Y: "))
    centre2 = (cy, cx)
    y = np.linspace(centre[0], centre2[0], processor.shape[0] - z_slice).astype(int)
    x = np.linspace(centre[1], centre2[1], processor.shape[0] - z_slice).astype(int)
    return roi, y, x


def _estimate_batch_size(H, W, safety=0.5):
    """Rough per-image GPU memory estimate for spectra-only mode."""
    free, _ = cp.cuda.Device().mem_info
    # input float32 + Fshift complex64 + padded complex64
    bytes_per_image = H * W * 4 + H * W * 8 + H * W * 8
    return max(1, int(free * safety / bytes_per_image))

def _process_batch_along_z(imgs_batch, pad_dz=0):
    imgs_batch = cp.asarray(imgs_batch, dtype=cp.float32)
    # dy = imgs_batch.shape[0] // 2 if pad is None else pad
    if pad_dz != 0:
        y_dim = imgs_batch.shape[1]
        x_dim = imgs_batch.shape[2]
        pad_top = cp.zeros((pad_dz, y_dim, x_dim), dtype=imgs_batch.dtype)
        pad_bottom = cp.zeros((pad_dz, y_dim, x_dim), dtype=imgs_batch.dtype)
        arr_padded = np.vstack([pad_top, imgs_batch, pad_bottom])
        return cp.fft.fftshift(cp.fft.fft(arr_padded, axis=0), axes=0)
    return cp.fft.fftshift(cp.fft.fft(imgs_batch, axis=0), axes=0)

def _process_batch(imgs_batch, cx, cy, w, h):
    """
    imgs_batch : (B, H, W)  (NumPy or CuPy)
    cx, cy     : length-B array of integer centers
    returns:
        spectra : (B, H, W) complex64, crop embedded in centre
        images  : (B, H, W) complex64 if compute_image else None
    """
    imgs_batch = cp.asarray(imgs_batch, dtype=cp.float32)

    # chain fftshift(fft2(...)) so the unshifted FFT is freed immediately
    Fshift = cp.fft.fftshift(cp.fft.fft2(imgs_batch, axes=(1, 2)), axes=(1, 2))
    B, H, W = Fshift.shape

    cx = cp.asarray(cx, dtype=cp.int64)
    cy = cp.asarray(cy, dtype=cp.int64)

    dx = cp.arange(-w // 2, w // 2, dtype=cp.int64)
    dy = cp.arange(-h // 2, h // 2, dtype=cp.int64)
    OX, OY = cp.meshgrid(dx, dy, indexing="xy")

    x_idx = cx[:, None, None] + OX[None, :, :]
    y_idx = cy[:, None, None] + OY[None, :, :]
    x_idx_c = cp.clip(x_idx, 0, W - 1)
    y_idx_c = cp.clip(y_idx, 0, H - 1)

    crop = Fshift[cp.arange(B)[:, None, None], y_idx_c, x_idx_c]  # (B, h, w)

def recon_zs(
    log,
    processor,
    centre,
    w,
    h,
    z_slice: int = 0,
    cuda_version: bool = False,
    dset: str = "1",
):
    roi, y, x = determine_properties(processor, centre, w, h, z_slice)
    log.info("Beginning full reconstruction...")
    packet = Dem2SweepPacket(
        str(DATA_PATH / FILE_NAME)[:-3] + "_recon.h5", "1", processor.get_attributes()
    )
    packet.open_file()
    if cuda_version:
        # If you can keep the slice in RAM; otherwise pass the h5py Dataset directly
        # imgs = processor[
        #     z_slice:,
        #     roi[0] if roi is not None else slice(None),
        #     roi[1] if roi is not None else slice(None),
        # ]
        log.info("This'll take a while...")
        Z = processor.shape[0]
        y_roi, x_roi = roi[0] if roi is not None else slice(None), roi[1] if roi is not None else slice(None)
        H = processor[0,y_roi,0].shape[0]
        W = processor[0,0,x_roi].shape[0]
        # imgs = holography_full_recon(processor[z_slice:,roi[0] if roi is not None else slice(None),roi[1] if roi is not None else slice(None)], np.array([y,x]), w, h)
        # packet.set_array(imgs)
        # process and stream to the packet's HDF5 file
        ds = packet.prepare_dataset(
            (Z - z_slice, H, W),
            dtype=np.complex64,
            data_set=dset,
        )

        cen = np.array([y, x])  # shape (2, Z)
        batch_size = _estimate_batch_size(H, W)

        for start in range(z_slice, Z, batch_size):
            t1 = time.time()
            end = min(start + batch_size, Z)
            images = _process_batch(
                processor[start:end, y_roi, x_roi],
                cen[0, start:end],
                cen[1, start:end],
                w,
                h,
            )
            packet.write_batch(start, cp.asnumpy(images), data_set=dset)
            del images
            cp.get_default_memory_pool().free_all_blocks()

            dt = (time.time() - t1) * ((Z - end)/batch_size)
            log.info(f"{start}:{end} / {Z} " + f"{int(end / Z * 100)}%, ETA: {int(dt // 60)} mins {int(dt % 60)} s.")
        packet.close_file()
        packet.set_attributes()
        return
    rng = processor.shape[0] - z_slice
    for i in range(rng):
        if SEE_ZS is not None:
            if z_slice + i not in SEE_ZS:
                continue
        t1 = time.time()
        packet.append_frame(
            abs(  # DONT USE COMPLEX!
                processor.reconstruct(
                    roi=roi,
                    centre=(y[i], x[i]),
                    width=w,
                    height=h,
                    plot=True if z_slice + i in SEE_ZS else False,
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
    except:
        pass  # will error if not tif, so for demo purposes, it handles the error.

    log.info(collect_h5_contents(processor.path))

    # start_pos = ()
    if input("Only convert to f32? (y/n): ").lower() == "y":
        packet = Dem2SweepPacket(
            str(DATA_PATH / FILE_NAME)[:-3] + "_f32.h5", "1", processor.get_attributes()
        )
        packet.open_file()
        for i in range(processor.shape[0]):
            packet.append_frame(np.abs(processor[i, :, :]).astype(np.float32))
            if i % (processor.shape[0] // 10) == 0:
                log.info(f"{i / processor.shape[0] * 100}%")
        packet.close_file()
        packet.get_info()
        return

    if OCT_RECON:
        padding = input("padding (auto/0/#): ")
        if padding.lower() == "auto":
            padding = None
        else:
            padding = int(padding) if padding != "" else 0
        cuda_version = input("cuda? (y/n): ")
        if cuda_version.lower() == "y":
            packet = Dem2SweepPacket(
                str(DATA_PATH / FILE_NAME)[:-3] + "_oct_recon.h5", "1", processor.get_attributes()
            )
            packet.open_file()
            Z, H, W = processor.shape
            dz = Z // 2 if padding is None else padding
            if dz != 0:
                Z += dz * 2
            # process and stream to the packet's HDF5 file
            ds = packet.prepare_dataset(
                (Z, H, W),
                dtype=np.complex64,
                chunks=(Z, 1, W),
                data_set="1",
            )
            packet._frame_count = Z
            batch_size = _estimate_batch_size(Z, W)

            log.info(f"Beginning reconstruction... Final file size estimate: {int((Z*H*W*8)/1e9)} GB.")
            for start in range(0, H, batch_size):
                t1 = time.time()
                end = min(start + batch_size, H)
                images = _process_batch_along_z(
                    processor[:,start:end,:],
                    dz
                )
                packet.write_batch(start, cp.asnumpy(images), data_set="1", axis=1)
                del images
                cp.get_default_memory_pool().free_all_blocks()

                dt = (time.time() - t1) * ((H - end) / batch_size)
                log.info(
                    f"{start}:{end} / {H} " + f"{int(end / H * 100)}%, ETA: {int(dt // 60)} mins {int(dt % 60)} s.")
            packet.close_file()
            packet.set_attributes()
            log.info("Reconstruction complete.")
            return
        oct_recon = processor.oct_reconstruct(abs(processor[:,Y,:]), pad=padding)
        # oct_recon = oct_recon[:oct_recon.shape[0]//2,:]
        processor._prep_plot(oct_recon, "OCT Recon", gamma=GAMMA)
        plt.show()
        return
    # processor.rename_dataset("images", "1")
    cuda_all_z_bool = False
    # Just plot the FFT of the image. Useful to find 1st order center point.
    cor_bool = input("Plot reconstruction? y/n: ")
    cor_bool = True if cor_bool.lower() == "y" else False
    recon_all_z_bool = False
    if len(processor.shape) == 3:
        recon_all_z_bool = input("reconstruct all z? y/n: ")
        recon_all_z_bool = True if recon_all_z_bool.lower() == "y" else False
        cuda_all_z_bool = input("with cuda? y/n: ")
        cuda_all_z_bool = True if cuda_all_z_bool.lower() == "y" else False
    z_slice = input("z slice " + ("(start)" if recon_all_z_bool else "") + ": ")
    if not z_slice:
        z_slice = 1
    else:
        z_slice = int(z_slice)
    # processor.plot_ft(z_index=z_slice)
    try:
        if RAISE or input("Change centre? (y/n):").lower() == "y":
            raise "Error"
        #
        #     # Reconstruct the object field and plot everything. 1st order center and width/height.
        #     # processor.reconstruct(centre=(766,758), width=600, height=600, z_slice=45)
        centre = None
        w = None  # None for off
        h = None  # None for off
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
            recon_zs(
                log, processor, centre, w, h, z_slice, cuda_version=cuda_all_z_bool
            )
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
            processor._prep_plot(ft_arr[roi[0], roi[1]], "FFTed Image", gamma=0.05)
            plt.show()
        cx = int(input("Centre X: "))
        cy = int(input("Centre Y: "))
        centre = (cy, cx)
        w = int(input("Width: "))
        h = int(input("Height: "))
        if not recon_all_z_bool:
            recon_arr = processor.reconstruct(
                centre=centre, width=w, height=h, plot=cor_bool, z_slice=z_slice
            )
        else:
            recon_zs(
                log, processor, centre, w, h, z_slice, cuda_version=cuda_all_z_bool
            )
            return
    # a, N = prep_zernike(processor, recon_arr, centre=(1620, 2455), radius=1550)
    # a, N = prep_zernike(processor, recon_arr, centre=(1650, 2355), radius=150)

    cor_bool = input("Correlate XY recon_arr? y/n: ")
    if cor_bool.lower() == "y":
        roi = (slice(2400, 2600), slice(2330, 2530))

        coefs = processor.determine_speckle_size(roi, plot=True)

        plt.figure()
        plt.plot(coefs[0, :], label="X correlation coefs")
        plt.grid()
        plt.legend()
        plt.title("X correlation coefs")
        plt.figure()
        plt.plot(coefs[1, :], label="Y correlation coefs")
        plt.grid()
        plt.legend()
        plt.title("Y correlation coefs")
        plt.show()

    corZ_bool = input("Correlate Z? y/n: ")
    if corZ_bool:
        z_slice = int(input(f"Z to correlate (shape[0]={processor.shape[0]}): "))
        z_start = input("Z stack start (def. 0): ")
        z_stop = input(f"Z stack start (def. max ({processor.shape[0]})): ")
        z_range = slice(int(z_start) if z_start else 0, int(z_stop) if z_stop else None)
        roi_tl_x, roi_tl_y, roi_br_x, roi_br_y = 1750, 900, 2250, 1400
        # roi_tl_x, roi_tl_y, roi_br_x, roi_br_y = (
        #     input("ROI TL X: "),
        #     input("ROI TL Y: "),
        #     input("ROI BR X: "),
        #     input("ROI BR Y: "),
        # )
        roi = (
            slice(
                int(roi_tl_y) if roi_tl_y else None, int(roi_br_y) if roi_br_y else None
            ),
            slice(
                int(roi_tl_x) if roi_tl_x else None, int(roi_br_x) if roi_br_x else None
            ),
        )
        rev_dir = True if input("Reverse direction? (y/n): ").lower() == "y" else False
        j_sim = True if input("Just Similarity? (y/n): ").lower() == "y" else False
        arr_z_coefs = processor.correlate_with_stack(
            z_slice, z_range, roi, j_sim, rev_dir, plot=True
        )

        plt.figure()
        plt.plot(arr_z_coefs[:], label="Z correlation coefs")
        plt.grid()
        plt.legend()
        plt.title(f"Z correlation coefs revv_dir={rev_dir}")
        plt.show()

    zer_bool = input("Zernike estimation? y/n: ")
    if zer_bool.lower() == "y":
        a, N = prep_zernike(processor, recon_arr, centre=(2070, 2410), radius=1300)
        # a, N = prep_zernike(processor, processor.ft(recon_arr), centre=(1712, 2352), radius=145)

        a_no_tdf = a.copy()
        # a_no_tdf[1] = 0.0  # Noll 2  (tilt)
        # a_no_tdf[2] = 0.0  # Noll 3  (tilt)
        # a_no_tdf[3] = 0.0  # Noll 4  (defocus)

        wave_no_tdf, inside = processor.reconstruct_from_zernikes(
            a_no_tdf, max_noll=len(a), N=N
        )

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
