import re
import os
import sys
import numpy as np
from typing import List
import logging
import time
import tempfile
from pathlib import Path
from datetime import datetime
from huggingface_hub import hf_hub_download, hf_hub_url
from appdirs import user_data_dir
import requests
import importlib.util
import NIDRA

logger = logging.getLogger(__name__)

class BatchScorer:
    """
    A class to handle batch scoring of a study directory.
    It finds all valid recordings in subdirectories and scores them in a single run.
    """
    def __init__(self, input_dir, output_dir=None, scorer_type=None, model_name=None, dir_list=None, zmax_mode=None):
        self.input_dir = Path(input_dir) if input_dir else None

        # Default output_dir to input_dir if not provided
        if output_dir is None:
            if self.input_dir is not None:
                self.output_dir = self.input_dir
                logger.info(f"No output_dir specified. Using input_dir as output_dir: {self.output_dir}")
            else:
                raise ValueError("output_dir must be specified when input_dir is not provided.")
        else:
            self.output_dir = Path(output_dir)

        self.scorer_type = scorer_type
        if self.scorer_type is None:
            raise ValueError("scorer_type must be specified: 'forehead' or 'psg'.")
        self.model_name = model_name
        self.dir_list = dir_list
        self.zmax_mode = zmax_mode
        self.files_to_process = self._find_files()

    def _find_files(self):
        """Finds all valid recording files in the input directory."""
        if self.dir_list:
            logger.info(f"Searching for recordings in {len(self.dir_list)} specified directories...")
            dirs_to_search = [Path(d) for d in self.dir_list]
        else:
            logger.info(f"Searching for recordings in '{self.input_dir}'...")
            # Exclude NIDRA-generated batch output folders to avoid spurious scans
            dirs_to_search = [
                subdir for subdir in sorted(self.input_dir.iterdir())
                if subdir.is_dir() and not subdir.name.startswith('batch_run_')
            ]

        files = []
        for subdir in dirs_to_search:
            if not subdir.is_dir():
                logger.warning(f"'{subdir}' is not a directory. Skipping.")
                continue
            try:
                if self.scorer_type == 'psg':
                    file = next(subdir.glob('*.edf'))
                    files.append(file)
                else:  # 'forehead'
                    # Default to 'two_files' if zmax_mode is not provided, to maintain old behavior
                    if self.zmax_mode in [None, 'two_files']:
                        l_file = next(subdir.glob('*[lL].edf'))
                        next(subdir.glob('*[rR].edf'))  # Verify R file exists
                        files.append(l_file)
                    else:  # 'one_file'
                        file = next(subdir.glob('*.edf'))
                        files.append(file)
            except StopIteration:
                logger.warning(f"Could not find a complete recording in subdirectory '{subdir}'. Skipping.")
                continue
        
        if not files:
            if self.dir_list:
                logger.warning(f"Could not find any suitable recordings in the provided list of directories.")
            else:
                logger.warning(f"Could not find any suitable recordings in subdirectories of '{self.input_dir}'.")
        else:
            logger.info(f"Found {len(files)} recording(s) to process.")
            logger.info("The following recordings will be processed:")
            for file in files:
                logger.info(f"  - {file}")
        return files

    def score(self, plot=True, gen_stats=True):
        """
        Runs the scoring process for all found recordings.
        Args:
            plot (bool): Generate a dashboard plot for each recording.
            gen_stats (bool): Generate sleep statistics for each recording.
        Returns:
            tuple: A tuple containing (number_of_files_successfully_processed, total_files_found).
        """
        if not self.files_to_process:
            return 0, 0

        batch_start_time = time.time()
        batch_output_dir = self.output_dir / f"batch_run_{time.strftime('%Y%m%d_%H%M%S')}"
        batch_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("\n" + "-" * 80)
        logger.info(f"Starting batch processing. Results will be saved to: {batch_output_dir}")

        processed_count = 0
        for i, file in enumerate(self.files_to_process):
            logger.info("\n" + "-" * 80)
            logger.info(f"[{i + 1}/{len(self.files_to_process)}] Processing: {file}")
            logger.info("-" * 80)
            
            recording_output_dir = batch_output_dir / file.parent.name
            recording_output_dir.mkdir(exist_ok=True)

            try:
                start_time = time.time()
                scorer = NIDRA.scorer(
                    scorer_type=self.scorer_type,
                    input_file=str(file),
                    output_dir=str(recording_output_dir),
                    model_name=self.model_name,
                    zmax_mode=self.zmax_mode
                )
                hypnogram, _ = scorer.score(plot=plot)
                logger.info("Autoscoring completed.")
                
                if gen_stats:
                    logger.info("Calculating sleep statistics...")
                    stats = compute_sleep_stats(hypnogram.tolist())
                    stats_output_path = recording_output_dir / f"{file.stem}_sleep_statistics.csv"
                    with open(stats_output_path, 'w') as f:
                        f.write("Metric,Value\n")
                        for key, value in stats.items():
                            f.write(f"{key},{value:.2f}\n" if isinstance(value, float) else f"{key},{value}\n")
                    logger.info(f"Sleep statistics saved to {stats_output_path}")

                execution_time = time.time() - start_time
                logger.info(f">> SUCCESS: Finished processing {file} in {execution_time:.2f} seconds.")
                logger.info(f"  Results saved to: {recording_output_dir}")
                processed_count += 1
            except Exception as e:
                logger.error(f">> FAILED to process {file}: {e}", exc_info=True)

        total_execution_time = time.time() - batch_start_time
        logger.info("\n" + "-" * 80)
        logger.info("BATCH PROCESSING COMPLETE")
        logger.info(f"Successfully processed {processed_count} of {len(self.files_to_process)} recordings.")
        logger.info(f"Total execution time: {total_execution_time:.2f} seconds.")
        logger.info(f"All results saved in: {batch_output_dir}")
        logger.info("-" * 80)
        
        return processed_count, len(self.files_to_process)

