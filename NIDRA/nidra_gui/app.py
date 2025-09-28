import sys
from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import logging
from pathlib import Path
import importlib.resources
import platform
import os
import psutil

import time
from NIDRA import scorer as scorer_factory
from NIDRA.utils import setup_logging, compute_sleep_stats, download_models, download_example_data


# --- Setup ---
LOG_FILE, logger = setup_logging()




# --- UI Text ---
TEXTS = {
    "WINDOW_TITLE": "NIDRA", "INPUT_TITLE": "Input Folder", "MODEL_TITLE": "Model",
    "OPTIONS_TITLE": "Options", "OPTIONS_PROBS": "Generate probabilities", "OPTIONS_PLOT": "Generate graph",
    "OPTIONS_STATS": "Generate sleep statistics", "OPTIONS_SCORE_SINGLE": "Score single recording",
    "OPTIONS_SCORE_SUBDIRS": "Score all recordings (in subfolders)", "DATA_SOURCE_TITLE": "Data Source",
    "DATA_SOURCE_FEE": "EEG wearable (e.g. ZMax)   ", "DATA_SOURCE_PSG": "PSG (EEG/EOG)   ",
    "OUTPUT_TITLE": "Output Folder", "RUN_BUTTON": "Run autoscoring", "BROWSE_BUTTON": "Browse files...",
    "HELP_TITLE": "Help & Info (opens in browser)",
    "CONSOLE_INIT_MESSAGE": "\n\nWelcome to NIDRA, the easy to use sleep autoscorer.\n\nSpecify input folder (location of your sleep recordings) to begin.\n\nTo shutdown NIDRA, simply close this window or tab.",
}

