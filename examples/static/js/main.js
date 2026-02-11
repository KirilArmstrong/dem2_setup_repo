/**
 * MAIN CONTROLLER LOGIC
 * Simulates hardware connection and state management.
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
    fftEnabled: false
};

const cameLiveintervalID = 0

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

    // Camera
    camImg: document.getElementById('imageDisplay'),
    camPlaceholder: document.getElementById('cam-feed-placeholder'),
    camFftCanvas: document.getElementById('cam-fft-canvas'),
    camFftPlaceholder: document.getElementById('cam-fft-placeholder'),
    camStatusText: document.getElementById('cam-status-text'),
    liveIndicator: document.getElementById('live-indicator'),

    // Laser
    laserInputs: {
        cw: document.getElementById('laser-cw-wl'),
        min: document.getElementById('laser-min-wl'),
        max: document.getElementById('laser-max-wl'),
        sweep: document.getElementById('laser-sweep')
    },
    laserModeDropdown: document.getElementById('laser-mode-select'),
    laserStatusText: document.getElementById('laser-status-text'),
    btnLaserOn: document.getElementById('btn-laser-on'),
    btnLaserOff: document.getElementById('btn-laser-off'),

    // Stage
    stageUiManual: document.getElementById('stage-ui-manual'),
    stageUiPattern: document.getElementById('stage-ui-pattern'),
    stageStatusText: document.getElementById('stage-status-text')
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

function sendMode(device, newMode){
    
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
            initialize();
        }
    )
}

function stage_calibrate(){
    showPopup("Remove Objective", `Initializing Demonstrator 2 includes calibrating the Stage.<br>Please ensure there <span class="text-red-600 font-bold">IS NO OBJECTIVE</span> attached to the revolver!`,
        () => {
            updateProperties();
            // initialize();
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

function updateProperties() {
    fetch('/get_properties')
        .then(response => response.json())
        .then(data => {
            setSystemInfo(JSON.stringify(data))
        });
}

function enableCamView(enable){
    if (enable){
        elements.camImg.classList.remove('hidden');
        elements.camPlaceholder.classList.add('hidden');
    }else{
        elements.camImg.classList.add('hidden');
        elements.camPlaceholder.classList.remove('hidden');
    }
}

function updateUI() {
    renderStatusTable();

    // 1. Camera Logic
    const cam = SYSTEM_STATE.devices.camera;
    elements.camStatusText.innerHTML = `STATUS: <span class="${getStatusObj(cam.status).text}">${getStatusObj(cam.status).label}</span> | MODE: ${MODES.camera[cam.mode]}`;

    if (cam.status != 3 && cam.status != 4) enableCamView(false);

    // Live Indicator
    if(SYSTEM_STATE.isLive) {
        elements.liveIndicator.classList.remove('hidden');
    } else {
        elements.liveIndicator.classList.add('hidden');
    }

    // 2. Laser Logic
    const laser = SYSTEM_STATE.devices.laser;
    elements.laserStatusText.innerHTML = `STATUS: <span class="${getStatusObj(laser.status).text}">${getStatusObj(laser.status).label}</span>`;

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
}

function connect() {
    stateLoadVisual()
    fetch('/connect', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function disconnect() {
    stateLoadVisual()
    SYSTEM_STATE.isLive = false;
    fetch('/disconnect', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function initialize() {
    stateLoadVisual()
    fetch('/initialize', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            updateAll()
//            if (data.success)
        });
}

function get_single_image(){
    const imageDisplayElement = document.getElementById('imageDisplay');
    fetch('/get_single_image', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.image) {
            imageDisplayElement.src = `data:image/png;base64,${data.image}`;
            enableCamView(true)
        }
//        else {
//            showNotification(data.error);
//        }
    });
}

function get_image_from_buffer(){
    const imageDisplayElement = document.getElementById('imageDisplay');
    fetch('/get_image_from_buffer', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.image != "None") {
            imageDisplayElement.src = `data:image/png;base64,${data.image}`;
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
                cameLiveintervalID = setInterval(() => {
                    get_image_from_buffer();
                }, 1000);
            }
            else {
                SYSTEM_STATE.isLive = false;
                enableCamView(false)
                clearInterval(cameLiveintervalID);
            }
            updateAll()
        });
}

// function calibrate_stage() {}

// --- Interaction Handlers ---


// Controller
document.getElementById('btn-ctrl-connect').onclick = () => {
    connect();
};
document.getElementById('btn-ctrl-init').onclick = () => {
    controller_initialise();
};
document.getElementById('btn-ctrl-disc').onclick = () => {
    disconnect()
};

// Camera
document.getElementById('btn-cam-connect').onclick = () => {};
document.getElementById('btn-cam-init').onclick = () => {};
document.getElementById('btn-cam-disc').onclick = () => {};

document.getElementById('cam-mode-select').onchange = (e) => {
    SYSTEM_STATE.devices.camera.mode = parseInt(e.target.value);
    updateUI();
};
document.getElementById('btn-cam-capture').onclick = () => {
    get_single_image();
};
document.getElementById('btn-cam-live').onclick = () => {
    toggle_live()
};
document.getElementById('toggle-fft').onchange = (e) => {
    SYSTEM_STATE.fftEnabled = e.target.checked;
    updateUI();
};

// Laser
document.getElementById('btn-laser-connect').onclick = () => {};
document.getElementById('btn-laser-init').onclick = () => {};
document.getElementById('btn-laser-disc').onclick = () => {};
document.getElementById('laser-mode-select').onchange = (e) => {
    SYSTEM_STATE.devices.laser.mode = parseInt(e.target.value);
    // send mode
};
document.getElementById('btn-laser-on').onclick = () => {
    toggle_emission()
};
document.getElementById('btn-laser-off').onclick = () => {
    toggle_emission()
};

// Stage
document.getElementById('btn-stage-connect').onclick = () => {};
document.getElementById('btn-stage-init').onclick = () => {}; // Then auto 3
document.getElementById('btn-stage-calib').onclick = () => {
    stage_calibrate();
};
document.getElementById('btn-stage-disc').onclick = () => {};
document.getElementById('stage-mode-select').onchange = (e) => {
    SYSTEM_STATE.devices.stage.mode = parseInt(e.target.value);
    updateUI();
};
document.getElementById('btn-stage-estop').onclick = () => {
    // Safety first
    emergency_stop();
};

document.getElementById('btn-estop').onclick = () => {
    // Safety first
    emergency_stop();
};

function emergency_stop() {
    // Stop laser and stage
    
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