import os
import sys
import logging
import time
import tempfile
from pathlib import Path
from datetime import datetime
from huggingface_hub import hf_hub_download
from appdirs import user_data_dir
import importlib.util
from types import SimpleNamespace

logger = logging.getLogger(__name__)

def find_files(input):

    input = Path(input)
    exts = {".edf", ".bdf"}
    skip_exact = {"BATT", "LIGHT", "DY", "BODY TEMP", "NOISE", "DX", "DZ"}
    skip_prefixes = ("OXY",)
    files = []

    def should_skip_file(f: Path):
        name = f.stem.upper()
        if name in skip_exact:
            return True
        return any(name.startswith(prefix) for prefix in skip_prefixes)

    def collect_from_dir(d: Path):
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() in exts and not should_skip_file(f):
                files.append(f)

    def collect_from_txt(txt: Path):
        with open(txt, "r") as f:
            for line in f:
                p = Path(line.strip())
                if not p.exists():
                    continue
                resolve_input(p)

    def resolve_input(p: Path):
        if p.is_file():
            if p.suffix.lower() == ".txt":
                collect_from_txt(p)
            elif p.suffix.lower() in exts and not should_skip_file(p):
                files.append(p)
        elif p.is_dir():
            collect_from_dir(p)

    resolve_input(input)

    # Remove *r.edf when matching *l.edf exists
    lowercase_set = {str(f).lower() for f in files}
    files_to_process = []
    for f in files:
        lf = str(f).lower()
        if lf.endswith("r.edf"):
            l_version = lf[:-5] + "l.edf"
            if l_version in lowercase_set:
                continue
        files_to_process.append(f)

    if input.is_file():
        output_base = input.parent
    else:
        output_base = input

    return files_to_process, output_base

def batch_scorer(input, output=None, type=None, model=None,
                 channels=None, hypnogram=None, hypnodensity=False, plot=False, cancel_event=None):

    if type not in ("forehead", "psg"):
        raise ValueError("type must be 'forehead' or 'psg'.")

    files_to_process, output_base_dir = find_files(input)

    if files_to_process:
        logger.info(f"The following {len(files_to_process)} recordings will be scored:")
        for f in files_to_process:
            logger.info(f"  > {f}")        
    else:
        logger.warning(f"Could not find any sleep recordings in the specified location.")

    if output:
        output_dir = Path(output)
    elif output_base_dir:
        output_dir = output_base_dir
    else:
        output_dir = Path.cwd()
        logger.warning(
            f"Could not determine a base directory for outputs. "
            f"Defaulting to current working directory: {output_dir}"
        )

    def score():
        if not files_to_process:
            return 0, 0

        batch_start = time.time()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except:
            logger.error(f"Unable to make output folder at {output_dir}, please specify a location where you have user rights.")

        success_count = 0
        total = len(files_to_process)

        for i, target in enumerate(files_to_process):
            target_path = Path(target)

            if cancel_event and cancel_event.is_set():
                logger.warning("Scoring cancelled by user.")
                break

            logger.info("\n" + "-" * 80)
            logger.info(f"[{i + 1}/{total}] Processing: {target_path}")

            #logger.info(f"Scoring on channels: {channels}")
            
            out_dir = output_dir
            out_dir.mkdir(exist_ok=True)

            try:
                start = time.time()

                if type == 'forehead':
                    from NIDRA.forehead_scorer import ForeheadScorer as Scorer
                elif type == 'psg':
                    from NIDRA.psg_scorer import PSGScorer as Scorer
                else:
                    raise ValueError(f"Unknown scorer type: {type}")

                scorer = Scorer(
                    input=target_path,
                    output=str(out_dir),
                    model=model,
                    channels=channels,
                    hypnogram=True if hypnogram is None else bool(hypnogram),
                    hypnodensity=bool(hypnodensity),
                    plot=bool(plot),
                )

                scorer.score()

                dt = time.time() - start
                logger.info(f">> SUCCESS: Finished scoring {target_path.name} in {dt:.2f} seconds.")
                logger.info(f"   Results saved to: {out_dir}")
                logger.info("-" * 80)
                success_count += 1

            except Exception as e:
                logger.error(f">> FAILED to score {target_path}: {e}", exc_info=True)

        total_dt = time.time() - batch_start
        logger.info("\n" + "="*80)
        logger.info("PROCESSING COMPLETE")
        logger.info(f"{success_count} of {total} recording(s) processed successfully.")
        logger.info(f"Total execution time: {total_dt:.2f} seconds.")
        logger.info(f"All results saved in: {output_dir}")
        logger.info("="*80)

        return success_count, total

    return SimpleNamespace(score=score)

