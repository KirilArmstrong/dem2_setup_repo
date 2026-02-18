from concurrent.futures.thread import ThreadPoolExecutor

import yaml
import logging
import os
from flask import Flask, render_template, jsonify, request, flash
from numpy.array_api import zeros

from src.dem_2_3d_label_free.dem2_common.dem2_constants import Dem2State, Dem2LaserMode, Dem2CameraMode
# from werkzeug.utils import secure_filename
from src.dem_2_3d_label_free.dem2_components.dem2_controller import Dem2Controller  # Assuming controller.py is in the same directory
from src.dem_2_3d_label_free.__globals__ import __config__
import numpy as np
from io import BytesIO
from PIL import Image
import base64

from src.dem_2_3d_label_free.dem2_devices.dem2_camera import Dem2Camera

default_config = __config__  # default config.yml file in ~/config.
app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Required for flashing messages

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


controller = Dem2Controller(default_config)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/stop', methods=['GET'])
def stop():
    controller.laser.kill_emission()
    controller.stage.stop_moving()
    return jsonify({"success": "Stopped"})


@app.route('/get_states', methods=['GET'])
def get_states():
    return jsonify({'controller': controller.state.value,
                    'camera': controller.camera.state.value,
                    'laser': controller.laser.state.value,
                    'stage': controller.stage.state.value})

@app.route('/get_modes', methods=['GET'])
def get_modes():
    return jsonify({'camera': controller.camera.mode.value,
                    'laser': controller.laser.mode.value,
                    'stage': controller.stage.mode.value})