def batch_scorer(input_dir, output_dir=None, scorer_type=None, model_name=None, dir_list=None, zmax_mode=None):
    """
    Factory function to create a BatchScorer instance.
    This is the recommended entry point for batch processing.

    Args:
        input_dir (str): Path to the main study directory that contains one subfolder per recording.
        output_dir (str, optional): Base directory where batch results will be saved. Defaults to input_dir when omitted.
        scorer_type (str): Type of data, either 'forehead' or 'psg'.
        model_name (str, optional): Name of the model to use.
        dir_list (list, optional): A list of specific directories to process instead of scanning all subdirectories.
        zmax_mode (str, optional): The ZMax mode ('one_file' or 'two_files') for forehead data.

    Returns:
        BatchScorer: Configured BatchScorer. Call .score() to run processing. A new timestamped folder 'batch_run_YYYYmmdd_HHMMSS'
                     will be created inside output_dir to contain all per-recording outputs.
    """
    return BatchScorer(input_dir, output_dir, scorer_type, model_name, dir_list=dir_list, zmax_mode=zmax_mode)

def calculate_font_size(screen_height, percentage, min_size, max_size):
    """Calculates font size as a percentage of screen height with min/max caps."""
    font_size = int(screen_height * (percentage / 100))
    return max(min_size, min(font_size, max_size))

