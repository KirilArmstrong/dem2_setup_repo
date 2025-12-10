"""IO for sweep data and images."""

import logging
import os

import numpy as np
import yaml

from src.dem_2_3d_label_free.__globals__ import __datapath__


class Dem2SweepPacket:
    """IO for sweep data and images (data for single a-scan)."""

    def __init__(
        self,
        data: np.ndarray | None = None,
        data_offset: int = 0,
        load_from_file: str = "",
    ):
        self._log = logging.getLogger(self.__class__.__name__)

        # self.images: list[images] = [] # Maybe the burst image returns a list of images, check the documentation.

        if data is not None and data_offset != 0:
            self._data = data.reshape(-1, data_offset)

        if load_from_file:
            self.load(load_from_file)

    def load(self, load_from_file: str):
        """Load sweep packet from file."""
        # TODO figure out how images work

    def save(self, filename: str = ""):
        _filename = filename
        if not filename:
            _filename = os.path.join(
                __datapath__, "default name"
            )  # TODO default name and extension.
        # TODO Save it all into a bundle if possible.


class Dem2SweepExperiment:
    """IO for managing full experimental data and results."""

    def __init__(self, load_from_directory: str = ""):
        self._log = logging.getLogger(self.__class__.__name__)

        # TODO load form zip file?

        self.packets: list[Dem2SweepPacket] = []

        self.config = None
        self.samples_per_a_scan = None
        self.a_scans_b_scan = None
        self.save_directory = os.path.join(__datapath__, "dem2_sweep_experiment")

        if load_from_directory:
            self.load(load_from_directory)

    def __getitem__(self, key):
        """For slicing support. I.e. ``Dem2SweepExperiment()[:,j]``.

        Returns images."""
        if isinstance(key, tuple):
            i, j = key
            # TODO might need to load specifically as 10GB in RAM may be bad...
            if isinstance(i, slice) and isinstance(j, slice):
                return [packet.images[j] for packet in self.packets[i]]
            elif isinstance(i, slice):
                return [packet.images[j] for packet in self.packets[i]]
            elif isinstance(j, slice):
                return self.packets[i].images[j]
            else:
                return self.packets[i].images[j]
        else:
            raise TypeError("Invalid key type")

    def load(self, load_from_directory: str = ""):
        """Load images from a directory."""
        self.save_directory = os.path.join(__datapath__, "dem2_sweep_experiment")
        if load_from_directory:
            self.save_directory = load_from_directory
        self._log.info(
            "Loading Sweep experiment from directory '%s'...", self.save_directory
        )
        with open(self.save_directory, encoding="utf-8") as yml_file:
            properties = yaml.safe_load(yml_file)
            self.config = properties["config"]
            self.samples_per_a_scan = properties["samples_per_a_scan"]
            self.a_scans_b_scan = properties["a_scans_b_scan"]

        # todo load the packets.

    def save(self, save_to_directory: str = ""):
        """Save images to a directory."""
        if save_to_directory:
            self.save_directory = save_to_directory
        properties_file = os.path.join(self.save_directory, "properties.yml")
        _dict_to_save = {
            "config": self.config,
            "samples_per_a_scan": self.samples_per_a_scan,
            "a_scans_b_scan": self.a_scans_b_scan,
        }
        self._log.info(
            "Saving Sweep experiment to directory '%s'...", self.save_directory
        )
        with open(properties_file, "w", encoding="utf-8") as yml_file:
            yaml.safe_dump(_dict_to_save, yml_file, default_style=False)

        # todo save the packets.



