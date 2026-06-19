"""Helper class to process data and measurements."""

import logging
from pathlib import Path
import os
from PIL import Image
from matplotlib import pyplot as plt
from matplotlib.gridspec import GridSpec
from numpy.linalg import lstsq
from scipy.ndimage import center_of_mass, label

from src.dem_2_3d_label_free.__globals__ import __datapath__

import h5py
import numpy as np
import scipy

from src.dem_2_3d_label_free.dem2_common.dem2_constants import ZERNIKE_NOLLS
from src.dem_2_3d_label_free.dem2_common.dem2_helper import zernike_noll


class Dem2Processor:
    def __init__(
        self,
        file_path: Path | None = None,
        data_path: Path = Path(__datapath__),
        dataset_name: str = "1",
    ):
        # Non-root logging. See dem2_helper.setup_root_logger() documentation.
        self._log = logging.getLogger(self.__class__.__name__)

        self._file_path: Path | None = file_path
        self._data_path: Path = data_path
        self._path_override: Path | None = None
        self.dataset: str = dataset_name
        self._attributes: dict = {}

    def __getitem__(self, key):
        """Allows slicing of images directly from the disk without filling RAM."""
        with h5py.File(self.path, "r") as f:
            # Slices are read directly from the disk and returned as a numpy array
            dset = f[self.dataset]
            ndim = dset.ndim

            # Normalize key to a tuple
            if not isinstance(key, tuple):
                key = (key,)

            # 3D dataset, 2D key: treat as [0, :, :]
            if ndim == 3 and len(key) == 2:
                key = (1,) + key

            # 2D dataset, 3D key -> drop the first index, use remaining 2
            if ndim == 2 and len(key) == 3:
                key = key[1:]

            # Optional: enforce correct number of indices
            if len(key) > ndim:
                raise IndexError(
                    f"{len(key)} indices given for {ndim}D dataset of shape {dset.shape}"
                )

            return dset[key]

    def __getattr__(self, name):
        # Called only if normal attributes (like path, dataset, etc.) are missing
        if name in self._attributes:
            return self._attributes[name]
        with h5py.File(self.path, "r") as f:
            attrs = f[self.dataset].attrs
            if name in attrs:
                return attrs[name]
        # Important: if not found, raise AttributeError
        raise AttributeError(
            f"No attribute '{name}' in HDF5 attrs or loaded attributes"
        )

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
        self.load()

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

        path = path if str(path) != "." else self.path
        ds_name = dataset_name if dataset_name else self.dataset

        with h5py.File(str(path), "a") as f:
            if array is not None:
                attrs.update(
                    {
                        "shape": array.shape,
                        "dtype": str(array.dtype),
                    }
                )
                # (Re)create or create dataset with compression
                if ds_name in f:
                    # Optional: decide whether to delete/overwrite or raise
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

            # Write all merged attributes
            for key, value in attrs.items():
                if value is not None:
                    dset.attrs[key] = value

        self._log.info(f"Saved H5 file: {path}")
        self._log.info(f"File size: {os.path.getsize(path) / 1024 / 1024:.2f} MB")

    def rename_dataset(self, dataset: str, new_name: str, path: Path = Path("")):
        """
        Rename a dataset in a H5 file.
        :param dataset: Original dataset name.
        :param new_name: New dataset name.
        :param path: Path to other h5 file if not using current loaded one. This won't load it, use load() first.
        """
        h5_path = path if str(path) != "." else self.path
        with h5py.File(str(h5_path), "r+") as f:
            if dataset not in f:
                raise KeyError(f"Dataset '{dataset}' not found in file '{h5_path}'.")
            if new_name in f:
                raise KeyError(
                    f"Target dataset name '{new_name}' already exists in file '{h5_path}'."
                )

            # Copy dataset to new name
            f.copy(dataset, new_name)
            # Remove old dataset
            del f[dataset]

        # Update instance default dataset name if it was renamed
        if self.dataset == dataset:
            self.dataset = new_name

        self._log.info(f"Renamed dataset '{dataset}' to '{new_name}' in file {h5_path}")

    def ft(
        self,
        array: np.ndarray | None = None,
        roi: tuple[slice, slice] | None = None,
        dataset: str | None = None,
    ) -> np.ndarray:
        """
        Fourier transform an roi of an array.
        :param array: Full array.
        :param roi: (y,x) Roi to FFT. Optional.
        :param dataset: Dataset to use from loaded h5 file. Optional, will default to loaded dataset.
        :return: FFTed array (size of roi if provided.)
        """
        if dataset is not None:
            self.dataset = dataset
        arr = array if array is not None else self[:, :]
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
        cft_arr = self.crop_and_centre(ft_arr, self.centre, self.width, self.height)
        recon_arr = self.ift(cft_arr)
        if plot:
            self._prep_plot(arr, "Intensity Hologram", roi=roi)
            self._prep_plot(ft_arr, "FFT of Hologram", gamma=0.05)
            self._prep_plot(cft_arr, "Cropped & Centred FFT", gamma=0.05)
            self._prep_plot(recon_arr, "Reconstructed Intensity")
            self._prep_plot(recon_arr, "Reconstructed Phase", cmap="hsv")
            plt.show()
        return recon_arr

    def _prep_plot(
        self,
        array: np.ndarray,
        title: str,
        roi: tuple[slice, slice] | None = None,
        gamma: float | None = None,
        cmap: str = "gray",
    ):
        """
        Prepare plots.
        :param array: Array to plot.
        :param title: Title of plot.
        :param roi: Plot a roi.
        :param gamma: Apply gamma to array.
        :param cmap: Color map, ie 'hsv' for phase.
        """
        plt.figure()
        if roi is not None:
            array = array[roi[0], roi[1]]
        if cmap == "hsv":
            array = np.angle(array)
        elif np.issubdtype(array.dtype, np.complexfloating):
            # array = (array * array.conj()).real
            array = abs(array)
            if gamma is not None:
                array = array**gamma
        plt.imshow(array, cmap=cmap)
        if cmap == "hsv":
            plt.colorbar(fraction=0.046, pad=0.04)
        plt.title(title)
        plt.axis("off")

    def plot_ft(
        self,
        full_array: np.ndarray | None = None,
        roi: tuple[slice, slice] | None = None,
        dataset: str | None = None,
    ):
        """
        Plot the fft of an array.
        :param full_array: Array to fft. Optional, will use loaded dataset.
        :param roi: (y,x) Roi of the array. Optional, will use the whole array.
        :param dataset: Dataset to use. Optional, will use loaded dataset.
        """
        ft_arr = self.ft(full_array, roi, dataset)
        self._prep_plot(ft_arr, "FFTed Image", gamma=0.05)
        plt.show()

    def estimate_ellipse_from_fft(self,
        fft_img, center_guess, gamma=0.05, roi_half_size=700, thresh_factor=0.5
    ):
        """
        Parameters
        ----------
        fft_img : np.ndarray (2D, complex or real)
            FFTed array (off-axis holography spectrum).
        center_guess : tuple (cy, cx)
            Approximate center (in pixel coordinates) of the signal lobe in k-space.
        gamma : float
            Gamma exponent (use 0.05 to match your acquisition).
        roi_half_size : int
            Half-size of the square ROI extracted around center_guess.
        thresh_factor : float in (0, 1)
            Factor between inside/outside means used for threshold.

        Returns
        -------
        center : tuple of int
            (center_y, center_x) in full-image coordinates.
        width : int
            Ellipse width (major-axis bounding box, in pixels).
        height : int
            Ellipse height (minor-axis bounding box, in pixels).
        """

        # magnitude + gamma
        mag = np.abs(fft_img).astype(np.float64)
        mag_gamma = mag**gamma

        H, W = mag_gamma.shape
        cy0, cx0 = center_guess

        # ROI bounds
        y1 = max(0, cy0 - roi_half_size)
        y2 = min(H, cy0 + roi_half_size)
        x1 = max(0, cx0 - roi_half_size)
        x2 = min(W, cx0 + roi_half_size)

        roi = mag_gamma[y1:y2, x1:x2]

        # Rough “inside vs outside” statistics using a circular mask
        yy, xx = np.mgrid[0 : roi.shape[0], 0 : roi.shape[1]]
        cy_roi = roi.shape[0] / 2.0
        cx_roi = roi.shape[1] / 2.0
        r = np.sqrt((yy - cy_roi) ** 2 + (xx - cx_roi) ** 2)

        r_in = np.percentile(r, 40)  # inner region
        r_out = np.percentile(r, 80)  # outer ring

        inside = roi[r <= r_in]
        outside = roi[(r >= r_out)]

        mean_in = inside.mean()
        mean_out = outside.mean()

        # threshold halfway between means (you mentioned ~1.7 vs 1.5 after gamma)
        thr = mean_out + thresh_factor * (mean_in - mean_out)

        # binary mask
        mask = roi > thr

        # keep only the connected component nearest to the ROI center
        labeled, num = label(mask)
        if num == 0:
            # fallback: everything is background; return guess with zero size
            return (int(cy0), int(cx0)), 0, 0

        # distance of component centroids to ROI center
        comps = np.arange(1, num + 1)
        cents = np.array(center_of_mass(mask, labeled, comps))
        d2 = (cents[:, 0] - cy_roi) ** 2 + (cents[:, 1] - cx_roi) ** 2
        best_lab = comps[np.argmin(d2)]
        mask_ellipse = labeled == best_lab

        # pixel coordinates of that component (in ROI coords)
        ys, xs = np.nonzero(mask_ellipse)
        if ys.size < 3:
            # not enough points
            return (int(cy0), int(cx0)), 0, 0

        # centroid in ROI coords
        cy_e = ys.mean()
        cx_e = xs.mean()

        # covariance matrix → ellipse axes via eigenvalues
        y_shift = ys - cy_e
        x_shift = xs - cx_e
        coords = np.vstack((y_shift, x_shift))
        cov = np.cov(coords)

        evals, evecs = np.linalg.eigh(cov)
        # sort eigenvalues: largest = major axis
        order = np.argsort(evals)[::-1]
        evals = evals[order]

        # std dev along axes
        sigma_major = np.sqrt(evals[0])
        sigma_minor = np.sqrt(evals[1])

        # choose k to approximate the boundary (3σ ~ 99.7%, adjust if needed)
        k = 3.0
        semi_major = k * sigma_major
        semi_minor = k * sigma_minor

        # convert to full-image coordinates
        cy_full = y1 + cy_e
        cx_full = x1 + cx_e

        width = int(np.round(2 * semi_major))
        height = int(np.round(2 * semi_minor))

        center = (int(np.round(cy_full)), int(np.round(cx_full)))
        return center, width, height

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
        array = array[
            centre[0] - radius : centre[0] + radius,
            centre[1] - radius : centre[1] + radius,
        ]
        # U: complex array, result of your holography reconstruction
        phase = np.angle(array)

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
        pupil_mask = r < (0.9 * r.max())  # or use a threshold on amplitude
        r_norm = r / r[pupil_mask].max()
        theta = np.arctan2(y, x)

        valid = (r_norm <= 1.0) & pupil_mask
        r_p = r_norm[valid]
        theta_p = theta[valid]
        phi_p = phase[valid]

        # --- Fit Zernike coefficients (Noll indexing) ---
        Z = []
        for j in range(1, max_noll + 1):
            Zj = zernike_noll(j, r_p, theta_p)
            Z.append(Zj)

        Z = np.vstack(Z).T  # shape: (num_points, num_modes)
        a, residuals, rank, s = lstsq(Z, phi_p, rcond=None)  # a[k] -> Noll index k+1

        if not plot:
            return a

        # --- Reconstruct each mode on full grid for display ---
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
            ax.set_title(f"Noll {k+1} ({ZERNIKE_NOLLS[k+1]})\na={a[k]:.3f}", fontsize=9)
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
        return a

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
