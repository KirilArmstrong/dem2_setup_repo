"""Helper class to process data and measurements."""

import logging
from pathlib import Path
import os

from PIL import Image
from matplotlib import pyplot as plt
from matplotlib.gridspec import GridSpec
from numpy.linalg import lstsq
from skimage.restoration import unwrap_phase

from src.dem_2_3d_label_free.__globals__ import __datapath__

import h5py
import numpy as np
import scipy

from src.dem_2_3d_label_free.dem2_common.dem2_constants import ZERNIKE_NOLLS
from src.dem_2_3d_label_free.dem2_common.dem2_helper import zernike_noll
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2SweepPacket


class Dem2Processor(Dem2SweepPacket):
    def __init__(
        self,
        file_path: Path | None = None,
        data_path: Path = Path(__datapath__),
        dataset_name: str = "1",
        attributes: dict | None = None,
    ):
        # Non-root logging. See dem2_helper.setup_root_logger() documentation.
        self._log = logging.getLogger(self.__class__.__name__)

        self._file_path: Path | None = file_path
        self._data_path: Path = data_path
        self._path_override: Path | None = None
        super().__init__(str(self.path), dataset_name, attributes)

    def convert_tif_to_h5(self, path: Path = Path("")):
        """
        Convert a `tif` or `tiff` file to a `h5` file, and load that h5 file.
        :param path: Path to alternate file.
        """
        p = str(path if str(path) != "." else self.path)
        if not os.path.exists(p):
            raise FileNotFoundError(f"TIFF file not found: {p}")
        base_name, extension = os.path.splitext(p)
        if extension.lower() not in (".tif", ".tiff"):
            raise "Converting non-tif file to h5 is unsupported."

        # Open image with PIL and convert to NumPy array
        with Image.open(p) as img:
            # Convert to numpy array (preserves data type from TIFF)
            array = np.array(img)

        h5_path = base_name + ".h5"
        # Remove existing file to avoid conflicts
        if os.path.exists(h5_path):
            os.remove(h5_path)
            self._log.info(f"Removed existing file: {h5_path}")

        self.save(array, Path(h5_path))
        # self.load(full_path=Path(h5_path))

    def load(
        self,
        file_path: Path | None = None,
        data_path: Path = Path(__datapath__),
        dataset_name: str = "1",
        full_path: Path | None = None,
    ):
        """
        Load a file.
        :param file_path: Sub-directory and file name.
        :param data_path: Data folder.
        :param dataset_name: Name of dataset to load.
        :param full_path: Full file path if outside the data folder.
        """
        self.__init__(file_path, data_path, dataset_name)
        self._path_override = full_path

    def save(
        self,
        array: np.ndarray | None = None,
        path: Path = Path(""),
        dataset_name: str = "",
        attributes: dict | None = None,
    ):
        """
        Save an array to a h5 file.
        :param array: Array to save.
        :param path: Path and name of h5 file to save as.
        :param dataset_name: Name of the dataset for the array, defaults to loaded dataset name.
        :param attributes: Additional attributes relevant to the dataset.
        """
        # Base attributes
        attrs = attributes if attributes is not None else self._attributes

        self.filepath = path if str(path) != "." else self.path
        self._path_override = self.filepath
        ds_name = dataset_name if dataset_name else self.data_set

        with h5py.File(self.path, "a") as f:
            if array is not None:
                attrs.update(
                    {
                        "shape": array.shape,
                        "dtype": str(array.dtype),
                    }
                )
                # (Re)create or create dataset with compression
                if ds_name in f:
                    a = dict(f[ds_name].attrs)
                    a.update(attrs)
                    attrs = a
                    del f[ds_name]
                dset = f.create_dataset(
                    ds_name,
                    data=array,
                    compression="gzip",
                    compression_opts=4,
                )
            else:
                # Only update attributes on existing dataset
                if ds_name not in f:
                    raise KeyError(f"Dataset {ds_name!r} does not exist in file {path}")
                dset = f[ds_name]
            a = dict(dset.attrs)
            a.update(attrs)
            attrs = a

            # Write all merged attributes
            # for key, value in attrs.items():
            #     if value is not None:
            #         dset.attrs[key] = value
        self.set_attributes(attrs, ds_name)

        self._log.info(f"Saved H5 file: {path}")
        self._log.info(f"File size: {os.path.getsize(path) / 1024 / 1024:.2f} MB")

    def ft(
        self,
        array: np.ndarray | None = None,
        roi: tuple[slice, slice] | None = None,
        dataset: str | None = None,
        z_index: int = 1,
    ) -> np.ndarray:
        """
        Fourier transform an roi of an array.
        :param array: Full array.
        :param roi: (y,x) Roi to FFT. Optional.
        :param dataset: Dataset to use from loaded h5 file. Optional, will default to loaded dataset.
        :return: FFTed array (size of roi if provided.)
        """
        if dataset is not None:
            self.data_set = dataset
        arr = array if array is not None else self[z_index, :, :]
        if roi is not None:
            arr = arr[roi[0], roi[1]]
        return scipy.fft.fftshift(scipy.fft.fft2(arr))

    def crop_and_centre(
        self, array: np.ndarray, centre: tuple[int, int], width: int, height: int
    ) -> np.ndarray:
        """
        Crop out a feature in an array and zero pad it to the input array size.
        :param array: Input array.
        :param centre: (y, x) Centre coordinate tuple.
        :param width: Width of cropped roi.
        :param height: Height of cropped roi.
        :return: Zero padded cropped array sized same as input array.
        """
        w = width - 1 if width % 2 == 1 else width
        h = height - 1 if height % 2 == 1 else height
        new_arr = np.zeros_like(array)
        if (
            centre[0] - int(h / 2) < 0
            or centre[1] - int(w / 2) < 0
            or centre[0] + int(h / 2) > array.shape[0]
            or centre[0] + int(w / 2) > array.shape[1]
        ):
            raise Exception(
                f"Selection out of array bounds! x is {centre[1] - int(w / 2)} to {centre[0] + int(w / 2)} "
                f"and y is {centre[0] - int(h / 2)} to {centre[0] + int(h / 2)}."
            )
        new_arr[
            int(array.shape[0] / 2) - int(h / 2) : int(array.shape[0] / 2) + int(h / 2),
            int(array.shape[1] / 2) - int(w / 2) : int(array.shape[1] / 2) + int(w / 2),
        ] = array[
            centre[0] - int(h / 2) : centre[0] + int(h / 2),
            centre[1] - int(w / 2) : centre[1] + int(w / 2),
        ]
        return new_arr

    def ift(self, array: np.ndarray) -> np.ndarray:
        """
        iFFT shift and iFFT and array.
        :param array: k-space array.
        :return: real space array.
        """
        return scipy.fft.ifft2(scipy.fft.ifftshift(array))

    def reconstruct(
        self,
        centre: tuple[int, int] | None = None,
        width: int | None = None,
        height: int | None = None,
        array: np.ndarray | None = None,
        roi: tuple[slice, slice] | None = None,
        dataset: str | None = None,
        z_slice: int = 1,
        plot: bool = True,
    ) -> np.ndarray:
        """
        Reconstruct the object field from a hologram and plot it.
        :param centre: (y, x) Centre point of 1st order.
        :param width: semi-major axis length. (rectangle width)
        :param height: semi-minor axis length. (rectangle height)
        :param array: Array to reconstruct. Optional, will use loaded dataset. 3d supported with z_slice.
        :param roi: ROI to reconstruct. Optional, will default to whole image.
        :param dataset: Dataset to reconstruct. Optional, will use loaded dataset.
        :param plot: Plot everything and show figures.
        :param z_slice: Which z index to use, i.e. image in image stack.
        :return: Reconstructed array (size of roi if provided.)
        """
        self._log.info(f"Beginning reconstruction for z={z_slice}")
        arr = array if array is not None else self[z_slice, :, :]
        arr = (
            arr if arr.ndim == 2 else arr[z_slice, :, :]
        )  # support for inputting 3d arrays.
        for name, value in (
            ("centre", centre),
            ("width", width),
            ("height", height),
            ("roi", roi),
        ):
            if value is not None:
                self._attributes[name] = value
        self.save()
        ft_arr = self.ft(arr, roi, dataset)
        self._log.info(
            "Using centre: "
            + str(self.centre)
            + ", with a height/width: "
            + str(self.height)
            + "/"
            + str(self.width)
            + " px."
        )
        cft_arr = self.crop_and_centre(ft_arr, self.centre, self.width, self.height)
        recon_arr = self.ift(cft_arr)
        if plot:
            self._log.info("Plotting...")
            self._prep_plot(arr, "Intensity Hologram", roi=roi)
            self._prep_plot(ft_arr, "FFT of Hologram", gamma=0.05, point=self.centre)
            self._prep_plot(cft_arr, "Cropped & Centred FFT", gamma=0.3)
            self._prep_plot(recon_arr, "Reconstructed Intensity")
            self._prep_plot(recon_arr, "Reconstructed Phase", cmap="hsv")
            self._prep_plot(
                recon_arr, "Reconstructed Phase Unwrapped", cmap="hsv", unwrap=True
            )
            pupil_field = self.ft(recon_arr)
            self._prep_plot(pupil_field, "Pupil Field Intensity")
            self._prep_plot(pupil_field, "Pupil Field Phase", cmap="hsv")
            self._prep_plot(
                pupil_field, "Pupil Field Phase Unwrapped", cmap="hsv", unwrap=True
            )
            plt.show()
        return recon_arr

    def _prep_plot(
        self,
        array: np.ndarray,
        title: str,
        roi: tuple[slice, slice] | None = None,
        gamma: float | None = None,
        cmap: str = "gray",
        unwrap: bool = False,
        point: tuple[int, int] = None,
        y: int = None,
        k: int = None,
        padding: int | None = None,
        y_ax_lbl: str = "Y [pix]",
        x_ax_lbl: str = "X [pix]",
        center_y=False,
    ):
        """
        Prepare plots.
        :param array: Array to plot.
        :param title: Title of plot.
        :param roi: Plot a roi.
        :param gamma: Apply gamma to array.
        :param cmap: Color map, ie 'hsv' for phase.
        """

        if k is not None and y is not None:
            raise ValueError("Only one of 'k' or 'y' can be set, not both.")
        fig = plt.figure()
        if roi is not None:
            array = array[roi[0], roi[1]]
        if cmap == "hsv":
            array = np.angle(array)
            if unwrap:
                array = unwrap_phase(array)
        elif np.issubdtype(array.dtype, np.complexfloating):
            # array = (array * array.conj()).real
            array = abs(array)
        if gamma is not None:
            array = array**gamma
        height, width = array.shape
        if center_y:
            plt.imshow(array, cmap=cmap, extent=(0, width, height / 2, -height / 2))
        else:
            plt.imshow(array, cmap=cmap)

        if point is not None:
            row, col = point

            if (
                isinstance(row, (int, np.integer))
                and isinstance(col, (int, np.integer))
                and 0 <= row < array.shape[0]
                and 0 <= col < array.shape[1]
            ):
                # imshow uses x=column and y=row
                plt.scatter(col, row, c="red", marker="x", s=80, linewidths=2)

        if k is not None:
            if gamma is not None:
                pad = height // 2 if padding is None else padding
                new_k = int((k / (height // 2)) * (((2 * pad) + height) // 2))
                plt.axhline(
                    # (height // 2 if center_y else 0) + new_k,
                    new_k,
                    color="red",
                    linestyle="-",
                    linewidth=0.5,
                )
            else:
                plt.axhline(
                    (height // 2 if center_y else 0) + k,
                    color="red",
                    linestyle="-",
                    linewidth=0.5,
                )
        elif y is not None:
            plt.axhline(y, color="red", linestyle="-", linewidth=0.5)

        if cmap == "hsv":
            plt.colorbar(fraction=0.046, pad=0.04)
        plt.title(title)
        plt.xlabel(x_ax_lbl)
        plt.ylabel(y_ax_lbl)
        # plt.axis("off")
        return fig

    def plot_ft(
        self,
        full_array: np.ndarray | None = None,
        roi: tuple[slice, slice] | None = None,
        dataset: str | None = None,
        z_index: int = 1,
    ):
        """
        Plot the fft of an array.
        :param full_array: Array to fft. Optional, will use loaded dataset.
        :param roi: (y,x) Roi of the array. Optional, will use the whole array.
        :param dataset: Dataset to use. Optional, will use loaded dataset.
        """
        ft_arr = self.ft(full_array, roi, dataset, z_index)
        self._prep_plot(ft_arr, "FFTed Image", gamma=0.05)
        plt.show()

    def get_zernike_coeffs(
        self,
        array: np.ndarray,
        centre: tuple[int, int],
        radius: int,
        max_noll: int = 15,
        plot: bool = True,
    ):
        """
        Get the Zernike Coefficients of a roi of a reconstructed field.
        :param array: Full array of object field.
        :param centre: Center of roi. (y,x)
        :param radius: Radius of roi.
        :param max_noll: Max Nolls. recommended = 15.
        :param plot: Represent nolls on plot.
        :return: Zernike coefficients array.
        """
        # square ROI
        array = array[
            centre[0] - radius - 1 : centre[0] + radius,
            centre[1] - radius - 1 : centre[1] + radius,
        ]
        phase = np.angle(array)
        phase = unwrap_phase(phase)

        Ny, Nx = phase.shape
        if Ny != Nx:
            # enforce square for the simple radial definition; crop or pad if needed
            N = min(Ny, Nx)
            cy = Ny // 2
            cx = Nx // 2
            phase = phase[cy - N // 2 : cy + N // 2, cx - N // 2 : cx + N // 2]
        else:
            N = Ny

        y, x = np.indices((N, N))
        x = x - (N - 1) / 2
        y = y - (N - 1) / 2

        r = np.sqrt(x**2 + y**2)
        pupil_mask = r <= radius  # or use a threshold on amplitude
        r_norm = r / radius
        theta = np.arctan2(y, x)

        valid = pupil_mask
        r_p = r_norm[valid]
        theta_p = theta[valid]
        phi_p = phase[valid]

        # fit Zernike coefficients w/ Noll indexing
        self._log.info("Fitting coefficients...")
        Z = []
        for j in range(1, max_noll + 1):
            Zj = zernike_noll(j, r_p, theta_p)
            Z.append(Zj)

        Z = np.vstack(Z).T  # shape: (num_points, num_modes)
        a, residuals, rank, s = lstsq(Z, phi_p, rcond=None)  # a[k] -> Noll index k+1

        if not plot:
            return a

        # --- Reconstruct each mode on full grid for display ---
        self._log.info("Plottings coefficients...")
        r_norm_full = r / r[pupil_mask].max()
        theta_full = theta
        inside = r_norm_full <= 1.0

        mode_maps = np.zeros((max_noll, N, N))

        for k in range(max_noll):
            j = k + 1  # Noll index
            Z_full = np.zeros_like(r_norm_full)
            Z_full_inside = zernike_noll(j, r_norm_full[inside], theta_full[inside])
            Z_full[inside] = Z_full_inside
            mode_maps[k] = a[k] * Z_full

        ncols = 5
        nrows = int(np.ceil(max_noll / ncols))

        # Extra column for the colorbar
        fig = plt.figure(figsize=(3 * ncols + 1.5, 3 * nrows))
        gs = GridSpec(
            nrows,
            ncols + 1,  # last column = colorbar
            width_ratios=[1] * ncols + [0.07],
            figure=fig,
            left=0.05,
            right=0.95,
            bottom=0.06,
            top=0.90,
            wspace=0.25,
            hspace=0.35,
        )

        axes = []
        vmax = np.max(np.abs(mode_maps))

        # Create image axes
        for i in range(nrows):
            for j in range(ncols):
                axes.append(fig.add_subplot(gs[i, j]))

        axes = np.array(axes).ravel()

        # Plot modes
        for k in range(max_noll):
            ax = axes[k]
            im = ax.imshow(
                mode_maps[k],
                cmap="twilight",
                origin="lower",
                vmin=-vmax,
                vmax=vmax,
            )
            ax.set_title(
                f"Noll {k + 1} ({ZERNIKE_NOLLS[k + 1]})\na={a[k]:.3f}", fontsize=9
            )
            ax.set_xticks([])
            ax.set_yticks([])

        # Hide unused axes
        for k in range(max_noll, len(axes)):
            axes[k].axis("off")

        # Colorbar occupying the last column, all rows
        cax = fig.add_subplot(gs[:, -1])
        cbar = fig.colorbar(im, cax=cax)
        cbar.set_label("Phase [rad]")

        # Clean, non-overlapping suptitle
        fig.suptitle("Zernike Mode Phase Contributions", fontsize=16, y=0.96)

        plt.show()
        return a, N

    def reconstruct_from_zernikes(self, a, N, max_noll=15):
        # Rebuild total wavefront from coefficients a[0..max_noll-1]
        y, x = np.indices((N, N))
        x = x - (N - 1) / 2
        y = y - (N - 1) / 2
        r = np.sqrt(x**2 + y**2)
        r_norm = r / r.max()
        theta = np.arctan2(y, x)
        inside = r_norm <= 1.0

        wave = np.zeros_like(r_norm, dtype=float)

        for k in range(max_noll):
            j = k + 1  # Noll index
            Z_full = np.zeros_like(r_norm)
            Z_full_inside = zernike_noll(j, r_norm[inside], theta[inside])
            Z_full[inside] = Z_full_inside
            wave += a[k] * Z_full  # sum contribution

        return wave, inside

    def determine_speckle_size(
        self,
        roi: tuple[slice, slice],
        full_array: np.ndarray | None = None,
        pixel_pos_no: int = 100,
        z_slice: int = 1,
        just_similarity: bool = True,
        plot: bool = False,
    ):
        """
        Determine the speckle size in both X adn Y desperately and plot.
        :param full_array: Full array
        :param roi: ROI to correlate (y:y,x:x)
        :param pixel_pos_no: Number of sample points.
        :param z_slice: z slice in image stack.
        :param just_similarity: Whether to absolute the resulting coeffs to just show similarity.
        :return: Coef array for x and y shape=(2,`pixel_pos_no`), 0=x & 1=y
        """
        arr = np.abs(
            full_array[roi[0], roi[1]]
            if full_array is not None
            else self[z_slice, roi[0], roi[1]]
        )
        if plot:
            plt.figure()
            plt.imshow(arr)
            plt.show()
        correlations_x = []
        correlations_y = []
        for i in range(pixel_pos_no):
            a = np.abs(
                full_array[roi[0], roi[1].start + i : roi[1].stop + i]
                if full_array is not None
                else self[z_slice, roi[0], roi[1].start + i : roi[1].stop + i]
            )
            correlations_x.append(np.corrcoef(arr.ravel(), a.ravel())[0, 1])
        for i in range(pixel_pos_no):
            a = np.abs(
                full_array[roi[0].start + i : roi[0].stop + i, roi[1]]
                if full_array is not None
                else self[z_slice, roi[0].start + i : roi[0].stop + i, roi[1]]
            )
            correlations_y.append(np.corrcoef(arr.ravel(), a.ravel())[0, 1])
        result = np.array([correlations_x, correlations_y])
        return np.abs(result) if just_similarity else result

    def correlate_with_stack(
        self,
        z_slice: int,
        z_range: slice,
        roi: tuple[slice, slice],
        just_similarity: bool = True,
        reverse_direction: bool = False,
        plot: bool = False,
    ):
        """
        Correlate an image with a stack of images. Starting with the z_range.start.
        :param z_slice: Z index of image to correlate stack with
        :param z_range: Z range of image stack.
        :param roi:  ROI to correlate (y:y,x:x)
        :param just_similarity: Whether to absolute the resulting coeffs to just show similarity.
        :param reverse_direction: Inverse the direction of correlation. (Start at z_range.stop to z_range.start)
        :return: Coef array.
        """
        arr = np.abs(self[z_slice, roi[0], roi[1]])
        if plot:
            plt.figure()
            plt.imshow(arr)
            plt.show()
        correlations = []
        end = self[z_range, 0, 0].shape[0] + z_range.start

        for z in range(z_range.start, end):
            a = np.abs(self[z, roi[0], roi[1]])
            correlations.append(np.corrcoef(arr.ravel(), a.ravel())[0, 1])
        result = np.array(correlations)
        if reverse_direction:
            result = result[::-1]
        return np.abs(result) if just_similarity else result

    @property
    def path(self) -> Path:
        """
        Get the loaded path.
        :return: Path object.
        """
        if self._path_override is not None:
            return self._path_override
        if self._file_path is None:
            raise "No file stored in `self._file_path`."
        return self._data_path / self._file_path
