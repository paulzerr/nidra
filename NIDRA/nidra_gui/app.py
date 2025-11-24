import sys
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import logging
from pathlib import Path
import importlib.resources
import platform
import os
import subprocess
import mne
import requests

from NIDRA import utils

LOG_FILE, logger = utils.setup_logging()

TEXTS = {
    "WINDOW_TITLE": "NIDRA", "INPUT_TITLE": "Input sleep recordings", "MODEL_TITLE": "Model",
    "OPTIONS_TITLE": "Options", "OPTIONS_PROBS": "Generate hypnodensity", "OPTIONS_PLOT": "Generate graph",
    "OPTIONS_STATS": "Generate sleep statistics",
    "DATA_SOURCE_TITLE": "Data Source",
    "DATA_SOURCE_FEE": "EEG wearable (e.g. ZMax)   ", "DATA_SOURCE_PSG": "PSG (EEG/EOG)   ",
    "OUTPUT_TITLE": "Output location", "RUN_BUTTON": "Run autoscoring",
    "SELECT_INPUT_FILE_BUTTON": "Select input file", "SELECT_INPUT_FOLDER_BUTTON": "Select input folder",
    "BROWSE_BUTTON": "Select output folder",
    "CANCEL_BUTTON": "Cancel autoscoring",
    "INPUT_PLACEHOLDER": "Select a recording, a folder containing recordings, or a .txt file containing paths...",
    "OUTPUT_PLACEHOLDER": "Select where to save results...",
    "HELP_TITLE": "Help & Info (opens in browser)",
    "CONSOLE_INIT_MESSAGE": "\n\nWelcome to NIDRA, the easy-to-use sleep autoscorer.\n\nSelect your sleep recordings to begin.\n\nTo shutdown NIDRA, simply close this window or tab.",

}

# setup resource paths
base_path, is_bundle = utils.get_app_dir()
if is_bundle:
    docs_path = base_path / 'docs'
    instance_relative = False
else:
    docs_path = importlib.resources.files('docs')
    instance_relative = True
    base_path = Path(__file__).parent
template_folder = str(base_path / 'neutralino' / 'resources' / 'templates')
static_folder = str(base_path / 'neutralino' / 'resources' / 'static')
# start flask server
app = Flask(
    __name__, 
    instance_relative_config=instance_relative,
    template_folder=template_folder, 
    static_folder=static_folder
)
app.docs_path = docs_path


# suppress noisy HTTP request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- Global State ---
is_scoring_running = False
is_cancelling = False # to give user feedback that cancellation is in progress
worker_thread = None
cancel_event = threading.Event()
_startup_check_done = False
frontend_url = None
last_frontend_contact = None
probe_thread = None
frontend_grace_period = 60  # seconds

dialog_lock = threading.Lock()

# --- Flask Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    global _startup_check_done

    logger.info("-------------------------- System Information --------------------------")
    logger.info(f"OS: {platform.platform()}")
    logger.info(f"Python Version: {' '.join(sys.version.splitlines())}")
    logger.info(f"Python Environment: {sys.prefix}")
    logger.info(f"Running Directory: {Path.cwd()}")
    logger.info(f"Log File: {LOG_FILE}")
    logger.info(f"User Agent: {request.headers.get('User-Agent', 'N/A')}")
    logger.info("--------------------------------------------------------------------------\n")

    logger.info("\n" + "="*80)
    logger.info("Welcome to NIDRA, the easy-to-use sleep autoscorer.\nSelect your sleep recordings to begin.\nTo shutdown NIDRA, simply close this window or tab.")
    logger.info("="*80 + "\n")
    if not _startup_check_done:
        _startup_check_done = True
        threading.Thread(
            target=utils.download_assets,
            args=("models", logger),
            daemon=True
        ).start()
    return render_template('index.html', texts=TEXTS)

@app.route('/docs/<path:filename>')
def serve_docs(filename):
    """Serves files from the docs directory."""
    return send_from_directory(app.docs_path, filename)

