/* Content ai generated and manually edited.

This is file is deprecated.
*/

function changeStatus(device, status) {
    const statusText = {
        0: 'Disconnected',
        1: 'Connected',
        2: 'Initialized',
        3: 'Ready',
        4: 'Running',
        99: '...'
    };

    const statusColor = {
        0: 'red',
        1: 'yellow',
        2: 'yellow',
        3: 'green',
        4: 'green',
        99: 'gray'
    };

    const element = document.getElementById(`${device}-status`);
    element.textContent = `${statusText[status]}`;
    element.className = `status rounded-full px-2 font-mono text-sm bg-${statusColor[status]}-500`;
}

function statusVisualFeedback(){
    const devices = [
        'controller',
        'camera',
        'laser',
        'stage'
    ];
    for (let i = 0; i < devices.length; i++){
        changeStatus(devices[i], 99)
    }
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

function toggleSysInfo(){
    const sysInfoContainer = document.getElementById('sysInfo')
    if (sysInfoContainer.classList.contains("p-4")){
        sysInfoContainer.classList.remove("p-4")
        sysInfoContainer.classList.add("h-0")
    }
    else {
        sysInfoContainer.classList.add("p-4")
        sysInfoContainer.classList.remove("h-0")
    }
}

function showPopup() {
    document.getElementById('warningPopup').classList.add('active');
}

function hidePopup() {
    document.getElementById('warningPopup').classList.remove('active');
}

function tryInitialize() {
    hidePopup()
    updateProperties()
    initialize()
}

function updateProperties() {
    fetch('/get_properties')
        .then(response => response.json())
        .then(data => {
            setSystemInfo(JSON.stringify(data))
        });
}

function updateStates(){
    fetch('/get_states')
        .then(response => response.json())
        .then(data => {
            for (const [key, value] of Object.entries(data)){
                changeStatus(key, value)
            }
        });
}

function toggleBtns(className) {
  // Get all elements with the specified className
  const elements = document.querySelectorAll(`.${className}`);

  // Iterate over each element
  elements.forEach(element => {
    // Check if the element has the 'pointer-event-none' class
    if (element.classList.contains('pointer-events-none')) {
      // Remove 'pointer-event-none' and 'opacity-50' classes
      element.classList.remove('pointer-events-none');
      element.classList.remove('opacity-50');
    } else {
      // Add 'pointer-event-none' and 'opacity-50' classes
      element.classList.add('pointer-events-none');
      element.classList.add('opacity-50');
    }
  });
}


function connect() {
    statusVisualFeedback()
    toggleBtns("controller-btn")
    fetch('/connect', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            updateStates()
            toggleBtns("controller-btn")
//            if (data.success)
        });
}

function disconnect() {
    statusVisualFeedback()
    toggleBtns("controller-btn")
    fetch('/disconnect', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            updateStates()
            toggleBtns("controller-btn")
//            if (data.success)
        });
}

function initialize() {
    statusVisualFeedback()
    toggleBtns("controller-btn")
    fetch('/initialize', {method: 'POST'})
        .then(response => response.json())
        .then(data => {
            updateStates()
            toggleBtns("controller-btn")
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
        } else {
            showNotification(data.error);
        }
    });
}
