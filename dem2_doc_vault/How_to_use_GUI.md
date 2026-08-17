# How_to_use_GUI

### Operation Modes
#### Single Image:
Camera Mode: Mono
Laser Mode: CW

1) Set CW wavelength.
2) Connect then Initialise.
3) Optional: Toggle FFT to fft it in gui (See Software ROI). Toggle Save to save as h5.
4) Click capture.

#### Live Images
Camera Mode: Mono
Laser Mode: CW

1) Set CW wavelength.
2) Connect then Initialise.
3) Optional: Toggle FFT to fft it in gui (See Software ROI). Toggle Save to save **every frame** as h5.
4) Click Live.

#### Continuous Sweep
Camera Mode: Frame Burst
Laser Mode: Single

1) Connect devices.
2) Set start & end wavelengths. **NOTE:** Total time, sweep speed, and number of frames are calculated automatically based on the z_max depth in config.yml. z_max=475 um --> ~100 images.
3) Initialise controller OR Initialise camera **then** Laser.
4) Click "Camera Burst". This will set the camera to wait for hardware trigger.
5) Toggle Laser.

> [!NOTE] 
> The images are saved into a h5 file called `images.h5` in the `data/` folder. Running multiple times will overwrite previous `images.h5` files.

#### Discrete Sweep
Camera Mode: Mono
Laser Mode: CW

1) Connect devices.
2) Set start & end wavelengths. **NOTE:** Number of frames are calculated automatically based on the z_max depth in config.yml. z_max=475 um --> ~100 images. This determines the number of ks you will sample. It also automatically keeps the ks linear (though stores in lambda using $k=\frac{2\pi}{\lambda}$)
3) Initialise controller OR Initialise camera **then** Laser.
4) Click "Discrete Sweep". **NOTE:** This will automatically turn the laser on and off over the sweep.

> [!NOTE] 
> The images are saved into a h5 file called `images.h5` in the `data/` folder. Running multiple times will overwrite previous `images.h5` files.

### Additional Information

#### Software ROI (SROI)

You can set a ROI for the GUI FFT to use to speed up calculation time.

In the camera section, under the ROI tab, you can set ROI corners.
##### Camera SROI
This is the ROI to FFT. Selects a ROI between top left point and bottom right.

##### FT SROI
This is the ROI to crop out the first order. Choose a centre X and Y point (within the camera SROI). Choose a Width and Height to determine the size of the ROI.

The chosen FT SROI will then be cropped out, the chosen centre XY will be shifted to the zero freq. point (0, 0). It will be zero padded to the size of the camera SROI. It will then be iFFTed, and the resulting phase shown in the third image.

#### Hardware ROI (HROI)

The camera has the ability to choose a ROI too. This can be set in the `config.yml` file and will apply to all camera modes.

The offset tells the starting pixel (top left corner) and the width/height controls the HROIs width and height.

You can also set this in the GUI, within the `H-ROI` tab, as long as you are connected to the camera.  

> [!IMPORTANT]
> You cant select any random number for these values. They must be a multiple of the `increment` parameter of the camera. This is printed in the logs when connecting to the camera. For Demonstrator 2, the increments for X and Y are 32 and 2 respectively.

> [!NOTE]
> Read time is increased by lowering the amount of vertical pixels (Height), and data transfer is increased by lowering the amount of horizontal pixels (Width)

---

Tags: #GUI | Quick Links: [[Home]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Home.md) | [[Set_Up]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Set_Up.md)

---