def calculate_font_size(screen_height, percentage, min_size, max_size):
    """Calculates font size as a percentage of screen height with min/max caps."""
    font_size = int(screen_height * (percentage / 100))
    return max(min_size, min(font_size, max_size))

def compute_sleep_stats(sleep_stages, epoch_duration_secs=30):
    stats = {}
    total_epochs = len(sleep_stages)

    stats['Time in Bed (minutes)'] = (total_epochs * epoch_duration_secs) / 60

    time_in_wake_mins = sleep_stages.count(0) * epoch_duration_secs / 60
    time_in_n1_mins = sleep_stages.count(1) * epoch_duration_secs / 60
    time_in_n2_mins = sleep_stages.count(2) * epoch_duration_secs / 60
    time_in_n3_mins = sleep_stages.count(3) * epoch_duration_secs / 60
    time_in_rem_mins = sleep_stages.count(5) * epoch_duration_secs / 60

    stats['Time in Wake (minutes)'] = time_in_wake_mins
    stats['Time in N1 (minutes)'] = time_in_n1_mins
    stats['Time in N2 (minutes)'] = time_in_n2_mins
    stats['Time in N3 (minutes)'] = time_in_n3_mins
    stats['Time in REM (minutes)'] = time_in_rem_mins

    total_sleep_time_mins = (time_in_n1_mins + time_in_n2_mins + 
                             time_in_n3_mins + time_in_rem_mins)
    stats['Total Sleep Time (minutes)'] = total_sleep_time_mins

    if stats['Time in Bed (minutes)'] > 0:
        stats['Sleep Efficiency (%)'] = (total_sleep_time_mins / stats['Time in Bed (minutes)']) * 100
    else:
        stats['Sleep Efficiency (%)'] = 0

    sleep_onset_epoch = -1
    for i, stage in enumerate(sleep_stages):
        if stage in [1, 2, 3, 4, 5]: 
            sleep_onset_epoch = i
            break
    
    if sleep_onset_epoch != -1:
        stats['Sleep Latency (minutes)'] = (sleep_onset_epoch * epoch_duration_secs) / 60
    else:
        stats['Sleep Latency (minutes)'] = 0 # Never fell asleep

    if sleep_onset_epoch != -1:
        waso_epochs = sleep_stages[sleep_onset_epoch:].count(0)
        stats['WASO (minutes)'] = (waso_epochs * epoch_duration_secs) / 60
    else:
        stats['WASO (minutes)'] = 0

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

    for key, value in stats.items():
        if isinstance(value, float):
            stats[key] = round(value, 2)

    return stats

# def select_channels(psg_data: np.ndarray, sample_rate: int, channel_names: List[str] = None) -> List[int]:
#     """
#     Select usable channels for PSG analysis based on signal quality metrics.
#     """
#     try:
#         print("=== STARTING CHANNEL SELECTION PROCESS ===")

#         if psg_data is None or psg_data.ndim != 2 or psg_data.size == 0:
#             print("Select Channels: Invalid input array.")
#             return []

#         psg_data_uv = psg_data * 1e6
#         n_channels, n_samples = psg_data_uv.shape

