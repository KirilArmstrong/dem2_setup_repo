"""Helper class to process data and measurements."""

import logging
from pathlib import Path
import os
from PIL import Image
from matplotlib import pyplot as plt

from src.dem_2_3d_label_free.__globals__ import __datapath__

import h5py
import numpy as np
import scipy


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

            # 2D dataset, 3D key: error
            if ndim == 2 and len(key) == 3:
                raise IndexError(
                    f"3 indices given for 2D dataset of shape {dset.shape}"
                )

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
        p = str(path if str(path)!="." else self.path)
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

        path = path if str(path)!="." else self.path
        ds_name = dataset_name if dataset_name else self.dataset

        with h5py.File(str(path), "a") as f:
            if array is not None:
                attrs.update({
                    "shape": array.shape,
                    "dtype": str(array.dtype),
                })
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
        h5_path = path if str(path)!="." else self.path
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
        :param roi: Roi to FFT. Optional.
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
        :param centre: Centre coordinate tuple.
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
        plot: bool = True,
    ) -> np.ndarray:
        """
        Reconstruct the object field from a hologram and plot it.
        :param centre: Centre point of 1st order.
        :param width: semi-major axis length. (rectangle width)
        :param height: semi-minor axis length. (rectangle height)
        :param array: Array to reconstruct. Optional, will use loaded dataset.
        :param roi: ROI to reconstruct. Optional, will default to whole image.
        :param dataset: Dataset to reconstruct. Optional, will use loaded dataset.
        :param plot: Plot everything and show figures.
        :return: Reconstructed array (size of roi if provided.)
        """
        arr = array if array is not None else self[:, :]
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
            array = (array * array.conj()).real
            if gamma is not None:
                array = array**gamma
        plt.imshow(array, cmap=cmap)
        if cmap == "hsv":
            plt.colorbar(fraction=0.046, pad=0.04)
        plt.title(title)
        plt.axis("off")

    def plot_ft(self,
        full_array: np.ndarray | None = None,
        roi: tuple[slice, slice] | None = None,
        dataset: str | None = None,):
        """
        Plot the fft of an array.
        :param full_array: Array to fft. Optional, will use loaded dataset.
        :param roi: Roi of the array. Optional, will use the whole array.
        :param dataset: Dataset to use. Optional, will use loaded dataset.
        """
        ft_arr = self.ft(full_array, roi, dataset)
        self._prep_plot(ft_arr, "FFTed Image", gamma=0.05)
        plt.show()

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
