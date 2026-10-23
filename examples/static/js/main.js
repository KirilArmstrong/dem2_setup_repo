/**
 * MAIN CONTROLLER LOGIC
 * Simulates hardware connection and state management.

Content ai generated and manually edited.

This is file is deprecated.
 */

// --- Global State ---
const SYSTEM_STATE = {
    devices: {
        controller: { id: 'controller', status: 0, name: 'MASTER_CTRL' },
        laser:      { id: 'laser', status: 0, mode: 0, name: 'LASER_SRC' }, // Mode: 0:CW, 1:Single, 2:Cont
        camera:     { id: 'camera', status: 0, mode: 0, name: 'XIB64_CAM' },  // Mode: 0:Mono, 1:Burst
        stage:      { id: 'stage', status: 0, mode: 0, name: 'MTB_STAGE' }   // Mode: 0:Manual, 1:Pattern
    },
    vars: [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    isLive: false,
    isCaptBurst: false,
    integration_time: 0.1,
    bspFileContent: "",
    fftEnabled: false,
    saveEnabled: false
};

cameLiveintervalID = 0

// --- Status Codes & Helpers ---
const STATUS_MAP = {
    0: { label: 'DISCONNECTED', color: 'bg-red-600', text: 'text-red-500' },
    1: { label: 'CONNECTED',    color: 'bg-yellow-500', text: 'text-yellow-500' },
    2: { label: 'INITIALISED',  color: 'bg-blue-400', text: 'text-blue-400' },
    3: { label: 'READY',        color: 'bg-emerald-500', text: 'text-emerald-500' },
    4: { label: 'RUNNING',      color: 'bg-blue-600 animate-flash', text: 'text-blue-400' },
    99: { label: 'WAITING...',     color: 'bg-gray-500', text: 'text-gray-500' }
};

const MODES = {
    camera: ['MONO', 'BURST'],
    laser: ['CW', 'SINGLE', 'CONTINUOUS'],
    stage: ['MANUAL', 'PATTERN']
};

// --- DOM Elements Cache ---
const elements = {
    statusBody: document.getElementById('status-table-body'),
    varContainer: document.getElementById('var-container'),
    laserWarning: document.getElementById('laser-warning-banner'),
    estopBanner: document.getElementById('emergency-stop-banner'),

    ctrlBtnConnect: document.getElementById('btn-ctrl-connect'),
    ctrlBtnDisc: document.getElementById('btn-ctrl-disc'),
    ctrlBtnInit: document.getElementById('btn-ctrl-init'),

    // Camera
    camBtnConnect: document.getElementById('btn-cam-connect'),
    camBtnInit: document.getElementById('btn-cam-init'),
    camBtnDisc: document.getElementById('btn-cam-disc'),
    camImg: document.getElementById('imageDisplay'),
    camImgCap: document.getElementById('imageCapturedDisplay'),
    camPlaceholder: document.getElementById('cam-feed-placeholder'),
    camPlaceholderCap: document.getElementById('cam-feed-placeholder-captured'),
    camFftCanvas: document.getElementById('cam-fft-canvas'),
    camFftPlaceholder: document.getElementById('cam-fft-placeholder'),
    camStatusText: document.getElementById('cam-status-text'),
    camGammaInput: document.getElementById("cam-gamma"),
    camIntegrationInput: document.getElementById("cam-integration-time"),
    camIntegrationSetBtn: document.getElementById("btn-cam-set-integration-time"),
    liveIndicator: document.getElementById('live-indicator'),
    burstIndicator: document.getElementById('captburst-indicator'),

    // Laser
    laserBtnConnect: document.getElementById('btn-laser-connect'),
    laserBtnInit: document.getElementById('btn-laser-init'),
    laserBtnDisc: document.getElementById('btn-laser-disc'),
    laserInputs: {
        cw: document.getElementById('laser-cw-wl'),
        min: document.getElementById('laser-min-wl'),
        max: document.getElementById('laser-max-wl'),
        sweep: document.getElementById('laser-sweep'),
        sweepSpeed: document.getElementById('laser-sweep-actual')
    },
    laserModeDropdown: document.getElementById('laser-mode-select'),
    laserStatusText: document.getElementById('laser-status-text'),
    btnLaserOn: document.getElementById('btn-laser-on'),
    btnLaserOff: document.getElementById('btn-laser-off'),

    // Stage
    stageBtnConnect: document.getElementById('btn-stage-connect'),
    stageBtnInit: document.getElementById('btn-stage-init'),
    stageBtnCalib: document.getElementById('btn-stage-calib'),
    stageBtnDisc: document.getElementById('btn-stage-disc'),
    stageUiManual: document.getElementById('stage-ui-manual'),
    stageUiPattern: document.getElementById('stage-ui-pattern'),
    stageStatusText: document.getElementById('stage-status-text'),
    stageInputs: {
        x: document.getElementById('stage-pos-x'),
        y: document.getElementById('stage-pos-y'),
        z: document.getElementById('stage-pos-z'),
        dx: document.getElementById('stage-delta-x'),
        dy: document.getElementById('stage-delta-y'),
        dz: document.getElementById('stage-delta-z'),
    },
    stageBtnApply: document.getElementById('btn-stage-apply'),
};

// --- Initialization ---
function init() {
    updateAll()
    // setInterval(() => {
    //     updateStates();
    //     updateUI();
    // }, 1000)
    startClock();
}

function updateAll(){
    updateProperties();
    updateStates();
    updateLaserProperties()
    updateStageProperties()
    get_integration_time()
    updateModes()
    updateUI();
}

// --- Rendering Logic ---

function getStatusObj(code) {
    return STATUS_MAP[code] || STATUS_MAP[99];
}

function renderStatusTable() {
    elements.statusBody.innerHTML = '';
    Object.values(SYSTEM_STATE.devices).forEach(dev => {
        const st = getStatusObj(dev.status);
        const modeStr = dev.mode !== undefined ? (MODES[dev.id]?.[dev.mode] || '-') : '-';

        const row = document.createElement('tr');
        row.className = 'hover:bg-slate-800/50 transition-colors';
        row.innerHTML = `
            <td class="py-2 pl-2 font-bold text-cyan-300">${dev.name}</td>
            <td class="py-2 font-mono">${dev.status}</td>
            <td class="py-2 ${st.text}">${st.label}</td>
            <td class="py-2 text-slate-400 text-xs">${modeStr}</td>
            <td class="py-2 text-right pr-2"><div class="led inline-block ${st.color}"></div></td>
        `;
        elements.statusBody.appendChild(row);
    });
}

function changeStatus(device, status) {
    switch (device) {
        case SYSTEM_STATE.devices.controller.id:
                SYSTEM_STATE.devices.controller.status = status
            break;
        case SYSTEM_STATE.devices.laser.id:
                SYSTEM_STATE.devices.laser.status = status
            break;
        case SYSTEM_STATE.devices.camera.id:
                SYSTEM_STATE.devices.camera.status = status
            break;
        case SYSTEM_STATE.devices.stage.id:
                SYSTEM_STATE.devices.stage.status = status
            break;
    }
}

function changeMode(device, mode) {
    switch (device) {
        case SYSTEM_STATE.devices.laser.id:
                SYSTEM_STATE.devices.laser.mode = mode
            break;
        case SYSTEM_STATE.devices.camera.id:
                SYSTEM_STATE.devices.camera.mode = mode
            break;
        case SYSTEM_STATE.devices.stage.id:
                SYSTEM_STATE.devices.stage.mode = mode
            break;
    }
}

function updateStates(){
    fetch('/get_states')
        .then(response => response.json())
        .then(data => {
            for (const [key, value] of Object.entries(data)){
                changeStatus(key, value)
            }
            updateUI();
        });
}

function updateModes(){
    fetch('/get_modes')
        .then(response => response.json())
        .then(data => {
            for (const [key, value] of Object.entries(data)){
                changeMode(key, value)
            }
            updateUI();
        });
}

function get_integration_time(){
    fetch('/get_integration_time')
        .then(response => response.json())
        .then(data => {
            SYSTEM_STATE.integration_time = data.integration_time;
            updateUI();
        });
}

function setMode(device, newMode){
    const payload = {
        device: device,
        newMode: newMode
    };

    fetch('/set_mode', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function stateLoadVisual(){
    for (let key in SYSTEM_STATE.devices){
        changeStatus(key, 99)
    }
    updateUI()
}

// showPopup("Yesy", "this is a test", () => test_func(true));
function showPopup(title, text, func) {
    document.getElementById('popup-title').innerHTML = title;
    document.getElementById('popup-text').innerHTML = text;
    document.getElementById('warningPopup').classList.add('active');
    document.getElementById('btn-popup-proceed').onclick = () => {
        hidePopup();
        func();
    }
}

function hidePopup() {
    document.getElementById('warningPopup').classList.remove('active');
}

function controller_initialise(){
    showPopup("Remove Objective", `Initializing Demonstrator 2 includes calibrating the Stage.<br>Please ensure there <span class="text-red-600 font-bold">IS NO OBJECTIVE</span> attached to the revolver!`,
        () => {
            updateProperties();
            sendLaserProperties()
            initialize("controller");
        }
    )
}

function stage_calibrate(){
    showPopup("Remove Objective", `Initializing Demonstrator 2 includes calibrating the Stage.<br>Please ensure there <span class="text-red-600 font-bold">IS NO OBJECTIVE</span> attached to the revolver!`,
        () => {
            updateProperties();
            calibrate();
        }
    )
}

function setSystemInfo(jsonString) {
    const info = JSON.parse(jsonString);
    document.getElementById('max-z').textContent = info.z_max;
    document.getElementById('na').textContent = info.na;
    document.getElementById('magnification').textContent = info.mag;
    document.getElementById('axial-bandwidth').textContent = info.axial_bandwidth;
    document.getElementById('exposure-range').textContent = info.exposure_lambda_range;
    document.getElementById('lateral-fov').textContent = info.lateral_fov;
    document.getElementById('lateral-spacing').textContent = info.lateral_spacing;
    document.getElementById('lateral-resolution').textContent = info.lateral_resolution;
}

function setLaserInfo(jsonString){
    const info = JSON.parse(jsonString);
    elements.laserInputs.max.value = info.max;
    elements.laserInputs.min.value = info.min;
    elements.laserInputs.max.max = info.cfg_max;
    elements.laserInputs.min.max = info.cfg_max;
    elements.laserInputs.min.min = info.cfg_min;
    elements.laserInputs.max.min = info.cfg_min;
    elements.laserInputs.cw.value = info.wavelength;
    elements.laserInputs.cw.max = info.cfg_max;
    elements.laserInputs.cw.min = info.cfg_min;
    elements.laserInputs.sweep.value = info.total_time;
    elements.laserInputs.sweep.max = (( info.cfg_max - info.cfg_min ) * 10);
}

function setStageInfo(jsonString){
    const info = JSON.parse(jsonString);
    elements.stageInputs.x.value = info.x;
    elements.stageInputs.y.value = info.y;
    elements.stageInputs.z.value = info.z;
}

function updateSweepSpeed() {
    elements.laserInputs.sweepSpeed.value = (elements.laserInputs.max.value - elements.laserInputs.min.value) / elements.laserInputs.sweep.value
}

function updateProperties() {
    fetch('/get_properties')
        .then(response => response.json())
        .then(data => {
            setSystemInfo(JSON.stringify(data))
        });
}

function updateLaserProperties() {
    if (SYSTEM_STATE.devices.laser.status == 0)
        return
    fetch('/get_laser_properties')
        .then(response => response.json())
        .then(data => {
            setLaserInfo(JSON.stringify(data))
        });
}

function updateStageProperties() {
    if (SYSTEM_STATE.devices.stage.status < 2 || SYSTEM_STATE.devices.stage.status == 99)
        return
    fetch('/get_stage_properties')
        .then(response => response.json())
        .then(data => {
            setStageInfo(JSON.stringify(data))
        });
}

function sendLaserProperties() {
    const payload = {
        wavelength: elements.laserInputs.cw.value,
        min: elements.laserInputs.min.value,
        max: elements.laserInputs.max.value,
        total_time: elements.laserInputs.sweep.value,
    };
    fetch('/set_laser_properties', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function sendStageProperties(relative, focus) {
    x = elements.stageInputs.x.value
    y = elements.stageInputs.y.value
    z = elements.stageInputs.z.value
    if (relative){
        x = elements.stageInputs.dx.value
        y = elements.stageInputs.dy.value
        z = elements.stageInputs.dz.value
    }
    const payload = {
        relative: relative,
        focus: focus,
        x: x,
        y: y,
        z: z,
    };
    fetch('/set_stage_properties', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function set_integration_time(){
    const payload = {
        integration_time: elements.camIntegrationInput.value,
    };
    fetch('/set_integration_time', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) get_integration_time();
        });
}

function enableCamView(enable){
    if (enable){
        elements.camImg.classList.remove('hidden');
        elements.camImgCap.classList.remove('hidden');
        elements.camPlaceholder.classList.add('hidden');
        elements.camPlaceholderCap.classList.add('hidden');
        elements.camFftCanvas.classList.remove('hidden');
        elements.camFftPlaceholder.classList.add('hidden');
    }else{
        elements.camImg.classList.add('hidden');
        elements.camImgCap.classList.add('hidden');
        elements.camPlaceholder.classList.remove('hidden');
        elements.camPlaceholderCap.classList.remove('hidden');
        elements.camFftCanvas.classList.add('hidden');
        elements.camFftPlaceholder.classList.remove('hidden');
    }
}

function updateUI() {
    renderStatusTable();
    const ctrl = SYSTEM_STATE.devices.controller;
    elements.ctrlBtnConnect.disabled = (ctrl.status > 0 || ctrl.status == 99)
    elements.ctrlBtnDisc.disabled = (ctrl.status == 0 || ctrl.status == 99)
    elements.ctrlBtnInit.disabled = (ctrl.status !== 1 || ctrl.status == 99)

    // 1. Camera Logic
    const cam = SYSTEM_STATE.devices.camera;
    elements.camStatusText.innerHTML = `STATUS: <span class="${getStatusObj(cam.status).text}">${getStatusObj(cam.status).label}</span> | MODE: ${MODES.camera[cam.mode]}`;

    if (cam.status != 3 && cam.status != 4) enableCamView(false);
    elements.camBtnConnect.disabled = (cam.status > 0 || cam.status == 99)
    elements.camBtnDisc.disabled = (cam.status == 0 || cam.status == 99)
    elements.camBtnInit.disabled = (cam.status !== 1 || cam.status == 99)
    elements.camIntegrationInput.value = SYSTEM_STATE.integration_time;

    // Live Indicator
    if(SYSTEM_STATE.isLive) {
        elements.liveIndicator.classList.remove('hidden');
    } else {
        elements.liveIndicator.classList.add('hidden');
    }
    // Capture Burst Indicator
    if(SYSTEM_STATE.isCaptBurst) {
        elements.burstIndicator.classList.remove('hidden');
    } else {
        elements.burstIndicator.classList.add('hidden');
    }

    // 2. Laser Logic
    const laser = SYSTEM_STATE.devices.laser;
    elements.laserStatusText.innerHTML = `STATUS: <span class="${getStatusObj(laser.status).text}">${getStatusObj(laser.status).label}</span>`;
    elements.laserBtnConnect.disabled = (laser.status > 0 || laser.status == 99)
    elements.laserBtnDisc.disabled = (laser.status == 0 || laser.status == 99)
    elements.laserBtnInit.disabled = (laser.status !== 1 || laser.status == 99)

    // Mode Dependent Inputs
    const isCW = laser.mode == 0;
    elements.laserInputs.cw.disabled = !isCW;
    elements.laserInputs.min.disabled = isCW;
    elements.laserInputs.max.disabled = isCW;
    elements.laserInputs.sweep.disabled = isCW;

    // Laser Buttons
    // On interactable when Ready (3), Off interactable when Running (4)
    elements.btnLaserOn.disabled = laser.status !== 3;
    elements.btnLaserOff.disabled = laser.status !== 4;
    elements.laserModeDropdown.disabled = laser.status > 1

    elements.laserModeDropdown.value = laser.mode

    // Laser Warning
    if(laser.status === 4) {
        elements.laserWarning.classList.remove('translate-y-full');
        elements.laserWarning.classList.add('shadow-[0_-5px_20px_rgba(234,179,8,0.5)]');
    } else {
        elements.laserWarning.classList.add('translate-y-full');
        elements.laserWarning.classList.remove('shadow-[0_-5px_20px_rgba(234,179,8,0.5)]');
    }

    // 3. Stage Logic
    const stage = SYSTEM_STATE.devices.stage;
    elements.stageStatusText.innerHTML = `STATUS: <span class="${getStatusObj(stage.status).text}">${getStatusObj(stage.status).label}</span>`;
    elements.stageBtnConnect.disabled = (stage.status > 0 || stage.status == 99)
    elements.stageBtnDisc.disabled = (stage.status == 0 || stage.status == 99)
    elements.stageBtnCalib.disabled = (stage.status !== 2 || stage.status == 99)
    elements.stageBtnInit.disabled = (stage.status !== 1 || stage.status == 99)

    if (SYSTEM_STATE.bspFileContent) elements.stageBtnApply.disabled = false;
    else elements.stageBtnApply.disabled = true;

    if (stage.mode == 0) {
        elements.stageUiManual.classList.remove('hidden');
        elements.stageUiPattern.classList.add('hidden');
    } else {
        elements.stageUiManual.classList.add('hidden');
        elements.stageUiPattern.classList.remove('hidden');
    }

    if (laser.status === 4 || stage.status === 4){
        elements.estopBanner.classList.remove('-translate-y-full');
    } else if (laser.status !== 4 && stage.status !== 4){
        elements.estopBanner.classList.add('-translate-y-full');
    }
    
    updateSweepSpeed()
}

function connect(device) {
    const payload = {
        device: device
    };
    stateLoadVisual()
    fetch('/connect', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function disconnect(device) {
    const payload = {
        device: device
    };
    stateLoadVisual()
    SYSTEM_STATE.isLive = false;
    SYSTEM_STATE.isCaptBurst = false;
    fetch('/disconnect', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function initialize(device) {
    const payload = {
        device: device
    };
    stateLoadVisual()
    fetch('/initialize', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function calibrate() {
    stateLoadVisual()
    fetch('/calibrate', {
        method: 'POST'
    })
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function get_single_image(){
    const imageDisplayElement = document.getElementById('imageDisplay');
    const payload = {
        ft: SYSTEM_STATE.fftEnabled,
        save: SYSTEM_STATE.saveEnabled,
        gamma: elements.camGammaInput.value,
        integration_time: elements.camIntegrationInput.value,
        captureLiveFrame: SYSTEM_STATE.isLive
    };
    fetch('/get_single_image', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
    .then(response => response.json())
    .then(data => {
        if (data.image) {
            imageDisplayElement.src = `data:image/png;base64,${data.image}`;
            elements.camFftCanvas.src = `data:image/png;base64,${data.ft}`;
            enableCamView(true)
            get_integration_time()
        }
//        else {
//            showNotification(data.error);
//        }
    });
}

// function get_image_fron_buffer(ftValue) {
//     const imageDisplayElement = document.getElementById('imageDisplay');
    
//     // Create the request payload with the 'ft' parameter
//     const payload = {
//         ft: ftValue
//     };

//     fetch('/get_single_image', {
//         method: 'POST',
//         headers: {
//             'Content-Type': 'application/json'
//         },
//         body: JSON.stringify(payload) // Convert the payload to a JSON string
//     })
//     .then(response => response.json())
//     .then(data => {
//         if (data.image) {
//             imageDisplayElement.src = `data:image/png;base64,${data.image}`;
//             enableCamView(true);
//         }
//     })
//     .catch(error => {
//         console.error('Error:', error);
//     });
// }


function get_image_from_buffer(){
    const imageDisplayElement = document.getElementById('imageDisplay');
    const imageCapturedDisplayElement = document.getElementById('imageCapturedDisplay');
    const payload = {
        ft: SYSTEM_STATE.fftEnabled,
        save: SYSTEM_STATE.saveEnabled,
        gamma: elements.camGammaInput.value,
    };
    fetch('/get_image_from_buffer', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload) // Convert the payload to a JSON string
    })
    .then(response => response.json())
    .then(data => {
        if (data.image != "None") {
            imageDisplayElement.src = `data:image/png;base64,${data.image}`;
        }
        if (data.captured != "None") {
            imageCapturedDisplayElement.src = `data:image/png;base64,${data.captured}`;
        }
        if (data.ft != "None") {
            elements.camFftCanvas.src = `data:image/png;base64,${data.ft}`;
        }
//        else {
//            showNotification(data.error);
//        }
    });
}

function toggle_emission(){
    
    fetch('/toggle_emission', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            if (data.error){
                console.log.error("Error in toggling emission: " + data.error)
                return;
            }
            updateAll()
        });
}

function toggle_live(){
    SYSTEM_STATE.isLive = false;
    enableCamView(false)
    clearInterval(cameLiveintervalID);
    updateAll()
    fetch('/toggle_live', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            if (data.error){
                console.log.error("Error in toggling camera live: " + data.error)
                return;
            }
            if (data.success.includes("RUNNING")){
                SYSTEM_STATE.isLive = true;
                enableCamView(true)
                updateAll()
                cameLiveintervalID = setInterval(() => {
                    get_image_from_buffer();
                }, 1000);
            }
        });
    updateAll()
}



function capt_fram_burst(){
    SYSTEM_STATE.isCaptBurst = false;
    enableCamView(false)
    updateAll()
    fetch('/start_trigger_capturing', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            if (data.error){
                console.log.error("Error in toggling camera frame burst: " + data.error)
                return;
            }
            if (data.success.includes("RUNNING")){
                SYSTEM_STATE.isCaptBurst = true;
                updateAll()
            }
        });
    updateAll()
}

function send_bsp(){
    if (!SYSTEM_STATE.bspFileContent) return;

    const payload = {
        yml: SYSTEM_STATE.bspFileContent  // File contents as a string with newlines preserved
    };

    // Send to Python backend
    fetch('/change_stage_b_scan_pattern', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
    });
}

// function calibrate_stage() {}

// --- Interaction Handlers ---


// Controller
document.getElementById('btn-ctrl-connect').onclick = () => {
    connect("controller");
};
document.getElementById('btn-ctrl-init').onclick = () => {
    controller_initialise();
};
document.getElementById('btn-ctrl-disc').onclick = () => {
    disconnect("controller")
};

// Camera
document.getElementById('btn-cam-connect').onclick = () => {
    connect("camera");
};
document.getElementById('btn-cam-init').onclick = () => {
    initialize("camera");
};
document.getElementById('btn-cam-disc').onclick = () => {
    disconnect("camera")
};

document.getElementById('cam-mode-select').onchange = (e) => {
    // SYSTEM_STATE.devices.camera.mode = parseInt(e.target.value);
    setMode("camera", parseInt(e.target.value))
};
elements.laserInputs.max.onchange = (e) => {
    updateSweepSpeed()
}
elements.laserInputs.min.onchange = (e) => {
    updateSweepSpeed()
}
elements.laserInputs.sweep.onchange = (e) => {
    updateSweepSpeed()
}
document.getElementById('btn-cam-capture').onclick = () => {
    get_single_image();
};
document.getElementById('btn-cam-set-integration-time').onclick = () => {
    set_integration_time();
};
document.getElementById('btn-cam-live').onclick = () => {
    toggle_live()
};
document.getElementById('btn-cam-captburst').onclick = () => {
    capt_fram_burst()
};
document.getElementById('toggle-fft').onchange = (e) => {
    SYSTEM_STATE.fftEnabled = e.target.checked;
    updateUI();
};
document.getElementById('toggle-save').onchange = (e) => {
    SYSTEM_STATE.saveEnabled = e.target.checked;
    updateUI();
};

// Laser
document.getElementById('btn-laser-connect').onclick = () => {
    connect("laser");
};
document.getElementById('btn-laser-init').onclick = () => {
    sendLaserProperties()
    initialize("laser");
};
document.getElementById('btn-laser-disc').onclick = () => {
    disconnect("laser")
};
document.getElementById('laser-mode-select').onchange = (e) => {
    // SYSTEM_STATE.devices.laser.mode = parseInt(e.target.value);
    // send mode
    setMode("laser", parseInt(e.target.value))
};
document.getElementById('btn-laser-on').onclick = () => {
    toggle_emission()
};
document.getElementById('btn-laser-off').onclick = () => {
    toggle_emission()
};

// Stage
document.getElementById('btn-stage-calib').onclick = () => {
    stage_calibrate();
};
document.getElementById('btn-stage-connect').onclick = () => {
    connect("stage");
};
document.getElementById('btn-stage-init').onclick = () => {
    initialize("stage-no-calib");
};
document.getElementById('btn-stage-disc').onclick = () => {
    disconnect("stage")
};
document.getElementById('stage-mode-select').onchange = (e) => {
    // SYSTEM_STATE.devices.stage.mode = parseInt(e.target.value);
    setMode("stage", parseInt(e.target.value))
};
document.getElementById('btn-stage-set').onclick = () => {
    sendStageProperties(false, false)
};
document.getElementById('btn-stage-move').onclick = () => {
    sendStageProperties(true, false)
};
document.getElementById('btn-stage-focus-set').onclick = () => {
    sendStageProperties(false, true)
};
document.getElementById('btn-stage-focus-move').onclick = () => {
    sendStageProperties(true, true)
};
document.getElementById('stage-pattern-input').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Read file as text (preserves newlines)
    SYSTEM_STATE.bspFileContent = await file.text();
    updateUI()
});
document.getElementById('btn-stage-estop').onclick = () => {
    // Safety first
    emergency_stop();
};

document.getElementById('btn-estop').onclick = () => {
    // Safety first
    emergency_stop();
};

document.getElementById('btn-stage-apply').onclick = () => {
    send_bsp();
};

function emergency_stop() {
    // Stop laser and stage
    fetch('/stop')
        .then(response => response.json())
        .then(data => {
            if (data.success){
                console.log(data.success)
                updateAll()
            }
        });
    updateAll()
}


// --- Utilities ---
function startClock() {
    setInterval(() => {
        const now = new Date();
        document.getElementById('clock').innerText = now.toLocaleTimeString('en-US', { hour12: false });
    }, 1000);
}

// Run
init();