#         if n_channels == 0 or n_samples == 0:
#             print("Select Channels: Array has 0 channels or 0 samples.")
#             return []

#         if channel_names is None or len(channel_names) != n_channels:
#             actual_channel_names = [f"Ch{i}" for i in range(n_channels)]
#         else:
#             actual_channel_names = channel_names

#         max_abs_val_uv = 500.0
#         relative_amp_factor = 10.0
#         min_std_dev_uv = 0.5
#         max_std_dev_uv = 250.0
#         one_over_f_range = (1.0, 30.0)
#         amp_persist_frac = 0.01
#         std_persist_frac = 0.01
#         weight_amp = 2.0
#         weight_std = 4.0
#         weight_1f = 1.0
#         METRIC_ANALYSIS_DURATION_SEC = 30

#         target_ds_freq = min(100, sample_rate / (2 * max(one_over_f_range[1], 50)))
#         decim = max(1, int(sample_rate / target_ds_freq))
#         sr_ds = sample_rate / decim
#         ds = psg_data_uv[:, ::decim]
#         n_total_ds_samples = ds.shape[1]

#         amp_frac = np.zeros(n_channels)
#         std_frac = np.zeros(n_channels)
#         alphas = np.zeros(n_channels)
#         noise_excl_metrics = np.zeros(n_channels, dtype=bool)

#         if n_total_ds_samples > 0:
#             metric_analysis_samples_ds = min(n_total_ds_samples, int(sr_ds * METRIC_ANALYSIS_DURATION_SEC))
#             ds_metric_window = ds[:, -metric_analysis_samples_ds:]
#             n_metric_window_ds_samples = ds_metric_window.shape[1]

#             if n_metric_window_ds_samples > 0:
#                 mean_abs_metric_window = np.mean(np.abs(ds_metric_window), axis=1)
#                 if n_channels > 1:
#                     ref_ma = ((np.sum(mean_abs_metric_window) - mean_abs_metric_window) / (n_channels - 1))
#                 else:
#                     ref_ma = mean_abs_metric_window
#                 amp_th = np.minimum(max_abs_val_uv, relative_amp_factor * ref_ma)
#                 exceed = np.sum(np.abs(ds_metric_window) > amp_th[:, None], axis=1)
#                 amp_frac = exceed / n_metric_window_ds_samples

#             amp_bad = amp_frac > amp_persist_frac
    
#             std_bad = np.zeros(n_channels, dtype=bool)
#             if n_metric_window_ds_samples > 0:
#                 std_win_samples_ds = int(sr_ds * 1.0)
#                 if std_win_samples_ds > 0:
#                     n_win = n_metric_window_ds_samples // std_win_samples_ds
#                     if n_win > 0:
#                         resh = ds_metric_window[:, :n_win * std_win_samples_ds].reshape(n_channels, n_win, std_win_samples_ds)
#                         win_stds = np.std(resh, axis=2)
#                         flat = np.sum(win_stds < min_std_dev_uv, axis=1)
#                         high = np.sum(win_stds > max_std_dev_uv, axis=1)
#                         std_frac = (flat + high) / n_win
#                         std_bad = np.logical_or((flat / n_win) > std_persist_frac, (high / n_win) > std_persist_frac)
    
#             nan_bad_metric_window = ~np.all(np.isfinite(ds_metric_window), axis=1)
#             noise_excl_metrics = amp_bad | std_bad | nan_bad_metric_window