def compute_sleep_stats(hypnogram, epoch_duration_secs=30):
    """
    Computes sleep statistics from a hypnogram.

    Args:
        hypnogram (list): A list of integers representing sleep stages for each epoch.
                          (0=Wake, 1=N1, 2=N2, 3=N3, 5=REM)
        epoch_duration_secs (int): The duration of each epoch in seconds (default is 30).

    Returns:
        dict: A dictionary containing key sleep statistics.
    """
    if not hypnogram:
        return {}

    stats = {}
    total_epochs = len(hypnogram)

    # --- Time-based Metrics ---
    stats['Time in Bed (minutes)'] = (total_epochs * epoch_duration_secs) / 60

    # Calculate time spent in each stage
    time_in_wake_mins = hypnogram.count(0) * epoch_duration_secs / 60
    time_in_n1_mins = hypnogram.count(1) * epoch_duration_secs / 60
    time_in_n2_mins = hypnogram.count(2) * epoch_duration_secs / 60
    time_in_n3_mins = hypnogram.count(3) * epoch_duration_secs / 60
    time_in_rem_mins = hypnogram.count(5) * epoch_duration_secs / 60

    stats['Time in Wake (minutes)'] = time_in_wake_mins
    stats['Time in N1 (minutes)'] = time_in_n1_mins
    stats['Time in N2 (minutes)'] = time_in_n2_mins
    stats['Time in N3 (minutes)'] = time_in_n3_mins
    stats['Time in REM (minutes)'] = time_in_rem_mins

    # --- Total Sleep Time (TST) ---
    # TST is the total time spent in all sleep stages (N1, N2, N3, REM)
    total_sleep_time_mins = (time_in_n1_mins + time_in_n2_mins + 
                             time_in_n3_mins + time_in_rem_mins)
    stats['Total Sleep Time (minutes)'] = total_sleep_time_mins

    # --- Sleep Efficiency ---
    # Percentage of time in bed that you are actually asleep
    if stats['Time in Bed (minutes)'] > 0:
        stats['Sleep Efficiency (%)'] = (total_sleep_time_mins / stats['Time in Bed (minutes)']) * 100
    else:
        stats['Sleep Efficiency (%)'] = 0

    # --- Sleep Latency ---
    # Time it takes to fall asleep (first epoch of any sleep stage)
    sleep_onset_epoch = -1
    for i, stage in enumerate(hypnogram):
        if stage in [1, 2, 3, 4, 5]: # Any stage other than Wake
            sleep_onset_epoch = i
            break
    
    if sleep_onset_epoch != -1:
        stats['Sleep Latency (minutes)'] = (sleep_onset_epoch * epoch_duration_secs) / 60
    else:
        stats['Sleep Latency (minutes)'] = 0 # Never fell asleep

    # --- Wake After Sleep Onset (WASO) ---
    # Total time awake after falling asleep for the first time
    if sleep_onset_epoch != -1:
        waso_epochs = hypnogram[sleep_onset_epoch:].count(0)
        stats['WASO (minutes)'] = (waso_epochs * epoch_duration_secs) / 60
    else:
        stats['WASO (minutes)'] = 0

    # --- Stage Percentages (of TST) ---
    if total_sleep_time_mins > 0:
        stats['N1 Sleep (%)'] = (time_in_n1_mins / total_sleep_time_mins) * 100
        stats['N2 Sleep (%)'] = (time_in_n2_mins / total_sleep_time_mins) * 100
        stats['N3 Sleep (Deep Sleep) (%)'] = (time_in_n3_mins / total_sleep_time_mins) * 100
        stats['REM Sleep (%)'] = (time_in_rem_mins / total_sleep_time_mins) * 100
    else:
        stats['N1 Sleep (%)'] = 0
        stats['N2 Sleep (%)'] = 0
        stats['N3 Sleep (Deep Sleep) (%)'] = 0
        stats['REM Sleep (%)'] = 0

    # Round all float values to 2 decimal places
    for key, value in stats.items():
        if isinstance(value, float):
            stats[key] = round(value, 2)

    return stats

