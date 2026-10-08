"""
Main GUI for Dem2. Broken down into 3 classes:
- SystemState - Object for storing global states for the set-up.
- ProcessingWorker - This is a background processor that runs a separate thread so the GUI doesnt lock up when
running long experiments, or live.
- MainWindow - The GUI and its functions.
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
import threading
import numpy as np
import cupy as cp
from PySide6.QtCore import Qt, QTimer, QThread, QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QMessageBox,
    QCheckBox,
    QSizePolicy,
    QTabWidget,
    QLineEdit,
)

from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern  # noqa: F401
from src.dem_2_3d_label_free.dem2_common.dem2_constants import (
    Dem2State,
    Dem2LaserMode,
    Dem2CameraMode,
    STATUS_MAP,
    MODES,
    Dem2StageMode,
)
from src.dem_2_3d_label_free.dem2_common.dem2_errors import Dem2Errors
from src.dem_2_3d_label_free.dem2_common.dem2_helper import (
    setup_root_logger,
    oct_reconstruct,
    compute_fft,
    covert_fft_to_img,
    numpy_to_qpixmap,
    crop_centre_ifft,
    phase_to_hsv,
    ui_prep_img,
)
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2SweepPacket
from src.dem_2_3d_label_free.dem2_components.dem2_capturer import Dem2Capturer
from src.dem_2_3d_label_free.dem2_components.dem2_controller import Dem2Controller
from src.dem_2_3d_label_free.__globals__ import __config__, __datapath__

DATA_PATH = Path(__datapath__)
default_config = __config__

# Single shared controller
controller = Dem2Controller(default_config)


class SystemState:
    def __init__(self):
        self.devices = {
            "controller": {"id": "controller", "status": 0, "name": "MASTER_CTRL"},
            "laser": {"id": "laser", "status": 0, "mode": 0, "name": "LASER_SRC"},
            "camera": {"id": "camera", "status": 0, "mode": 0, "name": "XIB64_CAM"},
            "stage": {"id": "stage", "status": 0, "mode": 0, "name": "MTB_STAGE"},
        }
        self.integration_time = controller.camera.t_exp
        self.isLive = False
        self.isCaptBurst = False
        self.fftEnabled = False
        self.saveEnabled = False
        self.octEnabled = False


class ProcessingWorker(QObject):
    """
    Worker that acquires frames from the camera and performs FFT/iFFT/phase
    computation off the GUI thread. Emits numpy arrays ready for display.
    """

    frame_ready = Signal(object, object, object)  # display_rgb, fft_img_u8, phase_rgb
    fft_roi_moved = Signal(int, int)  # new cx, cy

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._active = True  # overall loop flag
        self._running = False  # live flag
        self._fft_enabled = False
        self._fft_track = False
        self._gamma = 0.3
        self._oct_recon_y_level = 1
        self._oct_mode = False
        self._padding = 0
        # ROIs: (tl_x, tl_y, br_x, br_y)
        self._cam_roi = (0, 0, 0, 0)
        # FFT ROI now stored as (cx, cy, width, height)
        self._fft_roi = (0, 0, 0, 0)
        self._log = logging.getLogger(self.__class__.__name__)

    def stop(self):
        self._active = False

    def set_running(self, running: bool):
        self._running = running

    def set_oct_mode(self, oct_mode: bool):
        self._oct_mode = oct_mode

    def set_oct_recon_y_level(self, oct_recon_y_level: bool):
        self._oct_recon_y_level = oct_recon_y_level

    def set_padding(self, padding: int):
        self._padding = padding

    def set_fft_enabled(self, enabled: bool):
        self._fft_enabled = enabled

    def set_fft_tracking(self, enabled: bool):
        self._fft_track = bool(enabled)

    def set_gamma(self, gamma: float):
        self._gamma = float(gamma)

    def set_cam_roi(self, tl_x: int, tl_y: int, br_x: int, br_y: int):
        self._cam_roi = (int(tl_x), int(tl_y), int(br_x), int(br_y))

    def set_fft_roi(self, cx: int, cy: int, w: int, h: int):
        self._fft_roi = (int(cx), int(cy), int(w), int(h))

    def run(self):
        while self._active:
            if not self._running:
                QThread.msleep(50)
                continue
            if self.controller.camera.state != Dem2State.RUNNING:
                QThread.msleep(20)
                continue
            t0 = datetime.now()
            if self._oct_mode:
                image_array = controller.run_single_sweep()
                if image_array is None:
                    continue
                image_array = image_array[:, self._oct_recon_y_level, :]
                # image_array = np.real(image_array)
                image_array = oct_reconstruct(image_array, self._padding)
                y = image_array.shape[0] // 2
                image_array[y - 2 : y + 2, :] = 0
                image_array = image_array**self._gamma
            else:
                image_array = self.controller.camera.get_image(
                    self.controller.camera.image
                )

            if image_array is None:
                continue
            display_rgb, display_arr = ui_prep_img(image_array)

            if self._oct_mode:
                self.frame_ready.emit(display_rgb, None, None)
                self._log.info(f"FPS: {1 / (datetime.now() - t0).total_seconds()}.")
                continue
            h, w = display_arr.shape[:2]
            # Camera ROI (clamped independently of GUI spin max)
            tl_x, tl_y, br_x, br_y = self._cam_roi
            cx1 = max(0, min(tl_x, w - 1))
            cy1 = max(0, min(tl_y, h - 1))
            cx2 = max(0, min(br_x, w - 1))
            cy2 = max(0, min(br_y, h - 1))
            cx2 = max(cx1, cx2)
            cy2 = max(cy1, cy2)
            has_cam_roi = (cx2 > cx1) and (cy2 > cy1)
            color = [255, 255, 255]
            if has_cam_roi:
                thickness = 2
                display_rgb[cy1 : min(cy1 + thickness, cy2 + 1), cx1 : cx2 + 1] = color
                display_rgb[max(cy2 - thickness + 1, cy1) : cy2 + 1, cx1 : cx2 + 1] = (
                    color
                )
                display_rgb[cy1 : cy2 + 1, cx1 : min(cx1 + thickness, cx2 + 1)] = color
                display_rgb[cy1 : cy2 + 1, max(cx2 - thickness + 1, cx1) : cx2 + 1] = (
                    color
                )
            # Crop to camera ROI for FFT processing
            proc_array = display_arr[cy1:cy2, cx1:cx2] if has_cam_roi else display_arr
            fft_img = None
            phase_rgb = None
            if self._fft_enabled and proc_array.size > 0:
                # Full FFT/iFFT/phase every frame
                proc_arr_cp = cp.array(proc_array)
                ft_arr = compute_fft(proc_arr_cp)
                fft_img_u8 = covert_fft_to_img(ft_arr, self._gamma)
                fh, fw = ft_arr.shape[:2]

                # --- FFT ROI handling ---
                cx, cy, roi_w, roi_h = self._fft_roi

                # Initial TL/BR (clamped) defining the search window
                x1 = cx - roi_w // 2
                y1 = cy - roi_h // 2
                x2 = x1 + roi_w
                y2 = y1 + roi_h
                x1 = max(0, min(x1, fw - 1))
                y1 = max(0, min(y1, fh - 1))
                x2 = max(0, min(x2, fw - 1))
                y2 = max(0, min(y2, fh - 1))
                x2 = max(x1, x2)
                y2 = max(y1, y2)

                # TRACKING: find the brightest spot inside current ROI
                if self._fft_track and (x2 > x1) and (y2 > y1):
                    roi_slice = ft_arr[y1:y2, x1:x2]
                    if roi_slice.size > 0:
                        mag = np.abs(roi_slice)
                        max_val = mag.max()
                        ys, xs = np.where(mag == max_val)
                        cx = int(round(xs.mean().item())) + x1
                        cy = int(round(ys.mean().item())) + y1
                        self._fft_roi = (cx, cy, roi_w, roi_h)
                        self.fft_roi_moved.emit(cx, cy)

                # Final TL/BR using (possibly tracked) centre
                x1 = cx - roi_w // 2
                y1 = cy - roi_h // 2
                x2 = x1 + roi_w
                y2 = y1 + roi_h
                x1 = max(0, min(x1, fw - 1))
                y1 = max(0, min(y1, fh - 1))
                x2 = max(0, min(x2, fw - 1))
                y2 = max(0, min(y2, fh - 1))
                x2 = max(x1, x2)
                y2 = max(y1, y2)

                # Phase image via IFFT of centred crop
                ifft_arr = crop_centre_ifft(ft_arr, (x1, y1), (x2, y2))
                phase_rgb = phase_to_hsv(ifft_arr)

                # FFT display with ROI rectangle and centre cross
                rgb_fft = cp.stack([fft_img_u8, fft_img_u8, fft_img_u8], axis=-1)
                if x2 > x1 and y2 > y1:
                    th = 2
                    rgb_fft[y1 : min(y1 + th, y2), x1:x2] = cp.asarray(color)
                    rgb_fft[max(y2 - th, y1) : y2, x1:x2] = cp.asarray(color)
                    rgb_fft[y1:y2, x1 : min(x1 + th, x2)] = cp.asarray(color)
                    rgb_fft[y1:y2, max(x2 - th, x1) : x2] = cp.asarray(color)

                    # Red cross at centre
                    arm = (
                        max(5, min(roi_w, roi_h) // 4)
                        if roi_w > 0 and roi_h > 0
                        else 10
                    )
                    cx_c = max(0, min(cx, fw - 1))
                    cy_c = max(0, min(cy, fh - 1))
                    x_start = max(0, cx_c - arm)
                    x_end = min(fw, cx_c + arm + 1)
                    y_start = max(0, cy_c - arm)
                    y_end = min(fh, cy_c + arm + 1)
                    rgb_fft[cy_c, x_start:x_end] = cp.asarray(color)
                    rgb_fft[y_start:y_end, cx_c] = cp.asarray(color)
                fft_img = rgb_fft
            self.frame_ready.emit(
                display_rgb,
                fft_img.get() if fft_img is not None else fft_img,
                phase_rgb.get() if phase_rgb is not None else phase_rgb,
            )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._log = logging.getLogger(self.__class__.__name__)
        self.state = SystemState()
        self._stage_thread = None
        self._stage_generation = 0
        self._last_fft_array = None
        # Camera Hardware ROI (H ROI) – kept as OFFSET Y/X and H/W
        self.cam_hroi_ofs_x = 0
        self.cam_hroi_ofs_y = 0
        self.cam_hroi_width = 0
        self.cam_hroi_height = 0
        # Camera ROI (pre-FFT crop) – kept as TL / BR
        self.cam_roi_tl_x = 0
        self.cam_roi_tl_y = 0
        self.cam_roi_br_x = 0
        self.cam_roi_br_y = 0
        # FFT ROI (for phase calculation) – now centre + width/height
        self.fft_roi_cx = 0
        self.fft_roi_cy = 0
        self.fft_roi_w = 0
        self.fft_roi_h = 0
        # Worker thread for live acquisition + processing
        self.proc_thread = QThread(self)
        self.proc_worker = ProcessingWorker(controller)
        self.proc_worker.moveToThread(self.proc_thread)
        self.proc_thread.started.connect(self.proc_worker.run)
        self.proc_worker.frame_ready.connect(self._update_from_worker)
        self.proc_worker.fft_roi_moved.connect(self._on_fft_roi_moved)
        self.proc_thread.start()
        self.setWindowTitle("DEMONSTRATOR_2 // V.0.2")
        self.resize(1400, 900)
        # Main font similar to monospace terminal look
        mono_font = QFont("Courier New")
        self.setFont(mono_font)
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("DEMONSTRATOR 2")
        title_label.setStyleSheet("color: cyan; font-size: 20pt; font-weight: bold;")
        subtitle_label = QLabel("Control Panel v0.2")
        subtitle_label.setStyleSheet("color: #0ea5e9; font-size: 8pt;")
        left_header = QVBoxLayout()
        left_header.addWidget(title_label)
        left_header.addWidget(subtitle_label)
        self.clock_label = QLabel("")
        self.clock_label.setStyleSheet("color: cyan; font-weight: bold;")
        header_layout.addLayout(left_header)
        header_layout.addStretch()
        header_layout.addWidget(self.clock_label)
        main_layout.addLayout(header_layout)
        # Top: controller master and status table
        ctrl_group = QGroupBox("MASTER CONTROLLER")
        ctrl_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        ctrl_group.setStyleSheet("QGroupBox { color: #22d3ee; }")
        ctrl_layout = QVBoxLayout(ctrl_group)
        btn_layout = QHBoxLayout()
        self.btn_ctrl_connect = QPushButton("Connect")
        self.btn_ctrl_init = QPushButton("Initialize")
        self.btn_ctrl_disc = QPushButton("Disconnect")
        btn_layout.addWidget(self.btn_ctrl_connect)
        btn_layout.addWidget(self.btn_ctrl_init)
        btn_layout.addWidget(self.btn_ctrl_disc)
        btn_layout.addStretch()
        ctrl_layout.addLayout(btn_layout)
        # Status table
        self.status_table = QTableWidget(4, 5)
        self.status_table.setHorizontalHeaderLabels(
            ["DEVICE", "STATUS CODE", "STATE DESC", "MODE", "INDICATOR"]
        )
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        ctrl_layout.addWidget(self.status_table)
        ctrl_layout.addStretch()
        # Upper grid: Camera (full width)
        cam_group = QGroupBox("CAMERA FEEDS")
        cam_group.setStyleSheet("QGroupBox { color: #22c55e; }")
        cam_layout = QVBoxLayout(cam_group)
        # --- ROW 2: THREE IMAGE VIEWS (3 COLUMNS) ---
        images_row_layout = QHBoxLayout()
        # Main live view
        self.label_cam_live = QLabel("NO SIGNAL")
        # FFT view
        self.label_cam_fft = QLabel("NO DATA")
        # Captured view
        self.label_cam_phase = QLabel("NO DATA")
        for lbl in (self.label_cam_live, self.label_cam_fft, self.label_cam_phase):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("background-color: black; color: #64748b;")
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            lbl.setMinimumSize(200, 150)
        images_row_layout.addWidget(self.label_cam_live)  # main view
        images_row_layout.addWidget(self.label_cam_fft)  # FT view
        images_row_layout.addWidget(self.label_cam_phase)  # captured view
        cam_layout.addLayout(images_row_layout)
        # Cam control
        camctrl_group = QGroupBox("CAMERA CTRL")
        camctrl_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        camctrl_group.setStyleSheet("QGroupBox { color: #22c55e; }")
        # --- ROW 1: ALL CAMERA CONTROLS ---
        # Status + mode + connect/init/disc
        camctrl_layout = QVBoxLayout(camctrl_group)
        self.cam_status_label = QLabel("STATUS: DISCONNECTED")
        self.cam_mode_combo = QComboBox()
        self.cam_mode_combo.addItems(["Mono", "Frame Burst"])
        self.btn_cam_connect = QPushButton("Conn.")
        self.btn_cam_init = QPushButton("Init.")
        self.btn_cam_disc = QPushButton("Disc.")
        camctrl_layout.addWidget(self.cam_status_label)
        top_camctrl_btns = QHBoxLayout()
        top_camctrl_btns.addWidget(self.btn_cam_connect)
        top_camctrl_btns.addWidget(self.btn_cam_init)
        top_camctrl_btns.addWidget(self.btn_cam_disc)
        camctrl_layout.addLayout(top_camctrl_btns)
        camctrl_layout.addWidget(self.cam_mode_combo)
        # Capture / gamma / FFT / Save
        grid_camctrl = QGridLayout()
        self.btn_cam_capture = QPushButton("Capture")
        self.chk_fft = QCheckBox("FFT 2D")
        self.chk_save = QCheckBox("Save")
        self.chk_oct = QCheckBox("OCT Mode")
        self.gamma_spin = QDoubleSpinBox()
        self.frames = QLabel("1")
        self.frames2 = QLabel("1")
        self.gamma_spin.setRange(0.0, 1.0)
        self.gamma_spin.setSingleStep(0.1)
        self.gamma_spin.setValue(0.3)
        self.btn_cam_live = QPushButton("Live")
        self.btn_cam_burst = QPushButton("Capt. Burst")
        self.btn_reac_cont_oct = QPushButton("Show")
        self.btn_cam_disc_sweep = QPushButton("Discrete Swp.")
        self.btn_cam_set_int = QPushButton("Set Texp")
        self.int_time_spin = QDoubleSpinBox()
        self.int_time_spin.setRange(0.1, 1000.0)
        self.int_time_spin.setSingleStep(0.01)
        self.int_time_spin.setValue(controller.camera.t_exp)
        grid_camctrl.addWidget(QLabel("Int. time [ms]"), 0, 0)
        grid_camctrl.addWidget(self.int_time_spin, 0, 1)
        grid_camctrl.addWidget(self.btn_cam_set_int, 0, 2)
        grid_camctrl_mono = QGridLayout()
        grid_camctrl_burst = QGridLayout()
        grid_camctrl_mono.addWidget(QLabel("Gamma"), 2, 0)
        grid_camctrl_mono.addWidget(self.gamma_spin, 2, 1)
        grid_camctrl_mono.addWidget(self.frames, 1, 2)
        grid_camctrl_burst.addWidget(self.frames2, 0, 1)
        grid_camctrl_mono.addWidget(self.chk_fft, 1, 0)
        grid_camctrl_mono.addWidget(self.chk_save, 2, 2)
        grid_camctrl_mono.addWidget(self.chk_oct, 1, 1)
        grid_camctrl_mono.addWidget(self.btn_cam_capture, 0, 0)
        grid_camctrl_mono.addWidget(self.btn_cam_live, 0, 1)
        grid_camctrl_burst.addWidget(self.btn_cam_burst, 0, 0)
        grid_camctrl_burst.addWidget(self.btn_reac_cont_oct, 1, 0)
        grid_camctrl_mono.addWidget(self.btn_cam_disc_sweep, 0, 2)

        tabs_camctrl_mode = QTabWidget()
        # Control tab
        mono_widget = QWidget()
        mono_layout = QVBoxLayout(mono_widget)
        mono_layout.addLayout(grid_camctrl_mono)
        tabs_camctrl_mode.addTab(mono_widget, "Mono")
        # ROIs tab
        burst_widget = QWidget()
        burst_layout = QVBoxLayout(burst_widget)
        burst_layout.addLayout(grid_camctrl_burst)
        tabs_camctrl_mode.addTab(burst_widget, "Burst")

        grid_camctrl_sroi = QGridLayout()
        # Camera ROI controls (pre-FFT crop)
        self.spin_cam_sroi_tl_x = QSpinBox()
        self.spin_cam_sroi_tl_y = QSpinBox()
        self.spin_cam_sroi_br_x = QSpinBox()
        self.spin_cam_sroi_br_y = QSpinBox()
        for s in (
            self.spin_cam_sroi_tl_x,
            self.spin_cam_sroi_tl_y,
            self.spin_cam_sroi_br_x,
            self.spin_cam_sroi_br_y,
        ):
            s.setRange(0, 10000)
        self.btn_cam_sroi_apply = QPushButton("Apply")
        grid_camctrl_sroi.addWidget(QLabel("CAM TL X"), 0, 0)
        grid_camctrl_sroi.addWidget(self.spin_cam_sroi_tl_x, 0, 1)
        grid_camctrl_sroi.addWidget(QLabel("CAM TL Y"), 1, 0)
        grid_camctrl_sroi.addWidget(self.spin_cam_sroi_tl_y, 1, 1)
        grid_camctrl_sroi.addWidget(QLabel("CAM BR X"), 2, 0)
        grid_camctrl_sroi.addWidget(self.spin_cam_sroi_br_x, 2, 1)
        grid_camctrl_sroi.addWidget(QLabel("CAM BR Y"), 3, 0)
        grid_camctrl_sroi.addWidget(self.spin_cam_sroi_br_y, 3, 1)
        # FFT ROI controls (for phase calculation) – now centre + width/height
        self.spin_fft_roi_cx = QSpinBox()
        self.spin_fft_roi_cy = QSpinBox()
        self.spin_fft_roi_w = QSpinBox()
        self.spin_fft_roi_h = QSpinBox()
        for s in (
            self.spin_fft_roi_cx,
            self.spin_fft_roi_cy,
            self.spin_fft_roi_w,
            self.spin_fft_roi_h,
        ):
            s.setRange(0, 10000)
        self.btn_fft_roi_apply = QPushButton("Apply")
        grid_camctrl_sroi.addWidget(QLabel("FFT Cen X"), 0, 2)
        grid_camctrl_sroi.addWidget(self.spin_fft_roi_cx, 0, 3)
        grid_camctrl_sroi.addWidget(QLabel("FFT Cen Y"), 1, 2)
        grid_camctrl_sroi.addWidget(self.spin_fft_roi_cy, 1, 3)
        grid_camctrl_sroi.addWidget(QLabel("FFT Width"), 2, 2)
        grid_camctrl_sroi.addWidget(self.spin_fft_roi_w, 2, 3)
        grid_camctrl_sroi.addWidget(QLabel("FFT Height"), 3, 2)
        grid_camctrl_sroi.addWidget(self.spin_fft_roi_h, 3, 3)
        # Tracking checkbox under FFT Height
        self.chk_fft_track = QCheckBox("Track")
        grid_camctrl_sroi.addWidget(self.chk_fft_track, 4, 3)
        # Apply buttons on row 5
        grid_camctrl_sroi.addWidget(self.btn_cam_sroi_apply, 5, 1)
        grid_camctrl_sroi.addWidget(self.btn_fft_roi_apply, 5, 3)
        # HROIS
        grid_camctrl_hroi = QGridLayout()
        # Camera HROI controls (pre-FFT crop)
        self.spin_cam_hroi_ofs_x = QSpinBox()
        self.spin_cam_hroi_ofs_y = QSpinBox()
        self.spin_cam_hroi_width = QSpinBox()
        self.spin_cam_hroi_height = QSpinBox()
        self.btn_cam_hroi_apply = QPushButton("Apply")
        for s in (
            self.spin_cam_hroi_ofs_x,
            self.spin_cam_hroi_ofs_y,
            self.spin_cam_hroi_width,
            self.spin_cam_hroi_height,
        ):
            s.setEnabled(False)
            # s.setRange(0, 10000)
        self.btn_cam_hroi_apply.setEnabled(False)
        self.lbl_cam_hroi_ofs_x = QLabel("OFFSET X (Incr.: ?)")
        self.lbl_cam_hroi_ofs_y = QLabel("OFFSET Y (Incr.: ?)")
        self.lbl_cam_hroi_width = QLabel("WIDTH (Incr.: ?)")
        self.lbl_cam_hroi_height = QLabel("HEIGHT (Incr.: ?)")
        self.lbl_cam_hroi_info = QLabel("Connect to edit.")
        grid_camctrl_hroi.addWidget(self.lbl_cam_hroi_ofs_x, 0, 0)
        grid_camctrl_hroi.addWidget(self.spin_cam_hroi_ofs_x, 0, 1)
        grid_camctrl_hroi.addWidget(self.lbl_cam_hroi_ofs_y, 1, 0)
        grid_camctrl_hroi.addWidget(self.spin_cam_hroi_ofs_y, 1, 1)
        grid_camctrl_hroi.addWidget(self.lbl_cam_hroi_width, 2, 0)
        grid_camctrl_hroi.addWidget(self.spin_cam_hroi_width, 2, 1)
        grid_camctrl_hroi.addWidget(self.lbl_cam_hroi_height, 3, 0)
        grid_camctrl_hroi.addWidget(self.spin_cam_hroi_height, 3, 1)
        grid_camctrl_hroi.addWidget(self.btn_cam_hroi_apply, 4, 1)
        grid_camctrl_hroi.addWidget(self.lbl_cam_hroi_info, 4, 0)
        # --- Tabs for camera controls and ROIs ---
        tabs_camctrl = QTabWidget()
        # Control tab
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        control_layout.addLayout(grid_camctrl)
        tabs_camctrl.addTab(control_widget, "Control")
        # SROIs tab
        srois_widget = QWidget()
        srois_layout = QVBoxLayout(srois_widget)
        srois_layout.addLayout(grid_camctrl_sroi)
        tabs_camctrl.addTab(srois_widget, "S-ROIs")
        # HROIs tab
        hrois_widget = QWidget()
        hrois_layout = QVBoxLayout(hrois_widget)
        hrois_layout.addLayout(grid_camctrl_hroi)
        tabs_camctrl.addTab(hrois_widget, "H-ROI")
        camctrl_layout.addWidget(tabs_camctrl)
        control_layout.addWidget(tabs_camctrl_mode)
        # Laser
        laser_group = QGroupBox("SWEPT SOURCE")
        laser_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        laser_group.setStyleSheet("QGroupBox { color: #f97316; }")
        laser_layout = QVBoxLayout(laser_group)
        self.laser_status_label = QLabel("STATUS: DISCONNECTED")
        laser_layout.addWidget(self.laser_status_label)
        top_laser_btns = QHBoxLayout()
        self.btn_laser_connect = QPushButton("Conn.")
        self.btn_laser_init = QPushButton("Init.")
        self.btn_laser_disc = QPushButton("Disc.")
        top_laser_btns.addWidget(self.btn_laser_connect)
        top_laser_btns.addWidget(self.btn_laser_init)
        top_laser_btns.addWidget(self.btn_laser_disc)
        laser_layout.addLayout(top_laser_btns)
        self.laser_mode_combo = QComboBox()
        self.laser_mode_combo.addItems(["CW", "Single", "Cont."])
        laser_layout.addWidget(self.laser_mode_combo)
        # Laser numeric controls
        grid_laser = QGridLayout()
        self.spin_laser_cw = QDoubleSpinBox()
        self.spin_laser_min = QDoubleSpinBox()
        self.spin_laser_max = QDoubleSpinBox()
        self.spin_laser_sweep = QDoubleSpinBox()
        self.spin_laser_sweep_speed = QDoubleSpinBox()
        self.spin_laser_sweep_speed.setReadOnly(True)
        for s in (self.spin_laser_cw, self.spin_laser_min, self.spin_laser_max):
            s.setRange(800, 900)
            s.setDecimals(1)
        self.spin_laser_sweep.setRange(0.1, 100.0)
        self.spin_laser_sweep.setDecimals(2)
        grid_laser.addWidget(QLabel("CW λ [nm]"), 0, 0)
        grid_laser.addWidget(self.spin_laser_cw, 0, 1)
        grid_laser.addWidget(QLabel("Min λ"), 1, 0)
        grid_laser.addWidget(self.spin_laser_min, 1, 1)
        grid_laser.addWidget(QLabel("Max λ"), 2, 0)
        grid_laser.addWidget(self.spin_laser_max, 2, 1)
        grid_laser.addWidget(QLabel("Sweep Time"), 3, 0)
        grid_laser.addWidget(self.spin_laser_sweep, 3, 1)
        grid_laser.addWidget(QLabel("Sweep Speed"), 4, 0)
        grid_laser.addWidget(self.spin_laser_sweep_speed, 4, 1)
        laser_layout.addLayout(grid_laser)
        btns_laser_onoff = QHBoxLayout()
        self.btn_laser_on = QPushButton("EMISSION ON")
        self.btn_laser_off = QPushButton("OFF")
        btns_laser_onoff.addWidget(self.btn_laser_on)
        btns_laser_onoff.addWidget(self.btn_laser_off)
        laser_layout.addLayout(btns_laser_onoff)
        laser_layout.addStretch()
        # Stage
        stage_group = QGroupBox("MICROSCOPE STAGE")
        stage_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        stage_group.setStyleSheet("QGroupBox { color: #22c55e; }")
        stage_layout = QVBoxLayout(stage_group)
        self.stage_status_label = QLabel("STATUS: DISCONNECTED")
        stage_layout.addWidget(self.stage_status_label)
        top_stage_btns = QHBoxLayout()
        self.btn_stage_connect = QPushButton("Conn.")
        self.btn_stage_init = QPushButton("Init.")
        self.btn_stage_calib = QPushButton("Calib.")
        self.btn_stage_disc = QPushButton("Disc.")
        top_stage_btns.addWidget(self.btn_stage_connect)
        top_stage_btns.addWidget(self.btn_stage_init)
        top_stage_btns.addWidget(self.btn_stage_calib)
        top_stage_btns.addWidget(self.btn_stage_disc)
        stage_layout.addLayout(top_stage_btns)
        self.stage_mode_combo = QComboBox()
        self.stage_mode_combo.addItems(["Manual", "Pattern"])
        stage_layout.addWidget(self.stage_mode_combo)
        # Manual controls
        grid_stage = QGridLayout()
        self.spin_stage_x = QDoubleSpinBox()
        self.spin_stage_y = QDoubleSpinBox()
        self.spin_stage_z = QDoubleSpinBox()
        self.spin_stage_dx = QDoubleSpinBox()
        self.spin_stage_dy = QDoubleSpinBox()
        self.spin_stage_dz = QDoubleSpinBox()
        for s in (
            self.spin_stage_x,
            self.spin_stage_y,
            self.spin_stage_z,
            self.spin_stage_dx,
            self.spin_stage_dy,
            self.spin_stage_dz,
        ):
            s.setDecimals(3)
            s.setRange(-100000, 100000)
        self.btn_stage_set_xy = QPushButton("SET XY")
        self.btn_stage_move_xy = QPushButton("MOVE ΔXY")
        self.btn_stage_focus_set = QPushButton("SET Z")
        self.btn_stage_focus_move = QPushButton("MOVE ΔZ")
        self.btn_stage_estop = QPushButton("EMERGENCY STOP")
        self.btn_stage_estop.setStyleSheet("background-color: #dc2626; color: white;")
        grid_stage.addWidget(QLabel("X, Y"), 0, 0)
        grid_stage.addWidget(self.spin_stage_x, 0, 1)
        # grid_stage.addWidget(QLabel("Y"), 1, 0)
        grid_stage.addWidget(self.spin_stage_y, 0, 2)
        grid_stage.addWidget(self.btn_stage_set_xy, 0, 3)
        grid_stage.addWidget(QLabel("ΔX, ΔY"), 1, 0)
        grid_stage.addWidget(self.spin_stage_dx, 1, 1)
        # grid_stage.addWidget(QLabel("ΔY"), 3, 0)
        grid_stage.addWidget(self.spin_stage_dy, 1, 2)
        grid_stage.addWidget(self.btn_stage_move_xy, 1, 3)
        grid_stage.addWidget(QLabel("Z"), 2, 0)
        grid_stage.addWidget(self.spin_stage_z, 2, 1)
        grid_stage.addWidget(self.btn_stage_focus_set, 2, 2)
        grid_stage.addWidget(QLabel("ΔZ"), 3, 0)
        grid_stage.addWidget(self.spin_stage_dz, 3, 1)
        grid_stage.addWidget(self.btn_stage_focus_move, 3, 2)

        grid_stage_pat = QGridLayout()

        # --- PATH SECTION ---
        self.lbl_path = QLabel("Path:")
        self.edit_path = QLineEdit()
        self.edit_path.setText(str(Path(__datapath__) / "b_scan_pattern.yml"))
        self.btn_load_path = QPushButton("Load")
        self.btn_generate = QPushButton("Generate")

        # Layout: Label (0,0), Input (0,1), Button (0,2)
        grid_stage_pat.addWidget(self.lbl_path, 0, 0)
        grid_stage_pat.addWidget(self.edit_path, 0, 1, 1, 2)
        grid_stage_pat.addWidget(self.btn_load_path, 0, 3)
        grid_stage_pat.addWidget(self.btn_generate, 1, 3)

        # --- GENERATE SECTION ---
        # group_generate = QGroupBox("Generate")
        # gen_layout = QGridLayout()

        # Amount
        self.lbl_amount = QLabel("Generate Pattern with Amount:")
        self.spin_amount = QSpinBox()
        self.spin_amount.setRange(1, 1000000)
        grid_stage_pat.addWidget(self.lbl_amount, 1, 0, 1, 2)
        grid_stage_pat.addWidget(self.spin_amount, 1, 2)

        # Min X, Y, Z
        self.lbl_min = QLabel("Min X, Y, Z:")
        self.spin_min_x = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        self.spin_min_y = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        self.spin_min_z = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        grid_stage_pat.addWidget(self.lbl_min, 2, 0)
        grid_stage_pat.addWidget(self.spin_min_x, 2, 1)
        grid_stage_pat.addWidget(self.spin_min_y, 2, 2)
        grid_stage_pat.addWidget(self.spin_min_z, 2, 3)

        # Max X, Y, Z
        self.lbl_max = QLabel("Max X, Y, Z:")
        self.spin_max_x = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        self.spin_max_y = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        self.spin_max_z = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        grid_stage_pat.addWidget(self.lbl_max, 3, 0)
        grid_stage_pat.addWidget(self.spin_max_x, 3, 1)
        grid_stage_pat.addWidget(self.spin_max_y, 3, 2)
        grid_stage_pat.addWidget(self.spin_max_z, 3, 3)

        # Speckle Toggle
        self.chk_use_speckle = QCheckBox("Spckl. Size")
        grid_stage_pat.addWidget(self.chk_use_speckle, 4, 0)

        # Speckle Size X, Y
        self.spin_speckle_x = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        self.spin_speckle_y = QDoubleSpinBox(
            decimals=3, singleStep=0.001, minimum=-100000, maximum=100000
        )
        grid_stage_pat.addWidget(self.spin_speckle_x, 4, 1)
        grid_stage_pat.addWidget(self.spin_speckle_y, 4, 2)

        # group_generate.setLayout(gen_layout)

        # Add the group box to the main grid
        # grid_stage_pat.addWidget(group_generate, 1, 0, 1, 3)

        # Optional: Ensure the path input expands to fill space
        # grid_stage_pat.setColumnStretch(1, 1)
        # --- Tabs for stage controls and pattern settings ---
        tabs_stagectrl = QTabWidget()
        # Control tab
        stg_control_widget = QWidget()
        stg_control_layout = QVBoxLayout(stg_control_widget)
        stg_control_layout.addLayout(grid_stage)
        tabs_stagectrl.addTab(stg_control_widget, "Control")
        # Pattern tab
        stg_pat_widget = QWidget()
        stg_pat_layout = QVBoxLayout(stg_pat_widget)
        stg_pat_layout.addLayout(grid_stage_pat)
        tabs_stagectrl.addTab(stg_pat_widget, "Pattern")

        stage_layout.addWidget(tabs_stagectrl)
        stage_layout.addWidget(self.btn_stage_estop)
        stage_layout.addStretch()
        # --- TOP ROW: controller + laser + stage in one row ---
        top_row_layout = QHBoxLayout()
        top_row_layout.addWidget(ctrl_group, 0, Qt.AlignTop)
        top_row_layout.addWidget(camctrl_group, 0, Qt.AlignTop)
        top_row_layout.addWidget(laser_group, 0, Qt.AlignTop)
        top_row_layout.addWidget(stage_group, 0, Qt.AlignTop)
        main_layout.addLayout(top_row_layout)
        main_layout.addWidget(cam_group)
        # Wire signals
        self._connect_signals()
        # Timers: clock
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        # Initial state update
        self.update_all()

    # ------------------------------------------------------------------
    # Endpoint-equivalent helpers (formerly Flask routes)
    # ------------------------------------------------------------------
    def get_states(self):
        return {
            "controller": controller.state.value,
            "camera": controller.camera.state.value,
            "laser": controller.laser.state.value,
            "stage": controller.stage.state.value,
        }

    def get_modes(self):
        return {
            "camera": controller.camera.mode.value,
            "laser": controller.laser.mode.value,
            "stage": controller.stage.mode.value,
        }

    def get_properties(self):
        return {
            "z_max": controller.z_max,
            "mag": controller.mag,
            "na": controller.na,
            "axial_bandwidth": controller.axial_bandwidth,
            "exposure_lambda_range": controller.exposure_lambda_range,
            "lateral_fov": controller.lateral_fov,
            "lateral_resolution": controller.lateral_resolution,
        }

    def get_laser_properties(self):
        return {
            "max": controller.laser.wavelength_max,
            "min": controller.laser.wavelength_min,
            "cfg_max": controller.laser._cfg["wavelength_max"],
            "cfg_min": controller.laser._cfg["wavelength_min"],
            "wavelength": controller.laser.wavelength,
            "total_time": controller.laser.total_sweep_time,
        }

    def get_stage_properties(self):
        pos = controller.stage.get_position()
        return {"x": pos[0], "y": pos[1], "z": controller.stage.get_focus()}

    def connect_device(self, device: str):
        if device == "laser":
            controller.laser.connect()
        elif device == "camera":
            controller.camera.connect()
        elif device == "stage":
            controller.stage.connect()
        else:
            controller.connect()

    def disconnect_device(self, device: str):
        if device == "laser":
            controller.laser.disconnect()
        elif device == "camera":
            controller.camera.disconnect()
        elif device == "stage":
            controller.stage.disconnect()
        else:
            controller.disconnect()

    def initialize_device(self, device: str):
        if device == "laser":
            controller.laser.initialize()
        elif device == "camera":
            controller.camera.initialize()
        elif device == "stage":
            controller.stage.initialize(0)
        elif device == "stage-no-calib":
            controller.stage.initialize()
        else:
            controller.initialize(0)

    def calibrate_stage(self):
        if self._stage_thread is not None and self._stage_thread.is_alive():
            return

        def _run_calibration():
            try:
                controller.stage.calibrate(0)
            except Exception as exc:
                self._log.exception("Stage calibration failed: %s", exc)
            finally:
                self._stage_thread = None

        self._stage_thread = threading.Thread(
            target=_run_calibration,
            daemon=True,
        )
        self._stage_thread.start()

    def set_mode(self, device: str, new_mode: int):
        if device == "laser":
            controller.laser.change_mode(Dem2LaserMode(new_mode))
        elif device == "camera":
            controller.camera.change_mode(Dem2CameraMode(new_mode))
        elif device == "stage":
            controller.stage.change_mode(
                Dem2StageMode(new_mode)
            )  # same as your backend

    def set_laser_properties(self):
        controller.laser.wavelength = float(self.spin_laser_cw.value())
        controller.laser.wavelength_max = float(self.spin_laser_max.value())
        controller.laser.wavelength_min = float(self.spin_laser_min.value())
        # controller.laser.total_sweep_time = float(self.spin_laser_sweep.value()) # this is set in controller.update_burst_properties()
        controller.update_burst_properties()
        self._update_frames()
        self.update_all()

    def set_stage_properties(self, relative: bool, focus: bool):
        if relative:
            x = float(self.spin_stage_dx.value())
            y = float(self.spin_stage_dy.value())
            z = float(self.spin_stage_dz.value())
        else:
            x = float(self.spin_stage_x.value())
            y = float(self.spin_stage_y.value())
            z = float(self.spin_stage_z.value())
        # If a previous move is still running, optionally ignore or stop it
        if self._stage_thread is not None and self._stage_thread.is_alive():
            return
        self._stage_generation += 1
        gen = self._stage_generation

        def _run_move():
            try:
                if focus:
                    controller.stage.move_focus(z, relative)
                else:
                    controller.stage.move_stage(x, y, relative)
            except Exception as exc:
                # In a real app you should emit a Signal to show this in the GUI
                self._log.error(f"[Stage Error] Generation {gen}: {exc}")
            finally:
                # Only clear the thread reference if we are the most recent generation
                if self._stage_generation == gen:
                    self._stage_thread = None

        self._stage_thread = threading.Thread(target=_run_move, daemon=True)
        self._stage_thread.start()

    def toggle_emission(self):
        controller.laser.toggle_emission()

    def toggle_live(self):
        state = controller.camera.toggle_live_images()
        return state  # string as in backend

    def start_trigger_capturing(self):
        if controller.camera.state != Dem2State.READY:
            raise RuntimeError("Camera not initialized")
        if controller.camera.mode != Dem2CameraMode.FRAME_BURST_EXT_TRIGGER:
            raise RuntimeError("Camera not in frame burst mode")
        if controller.cam_capturer.is_alive():
            controller.cam_capturer.end()
            controller.cam_capturer.join()
        attrs = controller.settings
        centre_time_offset = controller.camera.t_exp / 2.0
        centre_lambdas = []
        self._log.info(
            "Calculating centre lambdas for each frame assuming linear lambda sweep."
        )
        for i in range(int(controller.camera.samples_a_scan)):
            time = (
                centre_time_offset + (controller.camera.t_frame * i)
            ) / 1000  # convert to seconds
            centre_lambdas.append(
                controller.laser.wavelength_min + (controller.laser.sweep_speed * time)
            )
        attrs["centre_lambdas"] = centre_lambdas
        controller.cam_capturer = Dem2Capturer(
            controller.camera,
            Dem2SweepPacket(str(DATA_PATH / "image_cont.h5"), attributes=attrs),
            int(controller.camera.samples_a_scan),
        )
        controller.cam_capturer.start()

    def emergency_stop(self):
        controller.laser.kill_emission()
        controller.stage.stop_moving()
        self._stage_generation += 1
        self._stage_thread = None

    # ------------------------------------------------------------------
    # UI / State handling
    # ------------------------------------------------------------------
    def _connect_signals(self):
        # controller
        self.btn_ctrl_connect.clicked.connect(
            lambda: self._with_wait(self._connect_controller)
        )
        self.btn_ctrl_init.clicked.connect(
            lambda: self._with_wait(self._init_controller)
        )
        self.btn_ctrl_disc.clicked.connect(
            lambda: self._with_wait(self._disc_controller)
        )
        # camera
        self.btn_cam_connect.clicked.connect(
            lambda: self._with_wait(self._connect_camera)
        )
        self.btn_cam_init.clicked.connect(lambda: self._with_wait(self._init_camera))
        self.btn_cam_disc.clicked.connect(lambda: self._with_wait(self._disc_camera))
        self.cam_mode_combo.currentIndexChanged.connect(
            lambda idx: self._with_wait(lambda: self.set_mode("camera", idx))
        )
        self.btn_cam_capture.clicked.connect(
            lambda: self._with_wait(self._get_single_image)
        )
        self.btn_cam_disc_sweep.clicked.connect(
            lambda: self._with_wait(self._run_discrete_sweep)
        )
        self.btn_cam_set_int.clicked.connect(
            lambda: self._with_wait(self._set_integration_time)
        )
        self.btn_cam_live.clicked.connect(
            lambda: self._with_wait(self._toggle_live_clicked)
        )
        self.btn_cam_burst.clicked.connect(lambda: self._with_wait(self._start_burst))
        self.btn_reac_cont_oct.clicked.connect(
            lambda: self._with_wait(self._read_oct_cont())
        )
        self.chk_fft.stateChanged.connect(self._update_flags)
        self.chk_save.stateChanged.connect(self._update_flags)
        self.chk_oct.stateChanged.connect(self._update_flags)
        # H ROI
        self.btn_cam_hroi_apply.clicked.connect(self._apply_cam_hroi)
        # Camera ROI
        self.btn_cam_sroi_apply.clicked.connect(self._apply_cam_roi)
        # FFT ROI
        self.btn_fft_roi_apply.clicked.connect(self._apply_fft_roi)
        # FFT tracking
        self.chk_fft_track.stateChanged.connect(self._update_fft_tracking)
        # gamma to worker
        self.gamma_spin.valueChanged.connect(self._update_worker_gamma)
        # laser
        self.btn_laser_connect.clicked.connect(
            lambda: self._with_wait(self._connect_laser)
        )
        self.btn_laser_init.clicked.connect(lambda: self._with_wait(self._init_laser))
        self.btn_laser_disc.clicked.connect(lambda: self._with_wait(self._disc_laser))
        self.laser_mode_combo.currentIndexChanged.connect(
            lambda idx: self._with_wait(lambda: self.set_mode("laser", idx))
        )
        self.spin_laser_min.valueChanged.connect(self._update_sweep_speed)
        self.spin_laser_max.valueChanged.connect(self._update_sweep_speed)
        self.spin_laser_sweep.valueChanged.connect(self._update_sweep_speed)
        self.btn_laser_on.clicked.connect(
            lambda: self._with_wait(self._toggle_emission_clicked)
        )
        self.btn_laser_off.clicked.connect(
            lambda: self._with_wait(self._toggle_emission_clicked)
        )
        # stage
        self.btn_stage_connect.clicked.connect(
            lambda: self._with_wait(self._connect_stage)
        )
        self.btn_stage_init.clicked.connect(lambda: self._with_wait(self._init_stage))
        self.btn_stage_calib.clicked.connect(
            lambda: self._with_wait(self._calibrate_stage)
        )
        self.btn_stage_disc.clicked.connect(lambda: self._with_wait(self._disc_stage))
        self.stage_mode_combo.currentIndexChanged.connect(
            lambda idx: self._with_wait(lambda: self.set_mode("stage", idx))
        )
        self.btn_stage_set_xy.clicked.connect(
            lambda: self._with_wait(lambda: self.set_stage_properties(False, False))
        )
        self.btn_stage_move_xy.clicked.connect(
            lambda: self._with_wait(lambda: self.set_stage_properties(True, False))
        )
        self.btn_stage_focus_set.clicked.connect(
            lambda: self._with_wait(lambda: self.set_stage_properties(False, True))
        )
        self.btn_stage_focus_move.clicked.connect(
            lambda: self._with_wait(lambda: self.set_stage_properties(True, True))
        )
        self.btn_stage_estop.clicked.connect(
            lambda: self._with_wait(self.emergency_stop)
        )
        # staage pattern
        self.btn_load_path.clicked.connect(self._read_b_scan_file)
        self.btn_generate.clicked.connect(self._generate_b_scan_file)

    def _with_wait(self, func):
        try:
            for dev in self.state.devices.values():
                dev["status"] = 99
            self._update_ui()
            func()
        except Exception as e:
            err = str(e)
            self._log.error(err)
            QMessageBox.critical(self, "Error", err)
        finally:
            self.update_all()

    def update_all(self):
        self._update_states()
        self._update_modes()
        self._update_properties()
        self._update_stage_properties()
        self._update_integration_time()
        self._update_laser_properties()
        self._update_frames()
        self._update_ui()

    def _update_states(self):
        data = self.get_states()
        for key, value in data.items():
            self.state.devices[key]["status"] = value

    def _update_modes(self):
        data = self.get_modes()
        for key, value in data.items():
            if key in self.state.devices:
                self.state.devices[key]["mode"] = value

    def _update_properties(self):
        _ = self.get_properties()

    def _update_laser_properties(self):
        if self.state.devices["laser"]["status"] == 0:
            return
        info = self.get_laser_properties()
        self.spin_laser_max.setValue(info["max"])
        self.spin_laser_min.setValue(info["min"])
        self.spin_laser_cw.setValue(info["wavelength"])
        self.spin_laser_sweep.setValue(
            info["total_time"] if info["total_time"] is not None else 0.0
        )
        self._update_sweep_speed()

    def _update_stage_properties(self):
        if (
            self.state.devices["stage"]["status"] < 2
            or self.state.devices["stage"]["status"] == 99
        ):
            return
        info = self.get_stage_properties()
        self.spin_stage_x.setValue(info["x"])
        self.spin_stage_y.setValue(info["y"])
        self.spin_stage_z.setValue(info["z"])

    def _update_integration_time(self):
        self.state.integration_time = controller.camera.t_exp
        self.int_time_spin.setValue(self.state.integration_time)

    def _update_frames(self):
        no_frames_str = "Unknown."
        if controller.camera.samples_a_scan is not None:
            no_frames_str = str(int(controller.camera.samples_a_scan))
        self.frames.setText("No. Frames: " + no_frames_str)
        self.frames2.setText("No. Frames: " + no_frames_str)

    def _update_sweep_speed(self):
        # controller.laser.wavelength_min = self.spin_laser_min.value()
        # controller.laser.wavelength_max = self.spin_laser_max.value()
        # controller.update_burst_properties()
        try:
            self.spin_laser_sweep_speed.setValue(controller.laser.sweep_speed)
        except Dem2Errors.PropertyNotSetError:
            self._log.warning("Property sweep_speed not set.")
            self.spin_laser_sweep_speed.setValue(0.0)
        self.spin_laser_sweep.setValue(
            controller.laser.total_sweep_time
            if controller.laser.total_sweep_time is not None
            else 0.0
        )

    def _update_flags(self):
        self.state.fftEnabled = self.chk_fft.isChecked()
        self.state.saveEnabled = self.chk_save.isChecked()
        self.state.octEnabled = self.chk_oct.isChecked()
        # propagate FFT flag to worker
        if self.proc_worker is not None:
            self.proc_worker.set_fft_enabled(self.state.fftEnabled)
            self.proc_worker.set_oct_mode(self.state.octEnabled)
            self.proc_worker.set_padding(400)

    def _update_fft_tracking(self):
        if self.proc_worker is not None:
            self.proc_worker.set_fft_tracking(self.chk_fft_track.isChecked())

    def _on_fft_roi_moved(self, cx: int, cy: int):
        """Slot for worker tracking updates."""
        self.fft_roi_cx = cx
        self.fft_roi_cy = cy
        self.spin_fft_roi_cx.setValue(cx)
        self.spin_fft_roi_cy.setValue(cy)

    def _update_ui(self):
        # status table
        self.status_table.setRowCount(0)
        for row_idx, dev in enumerate(self.state.devices.values()):
            self.status_table.insertRow(row_idx)
            code = dev["status"]
            label, color = STATUS_MAP.get(code, STATUS_MAP[99])
            mode_str = "-"
            if "mode" in dev:
                mode_list = MODES.get(dev["id"], [])
                if 0 <= dev["mode"] < len(mode_list):
                    mode_str = mode_list[dev["mode"]]
            self.status_table.setItem(row_idx, 0, QTableWidgetItem(dev["name"]))
            self.status_table.setItem(row_idx, 1, QTableWidgetItem(str(code)))
            self.status_table.setItem(row_idx, 2, QTableWidgetItem(label))
            self.status_table.setItem(row_idx, 3, QTableWidgetItem(mode_str))
            indicator = QTableWidgetItem("●")
            indicator.setForeground(Qt.red if color == "red" else Qt.white)
            self.status_table.setItem(row_idx, 4, indicator)
        # controller buttons
        ctrl_status = self.state.devices["controller"]["status"]
        self.btn_ctrl_connect.setEnabled(ctrl_status == 0)
        self.btn_ctrl_disc.setEnabled(ctrl_status not in (0, 99))
        self.btn_ctrl_init.setEnabled(ctrl_status == 1)
        # camera
        _inc, _res = controller.camera.get_increments, controller.camera.get_max_res
        res_known = _res != (0, 0)
        spins = (
            self.spin_cam_hroi_ofs_y,
            self.spin_cam_hroi_ofs_x,
            self.spin_cam_hroi_height,
            self.spin_cam_hroi_width,
        )
        for i, s in enumerate(spins):
            if res_known:
                s.setEnabled(True)
            else:
                s.setEnabled(False)
            idx = i % 2
            s.setRange(0, _res[idx])
            s.setSingleStep(_inc[idx])
        if res_known:
            self.btn_cam_hroi_apply.setEnabled(True)
            self.lbl_cam_hroi_height.setText(
                self.lbl_cam_hroi_height.text()[:15] + str(_inc[0]) + ")"
            )
            self.lbl_cam_hroi_width.setText(
                self.lbl_cam_hroi_width.text()[:14] + str(_inc[1]) + ")"
            )
            self.lbl_cam_hroi_ofs_y.setText(
                self.lbl_cam_hroi_ofs_y.text()[:17] + str(_inc[0]) + ")"
            )
            self.lbl_cam_hroi_ofs_x.setText(
                self.lbl_cam_hroi_ofs_x.text()[:17] + str(_inc[1]) + ")"
            )
            self.lbl_cam_hroi_info.setText("Ready.")
        else:
            self.btn_cam_hroi_apply.setEnabled(False)
            self.lbl_cam_hroi_info.setText("Connect to edit.")
        cam = self.state.devices["camera"]
        is_mono = cam["mode"] == 0
        self.chk_fft.setEnabled(is_mono)
        self.btn_cam_burst.setEnabled(not is_mono)
        self.btn_cam_capture.setEnabled(is_mono)
        label, color = STATUS_MAP.get(cam["status"], STATUS_MAP[99])
        self.cam_status_label.setText(
            f"STATUS: {label} | MODE: {MODES['camera'][cam['mode']]}"
        )
        self.btn_cam_connect.setEnabled(cam["status"] == 0)
        self.btn_cam_disc.setEnabled(cam["status"] not in (0, 99))
        self.btn_cam_init.setEnabled(cam["status"] == 1)
        self.cam_mode_combo.setCurrentIndex(cam["mode"])
        # laser
        laser = self.state.devices["laser"]
        label, _ = STATUS_MAP.get(laser["status"], STATUS_MAP[99])
        self.laser_status_label.setText(f"STATUS: {label}")
        self.btn_laser_connect.setEnabled(laser["status"] == 0)
        self.btn_laser_disc.setEnabled(laser["status"] not in (0, 99))
        self.btn_laser_init.setEnabled(laser["status"] == 1)
        self.laser_mode_combo.setCurrentIndex(laser["mode"])
        is_cw = laser["mode"] == 0
        is_single_burst = not is_mono and not is_cw
        self.btn_cam_live.setEnabled(is_mono or is_single_burst)
        self.chk_oct.setEnabled(is_single_burst)
        self.spin_laser_cw.setEnabled(is_cw)
        self.btn_cam_disc_sweep.setEnabled(is_mono and is_cw)
        # self.spin_laser_min.setEnabled(not is_cw)
        # self.spin_laser_max.setEnabled(not is_cw)
        self.spin_laser_sweep.setEnabled(not is_cw)
        self.btn_laser_on.setEnabled(laser["status"] == 3)
        self.btn_laser_off.setEnabled(laser["status"] == 4)
        self.laser_mode_combo.setEnabled(laser["status"] <= 1)
        # stage
        stage = self.state.devices["stage"]
        label, _ = STATUS_MAP.get(stage["status"], STATUS_MAP[99])
        self.stage_status_label.setText(f"STATUS: {label}")
        self.btn_stage_connect.setEnabled(stage["status"] == 0)
        self.btn_stage_disc.setEnabled(stage["status"] not in (0, 99))
        self.btn_stage_calib.setEnabled(stage["status"] == 2)
        self.btn_stage_init.setEnabled(stage["status"] == 1)
        self.btn_load_path.setEnabled(stage["status"] not in (0, 99))
        self.btn_generate.setEnabled(stage["status"] not in (0, 99))

    # ------------------------------------------------------------------
    # Actions (mirror JS functions)
    # ------------------------------------------------------------------
    def _connect_controller(self):
        self.connect_device("controller")

    def _init_controller(self):
        reply = QMessageBox.question(
            self,
            "Remove Objective",
            "Initializing Demonstrator 2 includes calibrating the Stage.\n"
            "Please ensure there IS NO OBJECTIVE attached to the revolver.\n\nProceed?",
        )
        if reply == QMessageBox.Yes:
            self.set_laser_properties()
            self.initialize_device("controller")

    def _disc_controller(self):
        self.state.isLive = False
        self.state.isCaptBurst = False
        if self.proc_worker is not None:
            self.proc_worker.set_running(False)
        self.disconnect_device("controller")

    def _connect_camera(self):
        self.connect_device("camera")

    def _init_camera(self):
        self.initialize_device("camera")
        self._log.info("Camera Initialized")
        controller.update_burst_properties()

    def _disc_camera(self):
        self.state.isLive = False
        self.state.isCaptBurst = False
        if self.proc_worker is not None:
            self.proc_worker.set_running(False)
        self.disconnect_device("camera")

    def _connect_laser(self):
        self.connect_device("laser")

    def _init_laser(self):
        self.set_laser_properties()
        self.initialize_device("laser")

    def _disc_laser(self):
        self.disconnect_device("laser")

    def _connect_stage(self):
        self.connect_device("stage")

    def _init_stage(self):
        self.initialize_device("stage-no-calib")

    def _calibrate_stage(self):
        reply = QMessageBox.question(
            self,
            "Remove Objective",
            "Calibrating the Stage.\n"
            "Please ensure there IS NO OBJECTIVE attached to the revolver.\n\nProceed?",
        )
        if reply == QMessageBox.Yes:
            self.calibrate_stage()

    def _disc_stage(self):
        self.disconnect_device("stage")

    def _read_b_scan_file(self):
        path = self.edit_path.text()
        if path:
            controller.stage.b_scan_pattern = Dem2BScanPattern(path)
        else:
            raise "Please enter a path"

    def _generate_b_scan_file(self):
        path = self.edit_path.text()
        if not path:
            raise "Please enter a path"
        b_scan_pattern = Dem2BScanPattern()
        amount = int(self.spin_amount.value())
        minimum = (
            self.spin_min_z.value(),
            self.spin_min_y.value(),
            self.spin_min_x.value(),
        )
        if self.chk_use_speckle.isChecked():
            speckle_size = (self.spin_speckle_y.value(), self.spin_speckle_x.value())
            b_scan_pattern.generate_line(
                amount, minimum, self.spin_max_z.value(), speckle_size
            )
        else:
            maximum = (
                self.spin_max_z.value(),
                self.spin_max_y.value(),
                self.spin_max_x.value(),
            )
            b_scan_pattern.generate_line(amount, minimum, maximum)
        b_scan_pattern.as_file(path)
        controller.stage.b_scan_pattern = b_scan_pattern

    def _get_single_image(self):
        if controller.stage.mode == Dem2StageMode.PATTERN:
            lambdas = np.array([controller.laser.wavelength])
            self._run_discrete_sweep(lambdas)
            return
        gamma = float(self.gamma_spin.value())
        if not 0.0 <= gamma <= 1.0:
            raise ValueError("Gamma must be between 0 and 1")
        controller.camera.t_exp = float(self.int_time_spin.value())
        image_array = controller.camera.acquire_single_image()
        if image_array is None:
            return
        # Normalise to uint8 for display / ROI drawing
        if image_array.dtype in (np.float32, np.float64):
            display_arr = (np.clip(image_array, 0, 1) * 255).astype(np.uint8)
        else:
            display_arr = image_array.astype(np.uint8)
        h, w = display_arr.shape[:2]
        # Update Camera ROI bounds based on this frame
        for s in (self.spin_cam_sroi_tl_x, self.spin_cam_sroi_br_x):
            s.setMaximum(max(0, w - 1))
        for s in (self.spin_cam_sroi_tl_y, self.spin_cam_sroi_br_y):
            s.setMaximum(max(0, h - 1))
        # Clamp camera ROI to image bounds (exclusive BR semantics)
        cx1 = max(0, min(self.cam_roi_tl_x, w - 1))
        cy1 = max(0, min(self.cam_roi_tl_y, h - 1))
        cx2 = max(0, min(self.cam_roi_br_x, w - 1))
        cy2 = max(0, min(self.cam_roi_br_y, h - 1))
        cx2 = max(cx1, cx2)
        cy2 = max(cy1, cy2)
        has_cam_roi = (cx2 > cx1) and (cy2 > cy1)
        # Build RGB display image and draw camera ROI if active
        if display_arr.ndim == 2:
            display_rgb = np.stack([display_arr, display_arr, display_arr], axis=-1)
        else:
            display_rgb = np.ascontiguousarray(display_arr)
        if has_cam_roi:
            thickness = 2
            color = [255, 255, 255]
            display_rgb[cy1 : min(cy1 + thickness, cy2 + 1), cx1 : cx2 + 1] = color
            display_rgb[max(cy2 - thickness + 1, cy1) : cy2 + 1, cx1 : cx2 + 1] = color
            display_rgb[cy1 : cy2 + 1, cx1 : min(cx1 + thickness, cx2 + 1)] = color
            display_rgb[cy1 : cy2 + 1, max(cx2 - thickness + 1, cx1) : cx2 + 1] = color
        qpix = numpy_to_qpixmap(display_rgb)
        self.label_cam_live.setPixmap(
            qpix.scaled(
                self.label_cam_live.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        # Crop to camera ROI for FFT processing (exclusive BR, no zero-padding)
        proc_array = display_arr[cy1:cy2, cx1:cx2] if has_cam_roi else display_arr
        if self.state.saveEnabled:
            filepath = str(
                DATA_PATH / f"image_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.h5"
            )
            results = Dem2SweepPacket(
                filepath,
                "1",
                controller.settings,
            )
            results.open_file()
            results.append_frame(image_array)
            results.close_file()
        if self.state.fftEnabled:
            ft_arr = compute_fft(proc_array)
            self._last_fft_array = covert_fft_to_img(ft_arr, gamma)
            self._update_phase_display(ft_arr)
            self._update_fft_display_with_roi()
        self._update_integration_time()

    def _toggle_emission_clicked(self):
        self.toggle_emission()

    def _toggle_live_clicked(self):
        state_str = self.toggle_live()
        self.state.isLive = "RUNNING" in state_str
        if self.proc_worker is not None:
            self.proc_worker.set_running(self.state.isLive)
            # ensure worker uses current gamma and FFT flag
            self.proc_worker.set_gamma(float(self.gamma_spin.value()))
            self.proc_worker.set_fft_enabled(self.state.fftEnabled)
            self.proc_worker.set_oct_mode(self.state.octEnabled)
            self.proc_worker.set_padding(400)

    def _start_burst(self):
        self.start_trigger_capturing()
        self.state.isCaptBurst = True

    def _read_oct_cont(self):
        packet = Dem2SweepPacket(str(DATA_PATH / "image_cont.h5"))
        image_array = packet[:, 1, :]
        # image_array = controller.run_single_sweep()
        # self._log.info("test)")
        # if image_array is None:
        #     return
        # image_array = image_array[:, 1, :]
        y = image_array.shape[0] // 2
        image_array = oct_reconstruct(image_array, y)
        image_array[y - 50 : y + 50, :] = 0
        image_array = image_array**0.52
        display_rgb, _ = ui_prep_img(image_array)
        self.proc_worker.frame_ready.emit(display_rgb, None, None)

    def _run_discrete_sweep(self, lambdas=None):
        lambdas = (
            controller.lambdas_array(
                controller.laser.wavelength_min,
                controller.laser.wavelength_max,
                int(controller.camera.samples_a_scan),
            )
            if lambdas is None
            else lambdas
        )
        if controller.stage.mode == Dem2StageMode.PATTERN:
            for i in range(controller.stage.b_scan_pattern[0].a_scans_b_scan):
                controller.stage.move_along_scan_pattern()
                self._log.info(
                    f"Moved to scan pattern position {controller.stage.b_scan_current_index}"
                )
                time.sleep(0.5)
                controller.run_multiple_lambdas(
                    str(DATA_PATH / "image_discrete.h5"),
                    lambdas,
                    False,
                    (controller.stage.b_scan_current_index + 1),
                )
                time.sleep(0.5)
            return
        controller.run_multiple_lambdas(
            str(DATA_PATH / "image_discrete.h5"),
            lambdas,
            False,
        )

    def _set_integration_time(self):
        controller.camera.t_exp = float(self.int_time_spin.value())
        controller.update_burst_properties()
        self._update_integration_time()

    def _apply_cam_hroi(self):
        self.cam_hroi_ofs_y = self.spin_cam_hroi_ofs_y.value()
        self.cam_hroi_ofs_x = self.spin_cam_hroi_ofs_x.value()
        self.cam_hroi_height = self.spin_cam_hroi_height.value()
        self.cam_hroi_width = self.spin_cam_hroi_width.value()
        controller.camera.roi_size = (self.cam_hroi_height, self.cam_hroi_width)
        controller.camera.roi_offset = (self.cam_hroi_ofs_y, self.cam_hroi_ofs_x)
        self.lbl_cam_hroi_info.setText("Applied.")

    def _apply_cam_roi(self):
        self.cam_roi_tl_x = self.spin_cam_sroi_tl_x.value()
        self.cam_roi_tl_y = self.spin_cam_sroi_tl_y.value()
        self.cam_roi_br_x = self.spin_cam_sroi_br_x.value()
        self.cam_roi_br_y = self.spin_cam_sroi_br_y.value()
        if self.proc_worker is not None:
            self.proc_worker.set_cam_roi(
                self.cam_roi_tl_x,
                self.cam_roi_tl_y,
                self.cam_roi_br_x,
                self.cam_roi_br_y,
            )

    def _apply_fft_roi(self):
        self.fft_roi_cx = self.spin_fft_roi_cx.value()
        self.fft_roi_cy = self.spin_fft_roi_cy.value()
        self.fft_roi_w = self.spin_fft_roi_w.value()
        self.fft_roi_h = self.spin_fft_roi_h.value()
        if self.proc_worker is not None:
            self.proc_worker.set_fft_roi(
                self.fft_roi_cx,
                self.fft_roi_cy,
                self.fft_roi_w,
                self.fft_roi_h,
            )
        # For single-capture path, still update the FFT overlay
        self._update_fft_display_with_roi()

    def _update_phase_display(self, ft_arr: np.ndarray):
        fh, fw = ft_arr.shape[:2]
        # Compute TL/BR from centre + width/height
        cx, cy, w, h = self.fft_roi_cx, self.fft_roi_cy, self.fft_roi_w, self.fft_roi_h
        x1 = cx - w // 2
        y1 = cy - h // 2
        x2 = x1 + w
        y2 = y1 + h
        # Clamp
        x1 = max(0, min(x1, fw - 1))
        y1 = max(0, min(y1, fh - 1))
        x2 = max(0, min(x2, fw - 1))
        y2 = max(0, min(y2, fh - 1))
        x2 = max(x1, x2)
        y2 = max(y1, y2)

        # Tracking on single capture
        if self.chk_fft_track.isChecked() and (x2 > x1) and (y2 > y1):
            roi_slice = ft_arr[y1:y2, x1:x2]
            if roi_slice.size > 0:
                mag = np.abs(roi_slice)
                max_val = mag.max()
                ys, xs = np.where(mag == max_val)
                self.fft_roi_cx = int(round(xs.mean())) + x1
                self.fft_roi_cy = int(round(ys.mean())) + y1
                # Update GUI
                self.spin_fft_roi_cx.setValue(self.fft_roi_cx)
                self.spin_fft_roi_cy.setValue(self.fft_roi_cy)
                # Recompute TL/BR with tracked centre
                x1 = self.fft_roi_cx - w // 2
                y1 = self.fft_roi_cy - h // 2
                x2 = x1 + w
                y2 = y1 + h
                x1 = max(0, min(x1, fw - 1))
                y1 = max(0, min(y1, fh - 1))
                x2 = max(0, min(x2, fw - 1))
                y2 = max(0, min(y2, fh - 1))
                x2 = max(x1, x2)
                y2 = max(y1, y2)

        ifft_arr = crop_centre_ifft(ft_arr, (x1, y1), (x2, y2))
        phase_hsv = phase_to_hsv(ifft_arr)
        qpix_phase = numpy_to_qpixmap(phase_hsv)
        self.label_cam_phase.setPixmap(
            qpix_phase.scaled(
                self.label_cam_phase.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    def _update_fft_display_with_roi(self):
        if self._last_fft_array is None:
            return
        ft_arr = self._last_fft_array.copy()
        fh, fw = ft_arr.shape
        # Keep FFT ROI spinboxes bounded to current FFT image size
        self.spin_fft_roi_cx.setMaximum(max(0, fw - 1))
        self.spin_fft_roi_cy.setMaximum(max(0, fh - 1))
        self.spin_fft_roi_w.setMaximum(max(0, fw))
        self.spin_fft_roi_h.setMaximum(max(0, fh))
        cx, cy, roi_w, roi_h = (
            self.fft_roi_cx,
            self.fft_roi_cy,
            self.fft_roi_w,
            self.fft_roi_h,
        )
        x1 = cx - roi_w // 2
        y1 = cy - roi_h // 2
        x2 = x1 + roi_w
        y2 = y1 + roi_h
        x1 = max(0, min(x1, fw - 1))
        y1 = max(0, min(y1, fh - 1))
        x2 = max(0, min(x2, fw - 1))
        y2 = max(0, min(y2, fh - 1))
        x2 = max(x1, x2)
        y2 = max(y1, y2)
        rgb = np.stack([ft_arr, ft_arr, ft_arr], axis=-1)
        if x2 > x1 and y2 > y1:
            th = 2
            color = [255, 255, 255]
            rgb[y1 : min(y1 + th, y2), x1:x2] = color
            rgb[max(y2 - th, y1) : y2, x1:x2] = color
            rgb[y1:y2, x1 : min(x1 + th, x2)] = color
            rgb[y1:y2, max(x2 - th, x1) : x2] = color
            # Red cross at centre
            arm = max(5, min(roi_w, roi_h) // 4) if roi_w > 0 and roi_h > 0 else 10
            cx_c = max(0, min(cx, fw - 1))
            cy_c = max(0, min(cy, fh - 1))
            x_start = max(0, cx_c - arm)
            x_end = min(fw, cx_c + arm + 1)
            y_start = max(0, cy_c - arm)
            y_end = min(fh, cy_c + arm + 1)
            rgb[cy_c, x_start:x_end] = color
            rgb[y_start:y_end, cx_c] = color
        qpix = numpy_to_qpixmap(rgb)
        self.label_cam_fft.setPixmap(
            qpix.scaled(
                self.label_cam_fft.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    def _update_from_worker(self, display_rgb, fft_img, phase_rgb):
        # Called in GUI thread via signal from worker
        if display_rgb is not None:
            qpix_live = numpy_to_qpixmap(display_rgb)
            self.label_cam_live.setPixmap(
                qpix_live.scaled(
                    self.label_cam_live.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        if fft_img is not None:
            qpix_fft = numpy_to_qpixmap(fft_img)
            self.label_cam_fft.setPixmap(
                qpix_fft.scaled(
                    self.label_cam_fft.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        if phase_rgb is not None:
            qpix_phase = numpy_to_qpixmap(phase_rgb)
            self.label_cam_phase.setPixmap(
                qpix_phase.scaled(
                    self.label_cam_phase.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def _update_worker_gamma(self, val):
        if self.proc_worker is not None:
            self.proc_worker.set_gamma(float(val))

    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def closeEvent(self, event):
        # Cleanly stop worker thread
        try:
            if self.proc_worker is not None:
                self.proc_worker.set_running(False)
                self.proc_worker.stop()
            if self.proc_thread is not None:
                self.proc_thread.quit()
                self.proc_thread.wait()
        finally:
            super().closeEvent(event)


def main():
    setup_root_logger(__name__)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
