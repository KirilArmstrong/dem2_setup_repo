# dem2_laser.py

Contains the `Dem2Laser` class.

To use:
- Instantiate a Dem2Laser object.
- Ensure the laser is connected to the computer.
- Run `connect()` to establish a connection.
- Set the time for a full sweep. The sweep speed is automatically calculated.
- Initialize the device with `initialize()`.
- After use, disconnect with `disconnect()`.

### Commands

Laser command definitions are in package `dem2_common > dem2_laser_defs.py`.

Send a command with `laser.send_command(cmd, param)`, i.e. `laser.send_command(LS_PRM_USR_SINGLE_WL, 0000)` or `laser.send_command(LS_DEVICE_INFO)`. Refer to laser documentation for command explanations.

Some built in functions for commands include (They all auto convert to hex where needed):
- `send_cw(wavelength)` - Single wavelength.
- `send_sweep_speed(sweep_speed)` - Sweep speed.
- `send_lambda_min_max(min_lambda, max_lambda)` - Min and max wavelengths. 
- `get_device_info` Sends info command.

---

Tags: # | Quick Links: [[Home]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Home.md) | [[Packages]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Packages.md) | [[dem2_devices]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Packages/dem2_devices.md)

---