def select_channels(psg_data: np.ndarray, sample_rate: int, channel_names: List[str] = None) -> List[int]:
    """
    Select usable channels for PSG analysis based on signal quality metrics.
    """
    try:
        print("=== STARTING CHANNEL SELECTION PROCESS ===")

        if psg_data is None or psg_data.ndim != 2 or psg_data.size == 0:
            print("Select Channels: Invalid input array.")
            return []

        psg_data_uv = psg_data * 1e6
        n_channels, n_samples = psg_data_uv.shape

        if n_channels == 0 or n_samples == 0:
            print("Select Channels: Array has 0 channels or 0 samples.")
            return []

        if channel_names is None or len(channel_names) != n_channels:
            actual_channel_names = [f"Ch{i}" for i in range(n_channels)]
        else:
            actual_channel_names = channel_names

        max_abs_val_uv = 500.0
        relative_amp_factor = 10.0
        min_std_dev_uv = 0.5
        max_std_dev_uv = 250.0
        one_over_f_range = (1.0, 30.0)
        amp_persist_frac = 0.01
        std_persist_frac = 0.01
        weight_amp = 2.0
        weight_std = 4.0
        weight_1f = 1.0
        METRIC_ANALYSIS_DURATION_SEC = 30

        target_ds_freq = min(100, sample_rate / (2 * max(one_over_f_range[1], 50)))
        decim = max(1, int(sample_rate / target_ds_freq))
        sr_ds = sample_rate / decim
        ds = psg_data_uv[:, ::decim]
        n_total_ds_samples = ds.shape[1]

        amp_frac = np.zeros(n_channels)
        std_frac = np.zeros(n_channels)
        alphas = np.zeros(n_channels)
        noise_excl_metrics = np.zeros(n_channels, dtype=bool)

        if n_total_ds_samples > 0:
            metric_analysis_samples_ds = min(n_total_ds_samples, int(sr_ds * METRIC_ANALYSIS_DURATION_SEC))
            ds_metric_window = ds[:, -metric_analysis_samples_ds:]
            n_metric_window_ds_samples = ds_metric_window.shape[1]

            if n_metric_window_ds_samples > 0:
                mean_abs_metric_window = np.mean(np.abs(ds_metric_window), axis=1)
                if n_channels > 1:
                    ref_ma = ((np.sum(mean_abs_metric_window) - mean_abs_metric_window) / (n_channels - 1))
                else:
                    ref_ma = mean_abs_metric_window
                amp_th = np.minimum(max_abs_val_uv, relative_amp_factor * ref_ma)
                exceed = np.sum(np.abs(ds_metric_window) > amp_th[:, None], axis=1)
                amp_frac = exceed / n_metric_window_ds_samples

            amp_bad = amp_frac > amp_persist_frac
    
            std_bad = np.zeros(n_channels, dtype=bool)
            if n_metric_window_ds_samples > 0:
                std_win_samples_ds = int(sr_ds * 1.0)
                if std_win_samples_ds > 0:
                    n_win = n_metric_window_ds_samples // std_win_samples_ds
                    if n_win > 0:
                        resh = ds_metric_window[:, :n_win * std_win_samples_ds].reshape(n_channels, n_win, std_win_samples_ds)
                        win_stds = np.std(resh, axis=2)
                        flat = np.sum(win_stds < min_std_dev_uv, axis=1)
                        high = np.sum(win_stds > max_std_dev_uv, axis=1)
                        std_frac = (flat + high) / n_win
                        std_bad = np.logical_or((flat / n_win) > std_persist_frac, (high / n_win) > std_persist_frac)
    
            nan_bad_metric_window = ~np.all(np.isfinite(ds_metric_window), axis=1)
            noise_excl_metrics = amp_bad | std_bad | nan_bad_metric_window

            try:
                F = np.fft.rfft(ds, axis=1)
                psd = (np.abs(F)**2) / (sr_ds * n_total_ds_samples)
                psd[:, 1:-1] *= 2
                freqs = np.fft.rfftfreq(n_total_ds_samples, d=1.0/sr_ds)
                fmask = (freqs >= one_over_f_range[0]) & (freqs <= one_over_f_range[1])
                if np.any(fmask) and freqs[fmask].size > 1:
                    xf = np.log(freqs[fmask])
                    xm = xf.mean()
                    denom = np.sum((xf - xm)**2)
                    if denom > 1e-10:
                        log_psd = np.log(psd[:, fmask] + 1e-20)
                        ym = log_psd.mean(axis=1)
                        numer = np.sum((xf[None, :] - xm) * (log_psd - ym[:, None]), axis=1)
                        alphas = -numer / denom
            except Exception as e_fft:
                print(f"FFT/PSD/Alpha calculation error: {e_fft}")
                alphas.fill(0.0)

        typical_eeg = [
            'FP1', 'FP2', 'AF7', 'AF3', 'AF4', 'AF8', 'F7', 'F5', 'F3', 'F1', 'FZ', 'F2', 'F4', 'F6', 'F8',
            'FT7', 'FC5', 'FC3', 'FC1', 'FCZ', 'FC2', 'FC4', 'FC6', 'FT8', 'T7', 'C5', 'C3', 'C1', 'CZ', 'C2', 'C4', 'C6', 'T8',
            'TP7', 'CP5', 'CP3', 'CP1', 'CPZ', 'CP2', 'CP4', 'CP6', 'TP8', 'P7', 'P5', 'P3', 'P1', 'PZ', 'P2', 'P4', 'P6', 'P8',
            'PO7', 'PO3', 'POZ', 'PO4', 'PO8', 'O1', 'OZ', 'O2','FT9', 'FT10', 'TP9', 'TP10', 'AFZ', 'FPZ','A1', 'A2', 'M1', 'M2'
        ]
        pat_eeg_str = r'\b(?:' + '|'.join(typical_eeg) + r'|EEG)\b'
        pat_eog_str = r'\b(?:EOG|LOC|ROC|E\d+)\b'
        pat_emg_str = r'\b(?:EMG|Chin|Submental|MENT)\b'
        pat_eeg = re.compile(pat_eeg_str, re.IGNORECASE)
        pat_eog = re.compile(pat_eog_str, re.IGNORECASE)
        pat_emg = re.compile(pat_emg_str, re.IGNORECASE)

        is_eeg = np.array([bool(pat_eeg.search(n)) for n in actual_channel_names])
        is_eog = np.array([bool(pat_eog.search(n)) and not bool(pat_eeg.search(n)) for n in actual_channel_names])
        is_emg = np.array([bool(pat_emg.search(n)) for n in actual_channel_names])
        in_any_class = is_eeg | is_eog | is_emg

        initial_final_excl_mask = noise_excl_metrics | ~in_any_class
        final_excl_mask = initial_final_excl_mask.copy()

        if np.all(final_excl_mask):
            final_excl_mask = noise_excl_metrics.copy()
            if np.all(final_excl_mask):
                critically_bad_amp = (amp_frac >= 0.95)
                critically_bad_std = (std_frac >= 0.95)
                final_excl_mask = nan_bad_metric_window | critically_bad_amp | critically_bad_std
                if np.all(final_excl_mask):
                    final_excl_mask = nan_bad_metric_window.copy()
                    if np.all(final_excl_mask):
                        return []

        scores = np.full(n_channels, np.inf)
        non_excluded_mask = ~final_excl_mask
        num_non_excluded = np.sum(non_excluded_mask)

        if num_non_excluded > 0 and n_total_ds_samples > 0:
            epsilon = 1e-10
            amp_frac_ne = amp_frac[non_excluded_mask]
            std_frac_ne = std_frac[non_excluded_mask]
            alphas_ne = alphas[non_excluded_mask]

            amp_score_ne = np.zeros(num_non_excluded)
            std_score_ne = np.zeros(num_non_excluded)
            one_f_score_ne = np.zeros(num_non_excluded)

            if num_non_excluded > 1:
                ref_amp_frac_ne = (np.sum(amp_frac_ne) - amp_frac_ne) / (num_non_excluded - 1)
                amp_score_ne = np.abs(amp_frac_ne / (ref_amp_frac_ne + epsilon) - 1.0)
                ref_std_frac_ne = (np.sum(std_frac_ne) - std_frac_ne) / (num_non_excluded - 1)
                std_score_ne = np.abs(std_frac_ne / (ref_std_frac_ne + epsilon) - 1.0)
                ref_alpha_ne = (np.sum(alphas_ne) - alphas_ne) / (num_non_excluded - 1)
                valid_alpha_denom_ne = np.abs(ref_alpha_ne) > epsilon
                one_f_score_ne[valid_alpha_denom_ne] = np.abs(alphas_ne[valid_alpha_denom_ne] / ref_alpha_ne[valid_alpha_denom_ne] - 1.0)

            current_scores_ne = (weight_amp * amp_score_ne + weight_std * std_score_ne + weight_1f * one_f_score_ne)
            scores[non_excluded_mask] = current_scores_ne

        eeg_indices = np.where(is_eeg & ~final_excl_mask)[0]
        ranked_eeg_indices = eeg_indices[np.argsort(scores[eeg_indices])].tolist()

        return ranked_eeg_indices

    except Exception as e:
        print(f"Error in channel selection: {e}", exc_info=True)
        return list(range(psg_data.shape[0]))



