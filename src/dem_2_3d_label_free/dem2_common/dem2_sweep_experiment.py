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


    def open_file(self):
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

    def close_file(self):
        """Safely closes the file after capture is complete."""
        if self._h5_file is not None:
            self._h5_file.close()
            self._h5_file = None
            self._log.info("Saved %d frames to %s in dataset %s", self._frame_count, self.filepath, self.data_set)

    def __getitem__(self, key):
        """
        Allows slicing of images directly from the disk without filling RAM.

        Supported patterns:
          - data["1", :, :, :]   -> 3D slice of dataset "1"
          - data["1"]            -> full array of dataset "1"
          - data["1", :, :]      -> 2D slice at z=1 of 3D dataset "1"
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
            attrs = f[self.data_set if dset is None else dset].attrs
            if name in attrs:
                return attrs[name]
        # Important: if not found, raise AttributeError
        raise AttributeError(
            f"No attribute '{name}' in HDF5 attrs or loaded attributes"
        )

    def set_attribute(self, name, value, data_set: str | None = None):
        """
        Set single attribute in dataset.
        :param name: Name of attribute.
        :param value: Value of attribute.
        :param data_set: Dataset to add to. Defaults to current loaded one.
        """
        dset = self.data_set if data_set is None else data_set

        with h5py.File(self.filepath, "r+") as f:
            if data_set is None:
                if value is None:
                    # remove from internal store if present
                    if name in self._attributes:
                        del self._attributes[name]
                    # remove from the actual dataset attributes
                    if name in f[dset].attrs:
                        del f[dset].attrs[name]
                    return
                # normal set when data_set is None
                self._attributes[name] = value
                f[dset].attrs.update(self._attributes)
                return

            # data_set specified
            if value is None:
                # delete attribute if exists
                if name in f[dset].attrs:
                    del f[dset].attrs[name]
                return

            f[dset].attrs[name] = value


    def set_attributes(
        self, attributes: dict | None = None, data_set: str | None = None
    ):
        """
        Set attributes for the current or another data set.
        :param data_set: Dataset. Defaults to current loaded one.
        :param attributes: Dictionary of attributes to replace current one with.
        """
        dset = self.data_set if data_set is None else data_set
        target_data = attributes if attributes is not None else getattr(self, '_attributes', {})

        with h5py.File(self.filepath, "r+") as f:
            dataset = f[dset]
            dataset.attrs.clear()

            def flatten(d, parent_key='', sep='__'):
                items = []
                for k, v in d.items():
                    new_key = f"{parent_key}{sep}{k}" if parent_key else k
                    if isinstance(v, dict):
                        items.extend(flatten(v, new_key, sep=sep).items())
                    elif isinstance(v, tuple):
                        # Convert tuple to list (numpy handles this better)
                        items.append((new_key, list(v)))
                    elif isinstance(v, (list, int, float, str, bool)):
                        items.append((new_key, v))
                    else:
                        # Skip unsupported types or convert to string
                        items.append((new_key, str(v)))
                return dict(items)

            flat_data = flatten(target_data)

            for key, value in flat_data.items():
                try:
                    dataset.attrs[key] = value
                except Exception as e:
                    # Fallback to string if specific type fails
                    self._log.warning(f"Failed to set attr {key} ({type(value)}), storing as string: {e}")
                    dataset.attrs[key] = str(value)

    def get_attributes(
        self, data_set: str | None = None
    )-> dict:
        """
        Get attributes for the current or another data set.
        :param data_set: Dataset. Defaults to current loaded one.
        """
        dset = self.data_set if data_set is None else data_set

        with h5py.File(self.filepath, "r") as f:
            # Read all attrs as a flat dict
            raw_attrs = dict(f[dset].attrs)

            if not raw_attrs:
                return {}

            # Helper to reconstruct nested dict
            def unflatten(flat_dict: dict, sep: str = '__') -> dict:
                result = {}
                for key, value in flat_dict.items():
                    parts = key.split(sep)
                    current = result

                    # Traverse/Create path
                    for i, part in enumerate(parts[:-1]):
                        if part not in current:
                            current[part] = {}
                        elif not isinstance(current[part], dict):
                            # Collision: key exists but isn't a dict (shouldn't happen if consistent)
                            current[part] = {}

                        current = current[part]

                    # Set the final value
                    current[parts[-1]] = value

                return result

            reconstructed = unflatten(raw_attrs, sep='__')

            # If this is the "current" dataset, update local cache
            if data_set is None:
                self._attributes = reconstructed

            return reconstructed

    def rename_dataset(self, dataset: str, new_name: str, path: Path = Path(""), overwrite: bool = False):
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
                if overwrite:
                    del f[new_name]
                else:
                    raise KeyError(
                        f"Target dataset name '{new_name}' already exists in file '{h5_path}'. Set overwrite=True to overwrite it."
                    )

            # Copy dataset to new name
            f.copy(dataset, new_name)
            # Remove old dataset
            del f[dataset]

        # Update instance default dataset name if it was renamed
        if self.data_set == dataset and h5_path == self.filepath:
            self.data_set = new_name

        self._log.info(f"Renamed dataset '{dataset}' to '{new_name}' in file {h5_path}")

    def trim_dataset(self, data_set, start, end):
        """
        Trim the no. of images in a data set.
        :param data_set: Dataset to trim.
        :param start: Start k index.
        :param end: End k index (does not include)
        """
        self.open_file()
        if "temp_ds" in self._h5_file:
            self.close_file()
            raise KeyError(
                f"Target dataset name 'temp_ds' already exists in file '{self.filepath}'. Please delete or rename it."
            )
        for i in range(self.shape[0]):
            self.append_frame(self[start+i:end,:,:], "temp_ds")
        self.close_file()
        self.set_attributes(self.get_attributes(data_set),"temp_ds")
        self.rename_dataset("temp_ds", data_set, overwrite=True)
        self._log.info(f"'{data_set}' dataset trimmed.")


    def delete_dataset(self, data_set):
        self.open_file()
        del self._h5_file[data_set]
        self.close_file()
        self._log.info(f"'{data_set}' dataset deleted.")

    @property
    def shape(self, data_set: str | None = None):
        """Returns the shape of the packet's images without loading into RAM."""
        with h5py.File(self.filepath, 'r') as f:
            return f[self.data_set if data_set is None else data_set].shape