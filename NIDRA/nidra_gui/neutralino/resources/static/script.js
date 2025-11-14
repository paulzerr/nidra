function initializeApp() {
    const stoppedPageHTML = `
    <div style="font-family: sans-serif; text-align: center; padding: 2em; position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%);">
        <h1>NIDRA has stopped due to timeout.</h1>
        <p>You can now close this window. <br>To continue using NIDRA, restart the application.</p>
    </div>`;

    // ============================================
    // MASTER SCALING CONTROLS
    // ============================================
    const MASTER_SCALE = 1.1;      // Overall size multiplier
    const DESIGN_WIDTH =  1920;     // Screen width where UI looks "native"
    const DESIGN_HEIGHT = 1080;    // Screen height where UI looks "native"
    
    function scaleUi() {
        const container = document.querySelector('.container');
        if (!container) return;
        
        // Get actual visible content area (excludes browser toolbars)
        const containerWidth = container.offsetWidth;
        const containerHeight = container.offsetHeight;
        
        // Calculate scale for both dimensions
        const widthScale = containerWidth / DESIGN_WIDTH;
        const heightScale = containerHeight / DESIGN_HEIGHT;
        
        // Use smaller scale to ensure everything fits
        const baseScale = Math.min(widthScale, heightScale);
        
        // Apply master multiplier
        const finalScale = baseScale * MASTER_SCALE;
        
        // Set CSS variable
        document.documentElement.style.setProperty('--scale', finalScale);
    }

    // Initial scale
    scaleUi();
    
    // Re-scale on window resize
    window.addEventListener('resize', scaleUi);
    
    // Observe container size changes (handles browser zoom, dev tools)
    const container = document.querySelector('.container');
    if (container && window.ResizeObserver) {
        const resizeObserver = new ResizeObserver(scaleUi);
        resizeObserver.observe(container);
    }

    const runBtn = document.getElementById('run-btn');
    const consoleOutput = document.getElementById('console');
    const dataSourceSelect = document.getElementById('data-source');
    const modelNameSelect = document.getElementById('model-name');
    const browseInputFolderBtn = document.getElementById('browse-input-folder-btn');
    const browseInputFileBtn = document.getElementById('browse-input-file-btn');
    const browseOutputDirBtn = document.getElementById('browse-output-btn');
    const helpBtn = document.getElementById('help-btn');
    const showExampleBtn = document.getElementById('show-example-btn');
    const openRecentBtn = document.getElementById('open-recent-btn');
    const selectChannelsBtn = document.getElementById('select-channels-btn');

    let logInterval;
    let statusInterval;
    window.scoringMode = 'subdirs'; // 'subdirs', 'single_file', or 'from_file'

    // Handle Data Source change to update model list and per-mode defaults
    dataSourceSelect.addEventListener('change', () => {
        const selectedSource = dataSourceSelect.value;
        if (selectedSource.includes('PSG')) {
            modelNameSelect.innerHTML = '<option value="u-sleep-nsrr-2024" selected>u-sleep-nsrr-2024</option>';
            // Do NOT preselect channels for PSG; default is to use all channels unless user opens the dialog
            window.selectedChannels = null;
        } else {
            modelNameSelect.innerHTML = `
                <option value="ez6" selected>ez6</option>
                <option value="ez6moe">ez6moe</option>
            `;
            // For ZMax, try to preselect sensible defaults (e.g., 2 EEG channels in one-file mode)
            preselectDefaultChannels();
        }
    });

    // Trigger the change event on load to set the initial state
    dataSourceSelect.dispatchEvent(new Event('change'));


    // Handle "Select Channels" button click
    selectChannelsBtn.addEventListener('click', async () => {
            const inputDir = document.getElementById('input-dir').value;
            const dataSource = document.getElementById('data-source').value;
            if (!inputDir) {
                alert('Please select an input directory first.');
                return;
            }
    
            try {
                const response = await fetch('/get-channels', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ input_dir: inputDir, data_source: dataSource })
                });
    
                const result = await response.json();
    
                if (response.ok) {
                    openChannelSelectionModal(result.channels, result.selection_mode, result.dialog_text);
                } else {
                    alert(`Error: ${result.message}`);
                }
            } catch (error) {
                console.error('Failed to get channels:', error);
                alert('An error occurred while fetching the channel list.');
            }
        });

    // Handle Run Button click
    runBtn.addEventListener('click', async () => {
        const isRunning = runBtn.dataset.isRunning === 'true';

        if (isRunning) {
            // --- CANCEL SCORING ---
            try {
                const response = await fetch('/cancel-scoring', { method: 'POST' });
                const result = await response.json();
                if (response.ok) {
                    console.log('Cancellation requested:', result.message);
                    // Update UI immediately to show cancellation is in progress
                    runBtn.textContent = 'Cancelling...';
                    runBtn.disabled = true;
                } else {
                    alert(`Error: ${result.message}`);
                }
            } catch (error) {
                console.error('Failed to send cancellation request:', error);
                alert('An error occurred while trying to cancel the scoring process.');
            }

        } else {
            // --- START SCORING ---
            const payload = {
                input_dir: document.getElementById('input-dir').value,
                output: document.getElementById('output-dir').value,
                data_source: dataSourceSelect.value,
                model: modelNameSelect.value,
                plot: document.getElementById('gen-plot').checked,
                hypnodensity: document.getElementById('gen-probs').checked,
                gen_stats: document.getElementById('gen-stats').checked,
                score_subdirs: window.scoringMode === 'subdirs',
                score_from_file: window.scoringMode === 'from_file',
                channels: window.selectedChannels || null
            };

            if (!payload.input_dir || !payload.output) {
                alert('Please provide both an Input and an Output directory path.');
                return;
            }

            setRunningState(true);

            try {
                const response = await fetch('/start-scoring', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const result = await response.json();

                if (response.ok) {
                    console.log('Scoring started:', result.message);
                    startPolling();
                } else {
                    alert(`Error: ${result.message}`);
                    setRunningState(false);
                }
            } catch (error) {
                console.error('Failed to start scoring process:', error);
                alert('An error occurred while trying to start the scoring process.');
                setRunningState(false);
            }
        }
    });

    const handleBrowseFolder = async (targetInputId) => {
        try {
            const response = await fetch('/select-directory');
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                const path = result.path;
                document.getElementById(targetInputId).value = path;

                if (targetInputId === 'input-dir') {
                    window.scoringMode = 'subdirs';
                    const outputDirInput = document.getElementById('output-dir');
                    if (!outputDirInput.value) { // Set default output if not already set
                        outputDirInput.value = path + '/autoscorer_output';
                    }
                }
            } else if (result.status === 'cancelled') {
                console.log('Folder selection was cancelled.');
            } else {
                alert(`Error selecting folder: ${result.message}`);
            }
        } catch (error) {
            console.error('Failed to open folder dialog:', error);
            alert('An error occurred while trying to open the folder dialog.');
        }
    };

    const handleBrowseFile = async () => {
        try {
            const response = await fetch('/select-input-file');
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                const filePath = result.path;
                document.getElementById('input-dir').value = filePath;

                // Set scoring mode based on file extension
                if (filePath.toLowerCase().endsWith('.txt')) {
                    window.scoringMode = 'from_file';
                } else {
                    window.scoringMode = 'single_file';
                }

                // Set default output directory based on the file's location
                const outputDirInput = document.getElementById('output-dir');
                if (!outputDirInput.value) {
                    const separatorIndex = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'));
                    const dirPath = filePath.substring(0, separatorIndex);
                    if (dirPath) {
                        outputDirInput.value = dirPath + '/autoscorer_output';
                    }
                }
            } else if (result.status === 'cancelled') {
                console.log('File selection was cancelled.');
            } else {
                alert(`Error selecting file: ${result.message}`);
            }
        } catch (error) {
            console.error('Failed to open file dialog:', error);
            alert('An error occurred while trying to open the file dialog.');
        }
    };

    browseInputFolderBtn.addEventListener('click', () => handleBrowseFolder('input-dir'));
    browseInputFileBtn.addEventListener('click', handleBrowseFile);
    browseOutputDirBtn.addEventListener('click', () => handleBrowseFolder('output-dir'));
    
    helpBtn.addEventListener('click', () => {
        window.open('/docs/manual.html', '_blank');
    });

    showExampleBtn.addEventListener('click', async () => {
        startPolling();

        try {
            const response = await fetch('/show-example', { method: 'POST' });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                document.getElementById('input-dir').value = result.path;
                document.getElementById('output-dir').value = result.path + '/autoscorer_output';
                window.scoringMode = 'subdirs';
                runBtn.click();
            } else {
                alert(`Error showing example: ${result.message}`);
                stopPolling(); 
            }
        } catch (error) {
            console.error('Failed to run example:', error);
            alert('An error occurred while trying to run the example.');
            stopPolling();
        }
    });

    openRecentBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/open-recent-results', { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                console.log(result.message);
            } else {
                alert(`Error: ${result.message}`);
            }
        } catch (error) {
            console.error('Failed to open recent results folder:', error);
            alert('An error occurred while trying to open the recent results folder.');
        }
    });


    // --- UI and Polling Functions ---

    function setRunningState(isRunning, isCancelling = false) {
        runBtn.dataset.isRunning = isRunning;
    
        if (isCancelling) {
            runBtn.disabled = true;
            runBtn.textContent = 'Cancelling...';
        } else if (isRunning) {
            runBtn.disabled = false; // Enable button for cancellation
            runBtn.textContent = 'Cancel';
        } else {
            runBtn.disabled = false;
            runBtn.textContent = 'Run Autoscoring';
        }
    }

    function startPolling() {
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(checkStatus, 2000); // Check status every 2 seconds
    }

    function stopPolling() {
        clearInterval(statusInterval);
    }

    async function fetchLogs() {
        try {
            const response = await fetch('/log');
            const logText = await response.text();
            const consolePre = consoleOutput.querySelector('pre');
            if (consolePre.textContent !== logText) {
                consolePre.textContent = logText;
                // Auto-scroll to the bottom
                consoleOutput.scrollTop = consoleOutput.scrollHeight;
            }
            return logText;
        } catch (error) {
            console.error('Error fetching logs:', error);
            return ""; 
        }
    }

    async function checkStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            setRunningState(data.is_running, data.is_cancelling);

            if (!data.is_running) {
                stopPolling();
                // Fetch logs one last time to get the final output
                setTimeout(fetchLogs, 500);
            }
        } catch (error) {
            console.error('Error checking status:', error);
            setRunningState(false);
            stopPolling();
        }
    }

    // Always poll logs while the UI is open
    if (logInterval) clearInterval(logInterval);
    logInterval = setInterval(fetchLogs, 1000);
    fetchLogs();

    checkStatus();

    // --- Backend Liveness & Shutdown ---

    // Register the frontend with the backend as soon as the page loads.
    async function registerFrontend() {
        try {
            await fetch('/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: window.location.origin })
            });
        } catch (error) {
            console.error('Failed to register frontend:', error);
        }
    }

    // When the user closes the tab, send a final signal to the backend.
    window.addEventListener('beforeunload', () => {
        // Use sendBeacon as it's more reliable for requests during page unload.
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/goodbye', new Blob());
        }
    });

    // Periodically check if the backend is still reachable. If not, show the stopped page.
    async function checkBackendStatus() {
        try {
            // A simple fetch to any endpoint will do. /status is a good choice.
            const response = await fetch('/status');
            if (!response.ok) {
                throw new Error('Backend not responding');
            }
        } catch (error) {
            console.error('Backend connection lost:', error);
            document.open();
            document.write(stoppedPageHTML);
            document.close();
            // Stop all polling once the backend is confirmed to be down.
            stopPolling();
            clearInterval(backendStatusInterval);
        }
    }

    registerFrontend();
    const backendStatusInterval = setInterval(checkBackendStatus, 5000); // Check every 5 seconds
}

