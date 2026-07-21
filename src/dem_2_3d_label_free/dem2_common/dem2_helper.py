"""Helper Script for Demonstrator 2."""

import logging
import os
from logging import Logger
from datetime import datetime
import numpy as np
from zeiss_helpers.common import setup_logging, ConfigurationFile

from src.dem_2_3d_label_free.__globals__ import (
    __configpath__,
    __datapath__,
    __root__,
    __template_path__,
)


def convert_to_hex(decimal: float) -> str:
    hexcode = hex(int(decimal))[2:]  # ignore the "0x" in front
    while len(hexcode) < 4: hexcode = "0" + hexcode
    return hexcode

def hex_to_decimal(hex_string: str) -> float:
    return float(int("0x" + hex_string, 16))

def wavelength_to_hex(lam: float, min_lam: float, resolution: float) -> str:
    return convert_to_hex((lam-min_lam) * resolution)

def get_current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def load_config_file(config_filepath: str = os.path.join(__configpath__, "config.yml")) -> dict:
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
    """Convert Noll index j (1-based) to (n, m)."""
    n = int(np.ceil((-3 + np.sqrt(9 + 8 * (j - 1))) / 2))
    p = j - n * (n + 1) // 2
    k = n % 2
    m = 2 * ((p + k) // 2) - k
    if j % 2 == 1:
        m = -m
    return n, m

def radial_poly(n: int, m: int, r: np.ndarray):
    """Radial Zernike polynomial R_n^m(r)."""
    m = abs(m)
    R = np.zeros_like(r, dtype=float)
    for k in range((n - m) // 2 + 1):
        c = ((-1) ** k *
             np.math.factorial(n - k) /
             (np.math.factorial(k) *
              np.math.factorial((n + m) // 2 - k) *
              np.math.factorial((n - m) // 2 - k)))
        R += c * r ** (n - 2 * k)
    return R

def zernike_noll(j: int, r: np.ndarray, theta: np.ndarray):
    """
    Noll-indexed Zernike polynomial Z_j(r, theta), normalized in the
    usual way (unit disk, real-valued).
    r, theta: 1D arrays of same shape, with 0 <= r <= 1.
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