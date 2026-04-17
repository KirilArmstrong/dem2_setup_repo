from logging import Logger
from threading import Thread
import xiapi
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2SweepPacket


class Dem2Capturer(Thread):
    """Camera frame capturing thread. Streams directly to a Packet."""

    def __init__(self, log: Logger, cam: xiapi.Camera, packet: Dem2SweepPacket):
        Thread.__init__(self)
        self._cam = cam
        self._packet = packet
        self._log = log

    def run(self):
        img = xiapi.Image()

        self._log.info("Capturer Thread: Starting acquisition...")
        self._cam.start_acquisition()

        is_capturing = False

        # Prepare the packet (creates the file and readies the dataset)
        self._packet.start_capture()
        self._log.info("Capturer Thread: Waiting for external signal to go HIGH...")

        try:
            while True:
                try:
                    # Timeout of 500ms acts as our event listener for LOW
                    self._cam.get_image(img, timeout=500)

                    if not is_capturing:
                        self._log.info("Capturer Thread: Signal is HIGH! Receiving frames...")
                        is_capturing = True

                    # Feed frame view directly to HDF5 appender
                    self._packet.append_frame(img.get_image_data_numpy())

                except xiapi.Xi_error as err:
                    if err.status == 10:  # Timeout / XI_TIMEOUT
                        if is_capturing:
                            self._log.info("Capturer Thread: Signal went LOW. Burst complete.")
                            break  # Exits the infinite loop, allowing thread to die cleanly
                        else:
                            # Still waiting for signal to go HIGH for the first time
                            continue
                    else:
                        raise  # Rethrow unexpected hardware errors
        finally:
            # Crucial cleanup
            self._packet.stop_capture()
            self._cam.stop_acquisition()
            self._log.info("Capturer Thread: Acquisition stopped. Thread finished.")