document.addEventListener('DOMContentLoaded', initializeApp);

function parseChannelType(name) {
    const MASTOIDS = new Set(['A1','A2','M1','M2']);
    const EEG_BASES = new Set(['FP1','FP2','F3','F4','C3','C4','P3','P4','O1','O2','F7','F8','T3','T4','T5','T6','FZ','CZ','PZ','F1','F2']);
    const UNAMBIGUOUS_EOG_PATTERNS = ['EOG','LOC','ROC','E1','E2'];
    const OTHER_NON_EEG = ['EMG','ECG','EKG'];

    const nameStripped = (name || '').trim();
    const upper = nameStripped.toUpperCase();

    // Remove leading modality prefixes like 'EEG ', 'EOG ', 'EMG '
    const prefixStripped = nameStripped.replace(/^(EEG|EOG|EMG)\s/i, '');
    // Strip trailing mastoid reference suffixes (e.g., ':A1', '-M2')
    let base = prefixStripped.replace(/[:\-]?(A1|A2|M1|M2)$/i, '');
    base = base.trim().toUpperCase();

    // If the full name is a mastoid, keep it as base
    if (MASTOIDS.has(upper)) {
        base = upper;
    }

    const searchName = nameStripped.toUpperCase();
    let chType = 'OTHER';

    if (UNAMBIGUOUS_EOG_PATTERNS.some(p => searchName.includes(p))) {
        chType = 'EOG';
    } else if (EEG_BASES.has(base) || (searchName.includes('EEG') && !OTHER_NON_EEG.some(o => searchName.includes(o)))) {
        chType = 'EEG';
    } else if (MASTOIDS.has(base)) {
        chType = 'MASTOID';
    }

    return { name: nameStripped, base, type: chType };
}