def setup_logging():
    """Configures logging for the application and returns the log file path and logger instance."""
    log_dir = Path(tempfile.gettempdir()) / "nidra_logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"nidra_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # --- Custom Handler Setup for Line Buffering ---
    # Open the file stream with line buffering (buffering=1)
    log_file_stream = open(log_file, 'w', encoding='utf-8', buffering=1)
    
    # Register a cleanup function to close the stream on exit
    import atexit
    atexit.register(log_file_stream.close)

    # Create handlers
    file_handler = logging.StreamHandler(log_file_stream)
    handlers = [file_handler]
    
    # Only add stdout handler if stdout is not None (e.g., when not running in a GUI)
    if sys.stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        handlers.append(stdout_handler)

    # Redirect stderr to the log file stream if it's None or not a valid stream
    if not hasattr(sys.stderr, 'write'):
        sys.stderr = log_file_stream

    # Use basicConfig with the custom handlers. force=True ensures this configuration is applied.
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        handlers=handlers,
        force=True
    )
    
    # Return the configured root logger instance
    return log_file, logging.getLogger()



def get_model_path(model_name=None):
    """
    returns model file path if name specified or model folder path if name not specified
    """
    app_dir, is_bundle = get_app_dir()
    base_path = Path(app_dir) if is_bundle else Path(user_data_dir())
    models_dir = base_path / "NIDRA" / "models"
    return models_dir / model_name if model_name else models_dir