def _open_native_dialog_mac(mode, prompt, file_types=None):
    """
    Opens a native file or folder selection dialog on macOS using AppleScript.
    This approach is thread-safe and avoids issues with tkinter in macOS bundles.
    """
    if not dialog_lock.acquire(blocking=False):
        logger.warning("Dialog blocked because another is already open.")
        return {'status': 'error', 'message': 'Another file dialog is already open.'}

    try:
        if mode == 'folder':
            script = f'POSIX path of (choose folder with prompt "{prompt}")'
        elif mode == 'file':
            if file_types:
                type_str = "of type {" + ", ".join(f'"{t}"' for t in file_types) + "}"
                script = f'POSIX path of (choose file with prompt "{prompt}" {type_str})'
            else:
                script = f'POSIX path of (choose file with prompt "{prompt}")'
        else:
            raise ValueError(f"Invalid dialog mode: {mode}")

        out = subprocess.check_output(["osascript", "-e", script], text=True)
        path = out.strip()
        if path:
            return {'status': 'success', 'path': path}
        else:
            return {'status': 'cancelled'}
    except subprocess.CalledProcessError:  # User cancelled
        return {'status': 'cancelled'}
    except Exception as e:
        logger.error(f"AppleScript dialog failed (mode: {mode}): {e}", exc_info=True)
        return {'status': 'error', 'message': 'Could not open the dialog.'}
    finally:
        if dialog_lock.locked():
            dialog_lock.release()

def _open_native_dialog(mode, title, file_types=None):
    if platform.system() == "Darwin":
        mac_file_types = None
        if file_types:
            # Convert tkinter-style file types to a simple list of extensions for AppleScript
            mac_file_types = []
            for _, patterns in file_types:
                mac_file_types.extend(p.split('.')[-1] for p in patterns.split())
        
        result = _open_native_dialog_mac(
            mode=mode,
            prompt=title,
            file_types=mac_file_types
        )
        if result.get('status') == 'error':
            return jsonify(result), 409
        return jsonify(result)

    # For other systems (Windows, Linux), use tkinter in a separate thread.
    if not dialog_lock.acquire(blocking=False):
        logger.warning("File dialog blocked because another is already open.")
        return jsonify({'status': 'error', 'message': 'Another file dialog is already open.'}), 409

    try:
        result = {}
        def open_dialog_thread():
            import tkinter as tk
            from tkinter import filedialog
            try:
                root = tk.Tk()
                root.withdraw()  # Hide the main window
                root.attributes('-topmost', True)  # Bring the dialog to the front

                path = None
                if mode == 'folder':
                    path = filedialog.askdirectory(title=title)
                elif mode == 'file':
                    path = filedialog.askopenfilename(title=title, filetypes=file_types)

                if path:
                    result['path'] = path
            except Exception as e:
                logger.error(f"An error occurred in the tkinter dialog thread: {e}", exc_info=True)
                result['error'] = "Could not open the file dialog. Please ensure you have a graphical environment configured."
            finally:
                if 'root' in locals() and root:
                    root.destroy()

        dialog_thread = threading.Thread(target=open_dialog_thread)
        dialog_thread.start()
        dialog_thread.join()

        if 'error' in result:
            return jsonify({'status': 'error', 'message': result['error']}), 500
        if 'path' in result:
            return jsonify({'status': 'success', 'path': result['path']})
        else:
            return jsonify({'status': 'cancelled'})
    finally:
        if dialog_lock.locked():
            dialog_lock.release()

@app.route('/select-directory')
def select_directory():
    """Opens a native directory selection dialog."""
    return _open_native_dialog(mode='folder', title="Select a Folder")


@app.route('/select-input-file')
def select_input_file():
    """
    Opens a native file selection dialog for input files.
    Supports .edf, .bdf, and .txt files.
    """
    file_types_supported = [
        ("Supported Files", "*.edf *.bdf *.txt"),
    ]
    return _open_native_dialog(
        mode='file',
        title="Select an input file",
        file_types=file_types_supported
    )

@app.route('/start-scoring', methods=['POST'])
def start_scoring():
    """Starts the scoring process in a background thread."""
    global is_scoring_running, worker_thread, cancel_event, is_cancelling

    if is_scoring_running:
        return jsonify({'status': 'error', 'message': 'Scoring is already in progress.'}), 409

    data = request.json
    required_keys = ['input_dir', 'output', 'data_source', 'model', 'score_subdirs']
    if not all(key in data for key in required_keys):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    is_scoring_running = True
    is_cancelling = False
    cancel_event.clear()
    logger.info("\n" + "=" * 80 + "\nStarting new scoring process on python backend...\n" + "=" * 80)

    def _run_scoring(config, cancel_event_obj):
        """The actual scoring logic that runs in a separate thread."""
        global is_scoring_running, is_cancelling
        try:
            scorer_type = 'psg' if config['data_source'] == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
            batch = utils.batch_scorer(
                input=config['input_dir'],
                output=config['output'],
                type=scorer_type,
                model=config['model'],
                channels=config.get('channels'),
                hypnodensity=config.get('hypnodensity', False),
                plot=config.get('plot', False),
                cancel_event=cancel_event_obj
            )
            batch.score()

        except Exception as e:
            logger.error(f"A critical error occurred in the scoring thread: {e}", exc_info=True)
        finally:
            is_scoring_running = False
            is_cancelling = False

    worker_thread = threading.Thread(
        target=_run_scoring,
        args=(data, cancel_event)
    )
    worker_thread.start()
    return jsonify({'status': 'success', 'message': 'Scoring process initiated.'})



