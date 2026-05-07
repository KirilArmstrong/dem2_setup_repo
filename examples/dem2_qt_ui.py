import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from io import BytesIO

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QGroupBox, QTableWidget, QTableWidgetItem,
    QSpinBox, QDoubleSpinBox, QComboBox, QMessageBox, QCheckBox, QLineEdit,
    QSizePolicy,
)


from src.dem_2_3d_label_free.dem2_common.dem2_bscan_pattern import Dem2BScanPattern
from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2LaserMode, Dem2CameraMode
from src.dem_2_3d_label_free.dem2_common.dem2_sweep_experiment import Dem2Results, Dem2SweepPacket
from src.dem_2_3d_label_free.dem2_components.dem2_capturer import Dem2Capturer
from src.dem_2_3d_label_free.dem2_components.dem2_controller import Dem2Controller
from src.dem_2_3d_label_free.__globals__ import __config__, __datapath__


DATA_PATH = Path(__datapath__)
default_config = __config__

# Single shared controller – same as in Flask backend
controller = Dem2Controller(default_config)


def numpy_to_qpixmap(array: np.ndarray) -> QPixmap:
    """Convert 2D/3D np.uint8 array to QPixmap."""
    if array.ndim == 2:
        h, w = array.shape
        img = QImage(array.data, w, h, w, QImage.Format_Grayscale8)
    else:
        h, w, c = array.shape
        img = QImage(array.data, w, h, w * c, QImage.Format_RGB888)
    return QPixmap.fromImage(img.copy())


def compute_fft_image(image_array: np.ndarray, gamma: float) -> np.ndarray:
    ft_array = np.fft.fft2(image_array)
    ft_array = np.fft.fftshift(ft_array)
    ft_array = np.abs(ft_array)
    ft_array = ft_array ** gamma
    # normalize to 0–255
    ft_array = ft_array - ft_array.min()
    if ft_array.max() > 0:
        ft_array = ft_array / ft_array.max()
    ft_array = (ft_array * 255).astype(np.uint8)
    return ft_array


class SystemState:
    def __init__(self):
        self.devices = {
            "controller": {"id": "controller", "status": 0, "name": "MASTER_CTRL"},
            "laser": {"id": "laser", "status": 0, "mode": 0, "name": "LASER_SRC"},
            "camera": {"id": "camera", "status": 0, "mode": 0, "name": "XIB64_CAM"},
            "stage": {"id": "stage", "status": 0, "mode": 0, "name": "MTB_STAGE"},
        }
        self.integration_time = 0.1
        self.isLive = False
        self.isCaptBurst = False
        self.fftEnabled = False
        self.saveEnabled = False


STATUS_MAP = {
    0: ("DISCONNECTED", "red"),
    1: ("CONNECTED", "yellow"),
    2: ("INITIALISED", "blue"),
    3: ("READY", "green"),
    4: ("RUNNING", "cyan"),
    99: ("WAITING...", "gray"),
}

