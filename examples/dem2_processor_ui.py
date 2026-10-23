"""
Dem2Processor GUI Application
A modern PySide6 interface for holographic image reconstruction

Content ai generated and manually edited.
"""

import sys
from pathlib import Path
from typing import Optional
import numpy as np

# Set matplotlib backend VERY EARLY
import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QFileDialog, QMessageBox,
    QSpinBox, QLineEdit, QComboBox, QTabWidget,
    QSplitter, QStatusBar, QFormLayout, QTextEdit
)
from PySide6.QtCore import Qt, Slot
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib import pyplot as plt

# Import your processor
try:
    from src.dem_2_3d_label_free.__globals__ import __datapath__
    from src.dem_2_3d_label_free.dem2_common.dem2_processor import Dem2Processor
except ImportError:
    print("Warning: Could not import Dem2Processor. Ensure paths are correct.")
    raise


class StyledGroupbox(QGroupBox):
    def __init__(self, title: str = ""):
        super().__init__(title)
        self.setStyleSheet("""
            QGroupBox {
                border: 2px solid #5a5a5a;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                background-color: #2d2d2d;
                color: #e0e0e0;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #64b5f6;
            }
        """)


class ParameterSpinBox(QWidget):
    def __init__(self, label: str, min_val: int = 0, max_val: int = 10000,
                 default: int = 500, step: int = 10):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(label)
        self.label.setMinimumWidth(120)
        self.spinbox = QSpinBox()
        self.spinbox.setRange(min_val, max_val)
        self.spinbox.setValue(default)
        self.spinbox.setSingleStep(step)
        self.spinbox.setStyleSheet("""
            QSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 4px;
                color: #e0e0e0;
            }
            QSpinBox:focus {
                border-color: #64b5f6;
            }
        """)

        layout.addWidget(self.label)
        layout.addWidget(self.spinbox)
        layout.addStretch()

    def value(self) -> int:
        return self.spinbox.value()

    def setValue(self, val: int):
        self.spinbox.setValue(val)


