import sys
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import logging
from pathlib import Path
import importlib.resources
import platform

from NIDRA import scorer as scorer_factory
from NIDRA.utils import setup_logging, compute_sleep_stats, download_models, download_example_data, batch_scorer

# --- Setup ---
LOG_FILE, logger = setup_logging()

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
ping_interval = 2  # seconds
ping_timeout = 5  # seconds


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
    download_models(logger=logger)
    logger.info(TEXTS.get("CONSOLE_INIT_MESSAGE", "Welcome to NIDRA."))
    # if not _startup_check_done:
    #     def startup_task():
    #         """A wrapper to run startup tasks in the correct order."""
    #         logger.info("Checking if autoscoring model files are available...")
    #         download_models(logger=logger)
    #         logger.info(TEXTS.get("CONSOLE_INIT_MESSAGE", "Welcome to NIDRA."))

    #     threading.Thread(target=startup_task, daemon=True).start()
    #     _startup_check_done = True

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
    This function runs the dialog in a separate thread to avoid blocking the Flask server.
    """
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
            # On some systems (like Linux without a display server), tkinter can fail.
            logger.error(f"An error occurred in the tkinter dialog thread: {e}", exc_info=True)
            result['error'] = "Could not open the file dialog. Please ensure you have a graphical environment configured."
        finally:
            try:
                # This ensures the tkinter root window is always destroyed.
                root.destroy()
            except:
                pass

    dialog_thread = threading.Thread(target=open_dialog)
    dialog_thread.start()
    dialog_thread.join()

    if 'error' in result:
        return jsonify({'status': 'error', 'message': result['error']}), 500
    if 'path' in result:
        return jsonify({'status': 'success', 'path': result['path']})
    else:
        return jsonify({'status': 'cancelled'})

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

        # If running as a PyInstaller bundle, use local examples
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            example_data_path = Path(sys._MEIPASS) / 'examples' / 'test_data_zmax'
            if example_data_path.exists():
                logger.info(f"Using local example data from: {example_data_path}")
                return jsonify({'status': 'success', 'path': str(example_data_path)})
            else:
                logger.error(f"Could not find local example data folder at: {example_data_path}")
                return jsonify({'status': 'error', 'message': 'Could not find local example data.'}), 500
        else:
            # Otherwise, download it
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



def _run_scoring_worker(input_dir, output_dir, score_subdirs, cancel_event, data_source, model_name, plot, gen_stats):
    """
    Main worker function to find and score files.
    Returns a tuple of (number_of_files_successfully_processed, total_files_found).
    """
    try:
        scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
        if score_subdirs:
            batch = batch_scorer(
                input_dir=input_dir,
                output_dir=output_dir,
                scorer_type=scorer_type,
                model_name=model_name
            )
            return batch.score(plot=plot, gen_stats=gen_stats)
        else:
            # Logic for single scoring.
            logger.info(f"Searching for recordings in '{input_dir}'...")
            input_path = Path(input_dir)
            try:
                if scorer_type == 'psg':
                    input_file = next(input_path.glob('*.edf'))
                else:  # forehead
                    input_file = next(input_path.glob('*[lL].edf'))
                    next(input_path.glob('*[rR].edf')) # Verify R file exists
            except StopIteration:
                # Check if we are in single-file mode but subdirectories exist.
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
            success = _run_scoring(input_file, output_dir, data_source, model_name, gen_stats, plot)
            return (1, 1) if success else (0, 1)

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




