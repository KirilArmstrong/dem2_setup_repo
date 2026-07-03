import logging
from threading import Thread

import xiapi
from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2CameraMode
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2SweepPacket
from src.dem_2_3d_label_free.dem2_devices.dem2_camera import Dem2Camera


class Dem2Capturer(Thread):
    """Camera frame capturing thread. Streams directly to a Packet."""

    def __init__(self, cam: Dem2Camera, packet: Dem2SweepPacket, expected_frames: int):
        Thread.__init__(self)
        self._cam = cam
        self._packet = packet
        self._log = logging.getLogger(self.__class__.__name__)
        self._break = False
        self._expected_frames = expected_frames

    def end(self):
        self._break = True

    def run(self):
        if self._cam.mode != Dem2CameraMode.FRAME_BURST_EXT_TRIGGER:
            raise Dem2Errors.CameraError("Camera must be in frame burst mode to run capturer")
        if self._expected_frames < 1:
            raise Dem2Errors.CameraError("Camera capturer must expect >0 frames.")
        # img = xiapi.Image()
        imgs = []

        self._log.info("Capturer Thread: Starting acquisition...")
        self._cam.start_acquisition()

        # Prepare the packet (creates the file and readies the dataset)
        self._packet.start_capture()
        self._log.info("Capturer Thread: Waiting for external trigger...")

        is_capturing = False
        # timeout = int(self._cam.concat_amm*(self._cam.t_exp+1))+1
        timeout = int(self._cam.t_exp+self._cam.t_read+1)
        self._log.info(f"Capturer Thread: Timeout set to {timeout} ms.")

        try:
            while True:
                if self._break: break
                try:
                    _img = xiapi.Image()
                    self._cam.get_image(_img, timeout=timeout, return_numpy=False)
                    imgs.append(_img)
                    if not is_capturing:
                        is_capturing = True
                        self._log.info("Capturer Thread: Triggered. Receiving frames...")

                except xiapi.Xi_error as err:
                    if err.status == 10:  # Timeout / XI_TIMEOUT
                        if is_capturing:
                            self._log.info("Capturer Thread: Time out after capturing started. Exiting...")
                            break
                        continue
                    else:
                        raise  # Rethrow unexpected hardware errors
        finally:
            # Crucial cleanup
            self._log.info("Writing frames to disk...")

            for i in range(len(imgs)):
                arr = imgs[i].get_image_data_numpy()
                # self._log.info(f"writing frame {imgs[i].nframe}-{imgs[i].nframe+self._cam.concat_amm} to disk... its shape is {arr.shape}")
                self._packet.append_frame(arr)
                if i%(len(imgs)//10)==0:
                    self._log.info(
                        f"writing frames {int((i/len(imgs))*100)}% ({('up to ' + str(imgs[i].nframe)) if i != 0 else 'starting at frame ' + str(imgs[i].nframe)})")
            self._packet.stop_capture()
            self._log.info(f"Skipped api frames: {self._cam.get_counter_value()}")
            self._cam.stop_acquisition()
            self._log.info("Capturer Thread: Acquisition stopped. Thread finished.")