class PlotWidget(QWidget):
    """Custom widget that properly embeds matplotlib figure"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Create figure and canvas
        self.fig = Figure(facecolor='#1e1e1e', figsize=(5, 4))
        self.canvas = FigureCanvasQTAgg(self.fig)  # Use FigureCanvasQTAgg explicitly

        # Add canvas to layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Use setParent to ensure proper relationship
        self.canvas.setParent(self)
        layout.addWidget(self.canvas)

        self.ax = self.fig.add_subplot(111)

    def clear(self):
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor: Optional[Dem2Processor] = None
        self.current_file: Optional[Path] = None
        self.data_path = Path(__datapath__)

        self.setWindowTitle("Dem2Processor - Holographic Reconstruction")
        self.setGeometry(100, 100, 1600, 900)

        self._apply_dark_theme()
        self._setup_ui()
        self._connect_signals()

    def _apply_dark_theme(self):
        style = """
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit, QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 5px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #64b5f6;
            }
            QPushButton {
                background-color: #37474f;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #455a64;
            }
            QPushButton:pressed {
                background-color: #263238;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #757575;
            }
            QSplitter::handle {
                background-color: #5a5a5a;
            }
        """
        self.setStyleSheet(style)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Top section
        top_group = StyledGroupbox("File Selection")
        top_layout = QHBoxLayout(top_group)

        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        self.file_label.setMinimumWidth(300)

        btn_load = QPushButton("📂 Load File")
        btn_load.clicked.connect(self.load_file)

        btn_save = QPushButton("💾 Save File")
        btn_save.clicked.connect(self.save_file)

        btn_browse = QPushButton("📁 Browse Data Path")
        btn_browse.clicked.connect(self.browse_data_path)

        top_layout.addWidget(QLabel("Current File:"))
        top_layout.addWidget(self.file_label)
        top_layout.addWidget(btn_load)
        top_layout.addWidget(btn_save)
        top_layout.addWidget(btn_browse)
        top_layout.addStretch()

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        params_group = StyledGroupbox("Reconstruction Parameters")
        params_layout = QFormLayout(params_group)

        self.centre_y_spin = ParameterSpinBox("Centre Y", 0, 10000, 500, 10)
        self.centre_x_spin = ParameterSpinBox("Centre X", 0, 10000, 500, 10)
        self.width_spin = ParameterSpinBox("Width", 1, 10000, 200, 10)
        self.height_spin = ParameterSpinBox("Height", 1, 10000, 200, 10)
        self.z_slice_spin = ParameterSpinBox("Z Slice", 0, 1000, 1, 1)

        params_layout.addRow(self.centre_y_spin)
        params_layout.addRow(self.centre_x_spin)
        params_layout.addRow(self.width_spin)
        params_layout.addRow(self.height_spin)
        params_layout.addRow(self.z_slice_spin)

        left_layout.addWidget(params_group)

        actions_group = StyledGroupbox("Actions")
        actions_layout = QVBoxLayout(actions_group)

        self.btn_reconstruct = QPushButton("🔄 Reconstruct")
        self.btn_reconstruct.clicked.connect(self.reconstruct)
        self.btn_reconstruct.setEnabled(False)

        self.btn_fft = QPushButton("📊 Show FFT")
        self.btn_fft.clicked.connect(self.show_fft)
        self.btn_fft.setEnabled(False)

        self.btn_clear_plots = QPushButton("🗑️ Clear Plots")
        self.btn_clear_plots.clicked.connect(self.clear_plots)

        actions_layout.addWidget(self.btn_reconstruct)
        actions_layout.addWidget(self.btn_fft)
        actions_layout.addWidget(self.btn_clear_plots)
        actions_layout.addStretch()

        left_layout.addWidget(actions_group)

        dataset_group = StyledGroupbox("Dataset")
        dataset_layout = QVBoxLayout(dataset_group)

        self.dataset_combo = QComboBox()
        self.dataset_combo.setMinimumWidth(200)
        self.dataset_combo.setEditable(True)
        self.dataset_combo.setCurrentText("images")  # Changed from "1" to match common naming

        dataset_layout.addWidget(QLabel("Select Dataset:"))
        dataset_layout.addWidget(self.dataset_combo)

        left_layout.addWidget(dataset_group)
        left_layout.addStretch()

        # Right panel - plots
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                background-color: #2d2d2d;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #64b5f6;
                color: #fff;
            }
        """)

        # Create plot widgets
        self.plot_holo = PlotWidget()
        self.plot_ft = PlotWidget()
        self.plot_cropped = PlotWidget()
        self.plot_recon_intensity = PlotWidget()
        self.plot_recon_phase = PlotWidget()

        # Add to tabs
        self.tabs.addTab(self.plot_holo, "Intensity Hologram")
        self.tabs.addTab(self.plot_ft, "FFT of Hologram")
        self.tabs.addTab(self.plot_cropped, "Cropped & Centred FFT")
        self.tabs.addTab(self.plot_recon_intensity, "Reconstructed Intensity")
        self.tabs.addTab(self.plot_recon_phase, "Reconstructed Phase")

        # Status
        status_group = StyledGroupbox("Status & Logs")
        status_layout = QVBoxLayout(status_group)

        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(100)
        self.status_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #5a5a5a;
                border-radius: 4px;
                padding: 5px;
                color: #b0bec5;
                font-size: 11px;
            }
        """)

        status_layout.addWidget(self.status_text)

        right_layout.addWidget(self.tabs)
        right_layout.addWidget(status_group)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 1200])

        main_layout.addWidget(top_group)
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _connect_signals(self):
        self.centre_y_spin.spinbox.valueChanged.connect(self._check_parameters)
        self.centre_x_spin.spinbox.valueChanged.connect(self._check_parameters)
        self.width_spin.spinbox.valueChanged.connect(self._check_parameters)
        self.height_spin.spinbox.valueChanged.connect(self._check_parameters)
        # IMPORTANT: Connect dataset combo change to update processor.dataset
        self.dataset_combo.currentTextChanged.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, new_dataset: str):
        """Called when user changes dataset in dropdown"""
        if self.processor and self.current_file:
            try:
                old_dataset = self.processor.dataset
                self.processor.dataset = new_dataset
                self.log_message(f"Switched dataset from '{old_dataset}' to '{new_dataset}'")
                self._update_parameters_from_file()  # Reload params for new dataset
            except Exception as e:
                self.log_message(f"Error switching dataset: {e}", error=True)

    def _check_parameters(self):
        has_valid_params = (
            self.centre_y_spin.value() >= 0 and
            self.centre_x_spin.value() >= 0 and
            self.width_spin.value() > 0 and
            self.height_spin.value() > 0
        )
        self.btn_reconstruct.setEnabled(has_valid_params and self.processor is not None)
        self.btn_fft.setEnabled(self.processor is not None)

    @Slot()
    def load_file(self):
        if self.processor is None:
            self.processor = Dem2Processor(data_path=self.data_path)

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", str(self.data_path),
            "HDF5 Files (*.h5);;TIFF Files (*.tif *.tiff);;All Files (*)"
        )

        if not file_path:
            return

        file_path = Path(file_path)

        try:
            self.status_bar.showMessage(f"Loading {file_path.name}...")
            QApplication.processEvents()

            if file_path.suffix.lower() in ['.tif', '.tiff']:
                self.processor.convert_tif_to_h5(file_path)
                h5_path = file_path.with_suffix('.h5')
                self.processor.load(full_path=h5_path)
                self.current_file = h5_path
                self.log_message(f"Converted TIFF to HDF5: {h5_path.name}")
            else:
                self.processor.load(full_path=file_path)
                self.current_file = file_path

            self.file_label.setText(f"✅ {file_path.name}")
            self.status_bar.showMessage(f"Loaded: {file_path.name}")
            self.log_message(f"Successfully loaded: {file_path.name}")

            # Update parameters from file attributes
            self._update_parameters_from_file()

            self._update_dataset_combo()

            # CRITICAL: Set processor.dataset to the currently selected item
            selected_dataset = self.dataset_combo.currentText()
            if self.processor:
                self.processor.dataset = selected_dataset
                self.log_message(f"Set processor dataset to: {selected_dataset}")

            self.btn_reconstruct.setEnabled(True)
            self.btn_fft.setEnabled(True)

        except Exception as e:
            self.log_message(f"Error loading file: {str(e)}", error=True)
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")
            self.status_bar.showMessage("Error loading file")

    def _update_parameters_from_file(self):
        """Read parameters from HDF5 file attributes and update GUI spinboxes"""
        if not self.current_file or not self.processor:
            return

        try:
            import h5py
            with h5py.File(str(self.current_file), 'r') as f:
                ds_name = self.processor.dataset  # Use CURRENT dataset from processor
                if ds_name in f:
                    attrs = f[ds_name].attrs

                    # Read centre coordinates from attributes
                    if 'centre' in attrs:
                        centre = attrs['centre']
                        if hasattr(centre, '__iter__') and len(centre) >= 2:
                            self.centre_y_spin.setValue(int(centre[0]))
                            self.centre_x_spin.setValue(int(centre[1]))
                        elif isinstance(centre, tuple) or isinstance(centre, list):
                            self.centre_y_spin.setValue(int(centre[0]))
                            self.centre_x_spin.setValue(int(centre[1]))

                    # Read dimensions from attributes
                    if 'width' in attrs:
                        self.width_spin.setValue(int(attrs['width']))
                    if 'height' in attrs:
                        self.height_spin.setValue(int(attrs['height']))

                    # Also check for shape-based defaults if no explicit dimensions
                    if 'shape' in attrs and 'width' not in attrs and 'height' not in attrs:
                        shape = attrs['shape']
                        if hasattr(shape, '__iter__') and len(shape) >= 2:
                            # Use 20% of image size as reasonable default
                            self.width_spin.setValue(int(shape[-1] * 0.2))
                            self.height_spin.setValue(int(shape[-2] * 0.2))

                    self.log_message(f"Loaded parameters from file: centre=({self.centre_y_spin.value()}, {self.centre_x_spin.value()}), size=({self.width_spin.value()}x{self.height_spin.value()})")

                else:
                    self.log_message(f"Warning: Dataset '{ds_name}' not found in file!", error=True)

        except Exception as e:
            self.log_message(f"Could not read parameters from file: {e}", error=True)

    @Slot()
    def save_file(self):
        if self.processor is None:
            QMessageBox.warning(self, "No File", "Please load a file first!")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save File", str(self.current_file or ""),
            "HDF5 Files (*.h5)"
        )

        if not file_path:
            return

        try:
            self.status_bar.showMessage(f"Saving {Path(file_path).name}...")
            QApplication.processEvents()

            # Save current parameters as attributes
            attributes = {
                'centre': (self.centre_y_spin.value(), self.centre_x_spin.value()),
                'width': self.width_spin.value(),
                'height': self.height_spin.value(),
            }

            self.processor.save(path=Path(file_path), attributes=attributes)
            self.current_file = Path(file_path)
            self.file_label.setText(f"💾 {Path(file_path).name}")
            self.log_message(f"Saved: {Path(file_path).name}")
            self.status_bar.showMessage(f"Saved: {Path(file_path).name}")

        except Exception as e:
            self.log_message(f"Error saving file: {str(e)}", error=True)
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")

    @Slot()
    def browse_data_path(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Data Directory", str(self.data_path)
        )

        if dir_path:
            self.data_path = Path(dir_path)
            if self.processor:
                self.processor._data_path = self.data_path
            self.log_message(f"Data path set to: {dir_path}")

    @Slot()
    def reconstruct(self):
        if self.processor is None:
            QMessageBox.warning(self, "No File", "Please load a file first!")
            return

        try:
            centre = (self.centre_y_spin.value(), self.centre_x_spin.value())
            width = self.width_spin.value()
            height = self.height_spin.value()
            z_slice = self.z_slice_spin.value()

            self.status_bar.showMessage("Reconstructing...")
            QApplication.processEvents()

            self.log_message(f"Starting reconstruction: centre={centre}, size=({width}x{height}), z={z_slice}, dataset={self.processor.dataset}")

            result = self.processor.reconstruct(
                centre=centre, width=width, height=height, z_slice=z_slice, plot=False
            )

            self._update_all_plots()
            self.log_message("✅ Reconstruction completed successfully!")
            self.status_bar.showMessage("Reconstruction completed")

        except Exception as e:
            self.log_message(f"Error during reconstruction: {str(e)}", error=True)
            QMessageBox.critical(self, "Error", f"Reconstruction failed:\n{str(e)}")
            self.status_bar.showMessage("Error during reconstruction")

    @Slot()
    def show_fft(self):
        if self.processor is None:
            QMessageBox.warning(self, "No File", "Please load a file first!")
            return

        try:
            self.status_bar.showMessage("Computing FFT...")
            QApplication.processEvents()

            arr = self.processor[:, :]
            ft_arr = self.processor.ft(arr)

            self._plot_array(self.plot_ft, "FFT of Hologram", np.abs(ft_arr), norm='log', cmap='gray')
            self.tabs.setCurrentIndex(1)
            self.log_message("FFT computed and displayed")
            self.status_bar.showMessage("FFT displayed")

        except Exception as e:
            self.log_message(f"Error computing FFT: {str(e)}", error=True)
            QMessageBox.critical(self, "Error", f"FFT computation failed:\n{str(e)}")

    @Slot()
    def clear_plots(self):
        self._clear_plot(self.plot_holo)
        self._clear_plot(self.plot_ft)
        self._clear_plot(self.plot_cropped)
        self._clear_plot(self.plot_recon_intensity)
        self._clear_plot(self.plot_recon_phase)
        self.log_message("Plots cleared")

    def _update_all_plots(self):
        try:
            centre = (self.centre_y_spin.value(), self.centre_x_spin.value())
            width = self.width_spin.value()
            height = self.height_spin.value()
            z_slice = self.z_slice_spin.value()

            arr = self.processor[z_slice, :, :]
            ft_arr = self.processor.ft(arr)
            cft_arr = self.processor.crop_and_centre(ft_arr, centre, width, height)
            recon_arr = self.processor.ift(cft_arr)

            self._plot_array(self.plot_holo, "Intensity Hologram", arr, cmap='gray')
            self._plot_array(self.plot_ft, "FFT of Hologram", np.abs(ft_arr), norm='log', cmap='gray')
            self._plot_array(self.plot_cropped, "Cropped & Centred FFT", np.abs(cft_arr), norm='log', cmap='gray')
            self._plot_array(self.plot_recon_intensity, "Reconstructed Intensity", np.abs(recon_arr)**2, cmap='gray')
            self._plot_array(self.plot_recon_phase, "Reconstructed Phase", np.angle(recon_arr), cmap='hsv')

            self.tabs.setCurrentIndex(3)

        except Exception as e:
            self.log_message(f"Error updating plots: {str(e)}", error=True)

    def _plot_array(self, plot_widget: PlotWidget, title: str, array: np.ndarray, norm=None, cmap='gray'):
        plot_widget.fig.clear()
        ax = plot_widget.fig.add_subplot(111)

        if norm is None:
            im = ax.imshow(array, cmap=cmap)
        else:
            im = ax.imshow(array, cmap=cmap, norm=norm)

        ax.set_title(title, color='#e0e0e0')
        ax.tick_params(colors='#e0e0e0')
        ax.title.set_color('#e0e0e0')

        if cmap == 'hsv' or np.issubdtype(array.dtype, np.complexfloating):
            plot_widget.fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        plot_widget.fig.tight_layout()
        plot_widget.canvas.draw()

    def _clear_plot(self, plot_widget: PlotWidget):
        plot_widget.clear()
        plot_widget.ax.text(0.5, 0.5, 'No Data', ha='center', va='center', color='#757575')
        plot_widget.ax.set_xticks([])
        plot_widget.ax.set_yticks([])
        plot_widget.fig.tight_layout()
        plot_widget.canvas.draw()

    def _update_dataset_combo(self):
        if not self.processor or not self.current_file:
            return

        try:
            import h5py
            with h5py.File(str(self.current_file), 'r') as f:
                datasets = list(f.keys())
                self.dataset_combo.clear()
                self.dataset_combo.addItems(datasets)

                # Set to first available dataset if nothing matches
                if datasets:
                    # Try to find current dataset first
                    if self.processor.dataset in datasets:
                        self.dataset_combo.setCurrentText(self.processor.dataset)
                    else:
                        # Default to first available or "images" if exists
                        if "images" in datasets:
                            self.dataset_combo.setCurrentText("images")
                        else:
                            self.dataset_combo.setCurrentIndex(0)
                        # Update processor.dataset to match
                        selected = self.dataset_combo.currentText()
                        if self.processor:
                            self.processor.dataset = selected
                            self.log_message(f"Defaulted to dataset: {selected}")

                else:
                    self.log_message("Warning: No datasets found in file!", error=True)

        except Exception as e:
            self.log_message(f"Could not list datasets: {e}", error=True)
            self.dataset_combo.clear()
            self.dataset_combo.addItem("images")
            if self.processor:
                self.processor.dataset = "images"

    def log_message(self, message: str, error: bool = False):
        timestamp = self._get_timestamp()
        prefix = "❌ ERROR" if error else "ℹ️ INFO"
        log_line = f"[{timestamp}] {prefix}: {message}"
        self.status_text.append(log_line)

    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def closeEvent(self, event):
        plt.close('all')
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Dem2Processor GUI")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()