function openChannelSelectionModal(channels, selectionMode, dialogText) {
    // --- Create Modal Structure ---
    const modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'modal-backdrop';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';

    const h2 = document.createElement('h2');
    h2.textContent = 'Select Channels';
    modalContent.appendChild(h2);

    const p = document.createElement('p');
    p.innerHTML = dialogText; // Use innerHTML to render line breaks from backend

    if (!p.innerHTML) { // Fallback if backend provides no text
        switch (selectionMode) {
            case 'zmax_one_file':
                p.innerHTML = 'Please select exactly two channels for a single-file ZMax recording.';
                break;
            case 'zmax_two_files':
                p.innerHTML = 'No channel selection in two-file mode, one channel per EDF is assumed.';
                break;
            case 'psg':
            default:
                p.innerHTML = 'Select the channels to be used for scoring.';
                break;
        }
    }
    p.style.marginBottom = "1em";
    modalContent.appendChild(p);

    const form = document.createElement('form');
    let defaultSelected = 0;

    // Determine required channel count for ZMax modes.
    // For PSG we will preselect all EEG and EOG channels using parseChannelType.
    let requiredCount = 2;
    switch (selectionMode) {
        case 'zmax_one_file':
            requiredCount = 2;
            break;
        case 'zmax_two_files':
            requiredCount = 1;
            break;
        case 'psg':
        default:
            requiredCount = 2;
            break;
    }

    channels.forEach(channel => {
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = 'channel';
        checkbox.value = channel;

        const parsed = parseChannelType(channel);
        let shouldPreselect = false;

        if (selectionMode === 'psg') {
            // PSG: select all EEG and EOG channels automatically
            shouldPreselect = (parsed.type === 'EEG' || parsed.type === 'EOG');
        } else {
            // ZMax: select only EEG channels limited by requiredCount
            if (parsed.type === 'EEG' && defaultSelected < requiredCount) {
                shouldPreselect = true;
            }
        }

        if (shouldPreselect) {
            checkbox.checked = true;
            defaultSelected++;
        }

        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(` ${channel}`));
        form.appendChild(label);
    });
    modalContent.appendChild(form);

    const okBtn = document.createElement('button');
    okBtn.textContent = 'OK';
    okBtn.className = 'run-btn';
    modalContent.appendChild(okBtn);

    modalBackdrop.appendChild(modalContent);
    document.body.appendChild(modalBackdrop);

    // --- Event Handlers ---
    const closeModal = () => {
        document.body.removeChild(modalBackdrop);
    };

    okBtn.addEventListener('click', () => {
        const selectedCheckboxes = Array.from(form.querySelectorAll('input[type="checkbox"]:checked'));
        const selectedCount = selectedCheckboxes.length;

        let isValid = false;
        let message = '';

        switch (selectionMode) {
            case 'zmax_one_file':
                isValid = (selectedCount === 2);
                if (!isValid) message = 'Please select exactly two channels for a single-file ZMax recording.';
                break;
            case 'zmax_two_files':
                isValid = true; // No selection required in two-file mode
                break;
            case 'psg':
            default:
                isValid = true; // Any number of channels is valid for PSG
                break;
        }

        if (!isValid) {
            alert(message);
            return; // Prevent modal from closing
        }

        // If valid, proceed to save/clear the selected channels and close the modal
        if (selectionMode === 'zmax_two_files') {
            window.selectedChannels = null; // No selection needed in two-file mode
        } else {
            window.selectedChannels = selectedCheckboxes.map(cb => cb.value);
            console.log('Selected channels:', window.selectedChannels);
            // Log the selection on the backend
            if (window.selectedChannels && window.selectedChannels.length > 0) {
                fetch('/log-channel-selection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channels: window.selectedChannels })
                });
            }
        }
        closeModal();
    });

    // Close modal if backdrop is clicked
    modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) {
            closeModal();
        }
    });
}