MODES = {
    "camera": ["MONO", "BURST"],
    "laser": ["CW", "SINGLE", "CONTINUOUS"],
    "stage": ["MANUAL", "PATTERN"],
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.state = SystemState()
        self.setWindowTitle("DEMONSTRATOR_2 // V.0.1")
        self.resize(1400, 900)

        # Main font similar to monospace terminal look
        mono_font = QFont("Courier New")
        self.setFont(mono_font)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("DEMONSTRATOR_2 // V.0.1")
        title_label.setStyleSheet("color: cyan; font-size: 20pt; font-weight: bold;")
        subtitle_label = QLabel("ELECTRIC BOOGALOO")
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
        ctrl_group.setStyleSheet("QGroupBox { color: #22d3ee; }")
        ctrl_layout = QVBoxLayout(ctrl_group)

        btn_layout = QHBoxLayout()
        self.btn_ctrl_connect = QPushButton("Connect")
        self.btn_ctrl_init = QPushButton("Initialize")
        self.btn_ctrl_disc = QPushButton("Disconnect")
        btn_layout.addWidget(self.btn_ctrl_connect)
        btn_layout.addWidget(self.btn_ctrl_init)
        btn_layout.addWidget(self.btn_ctrl_disc)

        ctrl_layout.addLayout(btn_layout)

        # Status table
        self.status_table = QTableWidget(4, 5)
        self.status_table.setHorizontalHeaderLabels(
            ["DEVICE", "STATUS CODE", "STATE DESC", "MODE", "INDICATOR"]
        )
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ctrl_layout.addWidget(self.status_table)

        # Upper grid: Camera (full width)
        cam_group = QGroupBox("XIMEA XIB64 CAMERA")
        cam_group.setStyleSheet("QGroupBox { color: #22c55e; }")
        cam_layout = QVBoxLayout(cam_group)

        # Top status/mode line remains the same
        cam_top_layout = QHBoxLayout()
        self.cam_status_label = QLabel("STATUS: DISCONNECTED")
        self.cam_mode_combo = QComboBox()
        self.cam_mode_combo.addItems(["Mono", "Frame Burst"])
        self.btn_cam_connect = QPushButton("Conn.")
        self.btn_cam_init = QPushButton("Init.")
        self.btn_cam_disc = QPushButton("Disc.")
        cam_top_layout.addWidget(self.cam_status_label)
        cam_top_layout.addStretch()
        cam_top_layout.addWidget(self.cam_mode_combo)
        cam_top_layout.addWidget(self.btn_cam_connect)
        cam_top_layout.addWidget(self.btn_cam_init)
        cam_top_layout.addWidget(self.btn_cam_disc)
        cam_layout.addLayout(cam_top_layout)

        # --- NEW: main camera area in 2 columns ---
        cam_main_layout = QHBoxLayout()
        cam_layout.addLayout(cam_main_layout)

        # LEFT COLUMN: 3 image frames stacked
        cam_view_column = QVBoxLayout()

        self.label_cam_live = QLabel("NO SIGNAL")
        self.label_cam_captured = QLabel("NO SIGNAL")
        self.label_cam_fft = QLabel("NO DATA")

        for lbl in (self.label_cam_live, self.label_cam_captured, self.label_cam_fft):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("background-color: black; color: #64748b;")
            # Fixed width, height flexible
            lbl.setFixedWidth(640)  # choose any width you like
            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            # Optional: default 16:9 minimum height
            lbl.setMinimumHeight(int(640 * 9 / 16))

        cam_view_column.addWidget(self.label_cam_live)
        cam_view_column.addWidget(self.label_cam_captured)
        cam_view_column.addWidget(self.label_cam_fft)

        cam_main_layout.addLayout(cam_view_column)

        # RIGHT COLUMN: all camera controls stacked
        cam_ctrl_column = QVBoxLayout()

        cam_ctrl1 = QHBoxLayout()
        self.btn_cam_capture = QPushButton("Capture")
        self.chk_fft = QCheckBox("FFT 2D")
        self.chk_save = QCheckBox("Save")
        self.gamma_spin = QDoubleSpinBox()
        self.gamma_spin.setRange(0.0, 1.0)
        self.gamma_spin.setSingleStep(0.1)
        self.gamma_spin.setValue(0.3)
        cam_ctrl1.addWidget(self.btn_cam_capture)
        cam_ctrl1.addSpacing(20)
        cam_ctrl1.addWidget(QLabel("Gamma"))
        cam_ctrl1.addWidget(self.gamma_spin)
        cam_ctrl1.addSpacing(20)
        cam_ctrl1.addWidget(self.chk_fft)
        cam_ctrl1.addWidget(self.chk_save)

        cam_ctrl2 = QHBoxLayout()
        self.btn_cam_set_int = QPushButton("Set Texp")
        self.int_time_spin = QDoubleSpinBox()
        self.int_time_spin.setRange(0.1, 1000.0)
        self.int_time_spin.setSingleStep(0.01)
        self.int_time_spin.setValue(0.1)
        cam_ctrl2.addWidget(self.btn_cam_set_int)
        cam_ctrl2.addWidget(QLabel("Integration time [ms]"))
        cam_ctrl2.addWidget(self.int_time_spin)

        cam_ctrl3 = QHBoxLayout()
        self.btn_cam_live = QPushButton("Live")
        self.btn_cam_burst = QPushButton("Capt. Burst")
        cam_ctrl3.addWidget(self.btn_cam_live)
        cam_ctrl3.addWidget(self.btn_cam_burst)

        # Add control rows to the right column
        cam_ctrl_column.addLayout(cam_ctrl1)
        cam_ctrl_column.addLayout(cam_ctrl2)
        cam_ctrl_column.addLayout(cam_ctrl3)
        cam_ctrl_column.addStretch()

        cam_main_layout.addLayout(cam_ctrl_column)

        # Laser
        laser_group = QGroupBox("SWEPT SOURCE")
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

        # Stage
        stage_group = QGroupBox("MICROSCOPE STAGE")
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

        grid_stage.addWidget(QLabel("X"), 0, 0)
        grid_stage.addWidget(self.spin_stage_x, 0, 1)
        grid_stage.addWidget(QLabel("Y"), 1, 0)
        grid_stage.addWidget(self.spin_stage_y, 1, 1)
        grid_stage.addWidget(self.btn_stage_set_xy, 0, 2, 2, 1)

        grid_stage.addWidget(QLabel("ΔX"), 2, 0)
        grid_stage.addWidget(self.spin_stage_dx, 2, 1)
        grid_stage.addWidget(QLabel("ΔY"), 3, 0)
        grid_stage.addWidget(self.spin_stage_dy, 3, 1)
        grid_stage.addWidget(self.btn_stage_move_xy, 2, 2, 2, 1)

        grid_stage.addWidget(QLabel("Z"), 4, 0)
        grid_stage.addWidget(self.spin_stage_z, 4, 1)
        grid_stage.addWidget(self.btn_stage_focus_set, 4, 2)

        grid_stage.addWidget(QLabel("ΔZ"), 5, 0)
        grid_stage.addWidget(self.spin_stage_dz, 5, 1)
        grid_stage.addWidget(self.btn_stage_focus_move, 5, 2)

        stage_layout.addLayout(grid_stage)
        stage_layout.addWidget(self.btn_stage_estop)

        # --- TOP ROW: controller + laser + stage in one row ---
        top_row_layout = QHBoxLayout()
        top_row_layout.addWidget(ctrl_group)
        top_row_layout.addWidget(laser_group)
        top_row_layout.addWidget(stage_group)
        main_layout.addLayout(top_row_layout)

        main_layout.addWidget(cam_group)

        # Wire signals
        self._connect_signals()

        # Timers: clock + live camera
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._get_image_from_buffer)

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
        controller.stage.calibrate(0)

    def set_mode(self, device: str, new_mode: int):
        if device == "laser":
            controller.laser.change_mode(Dem2LaserMode(new_mode))
        elif device == "camera":
            controller.camera.change_mode(Dem2CameraMode(new_mode))
        elif device == "stage":
            controller.stage.change_mode(Dem2LaserMode(new_mode))  # same as your backend

    def set_laser_properties(self):
        controller.laser.wavelength = float(self.spin_laser_cw.value())
        controller.laser.wavelength_max = float(self.spin_laser_max.value())
        controller.laser.wavelength_min = float(self.spin_laser_min.value())
        controller.laser.total_sweep_time = float(self.spin_laser_sweep.value())

    def set_stage_properties(self, relative: bool, focus: bool):
        if relative:
            x = float(self.spin_stage_dx.value())
            y = float(self.spin_stage_dy.value())
            z = float(self.spin_stage_dz.value())
        else:
            x = float(self.spin_stage_x.value())
            y = float(self.spin_stage_y.value())
            z = float(self.spin_stage_z.value())

        if focus:
            controller.stage.move_focus(z, relative)
        else:
            controller.stage.move_stage(x, y, relative)

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
        controller.cam_capturer = Dem2Capturer(
            None,
            controller.camera,
            Dem2SweepPacket(str(DATA_PATH / "image.h5")),
        )
        controller.cam_capturer.start()

    def emergency_stop(self):
        controller.laser.kill_emission()
        controller.stage.stop_moving()

    # ------------------------------------------------------------------
    # UI / State handling
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # controller
        self.btn_ctrl_connect.clicked.connect(lambda: self._with_wait(self._connect_controller))
        self.btn_ctrl_init.clicked.connect(lambda: self._with_wait(self._init_controller))
        self.btn_ctrl_disc.clicked.connect(lambda: self._with_wait(self._disc_controller))

        # camera
        self.btn_cam_connect.clicked.connect(lambda: self._with_wait(self._connect_camera))
        self.btn_cam_init.clicked.connect(lambda: self._with_wait(self._init_camera))
        self.btn_cam_disc.clicked.connect(lambda: self._with_wait(self._disc_camera))

        self.cam_mode_combo.currentIndexChanged.connect(
            lambda idx: self._with_wait(lambda: self.set_mode("camera", idx))
        )
        self.btn_cam_capture.clicked.connect(lambda: self._with_wait(self._get_single_image))
        self.btn_cam_set_int.clicked.connect(lambda: self._with_wait(self._set_integration_time))
        self.btn_cam_live.clicked.connect(lambda: self._with_wait(self._toggle_live_clicked))
        self.btn_cam_burst.clicked.connect(lambda: self._with_wait(self._start_burst))
        self.chk_fft.stateChanged.connect(self._update_flags)
        self.chk_save.stateChanged.connect(self._update_flags)

        # laser
        self.btn_laser_connect.clicked.connect(lambda: self._with_wait(self._connect_laser))
        self.btn_laser_init.clicked.connect(lambda: self._with_wait(self._init_laser))
        self.btn_laser_disc.clicked.connect(lambda: self._with_wait(self._disc_laser))
        self.laser_mode_combo.currentIndexChanged.connect(
            lambda idx: self._with_wait(lambda: self.set_mode("laser", idx))
        )
        self.spin_laser_min.valueChanged.connect(self._update_sweep_speed)
        self.spin_laser_max.valueChanged.connect(self._update_sweep_speed)
        self.spin_laser_sweep.valueChanged.connect(self._update_sweep_speed)
        self.btn_laser_on.clicked.connect(lambda: self._with_wait(self._toggle_emission_clicked))
        self.btn_laser_off.clicked.connect(lambda: self._with_wait(self._toggle_emission_clicked))

        # stage
        self.btn_stage_connect.clicked.connect(lambda: self._with_wait(self._connect_stage))
        self.btn_stage_init.clicked.connect(lambda: self._with_wait(self._init_stage))
        self.btn_stage_calib.clicked.connect(lambda: self._with_wait(self._calibrate_stage))
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
        self.btn_stage_estop.clicked.connect(lambda: self._with_wait(self.emergency_stop))

    def _with_wait(self, func):
        try:
            # simple "WAITING" visualization
            for dev in self.state.devices.values():
                dev["status"] = 99
            self._update_ui()
            func()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            self.update_all()

    def update_all(self):
        self._update_states()
        self._update_modes()
        self._update_properties()
        self._update_laser_properties()
        self._update_stage_properties()
        self._update_integration_time()
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
        # could render to extra labels if needed
        _ = self.get_properties()

    def _update_laser_properties(self):
        if self.state.devices["laser"]["status"] == 0:
            return
        info = self.get_laser_properties()
        self.spin_laser_max.setValue(info["max"])
        self.spin_laser_min.setValue(info["min"])
        self.spin_laser_cw.setValue(info["wavelength"])
        self.spin_laser_sweep.setValue(info["total_time"])
        self._update_sweep_speed()

    def _update_stage_properties(self):
        if self.state.devices["stage"]["status"] < 2 or self.state.devices["stage"]["status"] == 99:
            return
        info = self.get_stage_properties()
        self.spin_stage_x.setValue(info["x"])
        self.spin_stage_y.setValue(info["y"])
        self.spin_stage_z.setValue(info["z"])

    def _update_integration_time(self):
        self.state.integration_time = controller.camera.t_exp
        self.int_time_spin.setValue(self.state.integration_time)

    def _update_sweep_speed(self):
        dt = self.spin_laser_sweep.value()
        if dt <= 0:
            self.spin_laser_sweep_speed.setValue(0.0)
            return
        speed = (self.spin_laser_max.value() - self.spin_laser_min.value()) / dt
        self.spin_laser_sweep_speed.setValue(speed)

    def _update_flags(self):
        self.state.fftEnabled = self.chk_fft.isChecked()
        self.state.saveEnabled = self.chk_save.isChecked()

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
        cam = self.state.devices["camera"]
        label, color = STATUS_MAP.get(cam["status"], STATUS_MAP[99])
        self.cam_status_label.setText(f"STATUS: {label} | MODE: {MODES['camera'][cam['mode']]}")
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
        self.spin_laser_cw.setEnabled(is_cw)
        self.spin_laser_min.setEnabled(not is_cw)
        self.spin_laser_max.setEnabled(not is_cw)
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

    # ------------------------------------------------------------------
    # Actions (mirror JS functions)
    # ------------------------------------------------------------------

    def _connect_controller(self):
        self.connect_device("controller")

    def _init_controller(self):
        # show warning about objective
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
        self.live_timer.stop()
        self.disconnect_device("controller")

    def _connect_camera(self):
        self.connect_device("camera")

    def _init_camera(self):
        self.initialize_device("camera")

    def _disc_camera(self):
        self.state.isLive = False
        self.state.isCaptBurst = False
        self.live_timer.stop()
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

    def _get_single_image(self):
        gamma = float(self.gamma_spin.value())
        if not 0.0 <= gamma <= 1.0:
            raise ValueError("Gamma must be between 0 and 1")
        controller.camera.t_exp = float(self.int_time_spin.value())

        image_array = controller.camera.acquire_single_image()
        if image_array is None:
            return

        if self.state.saveEnabled:
            results = Dem2Results(
                image_array,
                controller.settings,
                controller._cfg,
                controller.stage.b_scan_pattern[0],
            )
            results.save(str(DATA_PATH / f"image_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.h5"))

        qpix = numpy_to_qpixmap(image_array.astype(np.uint8))
        self.label_cam_live.setPixmap(qpix.scaled(self.label_cam_live.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if self.state.fftEnabled:
            ft_arr = compute_fft_image(image_array, gamma)
            qpix_ft = numpy_to_qpixmap(ft_arr)
            self.label_cam_fft.setPixmap(
                qpix_ft.scaled(self.label_cam_fft.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        # update integration time display
        self._update_integration_time()

    def _get_image_from_buffer(self):
        if controller.camera.state != Dem2State.RUNNING:
            return
        image_array = controller.camera.get_image(controller.camera.image)
        if image_array is None:
            return

        qpix = numpy_to_qpixmap(image_array.astype(np.uint8))
        self.label_cam_live.setPixmap(qpix.scaled(self.label_cam_live.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if self.state.isLive:
            # Optional: capture one frame on demand like Flask version with capture_next_live_frame
            pass

        if self.state.fftEnabled:
            ft_arr = compute_fft_image(image_array, float(self.gamma_spin.value()))
            qpix_ft = numpy_to_qpixmap(ft_arr)
            self.label_cam_fft.setPixmap(
                qpix_ft.scaled(self.label_cam_fft.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def _toggle_emission_clicked(self):
        self.toggle_emission()

    def _toggle_live_clicked(self):
        state_str = self.toggle_live()
        self.state.isLive = "RUNNING" in state_str
        if self.state.isLive:
            self.live_timer.start(1000)
        else:
            self.live_timer.stop()

    def _start_burst(self):
        self.start_trigger_capturing()
        self.state.isCaptBurst = True

    def _set_integration_time(self):
        controller.camera.t_exp = float(self.int_time_spin.value())
        self._update_integration_time()

    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
