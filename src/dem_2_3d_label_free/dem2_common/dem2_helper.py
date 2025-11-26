"""Helper Script for Demonstrator 2."""

import logging
import os
from logging import Logger

from zeiss_helpers.common import setup_logging

from src.dem_2_3d_label_free.__globals__ import __configpath__, __datapath__, __root__


def setup_directories():
    """Setup config and data directories for development and testing."""
    if not os.path.exists(__configpath__):
        os.makedirs(__configpath__)
    if not os.path.exists(__datapath__):
        os.makedirs(__datapath__)


def setup_root_logger(root_file = __file__) -> Logger:
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