#             try:
#                 F = np.fft.rfft(ds, axis=1)
#                 psd = (np.abs(F)**2) / (sr_ds * n_total_ds_samples)
#                 psd[:, 1:-1] *= 2
#                 freqs = np.fft.rfftfreq(n_total_ds_samples, d=1.0/sr_ds)
#                 fmask = (freqs >= one_over_f_range[0]) & (freqs <= one_over_f_range[1])
#                 if np.any(fmask) and freqs[fmask].size > 1:
#                     xf = np.log(freqs[fmask])
#                     xm = xf.mean()
#                     denom = np.sum((xf - xm)**2)
#                     if denom > 1e-10:
#                         log_psd = np.log(psd[:, fmask] + 1e-20)
#                         ym = log_psd.mean(axis=1)
#                         numer = np.sum((xf[None, :] - xm) * (log_psd - ym[:, None]), axis=1)
#                         alphas = -numer / denom
#             except Exception as e_fft:
#                 print(f"FFT/PSD/Alpha calculation error: {e_fft}")
#                 alphas.fill(0.0)

#         typical_eeg = [
#             'FP1', 'FP2', 'AF7', 'AF3', 'AF4', 'AF8', 'F7', 'F5', 'F3', 'F1', 'FZ', 'F2', 'F4', 'F6', 'F8',
#             'FT7', 'FC5', 'FC3', 'FC1', 'FCZ', 'FC2', 'FC4', 'FC6', 'FT8', 'T7', 'C5', 'C3', 'C1', 'CZ', 'C2', 'C4', 'C6', 'T8',
#             'TP7', 'CP5', 'CP3', 'CP1', 'CPZ', 'CP2', 'CP4', 'CP6', 'TP8', 'P7', 'P5', 'P3', 'P1', 'PZ', 'P2', 'P4', 'P6', 'P8',
#             'PO7', 'PO3', 'POZ', 'PO4', 'PO8', 'O1', 'OZ', 'O2','FT9', 'FT10', 'TP9', 'TP10', 'AFZ', 'FPZ','A1', 'A2', 'M1', 'M2'
#         ]
#         pat_eeg_str = r'\b(?:' + '|'.join(typical_eeg) + r'|EEG)\b'
#         pat_eog_str = r'\b(?:EOG|LOC|ROC|E\d+)\b'
#         pat_emg_str = r'\b(?:EMG|Chin|Submental|MENT)\b'
#         pat_eeg = re.compile(pat_eeg_str, re.IGNORECASE)
#         pat_eog = re.compile(pat_eog_str, re.IGNORECASE)
#         pat_emg = re.compile(pat_emg_str, re.IGNORECASE)

#         is_eeg = np.array([bool(pat_eeg.search(n)) for n in actual_channel_names])
#         is_eog = np.array([bool(pat_eog.search(n)) and not bool(pat_eeg.search(n)) for n in actual_channel_names])
#         is_emg = np.array([bool(pat_emg.search(n)) for n in actual_channel_names])
#         in_any_class = is_eeg | is_eog | is_emg

#         initial_final_excl_mask = noise_excl_metrics | ~in_any_class
#         final_excl_mask = initial_final_excl_mask.copy()

#         if np.all(final_excl_mask):
#             final_excl_mask = noise_excl_metrics.copy()
#             if np.all(final_excl_mask):
#                 critically_bad_amp = (amp_frac >= 0.95)
#                 critically_bad_std = (std_frac >= 0.95)
#                 final_excl_mask = nan_bad_metric_window | critically_bad_amp | critically_bad_std
#                 if np.all(final_excl_mask):
#                     final_excl_mask = nan_bad_metric_window.copy()
#                     if np.all(final_excl_mask):
#                         return []

#         scores = np.full(n_channels, np.inf)
#         non_excluded_mask = ~final_excl_mask
#         num_non_excluded = np.sum(non_excluded_mask)

#         if num_non_excluded > 0 and n_total_ds_samples > 0:
#             epsilon = 1e-10
#             amp_frac_ne = amp_frac[non_excluded_mask]
#             std_frac_ne = std_frac[non_excluded_mask]
#             alphas_ne = alphas[non_excluded_mask]

#             amp_score_ne = np.zeros(num_non_excluded)
#             std_score_ne = np.zeros(num_non_excluded)
#             one_f_score_ne = np.zeros(num_non_excluded)