# Determine the base path for resources, accommodating PyInstaller and standard installs
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running as a PyInstaller bundle
    base_path = Path(sys._MEIPASS)
    template_folder = str(base_path / 'neutralino' / 'resources' / 'templates')
    static_folder = str(base_path / 'neutralino' / 'resources' / 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    # Running as a standard Python package
    app = Flask(__name__, instance_relative_config=True)
    app.template_folder = str(Path(__file__).parent / 'neutralino' / 'resources' / 'templates')
    app.static_folder = str(Path(__file__).parent / 'neutralino' / 'resources' / 'static')

# Suppress noisy HTTP request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- Global State ---
is_scoring_running = False
worker_thread = None
_startup_check_done = False
last_ping = None
ping_thread = None
ping_interval = 2  # seconds
ping_timeout = 5  # seconds


# --- Flask Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    global _startup_check_done

    # The JavaScript will now fetch the log content on page load,
    # so we no longer need to construct a special initial message here.
    logger.info("-------------------------- System Information --------------------------")
    logger.info(f"OS: {platform.platform()}")
    logger.info(f"Python Version: {' '.join(sys.version.splitlines())}")
    logger.info(f"Python Environment: {sys.prefix}")
    logger.info(f"Running Directory: {Path.cwd()}")
    logger.info(f"Log File: {LOG_FILE}")
    logger.info(f"User Agent: {request.headers.get('User-Agent', 'N/A')}")
    logger.info("--------------------------------------------------------------------------\n")

    if not _startup_check_done:
        def startup_task():
            """A wrapper to run startup tasks in the correct order."""
            logger.info("Checking if autoscoring model files are available...")
            download_models(logger=logger)
            logger.info(TEXTS.get("CONSOLE_INIT_MESSAGE", "Welcome to NIDRA."))

        threading.Thread(target=startup_task, daemon=True).start()
        _startup_check_done = True

    return render_template('index.html', texts=TEXTS)

@app.route('/docs/<path:filename>')
def serve_docs(filename):
    """Serves files from the docs directory."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as a PyInstaller bundle
        docs_path = Path(sys._MEIPASS) / 'docs'
    else:
        # For a standard package, 'docs' is a resource within the 'docs' package
        # Note: This requires Python 3.9+ for `files()`
        docs_path = importlib.resources.files('docs')

    return send_from_directory(docs_path, filename)

@app.route('/select-directory')
def select_directory():
    """
    Opens a native directory selection dialog on the server.
    """
    try:
        import subprocess
        command = ['zenity', '--file-selection', '--directory']
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            path = result.stdout.strip()
            return jsonify({'status': 'success', 'path': path})
        else:
            return jsonify({'status': 'cancelled'})

    except FileNotFoundError:
        logger.error("zenity is not installed. Please install it to use the directory selection feature.")
        return jsonify({'status': 'error', 'message': 'zenity is not installed.'}), 500
    except Exception as e:
        logger.error(f"An unexpected error occurred in select_directory: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/start-scoring', methods=['POST'])
def start_scoring():
    """Starts the scoring process in a background thread."""
    global is_scoring_running, worker_thread

    if is_scoring_running:
        return jsonify({'status': 'error', 'message': 'Scoring is already in progress.'}), 409

    data = request.json
    required_keys = ['input_dir', 'output_dir', 'data_source', 'model_name', 'score_subdirs']
    if not all(key in data for key in required_keys):
        return jsonify({'status': 'error', 'message': 'Missing required parameters.'}), 400

    is_scoring_running = True
    logger.info("\n" + "="*80 + "\nStarting new scoring process on python backend...\n" + "="*80)

    # --- Direct Call to the Original Worker Function ---
    worker_thread = threading.Thread(
        target=scoring_thread_wrapper,
        args=(
            data['input_dir'],
            data['output_dir'],
            data['score_subdirs'],
            data['data_source'],
            data['model_name'],
            data.get('plot', False),
            data.get('gen_stats', False)
        )
    )
    worker_thread.start()
    return jsonify({'status': 'success', 'message': 'Scoring process initiated.'})


@app.route('/show-example', methods=['POST'])
def show_example():
    """Downloads example data and returns the path."""
    try:
        logger.info("\n--- Preparing scoring of example data ---")
        example_data_path = download_example_data(logger=logger)
        if example_data_path:
            logger.info(f"Example data is ready at: {example_data_path}")
            return jsonify({'status': 'success', 'path': example_data_path})
        else:
            logger.error("Failed to download or locate the example data.")
            return jsonify({'status': 'error', 'message': 'Could not download example data.'}), 500
    except Exception as e:
        logger.error(f"An error occurred while preparing the example: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

def scoring_thread_wrapper(input_dir, output_dir, score_subdirs, data_source, model_name, plot, gen_stats):
    """A wrapper to manage the global running state around the original function."""
    global is_scoring_running
    success_count, total_count = -1, -1
    try:
        success_count, total_count = _run_scoring_worker(
            input_dir, output_dir, score_subdirs, None, data_source, model_name, plot, gen_stats
        )
    except Exception as e:
        logger.error(f"A critical error occurred in the scoring thread: {e}", exc_info=True)
        success_count, total_count = 0, 0  # Assume failure
    finally:
        is_scoring_running = False
        if 0 < success_count < total_count:
            logger.info(f"Autoscoring completed with {total_count - success_count} failure(s): "
                        f"Successfully processed {success_count} of {total_count} recordings.")
        elif success_count == 0:
            logger.info("Autoscoring failed for all recordings.")

        # A total_count of -1 indicates an unexpected error before the worker could return.

        logger.info("\n" + "="*80 + "\nScoring process finished.\n" + "="*80)


def _find_files_to_score(input_dir, data_source, score_subdirs):
    """Finds EDF files to be scored and returns a list of file paths."""
    logger.info(f"Searching for recordings in '{input_dir}'...")
    files_to_process = []
    data_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'

    if score_subdirs:
        for subdir in sorted(Path(input_dir).iterdir()):
            if subdir.is_dir():
                try:
                    if data_type == 'psg':
                        file = next(subdir.glob('*.edf'))
                        files_to_process.append(file)
                    else:  # forehead
                        l_file = next(subdir.glob('*[lL].edf'))
                        next(subdir.glob('*[rR].edf'))  # Verify R file exists
                        files_to_process.append(l_file)
                except StopIteration:
                    logger.warning(f"Could not find a complete recording in subdirectory '{subdir.name}'. Skipping.")
                    continue
    else:  # single directory
        try:
            if data_type == 'psg':
                input_file = next(Path(input_dir).glob('*.edf'))
            else:  # forehead
                input_file = next(Path(input_dir).glob('*[lL].edf'))
            files_to_process.append(input_file)
        except StopIteration:
            pass  # Let the caller handle the empty list

    if not files_to_process:
        input_path = Path(input_dir)
        # Check if we are in single-file mode but subdirectories exist.
        if not score_subdirs and any(item.is_dir() for item in input_path.iterdir()):
            raise ValueError(
                f"No recordings found in '{input_dir}', but subdirectories were detected."
                "\n\n"
                "If your recordings are in separate subfolders, please select the 'Score all recordings (in subfolders)' option."
            )
        raise FileNotFoundError(f"Could not find any suitable recordings in '{input_dir}'. Please check the input directory and data source settings.")

    logger.info(f"Found {len(files_to_process)} recording(s) to process.")
    if score_subdirs and files_to_process:
        logger.info("The following recordings will be processed:")
        for file in files_to_process:
            logger.info(f"  - {file}")
    return files_to_process


def _run_scoring(input_file, output_dir, data_source, model_name, gen_stats, plot):
    """
    Performs scoring on a single recording file.
    """
    try:
        start_time = time.time()
        scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
        scorer = scorer_factory(
            scorer_type=scorer_type,
            input_file=str(input_file),
            output_dir=output_dir,
            model_name=model_name
        )
        
        hypnogram, probabilities = scorer.score(plot=plot)

        logger.info("Autoscoring completed.")

        if gen_stats:
            logger.info("Calculating sleep statistics...")
            try:
                stats = compute_sleep_stats(hypnogram.tolist())
                stats_output_path = Path(output_dir) / f"{input_file.parent.name}_{input_file.stem}_sleep_statistics.csv"
                with open(stats_output_path, 'w') as f:
                    f.write("Metric,Value\n")
                    for key, value in stats.items():
                        if isinstance(value, float):
                            f.write(f"{key},{value:.2f}\n")
                        else:
                            f.write(f"{key},{value}\n")
                logger.info(f"Sleep statistics saved.")
            except Exception as e:
                logger.error(f"Could not generate sleep statistics for {input_file.name}: {e}", exc_info=True)

        execution_time = time.time() - start_time
        logger.info(f">> SUCCESS: Finished processing {input_file} in {execution_time:.2f} seconds.")
        logger.info(f"  Results saved to: {output_dir}")
        return True
    except Exception as e:
        logger.error(f">> FAILED to process {input_file}: {e}", exc_info=True)
        return False


def _run_batch_scoring(files_to_score, output_dir, data_source, model_name, gen_stats, plot):
    """
    Runs scoring for a batch of files.
    """
    batch_start_time = time.time()
    batch_output_dir = Path(output_dir) / f"batch_run_{time.strftime('%Y%m%d_%H%M%S')}"
    batch_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("\n" + "-" * 80)
    logger.info(f"Starting batch processing.")
    logger.info(f"All results will be saved to: {batch_output_dir}")

    processed_count = 0
    for i, file in enumerate(files_to_score):
        logger.info("\n" + "-" * 80)
        logger.info(f"[{i+1}/{len(files_to_score)}] Processing: {file}")
        logger.info("-" * 80)
        if _run_scoring(file, str(batch_output_dir), data_source, model_name, gen_stats, plot):
            processed_count += 1

    total_execution_time = time.time() - batch_start_time
    logger.info("\n" + "-" * 80)
    logger.info("BATCH PROCESSING COMPLETE")
    logger.info(f"Successfully processed {processed_count} of {len(files_to_score)} recordings.")
    logger.info(f"Total execution time: {total_execution_time:.2f} seconds.")
    logger.info(f"All results saved in: {batch_output_dir}")
    logger.info("-" * 80)
    return processed_count, len(files_to_score)

def _run_scoring_worker(input_dir, output_dir, score_subdirs, cancel_event, data_source, model_name, plot, gen_stats):
    """
    Main worker function to find and score files.
    Returns a tuple of (number_of_files_successfully_processed, total_files_found).
    """
    try:
        files_to_score = _find_files_to_score(input_dir, data_source, score_subdirs)
        if score_subdirs:
            return _run_batch_scoring(files_to_score, output_dir, data_source, model_name, gen_stats, plot)
        else:
            if files_to_score:
                logger.info("\n" + "-" * 80)
                logger.info(f"Processing: {files_to_score[0]}")
                logger.info("-" * 80)
                success = _run_scoring(files_to_score[0], output_dir, data_source, model_name, gen_stats, plot)
                return (1, 1) if success else (0, 1)
            else:
                return 0, 0
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 0, 0
    except Exception as e:
        logger.error(f"An unexpected error occurred during scoring: {e}", exc_info=True)
        return 0, 0


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


@app.route('/ping', methods=['POST'])
def ping():
    """Resets the ping timer."""
    global last_ping
    last_ping = time.time()
    return jsonify({'status': 'ok'})


def check_ping(port):
    """Periodically checks if the frontend is still alive."""
    global last_ping
    while True:
        time.sleep(ping_interval)
        if last_ping and time.time() - last_ping > ping_timeout:
            logger.info("Frontend timeout. Shutting down server...")
            import requests
            try:
                requests.post(f"http://127.0.0.1:{port}/shutdown")
            except requests.exceptions.RequestException:
                pass # Server might already be down
            break


def shutdown_server():
    """Function to shut down the server."""
    try:
        parent = psutil.Process(os.getpid())
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
    except psutil.NoSuchProcess:
        pass

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shuts down the Flask server."""
    global is_scoring_running, worker_thread

    if is_scoring_running:
        logger.warning("Shutdown requested, but scoring is in progress. Waiting for it to complete.")
        if worker_thread:
            worker_thread.join()  # Wait for the scoring thread to finish

    logger.info("Server is shutting down...")
    shutdown_server()
    return 'Server shutting down...'


if __name__ == '__main__':
    last_ping = time.time()
    ping_thread = threading.Thread(target=check_ping, daemon=True)
    ping_thread.start()
    # TODO: randomize port
    app.run(host='127.0.0.1', port=5000)
