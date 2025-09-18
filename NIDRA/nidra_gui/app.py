import sys
import os
from flask import Flask, render_template, request, jsonify
import threading
import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

# --- Path Setup ---
# --- Direct Import from Original, Working Code ---
# This is the most reliable way to ensure the scoring process works exactly as intended.
import time
from NIDRA import scorer as scorer_factory
from NIDRA.utils import setup_logging, compute_sleep_stats


# --- Setup ---
LOG_FILE = setup_logging()
logger = logging.getLogger(__name__)

# --- UI Text ---
TEXTS = {
    "WINDOW_TITLE": "NIDRA Sleep Autoscorer", "INPUT_TITLE": "Input Directory", "MODEL_TITLE": "Model",
    "OPTIONS_TITLE": "Options", "OPTIONS_PROBS": "Generate probabilities", "OPTIONS_PLOT": "Generate graph",
    "OPTIONS_STATS": "Generate sleep statistics", "OPTIONS_SCORE_SINGLE": "Score single recording",
    "OPTIONS_SCORE_SUBDIRS": "Score all recordings (in subfolders)", "DATA_SOURCE_TITLE": "Data Source",
    "DATA_SOURCE_FEE": "EEG wearable (e.g. ZMax)   ", "DATA_SOURCE_PSG": "full PSG (EEG, optional: EOG, EMG)   ",
    "OUTPUT_TITLE": "Output Directory", "RUN_BUTTON": "Run NIDRA autoscoring", "BROWSE_BUTTON": "Browse files...",
    "HELP_TITLE": "Help & Info (opens in browser)",
    "CONSOLE_INIT_MESSAGE": "Start by selecting a directory containing a sleep recording, or subfolders with one sleep recording each (Input Directory).",
}

# Determine the base path for resources, accommodating PyInstaller
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

template_folder = os.path.join(base_path, 'resources', 'templates')
static_folder = os.path.join(base_path, 'resources', 'static')

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

# Suppress noisy HTTP request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- Global State ---
is_scoring_running = False
worker_thread = None

# --- Flask Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html', texts=TEXTS)

@app.route('/select-directory')
def select_directory():
    """Opens a native directory selection dialog on the server."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        directory_path = filedialog.askdirectory(parent=root, title="Select Directory")
        root.destroy()
        if directory_path:
            return jsonify({'status': 'success', 'path': directory_path})
        return jsonify({'status': 'cancelled'})
    except Exception as e:
        logger.error(f"Error in directory dialog: {e}", exc_info=True)
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
    logger.info("\n" + "="*80 + "\nStarting new scoring process via Web UI...\n" + "="*80)

    # --- Direct Call to the Original Worker Function ---
    # We pass the parameters exactly as the original GUI would.
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

def scoring_thread_wrapper(input_dir, output_dir, score_subdirs, data_source, model_name, plot, gen_stats):
    """A wrapper to manage the global running state around the original function."""
    global is_scoring_running
    try:
        # The `cancel_event` is not used in the original GUI's threaded call, so we pass None.
        _run_scoring_worker(input_dir, output_dir, score_subdirs, None, data_source, model_name, plot, gen_stats)
    except Exception as e:
        logger.error(f"A critical error occurred in the scoring thread: {e}", exc_info=True)
    finally:
        is_scoring_running = False
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
                f"No recordings found in '{input_dir}', but subdirectories were detected.\n\n"
                "If your recordings are in separate subfolders, please select the 'Score all recordings (in subfolders)' option."
            )
        raise FileNotFoundError(f"Could not find any suitable recordings in '{input_dir}'. Please check the input directory and data source settings.")

    logger.info(f"Found {len(files_to_process)} recording(s) to process.")
    if score_subdirs and files_to_process:
        logger.info("The following recordings will be processed:")
        for file in files_to_process:
            logger.info(f"  - {file.parent.name}")
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
        logger.info(f">> SUCCESS: Finished processing {input_file.name} in {execution_time:.2f} seconds.")
        logger.info(f"  Results saved to: {output_dir}")
        return True
    except Exception as e:
        logger.error(f">> FAILED to process {input_file.name}: {e}", exc_info=True)
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
        logger.info(f"[{i+1}/{len(files_to_score)}] Processing: {file.parent.name}")
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

def _run_scoring_worker(input_dir, output_dir, score_subdirs, cancel_event, data_source, model_name, plot, gen_stats):
    try:
        files_to_score = _find_files_to_score(input_dir, data_source, score_subdirs)
        if score_subdirs:
            _run_batch_scoring(files_to_score, output_dir, data_source, model_name, gen_stats, plot)
        else:
            if files_to_score:
                logger.info("\n" + "-" * 80)
                logger.info(f"Processing: {files_to_score[0].name}")
                logger.info("-" * 80)
                _run_scoring(files_to_score[0], output_dir, data_source, model_name, gen_stats, plot)
    except (FileNotFoundError, ValueError) as e:
        # Catch specific, user-facing errors and log them cleanly without a traceback.
        logger.error(str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred during scoring: {e}", exc_info=True)


@app.route('/status')
def status():
    """Returns the current running status."""
    return jsonify({'is_running': is_scoring_running})

@app.route('/log')
def log_stream():
    """Streams the content of the log file."""
    try:
        if not LOG_FILE.exists():
            return ""
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        return f"Error reading log file: {e}"