def download_models(logger):
    """
    Checks for models in the user's data directory and downloads them if missing.
    Logs progress to the provided logger instance.
    Returns True if a download was attempted, False otherwise.
    """
    app_dir, is_bundle = get_app_dir()
    if is_bundle:
        return False

    # make local models folder
    repo_id = "pzerr/NIDRA_models"
    models = ["u-sleep-nsrr-2024.onnx", "u-sleep-nsrr-2024_eeg.onnx", "ez6.onnx", "ez6moe.onnx"]
    models_dir = get_model_path() 
    models_dir.mkdir(parents=True, exist_ok=True) 

    # check which model files already exist
    models_to_download = [m for m in models if not get_model_path(m).exists()]

    if not models_to_download:
        logger.info(f"Models found at: {models_dir}")
        return False

    # download models
    logger.info("--- Downloading model files ---")
    total_size = 0
    for model_name in models_to_download:
        try:
            url = hf_hub_url(repo_id, model_name)
            response = requests.head(url, timeout=30)
            response.raise_for_status()
            file_size = int(response.headers.get('content-length', 0))
            total_size += file_size
        except Exception:
            continue
    
    total_size_mb = total_size / (1024 * 1024)
    if total_size_mb < 0.1:
        total_size_mb = 152.0 # Fallback size
    size_info = f"({total_size_mb:.2f} MB)" if total_size_mb > 0 else ""
    logger.info(f"Downloading sleep scoring models to {models_dir}, please wait... {size_info}")

    for model_name in models_to_download:
        try:
            logger.info(f"Downloading {model_name}...")
            hf_hub_download(repo_id=repo_id, filename=model_name, local_dir=models_dir)
            logger.info(f"Successfully downloaded {model_name}.")
        except Exception as e:
            logger.error(f"Error downloading {model_name}: {e}", exc_info=True)
            repo_url = "https://huggingface.co/pzerr/NIDRA_models"
            download_dir = get_model_path(model_name)
            error_message = (
                "\n--- MODEL DOWNLOAD FAILED ---\n"
                f"Automatic download of the required model '{model_name}' failed.\n"
                "Please try one of the following solutions:\n"
                "1. Use the single-file executable version of NIDRA, which includes all models.\n"
                f"2. Manually download the model from: {repo_url}\n"
                f"   And place it in the following directory: {os.path.dirname(download_dir)}\n"
            )
            logger.error(error_message)
    
    logger.info("--- Model download complete ---")
    return True

def get_app_dir():
    """
    Returns (base_path, is_bundle)
      - base_path: Path object for the application's root directory
      - is_bundle: 1 if running as a PyInstaller bundle, 0 otherwise
    """
    # PyInstaller bundle (one-dir)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        internal_dir = exe_dir / "_internal"
        if internal_dir.exists():
            return internal_dir, 1
        return exe_dir, 1

    # Running from source
    this_file = Path(__file__).resolve()
    if this_file.is_file():
        return this_file.parent, 0

    # Installed as pip package
    spec = importlib.util.find_spec("NIDRA")
    if spec and spec.origin:
        return Path(spec.origin).resolve().parent, 0

    return None, 0


def download_example_data(logger):
    """
    Checks for example data in the user's data directory and downloads it if missing.
    Logs progress to the provided logger instance.
    Returns the path to the example data directory.
    """
    repo_id = "pzerr/NIDRA_models"
    example_files = ["EEG_L.edf", "EEG_R.edf"]

    # Place example data next to the models directory
    models_dir = Path(os.path.dirname(get_model_path("dummy.onnx")))
    example_data_dir = models_dir.parent / "example_zmax_data"
    os.makedirs(example_data_dir, exist_ok=True)

    files_to_download = [f for f in example_files if not (example_data_dir / f).exists()]

    if not files_to_download:
        return str(example_data_dir)

    logger.info("\n\n" + f"Downloading example data to {example_data_dir}, please wait...")

    for filename in files_to_download:
        try:
            logger.info(f"Downloading {filename}...")
            hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(example_data_dir))
            logger.info(f"Successfully downloaded {filename}.")
        except Exception as e:
            logger.error(f"Error downloading {filename}: {e}", exc_info=True)
            repo_url = "https://huggingface.co/pzerr/NIDRA_models"
            download_dir = example_data_dir / filename
            error_message = (
                "\n--- EXAMPLE DATA DOWNLOAD FAILED ---\n"
                f"Automatic download of the example data file '{filename}' failed.\n"
                f"Please try manually downloading the file from: {repo_url}\n"
                f"And place it in the following directory: {example_data_dir}\n"
            )
            logger.error(error_message)
            # If a download fails, return None to indicate an error
            return None

    logger.info("--- Example data download complete ---")
    return str(example_data_dir)