#             if num_non_excluded > 1:
#                 ref_amp_frac_ne = (np.sum(amp_frac_ne) - amp_frac_ne) / (num_non_excluded - 1)
#                 amp_score_ne = np.abs(amp_frac_ne / (ref_amp_frac_ne + epsilon) - 1.0)
#                 ref_std_frac_ne = (np.sum(std_frac_ne) - std_frac_ne) / (num_non_excluded - 1)
#                 std_score_ne = np.abs(std_frac_ne / (ref_std_frac_ne + epsilon) - 1.0)
#                 ref_alpha_ne = (np.sum(alphas_ne) - alphas_ne) / (num_non_excluded - 1)
#                 valid_alpha_denom_ne = np.abs(ref_alpha_ne) > epsilon
#                 one_f_score_ne[valid_alpha_denom_ne] = np.abs(alphas_ne[valid_alpha_denom_ne] / ref_alpha_ne[valid_alpha_denom_ne] - 1.0)

#             current_scores_ne = (weight_amp * amp_score_ne + weight_std * std_score_ne + weight_1f * one_f_score_ne)
#             scores[non_excluded_mask] = current_scores_ne

#         eeg_indices = np.where(is_eeg & ~final_excl_mask)[0]
#         ranked_eeg_indices = eeg_indices[np.argsort(scores[eeg_indices])].tolist()

#         return ranked_eeg_indices

#     except Exception as e:
#         print(f"Error in channel selection: {e}", exc_info=True)
#         return list(range(psg_data.shape[0]))



def setup_logging():
    """Configures logging for the application and returns the log file path and logger instance."""
    log_dir = Path(tempfile.gettempdir()) / "nidra_logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"nidra_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    app_dir, is_bundle = get_app_dir()
    base_path = Path(app_dir) if is_bundle else Path(user_data_dir())
    models_dir = base_path / "NIDRA" / "models"
    return models_dir / model_name if model_name else models_dir

def get_app_dir():
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

def download_assets(kind, logger):
    """
    Downloads either 'models' or 'example_data' into their appropriate
    directory. Skips files that already exist.
    """
    repo_id = "pzerr/NIDRA_models"
    if kind == "models":
        files = [
            "u-sleep-nsrr-2024.onnx",
            "u-sleep-nsrr-2024_eeg.onnx",
            "ez6.onnx",
            "ez6moe.onnx",
        ]
        base_dir = get_model_path()
        size_info = "(152 MB)"
    elif kind == "example_data":
        files = ["EEG_L.edf", "EEG_R.edf"]
        model_dir = Path(os.path.dirname(get_model_path("dummy.onnx")))
        base_dir = model_dir.parent / "example_zmax_data"
        size_info = "(24 MB)"

    base_dir.mkdir(parents=True, exist_ok=True)

    # Check existing
    missing = [f for f in files if not (base_dir / f).exists()]
    if not missing:
        logger.info(f"All {kind.replace('_', ' ')} found in: {base_dir}")
        return str(base_dir)

    # Download missing items
    logger.info(f"Downloading {kind.replace('_', ' ')} to {base_dir}, please wait... {size_info}")
    for name in missing:
        try:
            hf_hub_download(repo_id=repo_id, filename=name, local_dir=str(base_dir))
            logger.info(f"Downloaded {name}.")
        except Exception as e:
            logger.error(f"Error downloading {name}: {e}", exc_info=True)

            # unified failure message for ALL asset types
            repo_url = "https://huggingface.co/pzerr/NIDRA_models"
            logger.error(
                "\n--- DOWNLOAD FAILED ---\n"
                f"Automatic download of one or more required files for '{kind}' has failed.\n"
                "To continue, please manually download ALL required files from:\n"
                f"  {repo_url}\n"
                "Then place them in this directory:\n"
                f"  {base_dir}\n"
            )
            return None

    logger.info(f"--- {kind.replace('_', ' ').title()} download complete ---")
    return str(base_dir)
