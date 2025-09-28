function initializeApp() {
    // --- Dynamic UI Scaling ---

    // Adjust these constants to fine-tune the UI's appearance.
    const BASE_UI_SCALE = 1.4; // Overall size of UI elements (padding, margins, etc.)
    const BASE_FONT_SCALE = 2.8; // Overall font size

    const apect_ratio = 16 / 9;
    const apect_ratio_threshold = 0.1;

    function scaleUi() {
        const { clientWidth, clientHeight } = document.documentElement;
        const current_ap = clientWidth / clientHeight;
        const root = document.documentElement;

        let scale;
        // If the aspect ratio is within a certain threshold of the target,
        // use a simpler scaling method to avoid distortion.
        if (Math.abs(current_ap - apect_ratio) < apect_ratio_threshold) {
            // Scale based on width when close to the target aspect ratio
            scale = clientWidth / 100;
        } else {
            // More robust scaling for other aspect ratios
            scale = Math.min(clientWidth / (100 * 1.6), clientHeight / (100 * 0.9));
        }

        // --- Cross-platform DPI Scaling ---
        // Adjust scaling based on the device's pixel ratio. This is crucial for
        // ensuring the UI looks consistent on high-DPI displays (like Apple's
        // Retina screens), especially on macOS where this can be an issue.
        const dpi = window.devicePixelRatio || 1;
        const effective_scale = scale / dpi;


        // Set the CSS variables for independent scaling
        root.style.setProperty('--ui-scale', `${effective_scale * BASE_UI_SCALE}px`);
        root.style.setProperty('--font-scale', `${effective_scale * BASE_FONT_SCALE}px`);
    }


    // Initial scaling
    scaleUi();

    // --- Event Listeners ---

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

    let logInterval;
    let statusInterval;

    // --- Event Listeners ---

    // Handle Data Source change to update model list
    dataSourceSelect.addEventListener('change', () => {
        const selectedSource = dataSourceSelect.value;
        // Assuming config.TEXTS is available globally via the template
        if (selectedSource.includes('PSG')) { // A bit brittle, but works with current text
            modelNameSelect.innerHTML = '<option value="u-sleep-nsrr-2024" selected>u-sleep-nsrr-2024</option>';
        } else {
            modelNameSelect.innerHTML = `
                <option value="ez6" selected>ez6</option>
                <option value="ez6moe">ez6moe</option>
            `;
        }
    });

    // Handle Run Button click
    runBtn.addEventListener('click', async () => {
        const payload = {
            input_dir: document.getElementById('input-dir').value,
            output_dir: document.getElementById('output-dir').value,
            data_source: dataSourceSelect.value,
            model_name: modelNameSelect.value,
            plot: document.getElementById('gen-plot').checked,
            gen_stats: document.getElementById('gen-stats').checked,
            score_subdirs: document.querySelector('input[name="scoring-mode"]:checked').value === 'subdirs'
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
                // Automatically set default output path when input is selected
                if (targetInputId === 'input-dir') {
                    const outputDirInput = document.getElementById('output-dir');
                    if (!outputDirInput.value) { // Only set if output is empty
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
        // Immediately start polling for logs to show download progress
        startPolling();
        // We don't set running state here, as the main scoring hasn't started yet.
        // The backend will log progress which will appear in the console.

        try {
            // This fetch will wait until the download on the backend is complete
            const response = await fetch('/show-example', { method: 'POST' });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                // Once download is complete, fill paths and click run
                document.getElementById('input-dir').value = result.path;
                document.getElementById('output-dir').value = result.path + '/autoscorer_output';
                document.querySelector('input[name="scoring-mode"][value="single"]').checked = true;
                
                // Now, click the run button to start the actual scoring process
                runBtn.click();
            } else {
                alert(`Error showing example: ${result.message}`);
                stopPolling(); // Stop polling on error
            }
        } catch (error) {
            console.error('Failed to run example:', error);
            alert('An error occurred while trying to run the example.');
            stopPolling(); // Stop polling on error
        }
    });


    // --- UI and Polling Functions ---

    function setRunningState(isRunning) {
        runBtn.disabled = isRunning;
        runBtn.textContent = isRunning ? 'Running...' : 'Run Scoring';
    }

    function startPolling() {
        // Clear any existing intervals
        if (logInterval) clearInterval(logInterval);
        if (statusInterval) clearInterval(statusInterval);

        // Start new polling
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
            return ""; // Return empty string on error to prevent breaking checks
        }
    }

    async function checkStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();
            if (!data.is_running) {
                setRunningState(false);
                stopPolling();
                // Final log fetch to ensure we have the latest output
                setTimeout(fetchLogs, 500);
            }
        } catch (error) {
            console.error('Error checking status:', error);
            // If status check fails, stop polling to avoid flooding with errors
            setRunningState(false);
            stopPolling();
        }
    }

    // --- Initial Load ---
    // Fetch the logs as soon as the page loads to display any startup messages
    // from the server, such as system info or model download status.
    // Poll for logs during startup to show model download progress.
    const startupLogInterval = setInterval(async () => {
        const logText = await fetchLogs();
        // Stop polling once the welcome message is visible, indicating startup is complete.
        if (logText.includes('Welcome to NIDRA')) {
            clearInterval(startupLogInterval);
        }
    }, 1000); // Poll every second

    // Also, check the status immediately in case a scoring task was somehow
    // running before the GUI was opened.
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

function onReady() {
    try {
        Neutralino.window.maximize();
    } catch (err) {
        // This will fail in browser mode, which is fine.
    }
    initializeApp();
}

Neutralino.init();
Neutralino.events.on('ready', onReady);