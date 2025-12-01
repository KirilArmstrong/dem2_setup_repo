"""Helper Script for Demonstrator 2."""

import logging
import os
from logging import Logger

from zeiss_helpers.common import setup_logging, ConfigurationFile

from src.dem_2_3d_label_free.__globals__ import (
    __configpath__,
    __datapath__,
    __root__,
    __template_path__,
)


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