async function preselectDefaultChannels() {
    const inputDir = document.getElementById('input-dir').value;
    if (!inputDir) {
        // No input directory selected, so we can't get channels.
        // We'll handle this when the user clicks "Select Channels".
        return;
    }

    try {
        const response = await fetch('/get-channels', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input_dir: inputDir, data_source: document.getElementById('data-source').value })
        });

        const result = await response.json();

        if (response.ok) {
            const selMode = result.selection_mode || 'psg';
            let selected = [];

            if (selMode === 'psg') {
                // Select all EEG and EOG channels for PSG
                selected = result.channels.filter(c => {
                    const t = parseChannelType(c).type;
                    return t === 'EEG' || t === 'EOG';
                });
            } else if (selMode === 'zmax_two_files') {
                // Two-file mode: no channel selection needed
                selected = [];
            } else if (selMode === 'zmax_one_file') {
                // ZMax one-file: pick exactly 2 EEGs by default if available
                selected = result.channels.filter(c => parseChannelType(c).type === 'EEG').slice(0, 2);
            } else {
                // Fallback: pick up to 2 EEG channels
                selected = result.channels.filter(c => parseChannelType(c).type === 'EEG').slice(0, 2);
            }

            if (selected.length > 0) {
                window.selectedChannels = selected;
                console.log('Pre-selected channels:', selected);
            } else {
                window.selectedChannels = null;
            }
        } else {
            console.error(`Error getting channels for pre-selection: ${result.message}`);
            window.selectedChannels = null;
        }
    } catch (error) {
        console.error('Failed to pre-select channels:', error);
        window.selectedChannels = null;
    }
}