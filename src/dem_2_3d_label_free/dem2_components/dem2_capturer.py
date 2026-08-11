import logging
from threading import Thread

import numpy as np

import xiapi
from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2CameraMode, Dem2State
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2SweepPacket
from src.dem_2_3d_label_free.dem2_devices.dem2_camera import Dem2Camera


class Dem2Capturer(Thread):
    """Camera frame capturing thread. Streams directly to a Packet."""

    def __init__(
        self,
        cam: Dem2Camera,
        packet: Dem2SweepPacket | None,
        expected_frames: int,
        data_set: str | None = None,
    ):
        Thread.__init__(self)
        self._cam = cam
        self.packet = packet
        self.array_stack = None
        self.waiting = False
        if data_set is not None and self.packet is not None:
            if data_set:
                self.packet.data_set = data_set
        self._log = logging.getLogger(self.__class__.__name__)
        self._break = False
        self._expected_frames = expected_frames

    def end(self):
        self._break = True

    def run(self):
        if self._cam.mode != Dem2CameraMode.FRAME_BURST_EXT_TRIGGER:
            raise Dem2Errors.CameraError(
                "Camera must be in frame burst mode to run capturer"
            )
        if self._expected_frames < 1:
            raise Dem2Errors.CameraError("Camera capturer must expect >0 frames.")
        imgs = []

        is_capturing = False
        timeout = int(self._cam.t_frame + 1)
        self._log.info(f"Capturer Thread: Timeout set to {timeout} ms.")

        if self.packet is not None:
            # Prepare the packet (creates the file and readies the dataset)
            self.packet.open_file()
            self._log.info("Capturer Thread: Starting acquisition...")
            self._cam.start_acquisition()
        self._log.info("Capturer Thread: Waiting for external trigger...")

        try:
            while True:
                if self._break:
                    break
                try:
                    _img = xiapi.Image()
                    self.waiting = True
                    self._cam.get_image(_img, timeout=timeout, return_numpy=False)
                    imgs.append(_img)
                    if not is_capturing:
                        is_capturing = True
                        self._log.info(
                            "Capturer Thread: Triggered. Receiving frames..."
                        )

                except xiapi.Xi_error as err:
                    if err.status == 10:  # Timeout / XI_TIMEOUT
                        if is_capturing:
                            self._log.info(
                                "Capturer Thread: Time out after capturing started. Exiting..."
                            )
                            break
                        continue
                    else:
                        raise  # Rethrow unexpected hardware errors
        finally:
            # Crucial cleanup
            self._log.info(
                "Writing frames to " + "ram" if self.packet is None else "disk" + "..."
            )
            arrs = None
            for i in range(len(imgs)):
                if self._cam.state != Dem2State.RUNNING:
                    self._log.warning(
                        "Capturer Thread: Interruption while writing: Acquisition was stopped. Aborting."
                    )
                    break
                arr = imgs[i].get_image_data_numpy()
                if self.packet is not None:
                    self.packet.append_frame(arr)
                    if i % (len(imgs) // 10) == 0:
                        self._log.info(
                            f"writing frames {int((i / len(imgs)) * 100)}% ({('up to ' + str(imgs[i].nframe)) if i != 0 else 'starting at frame ' + str(imgs[i].nframe)})"
                        )
                else:
                    if i == 0:
                        arrs = np.zeros(shape=(len(imgs),) + arr.shape)
                    arrs[i] = arr
            self._log.info(f"Skipped api frames: {self._cam.get_counter_value()}")
            if self.packet is None:
                self.array_stack = arrs
                self._log.info("Capturer Thread: Arrays processed. Thread finished.")
                return
            self._log.info("Capturer Thread: Acquisition stopped. Thread finished.")
            self.packet.set_attributes()
            self.packet.close_file()
            self._cam.stop_acquisition()
