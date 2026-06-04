import logging
import os

import h5py
import numpy as np
import yaml

from src.dem_2_3d_label_free.__globals__ import __datapath__
from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern
from src.dem_2_3d_label_free.dem2_common.dem2_calculator import Dem2SystemCalculator


class Dem2SweepPacket:
    """IO for a single sweep (burst of images). Appends directly to HDF5 incrementally."""

    def __init__(self, filepath: str):
        self._log = logging.getLogger(self.__class__.__name__)
        self.filepath = filepath
        
        self._h5_file = None
        self._data = None
        self._frame_count = 0

    def start_capture(self):
        """Prepares the HDF5 file to receive streaming frames."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self._h5_file = h5py.File(self.filepath, 'w')
        self._data = None
        self._frame_count = 0

    def append_frame(self, frame_data: np.ndarray):
        """Appends a single frame to the open HDF5 dataset on the fly."""
        if self._h5_file is None:
            raise RuntimeError("Packet is not open. Call start_capture() first.")

        if self._data is None:
            h, w = frame_data.shape
            # Initialize resizable dataset on the first frame
            self._data = self._h5_file.create_dataset(
                "images",
                shape=(1, h, w),
                maxshape=(None, h, w),
                dtype=frame_data.dtype,
                chunks=(1, h, w)
            )
            self._data[0] = frame_data
        else:
            # Expand dataset and write new frame
            self._data.resize((self._frame_count + 1, self._data.shape[1], self._data.shape[2]))
            self._data[self._frame_count] = frame_data
            
        self._frame_count += 1

    def stop_capture(self):
        """Safely closes the file after capture is complete."""
        if self._h5_file is not None:
            self._h5_file.close()
            self._h5_file = None
            self._log.info("Saved %d frames to %s", self._frame_count, self.filepath)

    def __getitem__(self, key):
        """Allows slicing of images directly from the disk without filling RAM."""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Packet file {self.filepath} does not exist.")
        
        with h5py.File(self.filepath, 'r') as f:
            # Slices are read directly from the disk and returned as a numpy array
            return f['images'][key]

    @property
    def shape(self):
        """Returns the shape of the packet's images without loading into RAM."""
        with h5py.File(self.filepath, 'r') as f:
            return f['images'].shape


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