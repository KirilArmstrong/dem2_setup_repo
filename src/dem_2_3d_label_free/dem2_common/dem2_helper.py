"""Helper Script for Demonstrator 2."""

import logging
import os
from logging import Logger
from datetime import datetime

import cupy as cp
from PySide6.QtGui import QImage, QPixmap
import h5py
import numpy as np
import scipy
from zeiss_helpers.common import setup_logging, ConfigurationFile

from src.dem_2_3d_label_free.__globals__ import (
    __configpath__,
    __datapath__,
    __root__,
    __template_path__,
)


def numpy_to_qpixmap(array: np.ndarray) -> QPixmap:
    """Convert 2D/3D np.uint8 or float [0,1] array to QPixmap.
        This function was ai generated and manually edited."""
    # Handle float arrays in [0,1] range
    if array.dtype in (np.float32, np.float64):
        array = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    if array.ndim == 2:
        h, w = array.shape
        img = QImage(array.data, w, h, w, QImage.Format_Grayscale8)
    elif array.ndim == 3 and array.shape[2] == 3:
        h, w, c = array.shape
        # RGB image - ensure contiguous for QImage
        array = np.ascontiguousarray(array)
        img = QImage(array.data, w, h, w * c, QImage.Format_RGB888)
    else:
        raise ValueError(f"Unsupported array shape: {array.shape}")
    return QPixmap.fromImage(img.copy())


def normalize_to_255(array: np.ndarray):
    """Normalise an array to 0-255."""
    # normalize to 0–255
    array = array - array.min()
    if array.max() > 0:
        array = array / array.max()
    return (array * 255).astype(np.uint8)


def compute_fft(image_array: cp.ndarray) -> cp.ndarray:
    """Compute the 2D FFT of an array."""
    ft_array = cp.fft.fft2(image_array)
    ft_array = cp.fft.fftshift(ft_array)
    return ft_array


def covert_fft_to_img(ft_array: cp.ndarray, gamma: float) -> cp.ndarray:
    """Convert a complex array into a normalized to 255 image array with a gamma factor."""
    ft_array = np.abs(ft_array)
    ft_array = ft_array**gamma
    return normalize_to_255(ft_array)


def phase_to_hsv(array: cp.ndarray) -> cp.ndarray:
    """Convert -pi to pi to 0 - 1.
        This function was ai generated and manually edited."""
    from matplotlib.colors import hsv_to_rgb

    hue = (cp.angle(array) + cp.pi) / (2 * cp.pi)
    hsv = cp.zeros((*array.shape, 3), dtype=cp.float32)
    hsv[:, :, 0] = hue
    hsv[:, :, 1] = 1.0
    hsv[:, :, 2] = 1.0
    rgb = cp.array(hsv_to_rgb(hsv.get()))
    return (rgb * 255).astype(cp.uint8)


def crop_centre_ifft(ft_array: cp.ndarray, top_left, bottom_right) -> cp.ndarray:
    """
    Extract ft_array[top_left:bottom_right], place it in the centre of a
    zero-padded array of the same size as ft_array, then ifftshift + ifft2.
    top_left and bottom_right are (x, y) i.e. (column, row).
    """
    x1, y1 = top_left
    x2, y2 = bottom_right

    # Make coords even (round down) so centre alignment is unambiguous
    x1 = x1 - (x1 % 2)
    y1 = y1 - (y1 % 2)
    x2 = x2 - (x2 % 2)
    y2 = y2 - (y2 % 2)

    w = x2 - x1  # width  (cols)
    h = y2 - y1  # height (rows)

    if h <= 0 or w <= 0:
        ft_centred = ft_array
    else:
        ft_centred = cp.zeros_like(ft_array)
        ch = ft_array.shape[0] // 2
        cw = ft_array.shape[1] // 2

        row_start = ch - h // 2
        col_start = cw - w // 2

        # Target slice exactly matches source shape (h, w)
        ft_centred[row_start : row_start + h, col_start : col_start + w] = ft_array[
            y1:y2, x1:x2
        ]

    ft_unshifted = cp.fft.ifftshift(ft_centred)
    img_iffted = cp.fft.ifft2(ft_unshifted)
    return img_iffted


