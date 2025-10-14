function initializeApp() {
    // --- Dynamic UI Scaling ---
    const BASE_UI_SCALE = 1.4; // Overall size of UI elements (padding, margins, etc.)
    const BASE_FONT_SCALE = 2.4; // Overall font size

    const apect_ratio = 16 / 9;
    const apect_ratio_threshold = 0.1;

    function scaleUi() {
        const { clientWidth, clientHeight } = document.documentElement;
        const current_ap = clientWidth / clientHeight;
        const root = document.documentElement;

        let scale;
        if (Math.abs(current_ap - apect_ratio) < apect_ratio_threshold) {
            scale = clientWidth / 100;
        } else {
            scale = Math.min(clientWidth / (100 * 1.6), clientHeight / (100 * 0.9));
        }

        // --- Cross-platform DPI Scaling ---
        const dpi = window.devicePixelRatio || 1;
        const effective_scale = scale / dpi;

        root.style.setProperty('--ui-scale', `${effective_scale * BASE_UI_SCALE}px`);
        root.style.setProperty('--font-scale', `${effective_scale * BASE_FONT_SCALE}px`);
    }

    scaleUi();

    // Rescale UI on window resize
    window.addEventListener('resize', scaleUi);

    const runBtn = document.getElementById('run-btn');
    const consoleOutput = document.getElementById('console');
    const dataSourceSelect = document.getElementById('data-source');
    const modelNameSelect = document.getElementById('model-name');
    const browseInputDirBtn = document.getElementById('browse-input-btn');
    const browseOutputDirBtn = document.getElementById('browse-output-btn');
    const helpBtn = document.getElementById('help-btn');
    const showExampleBtn = document.getElementById('show-example-btn');
    const zmaxOptions = document.getElementById('zmax-options');
    const selectChannelsBtn = document.getElementById('select-channels-btn');
    const zmaxModeRadios = document.querySelectorAll('input[name="zmax-mode"]');

    let logInterval;
    let statusInterval;

    // Handle Data Source change to update model list and show/hide ZMax options
    dataSourceSelect.addEventListener('change', () => {
        const selectedSource = dataSourceSelect.value;
        if (selectedSource.includes('PSG')) {
            modelNameSelect.innerHTML = '<option value="u-sleep-nsrr-2024" selected>u-sleep-nsrr-2024</option>';
            zmaxOptions.style.display = 'none';
        } else {
            modelNameSelect.innerHTML = `
                <option value="ez6" selected>ez6</option>
                <option value="ez6moe">ez6moe</option>
            `;
            zmaxOptions.style.display = 'block';
        }
    });

    // Trigger the change event on load to set the initial state
    dataSourceSelect.dispatchEvent(new Event('change'));

    // Handle ZMax mode change to show/hide the "Select Channels" button
    zmaxModeRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            if (radio.value === 'one_file' && radio.checked) {
                selectChannelsBtn.classList.add('visible');
                // Automatically pre-select channels when this option is chosen
                preselectDefaultChannels();
            } else {
                selectChannelsBtn.classList.remove('visible');
            }
        });
    });

    // Handle "Select Channels" button click
    selectChannelsBtn.addEventListener('click', async () => {
        const inputDir = document.getElementById('input-dir').value;
        if (!inputDir) {
            alert('Please select an input directory first.');
            return;
        }

        try {
            const response = await fetch('/get-channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_dir: inputDir })
            });

            const result = await response.json();

            if (response.ok) {
                openChannelSelectionModal(result.channels);
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
        const zmaxMode = document.querySelector('input[name="zmax-mode"]:checked').value;
        const payload = {
            input_dir: document.getElementById('input-dir').value,
            output_dir: document.getElementById('output-dir').value,
            data_source: dataSourceSelect.value,
            model_name: modelNameSelect.value,
            plot: document.getElementById('gen-plot').checked,
            gen_stats: document.getElementById('gen-stats').checked,
            score_subdirs: document.querySelector('input[name="scoring-mode"]:checked').value === 'subdirs',
            zmax_mode: zmaxMode,
            zmax_channels: zmaxMode === 'one_file' ? window.selectedChannels : null
        };

        if (!payload.input_dir || !payload.output_dir) {
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
    });

    // "Browse" button functionality
    const handleBrowseClick = async (targetInputId) => {
        try {
            const response = await fetch('/select-directory');
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                document.getElementById(targetInputId).value = result.path;
                if (targetInputId === 'input-dir') {
                    const outputDirInput = document.getElementById('output-dir');
                    if (!outputDirInput.value) {
                        outputDirInput.value = result.path + '/autoscorer_output';
                    }
                }
            } else if (result.status === 'cancelled') {
                console.log('Directory selection was cancelled.');
            } else {
                alert(`Error selecting directory: ${result.message}`);
            }
        } catch (error) {
            console.error('Failed to open directory dialog:', error);
            alert('An error occurred while trying to open the directory dialog.');
        }
    };

    browseInputDirBtn.addEventListener('click', () => handleBrowseClick('input-dir'));
    helpBtn.addEventListener('click', () => {
        window.open('/docs/manual.html', '_blank');
    });
    browseOutputDirBtn.addEventListener('click', () => handleBrowseClick('output-dir'));

    showExampleBtn.addEventListener('click', async () => {
        startPolling();

        try {
            const response = await fetch('/show-example', { method: 'POST' });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                document.getElementById('input-dir').value = result.path;
                document.getElementById('output-dir').value = result.path + '/autoscorer_output';
                document.querySelector('input[name="scoring-mode"][value="single"]').checked = true;
                
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


    // --- UI and Polling Functions ---

    function setRunningState(isRunning) {
        runBtn.disabled = isRunning;
        runBtn.textContent = isRunning ? 'Running...' : 'Run Scoring';
    }

    function startPolling() {
        if (logInterval) clearInterval(logInterval);
        if (statusInterval) clearInterval(statusInterval);

        logInterval = setInterval(fetchLogs, 1000); // Poll logs every second
        statusInterval = setInterval(checkStatus, 2000); // Check status every 2 seconds
    }

    function stopPolling() {
        clearInterval(logInterval);
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
            if (!data.is_running) {
                setRunningState(false);
                stopPolling();
                setTimeout(fetchLogs, 500);
            }
        } catch (error) {
            console.error('Error checking status:', error);
            setRunningState(false);
            stopPolling();
        }
    }

    const startupLogInterval = setInterval(async () => {
        const logText = await fetchLogs();
        if (logText.includes('Welcome to NIDRA')) {
            clearInterval(startupLogInterval);
        }
    }, 1000);

    checkStatus();

    // --- Ping Server ---
    const PING_INTERVAL = 2000; 

    async function pingServer() {
        try {
            await fetch('/ping', { method: 'POST' });
        } catch (error) {
            console.error('Ping failed:', error);
        }
    }

    setInterval(pingServer, PING_INTERVAL);
}

document.addEventListener('DOMContentLoaded', initializeApp);

function openChannelSelectionModal(channels) {
    // --- Create Modal Structure ---
    const modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'modal-backdrop';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';

    const h2 = document.createElement('h2');
    h2.textContent = 'Select Two Channels';
    modalContent.appendChild(h2);

    const form = document.createElement('form');
    const eegChannels = channels.filter(c => c.toLowerCase().includes('eeg'));
    let defaultSelected = 0;

    channels.forEach(channel => {
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = 'channel';
        checkbox.value = channel;

        // Pre-select up to two EEG channels
        if (eegChannels.includes(channel) && defaultSelected < 2) {
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
        const selectedChannels = Array.from(form.querySelectorAll('input[name="channel"]:checked'))
                                      .map(cb => cb.value);
        if (selectedChannels.length !== 2) {
            alert('Please select exactly two channels.');
        } else {
            window.selectedChannels = selectedChannels;
            console.log('Selected channels:', selectedChannels);
            closeModal();
        }
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
            body: JSON.stringify({ input_dir: inputDir })
        });

        const result = await response.json();

        if (response.ok) {
            const eegChannels = result.channels
                .filter(c => c.toLowerCase().includes('eeg'))
                .slice(0, 2);
            
            if (eegChannels.length === 2) {
                window.selectedChannels = eegChannels;
                console.log('Pre-selected channels:', eegChannels);
            } else {
                // Could not find two EEG channels, clear selection
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