import logging
import os
from pathlib import Path

import h5py
import numpy as np
import yaml

from src.dem_2_3d_label_free.__globals__ import __datapath__
from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern
from src.dem_2_3d_label_free.dem2_common.dem2_calculator import Dem2SystemCalculator


class Dem2SweepPacket:
    """IO for a single sweep (burst of images). Appends directly to HDF5 incrementally."""

    def __init__(self, filepath: str, data_set: str = "1", attributes: dict|None = None):
        self._log = logging.getLogger(self.__class__.__name__)
        self.filepath = filepath
        self.data_set: str = data_set
        self._attributes: dict = attributes if attributes is not None else {}

        self._h5_file = None
        self._data = None
        self._frame_count = 0


    def start_capture(self):
        """Prepares the HDF5 file to receive streaming frames."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self._h5_file = h5py.File(self.filepath, 'w')
        self._data = None
        self._frame_count = 0

    def append_frame(self, frame_data: np.ndarray, data_set: str | None = None):
        """Appends a single frame to the open HDF5 dataset on the fly."""
        if self._h5_file is None:
            raise RuntimeError("Packet is not open. Call start_capture() first.")

        if self._data is None:
            h, w = frame_data.shape
            # Initialize resizable dataset on the first frame
            self._data = self._h5_file.create_dataset(
                self.data_set if data_set is None else data_set,
                shape=(1, h, w),
                maxshape=(None, h, w),
                dtype=frame_data.dtype,
                chunks=(1, h, w)
            )
            self._data[0] = frame_data
        else:
            # Expand dataset and write new frame
            self._data.resize((self._frame_count + 1, self._data.shape[1], self._data.shape[2]))
            if self._data[self._frame_count].shape == frame_data.shape:
                self._data[self._frame_count] = frame_data
            else:
                self._log.error(
                    f"Frame shape mismatch for frame {self._frame_count}. ")
            
        self._frame_count += 1

    def stop_capture(self):
        """Safely closes the file after capture is complete."""
        if self._h5_file is not None:
            self._h5_file.close()
            self._h5_file = None
            self._log.info("Saved %d frames to %s in dataset %s", self._frame_count, self.filepath, self.data_set)

    def __getitem__(self, key):
        """
        Allows slicing of images directly from the disk without filling RAM.

        Supported patterns:
          - data["set1", :, :, :]   -> 3D slice of dataset "set1"
          - data["set1"]            -> full array of dataset "set1"
          - data["set1", :, :]      -> 2D slice at z=1 of 3D dataset "set1"
          - data[:, :, :]           -> 3D slice of default dataset self.data_set
          - data[:, :]              -> 2D slice at z=1 of default 3D dataset self.data_set
        """
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Packet file {self.filepath} does not exist.")

        with h5py.File(self.filepath, "r") as f:
            # Normalize key to a tuple
            if not isinstance(key, tuple):
                key = (key,)

            # Decide which dataset we are indexing
            if key and isinstance(key[0], str):
                # First element is dataset name
                dset_name = key[0]
                slice_key = key[1:]  # remaining elements are indices/slices
            else:
                # No dataset name provided: use default
                if self.data_set is None:
                    raise KeyError(
                        "No default dataset set for this packet and no dataset name "
                        "given in the index (e.g. data['set1', ...])."
                    )
                dset_name = self.data_set
                slice_key = key

            dset = f[dset_name]
            ndim = dset.ndim

            # If no explicit indices given -> return entire dataset
            if len(slice_key) == 0:
                return dset[...]  # same as dset[:], but more general

            # --- Dimension-normalization logic ---

            # 3D dataset, 2D key: treat as [1, :, :]
            # (change 1 -> 0 here if you want z=0 instead)
            if ndim == 3 and len(slice_key) == 2:
                slice_key = (1,) + slice_key

            # 2D dataset, 3D key: drop the first index, use remaining 2
            if ndim == 2 and len(slice_key) == 3:
                slice_key = slice_key[1:]

            # Optional: enforce correct number of indices
            if len(slice_key) > ndim:
                raise IndexError(
                    f"{len(slice_key)} indices given for {ndim}D dataset of "
                    f"shape {dset.shape}"
                )

            return dset[slice_key]

    def __getattr__(self, name, dset: str|None = None):
        """
        Get attribute if exists. Usage: ``self.some_attr`` or ``self.__getattr__("some_attr",dset="other_dataset")``.
        :param name: Attribute name.
        :param dset: Dataset. Defaults to current loaded one.
        :return: Attribute value.
        """
        # Called only if normal attributes (like path, dataset, etc.) are missing
        if name in self._attributes and dset is None:
            return self._attributes[name]
        with h5py.File(self.filepath, "r") as f:
            attrs = f[self.dataset if dset is None else dset].attrs
            if name in attrs:
                return attrs[name]
        # Important: if not found, raise AttributeError
        raise AttributeError(
            f"No attribute '{name}' in HDF5 attrs or loaded attributes"
        )

    def set_attribute(self, name, value, data_set: str|None = None):
        """
        Set single attribute in dataset.
        :param name: Name of attribute.
        :param value: Value of attribute.
        :param data_set: Dataset to add to. Defaults to current loaded one.
        """
        dset  = self.data_set if data_set is not None else data_set
        with h5py.File(self.filepath, "r+") as f:
            attrs = f[dset].attrs
            if data_set is None:
                self._attributes[name] = value
                attrs.update(self._attributes)
            else:
                attrs[name] = value
            f[dset].attrs = attrs

    def set_attributes(
        self, data_set: str | None = None, attributes: dict | None = None
    ):
        """
        Set attributes for the current or another data set.
        :param data_set: Dataset. Defaults to current loaded one.
        :param attributes: Dictionary of attributes to replace current one with.
        """
        dset  = self.data_set if data_set is not None else data_set
        with h5py.File(self.filepath, "r+") as f:
            f[dset].attrs = attributes if attributes is not None else self._attributes

    def rename_dataset(self, dataset: str, new_name: str, path: Path = Path("")):
        """
        Rename a dataset in a H5 file.
        :param dataset: Original dataset name.
        :param new_name: New dataset name.
        :param path: Path to other h5 file if not using current loaded one. This won't load it.
        """
        h5_path = path if str(path) != "." else self.filepath
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
        if self.data_set == dataset and h5_path == self.filepath:
            self.data_set = new_name

        self._log.info(f"Renamed dataset '{dataset}' to '{new_name}' in file {h5_path}")


    @property
    def shape(self, data_set: str | None = None):
        """Returns the shape of the packet's images without loading into RAM."""
        with h5py.File(self.filepath, 'r') as f:
            return f[self.data_set if data_set is None else data_set].shape


