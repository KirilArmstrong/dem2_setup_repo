# dem2_sweep_experiment.py

### Data Format
This is the class that handles measurement files. It uses H5 files to store measurements in a compressed format.

Sample positions (C-scans) are stored in one H5 file as different Datasets. Indexing starts at 1.

Each dataset is a 2- or 3-dimensional array containing images of $\text{Height }(Y)\times \text{Width }(X)$ stacked along $Z$. If a single image was taken, then $Z=1$, otherwise it is the amount of images taken in a single sweep.

The class stores the file path of the H5 it interacts with.
```
packet = Dem2SweepPacket(filepath)
```
Dataset defaults to `"1"`.
### Reading
The class uses lazy loading to directly pull data from disk without needing to load the whole dataset.

You can read by directly passing it array parameters: `[Z: slice, H: slice, W, slice]`
```
first_image = packet[0, :, :]
```

You can read different datasets too: `[dataset: str, Z: slice, H: slice, W, slice]`
```
first_pos_third_image = packet["1", 2, :, :]

pos = 3
third_pos_first_image = packet[str(pos), 0, :, :]]
```

See `# Additional Functions > Attributes` on this page for information regarding reading attributes.
### Writing
There are two methods of writing into datasets.
1) Overwriting a whole dataset.
2) Appending a frame or multiple frames to a dataset.

In all cases, the file must be opened with
```
packet.open_file()
```

When finished, close with
```
packet.close_file()
```

#### 1. Overwriting
Overwrite a datasets data with
```
packet.set_array(data: np.ndarray, dataset: str)
```

> [!NOTE]
> This will preserve the datasets attributes. Overwrite them with `packet.set_attributes(attrs: dict)`.
> 
 See `# Additional Functions > Attributes` on this page for more information.

#### 2. Appending
You can append a single, or multiple frames to a dataset.

> [!IMPORTANT]
> Once a dataset is created and an append method is chosen, switching to another append method is not yet supported.

> [!NOTE]
> The frame(s) you are appending must be the same width and height as the existing frames in the dataset.
##### Single Frame
Append a single frame to the end of the image stack with
```
packet.append_frame(frame_array: np.ndarray, dataset: str)
```

##### Multiple Frames
First, create and prepare the dataset to accept frame batches with
```
packet.prepare_dataset(shape: tuple, dtype, chunks: tuple, dataset: str)
```
where `shape` is the shape of your frame or frame batch, i.e. (1, H, W) or (z, H, W), and `chunks` is the shape of how many frames to append each time, i.e. (z, H, W).

Then, append with
```
packet.write_batch(starting_index: int, data_batch: np.ndarray, dataset: str, axis: int)
```
where `starting_index` is the index to append to, which can be larger than the existing dataset.

> [!NOTE]
> Here, `axis` is default to 0. This appends a batch over Z. If you wish to append B scans over Y (Height) then set this to 1. This can be useful for batching OCT reconstruction.

### Additional Functions
#### Attributes
You can set individual attributes with
```
packet.set_attribute(attribute_name: str, value, dataset: str)
```

Overwrite attributes with a provided dictionary with
```
packet.set_attributes(attributes: dict, dataset: str)
```

You can get all attributes from a dataset with:
```
packet.get_attributes(dataset)
```

You can access individual attributes (settings and configs) by there names. i.e.
```
lam_min = packet.laser__wavelength_min
z_max = packet.system__depth_max
```

Config sub dictionaries have double underscores to indicate which parent dictionary they belonged to. So,
```
{
	laser: {
		wavelength_min: 805.0 
		wavelength_max: 880.0
	}
	system: {
		depth_max: 1000.0
	}
}
```
converts to:
```
{
	laser__wavelength_min: 805.0
	laser__wavelength_max: 880.0
	system__depth_max: 1000.0
}
```

> [!NOTE]
> Each dataset can have different attributes.

Get a string representation of all attributes with
```
print(packet.get_info())
```
#### Delete a dataset
Delete a dataset with 
```
packet.delete_dataset(dataset: str)
```

#### Trim a dataset
Trim a dataset along Z with
```
packet.trim_dataset(dataset: str, start: int, end: int)
```
where `start` index is included and `end` index is excluded.

> [!NOTE]
> This requires that no datasets in the H5 files are named `"temp_ds"`.

#### Rename a dataset
Rename a dataset with
```
packet.rename_dataset(dataset_to_rename: str, new_name: str, path, overwrite: bool)
```
where `path` points to the H5 file, though when this is `None` (its default) it will use the `self.filepath`. If the new name matches an existing one, it will not overwrite it unless `overwrite` is set to `True` (it is `False` by default.)

#### Properties
- `shape(dataset: str)` gives you the shape of a dataset without needing to load it into RAM. 

---

Tags: # | Quick Links: [[Home]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Home.md) | [[Packages]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Packages.md) | [[dem2_common]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Packages/dem2_common.md)

---