def collect_attrs(obj, lines, indent=""):
    """Collect all attributes of an HDF5 object into lines."""
    if len(obj.attrs) == 0:
        return
    lines.append(f"{indent}Attributes:")
    for key, val in obj.attrs.items():
        lines.append(f"{indent}  {key}: {val}")


def collect_dataset_data(ds, lines, indent="", max_elements=50):
    """
    Optionally collect dataset contents.
    Be careful with large datasets: we only show up to max_elements.
    """
    try:
        data = ds[()]  # read entire dataset
    except Exception as e:
        lines.append(f"{indent}  (Could not read data: {e})")
        return

    # Flatten just for nice printing
    flat = np.array(data).ravel()
    if flat.size <= max_elements:
        lines.append(f"{indent}  Data (all {flat.size} elements): {flat}")
    else:
        lines.append(
            f"{indent}  Data (first {max_elements} of {flat.size} elements): {flat[:max_elements]}"
        )


def collect_h5_contents(filename, log=None, max_elements=0) -> str:
    """
    Recursively collect the full structure of an HDF5 file into a string:
    - File attributes
    - All groups and their attributes
    - All datasets, with shape, dtype, attributes
    - Optionally some data values
    Returns a single string with all information.
        This function was ai generated and manually edited.
    """
    lines = []
    with h5py.File(filename, "r") as f:
        lines.append(f"File: {filename}")
        collect_attrs(f, lines, indent="  ")
        lines.append(f"\nContents of {filename}:")

        def visitor(name, obj):
            # indent based on depth (number of '/' in the path)
            depth = name.count("/")
            indent = "  " * (depth + 1)

            if isinstance(obj, h5py.Group):
                lines.append(f"{indent}Group: {name}")
                collect_attrs(obj, lines, indent=indent + "  ")

            elif isinstance(obj, h5py.Dataset):
                lines.append(f"{indent}Dataset: {name}")
                lines.append(f"{indent}  Shape: {obj.shape}")
                lines.append(f"{indent}  Dtype: {obj.dtype}")
                collect_attrs(obj, lines, indent=indent + "  ")

                if max_elements > 0:
                    collect_dataset_data(
                        obj, lines, indent=indent + "  ", max_elements=max_elements
                    )

        # Walk the file tree
        f.visititems(visitor)

    strs = "\n".join(lines)
    if log is not None:
        log.info(strs)
    return strs