class Dem2SweepExperiment:
    """IO for managing full experimental data (multiple packets)."""

    def __init__(self, save_directory: str = ""):
        self._log = logging.getLogger(self.__class__.__name__)
        
        self.save_directory = save_directory or os.path.join(__datapath__, "dem2_sweep_experiment")
        self.packets: list[Dem2SweepPacket] =[]

        self.config = {}
        self.samples_per_a_scan = 0
        self.a_scans_b_scan = 0

        if os.path.exists(os.path.join(self.save_directory, "properties.yml")):
            self.load(self.save_directory)

    def create_new_packet(self) -> Dem2SweepPacket:
        """Instantiates a new empty packet in the experiment directory."""
        packet_idx = len(self.packets)
        packet_path = os.path.join(self.save_directory, f"sweep_packet_{packet_idx:03d}.h5")
        packet = Dem2SweepPacket(packet_path)
        self.packets.append(packet)
        return packet

    def __getitem__(self, key):
        """
        Slicing support. I.e. ``experiment[:, j]``.
        Returns frames across packets without killing RAM.
        """
        if isinstance(key, tuple):
            i, j = key
            if isinstance(i, slice):
                return [packet[j] for packet in self.packets[i]]
            else:
                return self.packets[i][j]
        else:
            return self.packets[key]

    def load(self, load_directory: str = ""):
        """Load experiment properties and identify all packet files."""
        if load_directory:
            self.save_directory = load_directory
            
        self._log.info("Loading Sweep experiment from directory '%s'...", self.save_directory)
        
        props_path = os.path.join(self.save_directory, "properties.yml")
        if not os.path.exists(props_path):
            self._log.warning("No properties.yml found in %s", self.save_directory)
            return

        with open(props_path, encoding="utf-8") as yml_file:
            properties = yaml.safe_load(yml_file)
            self.config = properties.get("config", {})
            self.samples_per_a_scan = properties.get("samples_per_a_scan", 0)
            self.a_scans_b_scan = properties.get("a_scans_b_scan", 0)

        # Load all h5 packets in alphabetical order
        self.packets =[]
        for file in sorted(os.listdir(self.save_directory)):
            if file.startswith("sweep_packet_") and file.endswith(".h5"):
                self.packets.append(Dem2SweepPacket(os.path.join(self.save_directory, file)))

    def save(self):
        """Save overarching experiment settings to directory."""
        os.makedirs(self.save_directory, exist_ok=True)
        properties_file = os.path.join(self.save_directory, "properties.yml")
        
        _dict_to_save = {
            "config": self.config,
            "samples_per_a_scan": self.samples_per_a_scan,
            "a_scans_b_scan": self.a_scans_b_scan,
        }
        
        self._log.info("Saving Sweep experiment to directory '%s'...", self.save_directory)
        with open(properties_file, "w", encoding="utf-8") as yml_file:
            yaml.safe_dump(_dict_to_save, yml_file, default_style=False)


class Dem2Results(Dem2SystemCalculator):
    """The Big Manager: Manages Configuration, State, and the Experiment."""

    def __init__(
        self,
        experiment: Dem2SweepExperiment | None = None,
        settings: dict | None = None,
        config: dict | None = None,
        b_scan_pattern: Dem2BScanPattern | None = None,
        load_from_directory: str = "",
    ):
        self._log = logging.getLogger(self.__class__.__name__)

        self.experiment = experiment if experiment is not None else Dem2SweepExperiment()

        # Update settings dictionary
        self._settings = config if config else {}
        self._settings.update(settings if settings else {})

        self.b_scan_pattern = b_scan_pattern if b_scan_pattern else Dem2BScanPattern()

        if load_from_directory:
            self.experiment.load(load_from_directory)
            self._settings.update(self.experiment.config)

        super().__init__(self._settings)

    def save_all(self):
        """Syncs config values and saves the whole experiment metadata."""
        self.experiment.config = self._settings
        self.experiment.save()

    @property
    def settings(self) -> dict:
        return self._settings

    @settings.setter
    def settings(self, value: dict):
        self._settings.update(value)