@app.route('/cancel-scoring', methods=['POST'])
def cancel_scoring():
    """Signals the scoring process to cancel."""
    global is_scoring_running, cancel_event, is_cancelling
    if is_scoring_running:
        is_cancelling = True
        cancel_event.set()
        logger.info("Cancellation request received. Scoring will stop after the current file.")
        return jsonify({'status': 'success', 'message': 'Cancellation requested.'})
    else:
        return jsonify({'status': 'error', 'message': 'No scoring process is running.'}), 409


@app.route('/open-recent-results', methods=['POST'])
def open_recent_results():
    """Finds the most recent output folder from the log and opens it."""
    try:
        if not LOG_FILE.exists():
            return jsonify({'status': 'error', 'message': 'Log file not found.'}), 404

        last_output_dir = None
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "Results saved to:" in line:
                    # Extract the path after the colon and strip whitespace
                    path_str = line.split("Results saved to:", 1)[1].strip()
                    last_output_dir = Path(path_str)

        if last_output_dir and last_output_dir.exists():
            logger.info(f"Opening recent results folder: {last_output_dir}")
            if platform.system() == "Windows":
                os.startfile(last_output_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", last_output_dir])
            else:  # Linux and other UNIX-like systems
                subprocess.run(["xdg-open", last_output_dir])
            return jsonify({'status': 'success', 'message': f'Opened folder: {last_output_dir}'})
        elif last_output_dir:
            logger.error(f"Could not open recent results folder because it does not exist: {last_output_dir}")
            return jsonify({'status': 'error', 'message': f'The most recent results folder does not exist:\n{last_output_dir}'}), 404
        else:
            logger.warning("Could not find a recent results folder in the log file.")
            return jsonify({'status': 'error', 'message': 'No recent results folder found in the log.'}), 404

    except Exception as e:
        logger.error(f"An error occurred while trying to open the recent results folder: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred.'}), 500


@app.route('/show-example', methods=['POST'])
def show_example():
    """Downloads example data and returns the path."""
    try:
        # If running as a PyInstaller bundle, use local examples
        app_dir, is_bundle = utils.get_app_dir()
        if is_bundle:
            example_data_path = app_dir / 'examples' / 'test_data_zmax'
            if example_data_path.exists():
                logger.info(f"Using local example data from: {example_data_path}")
                return jsonify({'status': 'success', 'path': str(example_data_path)})
            else:
                logger.error(f"Could not find local example data folder at: {example_data_path}")
                return jsonify({'status': 'error', 'message': 'Could not find local example data.'}), 500
        else:
            # Otherwise, download it
            example_data_path = utils.download_assets("example_data",logger)
            if example_data_path:
                return jsonify({'status': 'success', 'path': example_data_path})
            else:
                logger.error("Failed to download or locate the example data.")
                return jsonify({'status': 'error', 'message': 'Could not download example data.'}), 500

    except Exception as e:
        logger.error(f"An error occurred while preparing the example: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/get-channels', methods=['POST'])
def get_channels():
    """
    Reads channel names from the first available EDF file and determines the
    required channel selection mode.
    """
    data = request.json
    input_path_str = data.get('input_dir')
    data_source = data.get('data_source')

    if not input_path_str:
        return jsonify({'status': 'error', 'message': 'Input path not provided.'}), 400
    if not data_source:
        return jsonify({'status': 'error', 'message': 'Data source not provided.'}), 400

    try:
        # Use utils.find_files to get a list of all EDFs.
        # It handles .txt files, directories, and single files recursively.
        files_to_process, _ = utils.find_files(input_path_str)

        if not files_to_process:
            return jsonify({'status': 'error', 'message': f'No sleep recordings (.edf, .bdf) found for input: {input_path_str}'}), 404

        first_file = files_to_process[0]
        scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
        selection_mode = 'psg'  # Default
        channels = []
        dialog_text = ""
        mode_hint = ""
        warning_hint = ""

        if scorer_type == 'forehead':
            import re
            file_str = str(first_file)
            # Check for L/R pair to determine if it's two-file ZMax
            if re.search(r'(?i)[_ ]?L\.edf$', file_str):
                r_file_str = re.sub(r'(?i)([_ ]?)L\.edf$', r'\1R.edf', file_str)
                if Path(r_file_str).exists():
                    selection_mode = 'zmax_two_files'
                else:  # It's an L file but no R file, treat as one file
                    selection_mode = 'zmax_one_file'
            else:  # Not an L file, so must be single file mode
                selection_mode = 'zmax_one_file'
        
        # Set hints based on the determined mode
        if selection_mode == 'zmax_one_file':
            mode_hint = "For single-file ZMax, please select exactly two channels."
        elif selection_mode == 'zmax_two_files':
            mode_hint = "Two-file ZMax recording (L/R) detected. No channel selection is required as one channel per file is assumed."

        # Set warning hint if multiple files are being processed and selection is relevant
        if len(files_to_process) > 1:
            warning_hint = "Channels are based on the first recording found. All other recordings in this batch are assumed to have the same channels."
        
        # Combine hints in the correct order with a blank line between them, if both exist
        dialog_parts = [p for p in [mode_hint, warning_hint] if p]
        dialog_text = "<br><br>".join(dialog_parts)

        # For PSG or single-file ZMax, we need to read the channels from the first file.
        if selection_mode in ['psg', 'zmax_one_file']:
            try:
                raw = mne.io.read_raw_edf(first_file, preload=False, verbose=False)
                channels = raw.ch_names
            except Exception as e:
                logger.error(f"Could not read channels from {first_file}: {e}", exc_info=True)
                return jsonify({'status': 'error', 'message': f'Error reading file: {first_file.name}\n{e}'}), 500

        return jsonify({
            'status': 'success',
            'channels': channels,
            'selection_mode': selection_mode,
            'dialog_text': dialog_text
        })

    except Exception as e:
        logger.error(f"Error determining channels: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/log-channel-selection', methods=['POST'])
def log_channel_selection():
    """Logs the user-selected channels."""
    data = request.json
    channels = data.get('channels')
    if channels:
        logger.info(f"Manually selected channels: {', '.join(channels)}")
    return jsonify({'status': 'success'})

@app.route('/status')
def status():
    return jsonify({'is_running': is_scoring_running, 'is_cancelling': is_cancelling})


@app.route('/log')
def log_stream():
    try:
        if not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0:
            return TEXTS["CONSOLE_INIT_MESSAGE"]
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        return f"Error reading log file: {e}"


# heartbeat to ensure NIDRA is shutdown when tab is closed (ping disappears).
def probe_frontend_loop():
    """
    Periodically probes the frontend to ensure it's still alive.
    If the frontend is unresponsive for a grace period, the backend shuts down.
    """
    global last_frontend_contact
    while True:
        if frontend_url and last_frontend_contact:
            try:
                # The frontend doesn't need to respond to this, we just need to see if the server is up.
                requests.head(f"{frontend_url}/alive-ping", timeout=3)
                last_frontend_contact = time.time()
            except requests.exceptions.RequestException:
                # If the probe fails, we don't update last_frontend_contact.
                pass

            if time.time() - last_frontend_contact > frontend_grace_period:
                logger.warning(f"Frontend has been unresponsive for {frontend_grace_period} seconds. Shutting down backend.")
                os._exit(0)

        time.sleep(5)

@app.route('/alive-ping')
def alive_ping():
    return jsonify({'status': 'ok'})

@app.route('/goodbye', methods=['POST'])
def goodbye():
    logger.info("Received /goodbye signal from frontend. Shutting down.")
    threading.Thread(target=lambda: (time.sleep(1), os._exit(0))).start()
    return jsonify({'status': 'ok'})

@app.route('/register', methods=['POST'])
def register_frontend():
    """
    Receives the frontend's URL and starts the monitoring thread.
    """
    global frontend_url, last_frontend_contact, probe_thread
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'URL not provided'}), 400

    frontend_url = url
    last_frontend_contact = time.time()
    if probe_thread is None:
        probe_thread = threading.Thread(target=probe_frontend_loop, daemon=True)
        probe_thread.start()

    return jsonify({'status': 'success'})