def ui_prep_img(
    image_array: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    # Normalize to uint8 for display / ROI drawing
    if image_array.dtype in (np.float32, np.float64):
        display_arr = (np.clip(image_array, 0, 1) * 255).astype(np.uint8)
    else:
        display_arr = image_array.astype(np.uint8)
    # Build RGB display image and draw camera ROI if active
    if display_arr.ndim == 2:
        display_rgb = np.stack([display_arr, display_arr, display_arr], axis=-1)
    else:
        display_rgb = np.ascontiguousarray(display_arr)
    return display_rgb, display_arr


def oct_reconstruct(
    array: np.ndarray,
    pad: int | None = None,
) -> np.ndarray:
    """Apply a 1D FFT over a image/volume."""
    dy = array.shape[0] // 2 if pad is None else pad
    if dy != 0:
        pad_top = np.zeros((dy, array.shape[1]), dtype=array.dtype)
        pad_bottom = np.zeros((dy, array.shape[1]), dtype=array.dtype)
        arr_padded = np.vstack([pad_top, array, pad_bottom])
        return scipy.fft.fftshift(scipy.fft.fft(arr_padded, axis=0), axes=0)
    return scipy.fft.fftshift(scipy.fft.fft(array, axis=0), axes=0)


def convert_to_hex(decimal: float) -> str:
    """Convert a decimal value to hex code."""
    hexcode = hex(int(decimal))[2:]  # ignore the "0x" in front
    while len(hexcode) < 4:
        hexcode = "0" + hexcode
    return hexcode


def hex_to_decimal(hex_string: str) -> float:
    """Convert hex code to decimal."""
    return float(int("0x" + hex_string, 16))


def wavelength_to_hex(lam: float, min_lam: float, resolution: float) -> str:
    """Convert a wavelength to hex code."""
    return convert_to_hex((lam - min_lam) * resolution)


def get_current_timestamp() -> str:
    """Get the current formatted timestamp."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def load_config_file(
    config_filepath: str = os.path.join(__configpath__, "config.yml"),
) -> dict:
    """
    Load and parse a config file in the ``config`` directory into a config dict.
    :param config_filepath: file path to config yml file.
    :return: Config dictionary.
    """
    return (
        ConfigurationFile(path=config_filepath)
        .with_defaults_from_file(os.path.join(__template_path__, "config.template.yml"))
        .with_copy_defaults_if_missing()
        .parse()
    )


def setup_directories():
    """Setup config and data directories for development and testing."""
    if not os.path.exists(__configpath__):
        os.makedirs(__configpath__)
    if not os.path.exists(__datapath__):
        os.makedirs(__datapath__)


def setup_root_logger(root_file=__file__) -> Logger:
    """Setup root logging. This is typically done in your main application!

    For non-root logging, use the following in a class's ``__init__()``:

    >>> self._log = logging.getLogger(self.__class__.__name__)

    :param root_file: Root script file that is calling this function. Use ``setup_logger(__file__)``.
    :return Logger: Root logging object.
    """
    # Logging should happen in root.

    # Setup root logger - Is typically done in your main application!
    # ! For non-root classes use `self._log = logging.getLogger(self.__class__.__name__)`
    setup_logging(verbose=False, logfile_directory=os.path.join(__root__, "logs"))
    # Return the root logger
    return logging.getLogger(os.path.basename(root_file))


def noll_to_nm(j: int):
    """Convert Noll index j (1-based) to (n, m).
        This function was ai generated and manually edited."""
    n = int(np.ceil((-3 + np.sqrt(9 + 8 * (j - 1))) / 2))
    p = j - n * (n + 1) // 2
    k = n % 2
    m = 2 * ((p + k) // 2) - k
    if j % 2 == 1:
        m = -m
    return n, m


def radial_poly(n: int, m: int, r: np.ndarray):
    """Radial Zernike polynomial R_n^m(r).
        This function was ai generated and manually edited."""
    m = abs(m)
    R = np.zeros_like(r, dtype=float)
    for k in range((n - m) // 2 + 1):
        c = (
            (-1) ** k
            * np.math.factorial(n - k)
            / (
                np.math.factorial(k)
                * np.math.factorial((n + m) // 2 - k)
                * np.math.factorial((n - m) // 2 - k)
            )
        )
        R += c * r ** (n - 2 * k)
    return R


def zernike_noll(j: int, r: np.ndarray, theta: np.ndarray):
    """
    Noll-indexed Zernike polynomial Z_j(r, theta), normalized in the
    usual way (unit disk, real-valued).
    r, theta: 1D arrays of same shape, with 0 <= r <= 1.
        This function was ai generated and manually edited.
    """
    n, m = noll_to_nm(j)
    R = radial_poly(n, m, r)
    if m == 0:
        Z = np.sqrt(n + 1) * R
    elif m > 0:
        Z = np.sqrt(2 * (n + 1)) * R * np.cos(m * theta)
    else:  # m < 0
        Z = np.sqrt(2 * (n + 1)) * R * np.sin(-m * theta)
    return Z
