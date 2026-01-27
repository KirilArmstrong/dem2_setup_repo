function changeStatus(device, status) {
    const statusText = {
        0: 'Disconnected',
        1: 'Connected',
        2: 'Initialized',
        3: 'Ready',
        4: 'Running'
    };

    const statusColor = {
        0: 'red',
        1: 'yellow',
        2: 'yellow',
        3: 'green',
        4: 'green'
    };

    const element = document.getElementById(`${device}-status`);
    element.textContent = `${statusText[status]}`;
    element.className = `status rounded-full px-2 font-mono text-sm bg-${statusColor[status]}-500`;
}

function updateSystemInfo(jsonString) {
    const info = JSON.parse(jsonString);
    document.getElementById('max-z').textContent = info.z_max;
    document.getElementById('na').textContent = info.na;
    document.getElementById('magnification').textContent = info.mag;
    document.getElementById('axial-resolution').textContent = info.axial_resolution;
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
    changeStatus('controller', 2)
}

function updateProperties() {
    fetch('/get_properties')
        .then(response => response.json())
        .then(data => {
            propertiesElement.innerHTML = '';
            for (const [key, value] of Object.entries(data)) {
                const li = document.createElement('li');
                li.textContent = `${key}: ${value}`;
                propertiesElement.appendChild(li);
            }
        });
}

// Example usage:
// changeStatus('controller', 1);
// updateSystemInfo('{"maxZ": "100", "na": "1.4", "magnification": "60x", "axialResolution": "0.2", "exposureRange": "400-700nm", "lateralFOV": "200um", "lateralSpacing": "0.5um", "lateralResolution": "0.3um"}');
