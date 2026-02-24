"""IO for sweep data and images."""

import logging
import os

import h5py
import numpy as np
import yaml

from src.dem_2_3d_label_free.__globals__ import __datapath__
from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern

from src.dem_2_3d_label_free.dem2_common.dem2_calculator import Dem2SystemCalculator


class Dem2Results(Dem2SystemCalculator):
    """IO for sweep data and images (data for single a-scan)."""

    def __init__(
        self,
        images: np.ndarray | None = None,
        settings: dict | None = None,
        config: dict | None = None,
        b_scan_pattern: Dem2BScanPattern | None = None,
        load_from_file: str = "",
    ):
        """
        Experiment data. Inherits from Dem2SystemCalculator.

        :param images: image data, 3D array. Stack of 2D image arrays.
        :param settings: settings data, config data plus additional settings.
        :param load_from_file: Load from file.
        """
        self._log = logging.getLogger(self.__class__.__name__)

        # self.images: list[images] = [] # Maybe the burst image returns a list of images, check the documentation.
        self.images = images if images is not None else np.array([])

        # take config, and replace/add additional settings to it.
        self._settings = config if config else {}
        self._settings.update(settings if settings else {})

        self.b_scan_pattern = b_scan_pattern if b_scan_pattern else Dem2BScanPattern()

        if load_from_file:
            self.load(load_from_file)

        super().__init__(self._settings)

    def _load_dict_from_h_file(self, f: h5py.File, dict_name: str) -> dict:
        """
        Load a dictionary from a given h5 file.

        :param f: opened h5 file object.
        :param dict_name: String name of dictionary.
        :return: dictionary
        """
        dictionary = {}
        if dict_name in f:
            # Iterate over the keys in the "settings" group
            for key in f[dict_name].keys():
                # Extract the scalar value using [()]
                val = f[f"{dict_name}/{key}"][()]

                # h5py stores strings as bytes, so we decode them back to Python strings
                if isinstance(val, bytes):
                    val = val.decode('utf-8')

                dictionary[key] = val
        return dictionary

    def _save_dict_to_h_file(self, f: h5py.File, dict_name: str, dictionary: dict):
        """
        Save a dictionary from a given h5 file.

        :param f: opened h5 file object.
        :param dict_name: String name of dictionary.
        :param dictionary: The dictionary object to save.
        """
        # Iterate through the dictionary and save each item dynamically
        for key, value in dictionary.items():
            # This automatically creates a "settings" group (folder)
            # and places a dataset named after the key inside it.
            f.create_dataset(f"{dict_name}/{key}", data=value)

    def load(self, load_from_file: str):
        """Load sweep packet from file."""
        with h5py.File(load_from_file, 'r') as f:
            # Load the images array
            self.images = f['images'][:]

            # Reconstruct the settings dictionary
            self._settings = self._load_dict_from_h_file(f, "settings")
            self.b_scan_pattern.from_dict(self._load_dict_from_h_file(f, "b_scan_pattern"))

    def save(self, filename: str = ""):
        if not filename:
            filename = "output.h5"

        if not filename.endswith('.h5'):
            filename += '.h5'

        with h5py.File(filename, 'w') as f:
            # Save the 3D numpy array
            f.create_dataset('images', data=self.images)

            self._save_dict_to_h_file(f, "settings", self._settings)
            self._save_dict_to_h_file(f, "b_scan_pattern", self.b_scan_pattern.as_dict())

    # # Properties

    @property
    def settings(self) -> dict:
        """Get settings dictionary."""
        return self._settings

    @settings.setter
    def settings(self, value: dict):
        """
        Replace keys in ``settings`` with keys in ``value`` without removing other keys.

        Please re-init the object to clear the settings dictionary.

        :param value: dictionary with keys to replace.
        """
        self._settings.update(value)


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