@app.route("/set_mode", methods=["POST"])
def set_modes():
    try:
        # Retrieve the 'ft' parameter from the request
        device = request.json.get("device", "")
        new_mode = request.json.get("newMode", "")

        match device:
            case "laser":
                controller.laser.change_mode(Dem2LaserMode(new_mode))
            case "camera":
                controller.camera.change_mode(Dem2CameraMode(new_mode))
            case "stage":
                controller.stage.change_mode(Dem2LaserMode(new_mode))
            case _:
                return jsonify({'error': "No device specified."}), 500


        return jsonify({"success": f"New Mode of {device}: {new_mode}"}), 200
    except Exception as e:
        logger.error(f"Error getting image: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/get_properties', methods=['GET'])
def get_properties():
    properties = {
        'z_max': controller.z_max,
        'mag': controller.mag,
        'na': controller.na,
        'axial_bandwidth': controller.axial_bandwidth,
        'exposure_lambda_range': controller.exposure_lambda_range,
        'lateral_fov': controller.lateral_fov,
        # 'lateral_spacing': controller.lateral_spacing,
        'lateral_resolution': controller.lateral_resolution
    }
    return jsonify(properties)


@app.route('/get_laser_properties', methods=['GET'])
def get_laser_properties():
    properties = {
        'max': controller.laser.wavelength_max,
        'min': controller.laser.wavelength_min,
        'cfg_max': controller.laser._cfg["wavelength_max"],
        'cfg_min': controller.laser._cfg["wavelength_min"],
        'wavelength': controller.laser.wavelength,
        'total_time': controller.laser.total_sweep_time,
    }
    return jsonify(properties)


@app.route('/get_stage_properties', methods=['GET'])
def get_stage_properties():
    pos = controller.stage.get_position()
    properties = {
        'x': pos[0],
        'y': pos[1],
        'z': controller.stage.get_focus(),
    }
    return jsonify(properties)


@app.route('/set_laser_properties', methods=['POST'])
def set_laser_properties():
    try:
        controller.laser.wavelength = float(request.json.get("wavelength", 840.0))
        controller.laser.wavelength_max = float(request.json.get("max", 880.0))
        controller.laser.wavelength_min = float(request.json.get("min", 805.0))
        controller.laser.total_sweep_time = float(request.json.get("total_time", 25.0))

        return jsonify({"success": "Laser properties set"}), 200
    except Exception as e:
        logger.error(f"Error getting image: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/set_stage_properties', methods=['POST'])
def set_stage_properties():
    try:
        relative = bool(request.json.get("relative", False))
        focus = bool(request.json.get("focus", False))
        x = float("0" + request.json.get("x", 0.0))
        y = float("0" + request.json.get("y", 0.0))
        z = float("0" + request.json.get("z", 0.0))

        if focus:
            controller.stage.move_focus(z, relative)
            return jsonify({"success": "Stage focus set"}), 200
        controller.stage.move_stage(x, y, relative)

        return jsonify({"success": "Stage position set"}), 200
    except Exception as e:
        logger.error(f"Error setting stage position: {str(e)}")
        return jsonify({'error': str(e)}), 500


# @app.route('/upload_config', methods=['POST'])
# def upload_config():
#     if 'file' not in request.files:
#         flash('No file part')
#         return jsonify({'error': 'No file part'}), 400
#     file = request.files['file']
#     if file.filename == '':
#         flash('No selected file')
#         return jsonify({'error': 'No selected file'}), 400
#     if file and file.filename.endswith('.yml'):
#         filename = secure_filename(file.filename)
#         file_path = os.path.join('uploads', filename)
#         file.save(file_path)
#         with open(file_path, 'r') as f:
#             config = yaml.safe_load(f)
#         controller.__init__(config)
#         logger.info("Configuration updated and controller reinitialized.")
#         return jsonify({'success': 'Configuration updated'}), 200
#     else:
#         flash('Invalid file format')
#         return jsonify({'error': 'Invalid file format'}), 400

# @app.route('/upload_bscan', methods=['POST'])
# def upload_bscan():
#     if 'file' not in request.files:
#         flash('No file part')
#         return jsonify({'error': 'No file part'}), 400
#     file = request.files['file']
#     if file.filename == '':
#         flash('No selected file')
#         return jsonify({'error': 'No selected file'}), 400
#     if file and file.filename.endswith('.yml'):
#         filename = secure_filename(file.filename)
#         file_path = os.path.join('uploads', filename)
#         file.save(file_path)
#         with open(file_path, 'r') as f:
#             bscan_pattern = yaml.safe_load(f)
#         controller.bscan_pattern = bscan_pattern
#         logger.info("BScan pattern uploaded.")
#         return jsonify({'success': 'BScan pattern uploaded'}), 200
#     else:
#         flash('Invalid file format')
#         return jsonify({'error': 'Invalid file format'}), 400

@app.route('/connect', methods=['POST'])
def connect():
    try:
        device = request.json.get("device", "controller")

        match device:
            case "laser":
                controller.laser.connect()
            case "camera":
                controller.camera.connect()
            case "stage":
                controller.stage.connect()
            case _:
                controller.connect()
        logger.info(f"Device {device} connected.")
        return jsonify({'success': f"Device {device} connected."}), 200
    except Exception as e:
        logger.error(f"Error connecting device: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/disconnect', methods=['POST'])
def disconnect():
    try:
        device = request.json.get("device", "controller")

        match device:
            case "laser":
                controller.laser.disconnect()
            case "camera":
                controller.camera.disconnect()
            case "stage":
                controller.stage.disconnect()
            case _:
                controller.disconnect()
        logger.info(f"Device {device} disconnected.")
        return jsonify({'success': f"Device {device} disconnected."}), 200
    except Exception as e:
        logger.error(f"Error disconnecting device: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/initialize', methods=['POST'])
def initialize():
    try:
        device = request.json.get("device", "controller")

        match device:
            case "laser":
                controller.laser.initialize()
            case "camera":
                controller.camera.initialize()
            case "stage":
                controller.stage.initialize(0)
            case "stage-no-calib":
                controller.stage.initialize()
            case _:
                controller.initialize(0)
                logger.info("Demonstrator initialized.")
                return jsonify({'success': 'Demonstrator initialized'}), 200

        logger.info(f"{device} initialized.")
        return jsonify({'success': f"{device} initialized."}), 200
    except Exception as e:
        logger.error(f"Error initializing device: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/calibrate', methods=['POST'])
def calibrate():
    try:
        controller.stage.calibrate(0)

        logger.info("stage calibrated.")
        return jsonify({'success': "stage calibrated."}), 200
    except Exception as e:
        logger.error(f"Error initializing device: {str(e)}")
        return jsonify({'error': str(e)}), 500

# @app.route('/run_bscan_pattern', methods=['POST'])
# def run_bscan_pattern():
#     try:
#         controller.run_bscan_pattern(controller.bscan_pattern)
#         logger.info("BScan pattern executed.")
#         return jsonify({'success': 'BScan pattern executed'}), 200
#     except Exception as e:
#         logger.error(f"Error running BScan pattern: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/toggle_live', methods=['POST'])
def toggle_live():
    try:
        state = controller.camera.toggle_live_images()
        # state = ""
        # controller.executor.submit(controller.camera.acquire_images())
        logger.info("Live: " + state)
        return jsonify({'success': "Live: " + state}), 200
    except Exception as e:
        logger.error(f"Error toggling live: {str(e)}")
        return jsonify({'error': str(e)}), 500

def convert_to_base64(image_array: np.ndarray) -> str:
        image_array = image_array.astype(np.uint8)
        # Convert the numpy array to a PIL image
        image = Image.fromarray(image_array)
        # Save the image to a bytes buffer
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        # Encode the image to base64
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        return image_base64

@app.route("/get_single_image", methods=["POST"])
def get_single_image():
    try:
        # Retrieve the 'ft' parameter from the request
        ft = request.json.get("ft", False)
        gamma = float(request.json.get("gamma", 0.5))
        if gamma < 0 or gamma > 1:
            raise Exception(f"Invalid gamma value: {gamma}. Must be between 0 and 1.")

        # Get the image from the controller
        image_array = controller.camera.acquire_single_image()
        ft_array = np.zeros(image_array.shape)

        if ft:
            ft_array = np.fft.fft2(image_array)
            ft_array = np.fft.fftshift(ft_array)
            ft_array = np.abs(ft_array)
            # Gamma Correction
            ft_array = ft_array ** gamma
            # ft_array = (ft_array - np.min(ft_array)) / (np.max(ft_array) - np.min(ft_array))

        # Encode the image to base64
        image_base64 = convert_to_base64(image_array)
        ft_base64 = convert_to_base64(ft_array)

        return jsonify({"image": image_base64, "ft": ft_base64}), 200
    except Exception as e:
        logger.error(f"Error getting image: {str(e)}")
        return jsonify({'error': str(e)}), 500





@app.route("/get_image_from_buffer", methods=["POST"])
def get_image():
    try:
        # Retrieve the 'ft' parameter from the request
        # ft = request.json.get("ft", False)

        # Get the image from the controller
        if controller.camera.state != Dem2State.RUNNING:
            logger.error("Error getting image: Not running")
            return jsonify({'error': "Error getting image: Not running"}), 500
        image_array = controller.camera.get_image(controller.camera.image)
        if image_array is None:
            return jsonify({"image": "None"}), 200

        # Perform FFT if 'ft' is True
        # if ft:
        #     image_array = np.fft.fft2(image_array)
        #     image_array = np.fft.fftshift(image_array)
        #     image_array = np.abs(image_array)

        # Normalize the image array to 0-255
        # image_array = (
        #     255
        #     * (image_array - np.min(image_array))
        #     / (np.max(image_array) - np.min(image_array))
        # )

        # Encode the image to base64
        image_base64 = convert_to_base64(image_array)

        return jsonify({"image": image_base64}), 200
    except Exception as e:
        logger.error(f"Error getting image: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route("/get_stage_pos", methods=["POST"])
def get_stage_pos():
    try:
        xy = controller.stage.get_position()
        z = controller.stage.get_focus()
        return jsonify({"x": xy[0], "y": xy[1], "z": z}), 200
    except Exception as e:
        logger.error(f"Error getting stage position: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route("/set_stage_pos", methods=["POST"])
def set_stage_pos():
    try:
        # Retrieve the pos parameters from the request
        x = request.json.get("x", False)
        y = request.json.get("y", False)
        controller.stage.move_stage(x, y)
        return jsonify({'success': "New position: " + str(controller.stage.get_position())}), 200
    except Exception as e:
        logger.error(f"Error getting stage position: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route("/move_stage_pos", methods=["POST"])
def move_stage_pos():
    try:
        # Retrieve the pos parameters from the request
        x = request.json.get("x", False)
        y = request.json.get("y", False)
        controller.stage.move_stage(x, y, True)
        return jsonify({'success': "New position: " + str(controller.stage.get_position())}), 200
    except Exception as e:
        logger.error(f"Error getting stage position: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/toggle_emission', methods=['POST'])
def toggle_emission():
    try:
        controller.laser.toggle_emission()
        logger.info("Emission toggled. Now:" + controller.laser.state.name)
        return jsonify({'success': 'Emission toggled. Now:' + controller.laser.state.name}), 200
    except Exception as e:
        logger.error(f"Error initializing demonstrator: {str(e)}")
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True)
