# Set_Up

### Camera Hardware Triggering

To properly connect the camera to the laser for triggering ensure:
- The Laser Sync PCB is connected to the REMOTE port of the laser.
- Your trigger cable is connected to the OUT port of the Laser Sync PCB
- You know what cable is Ground.

For Demonstrator 2 Yellow is Ground and Green is Out.
##### Connect it to the Camera trigger cables as follows:

If `camera.initialize()` has `set_gpi_selector` set to `XI_GPI_PORT2`:
```
PCB GND > Yellow (Ground) --> Grey > Camera
PCB OUT > Green (Out)     --> Pink > Camera
```

OR

If `camera.initialize()` has `set_gpi_selector` set to `XI_GPI_PORT1`:
```
PCB GND > Yellow (Ground) --> Red  > Camera
PCB OUT > Green (Out)     --> Blue > Camera
```

