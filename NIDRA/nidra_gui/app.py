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

from NIDRA import scorer as scorer_factory
from NIDRA import utils

LOG_FILE, logger = utils.setup_logging()

TEXTS = {
    "WINDOW_TITLE": "NIDRA", "INPUT_TITLE": "Input Folder", "MODEL_TITLE": "Model",
    "OPTIONS_TITLE": "Options", "OPTIONS_PROBS": "Generate probabilities", "OPTIONS_PLOT": "Generate graph",
    "OPTIONS_STATS": "Generate sleep statistics", "OPTIONS_SCORE_SINGLE": "Score single recording",
    "OPTIONS_SCORE_SUBDIRS": "Score all recordings (in subfolders)", "DATA_SOURCE_TITLE": "Data Source",
    "DATA_SOURCE_FEE": "EEG wearable (e.g. ZMax)   ", "DATA_SOURCE_PSG": "PSG (EEG/EOG)   ",
    "OUTPUT_TITLE": "Output Folder", "RUN_BUTTON": "Run autoscoring", "BROWSE_BUTTON": "Browse files...",
    "HELP_TITLE": "Help & Info (opens in browser)",
    "CONSOLE_INIT_MESSAGE": "\n\nWelcome to NIDRA, the easy-to-use sleep autoscorer.\n\nSpecify input folder (location of your sleep recordings) to begin.\n\nTo shutdown NIDRA, simply close this window or tab.",
    "ZMAX_OPTIONS_2_FILES": "2 files per recording (e.g. EEG R.edf & EEG L.edf)",
    "ZMAX_OPTIONS_1_FILE": "1 file per recording (2+ channels)",
    "ZMAX_OPTIONS_SELECT_CHANNELS": "Select channels (optional)"
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
worker_thread = None
_startup_check_done = False
frontend_url = None
last_frontend_contact = None
probe_thread = None
frontend_grace_period = 2  # seconds (should be 60)


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

    logger.info("\nChecking if autoscoring model files are available...")
    utils.download_models(logger=logger)
    logger.info(TEXTS.get("CONSOLE_INIT_MESSAGE", "Welcome to NIDRA."))

    return render_template('index.html', texts=TEXTS)

@app.route('/docs/<path:filename>')
def serve_docs(filename):
    """Serves files from the docs directory."""
    return send_from_directory(app.docs_path, filename)

def _choose_folder_mac(prompt="Select a folder"):
    """Opens a folder selection dialog on macOS using AppleScript."""
    try:
        script = f'POSIX path of (choose folder with prompt "{prompt}")'
        out = subprocess.check_output(["osascript", "-e", script], text=True)
        return out.strip()
    except subprocess.CalledProcessError:  # User cancelled
        return None
    except Exception as e:
        logger.error(f"AppleScript folder selection failed: {e}", exc_info=True)
        return None

def _choose_file_mac(prompt="Select a file", file_type='txt'):
    """Opens a file selection dialog on macOS using AppleScript."""
    try:
        script = f'POSIX path of (choose file with prompt "{prompt}" of type {{"{file_type}"}})'
        out = subprocess.check_output(["osascript", "-e", script], text=True)
        return out.strip()
    except subprocess.CalledProcessError:  # User cancelled
        return None
    except Exception as e:
        logger.error(f"AppleScript file selection failed: {e}", exc_info=True)
        return None

@app.route('/select-directory')
def select_directory():
    """
    Opens a native directory selection dialog on the server.
    This function runs the dialog in a separate thread to avoid blocking the Flask server.
    On macOS, it uses a thread-safe AppleScript dialog.
    """
    if platform.system() == "Darwin":
        path = _choose_folder_mac(prompt="Select a Folder")
        if path:
            return jsonify({'status': 'success', 'path': path})
        else:
            return jsonify({'status': 'cancelled'})

    result = {}
    def open_dialog():
        import tkinter as tk
        from tkinter import filedialog
        try:
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            root.attributes('-topmost', True)  # Bring the dialog to the front
            path = filedialog.askdirectory(title="Select a Folder")
            if path:
                result['path'] = path
        except Exception as e:
            logger.error(f"An error occurred in the tkinter dialog thread: {e}", exc_info=True)
            result['error'] = "Could not open the file dialog. Please ensure you have a graphical environment configured."
        finally:
            if 'root' in locals() and root:
                root.destroy()

    dialog_thread = threading.Thread(target=open_dialog)
    dialog_thread.start()
    dialog_thread.join()

    if 'error' in result:
        return jsonify({'status': 'error', 'message': result['error']}), 500
    if 'path' in result:
        return jsonify({'status': 'success', 'path': result['path']})
    else:
        return jsonify({'status': 'cancelled'})

@app.route('/select-file')
def select_file():
    """
    Opens a native file selection dialog on the server, filtered for .txt files.
    This function runs the dialog in a separate thread to avoid blocking the Flask server.
    On macOS, it uses a thread-safe AppleScript dialog.
    """
    if platform.system() == "Darwin":
        path = _choose_file_mac(prompt="Select a .txt file with recording paths", file_type='txt')
        if path:
            return jsonify({'status': 'success', 'path': path})
        else:
            return jsonify({'status': 'cancelled'})

    result = {}
    def open_dialog():
        import tkinter as tk
        from tkinter import filedialog
        try:
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            root.attributes('-topmost', True)  # Bring the dialog to the front
            path = filedialog.askopenfilename(
                title="Select a .txt file with recording paths",
                filetypes=[("Text files", "*.txt")]
            )
            if path:
                result['path'] = path
        except Exception as e:
            logger.error(f"An error occurred in the tkinter dialog thread: {e}", exc_info=True)
            result['error'] = "Could not open the file dialog. Please ensure you have a graphical environment configured."
        finally:
            if 'root' in locals() and root:
                root.destroy()

    dialog_thread = threading.Thread(target=open_dialog)
    dialog_thread.start()
    dialog_thread.join()

    if 'error' in result:
        return jsonify({'status': 'error', 'message': result['error']}), 500
    if 'path' in result:
        return jsonify({'status': 'success', 'path': result['path']})
    else:
        return jsonify({'status': 'cancelled'})


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
                    path_str = line.split("Results saved to:", 1).strip()
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

@app.route('/start-scoring', methods=['POST'])
def start_scoring():
    """Starts the scoring process in a background thread."""
    global is_scoring_running, worker_thread

    if is_scoring_running:
        return jsonify({'status': 'error', 'message': 'Scoring is already in progress.'}), 409

    data = request.json
    required_keys = ['input_dir', 'output', 'data_source', 'model', 'score_subdirs']
    if not all(key in data for key in required_keys):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    is_scoring_running = True
    logger.info("\n" + "="*80 + "\nStarting new scoring process on python backend...\n" + "="*80)

    # call scorer
    worker_thread = threading.Thread(
        target=scoring_thread_wrapper,
        args=(
            data['input_dir'],
            data['output'],
            data.get('score_subdirs', False) or data.get('score_from_file', False),
            data['data_source'],
            data['model'],
            data.get('plot', False),
            data.get('probabilities', False),
            data.get('gen_stats', False),
            data.get('channels')
        )
    )
    worker_thread.start()
    return jsonify({'status': 'success', 'message': 'Scoring process initiated.'})


@app.route('/show-example', methods=['POST'])
def show_example():
    """Downloads example data and returns the path."""
    try:
        logger.info("\n--- Preparing scoring of example data ---")

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
            example_data_path = utils.download_example_data(logger=logger)
            if example_data_path:
                logger.info(f"Example data is ready at: {example_data_path}")
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
    Reads channel names from EDF files and determines the required channel selection mode
    based on the data source and file structure (e.g., for ZMax recordings).
    """
    data = request.json
    input_path_str = data.get('input_dir')
    data_source = data.get('data_source')

    if not input_path_str:
        return jsonify({'status': 'error', 'message': 'Input path not provided.'}), 400
    if not data_source:
        return jsonify({'status': 'error', 'message': 'Data source not provided.'}), 400

    try:
        input_path = Path(input_path_str)
        search_dir = None
        search_file = None

        if input_path.is_file() and input_path.suffix.lower() == '.txt':
            logger.info(f"Reading first path from text file: {input_path}")
            with open(input_path, 'r') as f:
                first_line = f.readline().strip()
            if not first_line:
                return jsonify({'status': 'error', 'message': 'The selected .txt file is empty.'}), 400
            first_target = Path(first_line)
            if first_target.is_dir():
                search_dir = first_target
            elif first_target.is_file():
                search_file = first_target
            else:
                return jsonify({'status': 'error', 'message': f'Path from .txt not found: {first_target}'}), 404
        else:
            # Allow either a directory or a direct EDF file path
            if input_path.is_dir():
                search_dir = input_path
            elif input_path.is_file():
                search_file = input_path
            else:
                return jsonify({'status': 'error', 'message': f'Invalid input path: {input_path}'}), 404

        if (search_dir is None and search_file is None):
            return jsonify({'status': 'error', 'message': 'No valid directory or file resolved from input.'}), 404

        scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
        selection_mode = 'psg'  # Default for PSG

        if scorer_type == 'forehead':
            # If the input resolves to a specific EDF file (from .txt or direct file path), decide mode from file.
            if search_file is not None:
                import re
                file_path = search_file
                file_str = str(file_path)
                # Detect two-file mode if filename indicates L/R and counterpart exists
                if re.search(r'(?i)([_ ])?L\.edf$', file_str):
                    r_file = Path(re.sub(r'(?i)([_ ])?L\.edf$', r'\1R.edf', file_str))
                    if r_file.exists():
                        selection_mode = 'zmax_two_files'
                        # Two-file mode: no channel selection needed
                        channels = []
                        return jsonify({'status': 'success', 'channels': channels, 'selection_mode': selection_mode})
                if re.search(r'(?i)([_ ])?R\.edf$', file_str):
                    l_file = Path(re.sub(r'(?i)([_ ])?R\.edf$', r'\1L.edf', file_str))
                    if l_file.exists():
                        selection_mode = 'zmax_two_files'
                        channels = []
                        return jsonify({'status': 'success', 'channels': channels, 'selection_mode': selection_mode})
                # Otherwise, treat as single-file ZMax (multi-channel)
                raw = mne.io.read_raw_edf(file_path, preload=False, verbose=False)
                channels = raw.ch_names
                selection_mode = 'zmax_one_file'
                return jsonify({'status': 'success', 'channels': channels, 'selection_mode': selection_mode})

            # Inspect only a single recording directory.
            # First try the selected directory (non-recursive). If it doesn't contain a single recording,
            # look for the first immediate subdirectory that does.
            def _dedup(paths):
                seen = set()
                out = []
                for p in paths:
                    key = str(p).lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(p)
                return out

            def _detect_zmax_in_dir(d: Path):
                l_files = sorted(d.glob('*[lL].edf'))
                r_files = sorted(d.glob('*[rR].edf'))
                all_edfs = sorted(d.glob('*.edf')) + sorted(d.glob('*.EDF'))

                # Deduplicate to avoid duplicates on case-insensitive filesystems
                all_edfs_loc = _dedup(all_edfs)
                l_files_loc = _dedup(l_files)
                r_files_loc = _dedup(r_files)

                # Detect single-file ZMax first: exactly one EDF in this folder (name may contain L/R)
                if len(all_edfs_loc) == 1:
                    raw = mne.io.read_raw_edf(all_edfs_loc[0], preload=False, verbose=False)
                    return 'zmax_one_file', raw.ch_names

                # Detect two-file ZMax: exactly one L and one R file
                if len(l_files_loc) == 1 and len(r_files_loc) == 1:
                    # Two-file mode: no channel selection in UI; one channel per EDF is assumed
                    return 'zmax_two_files', []

                return None, None

            selection_mode = None
            channels = None

            # Try selected directory first (non-recursive)
            selection_mode, channels = _detect_zmax_in_dir(search_dir)

            # If not determinable, try first immediate subdirectory with a determinable pattern
            if selection_mode is None:
                for sub in sorted(search_dir.iterdir()):
                    if sub.is_dir():
                        selection_mode, channels = _detect_zmax_in_dir(sub)
                        if selection_mode is not None:
                            break

            # If still not determinable, recursively search deeper subfolders for the first determinable recording
            if selection_mode is None:
                for sub in sorted(search_dir.rglob('*')):
                    if sub.is_dir():
                        selection_mode, channels = _detect_zmax_in_dir(sub)
                        if selection_mode is not None:
                            break

            if selection_mode is None:
                # Build counts only for the selected directory (not recursive) for a clear error
                l_top = list(search_dir.glob('*[lL].edf'))
                r_top = list(search_dir.glob('*[rR].edf'))
                all_top = list(search_dir.glob('*.edf')) + list(search_dir.glob('*.EDF'))
                non_lr_top = [f for f in all_top if f not in l_top and f not in r_top]
                message = (f'Could not determine ZMax recording type in {search_dir}. '
                           f'Found {len(l_top)} L-files, {len(r_top)} R-files, and {len(non_lr_top)} other EDF files in this folder. '
                           'If your recordings are in subfolders, please select one recording folder, '
                           'or choose "Score all recordings (in subfolders)"; channel selection uses a single recording.')
                return jsonify({'status': 'error', 'message': message}), 404

        else:  # For PSG, read the first available EDF from this folder or the first immediate subfolder
            if search_file is not None:
                raw = mne.io.read_raw_edf(search_file, preload=False, verbose=False)
                channels = raw.ch_names
                return jsonify({'status': 'success', 'channels': channels, 'selection_mode': selection_mode})
            edf_files = sorted(search_dir.glob('*.edf')) + sorted(search_dir.glob('*.EDF'))
            if not edf_files:
                # look into first immediate subdirectory that contains an EDF
                for sub in sorted(search_dir.iterdir()):
                    if sub.is_dir():
                        edf_files = sorted(sub.glob('*.edf')) + sorted(sub.glob('*.EDF'))
                        if edf_files:
                            break
            if not edf_files:
                return jsonify({'status': 'error', 'message': f'No EDF files found in {search_dir} or its immediate subfolders.'}), 404
            raw = mne.io.read_raw_edf(edf_files[0], preload=False, verbose=False)
            channels = raw.ch_names

        return jsonify({'status': 'success', 'channels': channels, 'selection_mode': selection_mode})

    except Exception as e:
        logger.error(f"Error reading channels from EDF file: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


# this enables reporting on successful/failed scorings
def scoring_thread_wrapper(input_dir, output, score_subdirs, data_source, model, plot, probabilities, gen_stats, channels=None):
    """
    Manages the global running state and executes the scoring process.
    This function is intended to be run in a separate thread.
    """
    global is_scoring_running
    success_count, total_count = 0, 0
    try:
        scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
        if score_subdirs:
            dir_list = None
            # If the input is a text file, read the directories from it
            if Path(input_dir).suffix.lower() == '.txt':
                try:
                    with open(input_dir, 'r') as f:
                        dir_list = [line.strip() for line in f if line.strip()]
                    logger.info(f"Found {len(dir_list)} directories to process from {input_dir}.")
                except Exception as e:
                    logger.error(f"Error reading directory list from {input_dir}: {e}", exc_info=True)
                    is_scoring_running = False
                    return

            batch = utils.batch_scorer(
                input_dir=input_dir,
                output=output,
                type=scorer_type,
                model=model,
                dir_list=dir_list,
                channels=channels,
                probabilities=probabilities,
                plot=plot
            )
            success_count, total_count = batch.score(gen_stats=gen_stats)
        else:
            # Logic for single scoring.
            logger.info(f"Looking for recordings in '{input_dir}'...")
            input_path = Path(input_dir)
            zmax_mode = None
            try:
                if scorer_type == 'psg':
                    input_file = next(input_path.glob('*.edf'))
                else:  # for zmax recordings, auto-detect
                    l_files = list(input_path.glob('*[lL].edf'))
                    r_files = list(input_path.glob('*[rR].edf'))
                    all_edfs = list(input_path.glob('*.edf'))

                    if len(l_files) == 1 and len(r_files) == 1:
                        zmax_mode = 'two_files'
                        input_file = l_files[0]
                    elif len(all_edfs) == 1:
                        zmax_mode = 'one_file'
                        input_file = all_edfs[0]
                    else:
                        raise StopIteration # Let the exception handling below deal with it

            except StopIteration:
                if any(item.is_dir() for item in input_path.iterdir()):
                    raise ValueError(
                        f"No recordings found in '{input_dir}', but subdirectories were detected."
                        "\n\n"
                        "If your recordings are in separate subfolders, please select the 'Score all recordings (in subfolders)' option."
                    )
                raise FileNotFoundError(f"Could not find any suitable recordings in '{input_dir}'. Please check the input directory and data source settings.")

            logger.info("\n" + "-" * 80)
            logger.info(f"Processing: {input_file}")
            logger.info("-" * 80)
            total_count = 1
            if _run_scoring(input_file, output, data_source, model, gen_stats, plot, probabilities, zmax_mode, channels):
                success_count = 1

    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
    except Exception as e:
        logger.error(f"A critical error occurred in the scoring thread: {e}", exc_info=True)
    finally:
        is_scoring_running = False
        if total_count > 0:
            if success_count == total_count:
                logger.info(f"Successfully processed {total_count} recording(s).")
            elif 0 < success_count < total_count:
                logger.info(f"Autoscoring completed with {total_count - success_count} failure(s): "
                            f"Successfully processed {success_count} of {total_count} recording(s).")
            elif success_count == 0:
                logger.info("Autoscoring failed for all recordings.")

        logger.info("\n" + "="*80 + "\nScoring process finished.\n" + "="*80)

def _run_scoring(input, output, data_source, model, gen_stats, plot, probabilities, zmax_mode=None, channels=None):
    """
    Performs scoring on a single recording file.
    """
    if channels:
        logger.info(f"Using custom channel selection: {channels}")
    try:
        start_time = time.time()
        scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
        
        scorer_kwargs = {
            'input': str(input),
            'output': output,
            'model': model,
            'channels': channels,
            'probabilities': probabilities,
            'plot': plot
        }
        if scorer_type == 'forehead':
            scorer_kwargs['zmax_mode'] = zmax_mode

        scorer = scorer_factory(type=scorer_type, **scorer_kwargs)
        
        hypnogram, probabilities = scorer.score()

        if gen_stats:
            logger.info("Calculating sleep statistics...")
            try:
                stats = utils.compute_sleep_stats(hypnogram.tolist())
                stats_output_path = Path(output) / f"{input.parent.name}_{input.stem}_sleep_statistics.csv"
                with open(stats_output_path, 'w') as f:
                    f.write("Metric,Value\n")
                    for key, value in stats.items():
                        if isinstance(value, float):
                            f.write(f"{key},{value:.2f}\n")
                        else:
                            f.write(f"{key},{value}\n")
                logger.info(f"Sleep statistics saved.")
            except Exception as e:
                logger.error(f"Could not generate sleep statistics for {input.name}: {e}", exc_info=True)
        
        logger.info("Autoscoring process completed.")

        execution_time = time.time() - start_time
        logger.info(f">> SUCCESS: Finished processing {input.name} in {execution_time:.2f} seconds.")
        logger.info(f"  Results saved to: {output}")
        return True
    except Exception as e:
        logger.error(f">> FAILED to process {input.name}: {e}", exc_info=True)
        return False


@app.route('/status')
def status():
    """Returns the current running status."""
    return jsonify({'is_running': is_scoring_running})

@app.route('/log')
def log_stream():
    """Streams the content of the log file."""
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
    # logger.info("Starting frontend probe loop...")

    while True:
        if frontend_url and last_frontend_contact:
            try:
                # The frontend doesn't need to respond to this, we just need to see if the server is up.
                # A simple HEAD request is lighter than GET.
                requests.head(f"{frontend_url}/alive-ping", timeout=3)
                last_frontend_contact = time.time()
            except requests.exceptions.RequestException:
                # If the probe fails, we don't update last_frontend_contact.
                pass

            if time.time() - last_frontend_contact > frontend_grace_period:
                logger.warning(f"Frontend has been unresponsive for {frontend_grace_period} seconds. Shutting down backend.")
                os._exit(0)

        time.sleep(5) # Probe every 5 seconds


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
    # logger.info(f"Frontend registered from URL: {frontend_url}")

    if probe_thread is None:
        probe_thread = threading.Thread(target=probe_frontend_loop, daemon=True)
        probe_thread.start()

    return jsonify({'status': 'success'})


@app.route('/goodbye', methods=['POST'])
def goodbye():
    """
    Provides a way for the frontend to signal a clean shutdown.
    """
    logger.info("Received /goodbye signal from frontend. Shutting down in 0.3 seconds.")
    # Short delay to allow the beacon to be sent successfully
    threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0))).start()
    return jsonify({'status': 'ok'})


@app.route('/alive-ping')
def alive_ping():
    """A lightweight endpoint for the backend to probe itself to see if the frontend is still responsive."""
    return jsonify({'status': 'ok'})
