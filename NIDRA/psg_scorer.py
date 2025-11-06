import re
import mne
import numpy as np
import onnxruntime as ort
import logging
from scipy.signal import resample_poly
from pathlib import Path
from collections import namedtuple, OrderedDict
from itertools import product
from typing import List, Tuple, Dict, Any
from NIDRA.plotting import plot_hypnodensity
from NIDRA import utils


# --- Channel Definitions ---
MASTOIDS = {'A1', 'A2', 'M1', 'M2'}
EEG_BASES = {'FP1', 'FP2', 'F3', 'F4', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2', 'F7', 'F8', 'T3', 'T4', 'T5', 'T6', 'FZ', 'CZ', 'PZ', 'F1', 'F2'}
UNAMBIGUOUS_EOG_PATTERNS = {'EOG', 'LOC', 'ROC', 'E1', 'E2'}
EOG_BASES = ('EOG', 'OC', 'E1', 'E2')
OTHER_NON_EEG = {'EMG', 'ECG', 'EKG'}

class PSGScorer:
    """
    Scores sleep stages from PSG data.
    """
    def __init__(self, input: str = None, output: str = None, data: np.ndarray = None, channels: List[str] = None, sfreq: float = None, model: str = "u-sleep-nsrr-2024_eeg", epoch_sec: int = 30, create_output_files: bool = None):
        self.logger = logging.getLogger(__name__)
        if input is None and data is None:
            raise ValueError("Either 'input' or 'data' must be provided.")
        if data is not None and sfreq is None:
            raise ValueError("'sfreq' must be provided when 'data' is given.")

        if input:
            input_path = Path(input)
            if input_path.is_dir():
                input_dir = input_path
                try:
                    self.input_file = next(input_path.glob('*.edf'))
                except StopIteration:
                    raise FileNotFoundError(f"Could not find an EDF file in directory '{input_path}'.")
            else:
                input_dir = input_path.parent
                self.input_file = input_path
            self.base_filename = f"{self.input_file.parent.name}_{self.input_file.stem}"
        else:
            input_dir = None
            self.input_file = None
            self.base_filename = "numpy_input"

        if output is None:
            if input_dir:
                output = Path(input_dir) / "autoscorer_output"

        # if no output file parameter given, and we're using numpy array data input, no outfiles should be written
        # otherwise, if we're scoring edf's we do want to write output files by default
        if create_output_files is None:
            self.create_output_files = True if input else False
        else:
            # if we specified output file parameter, use that specification
            self.create_output_files = create_output_files

        if output is None and self.create_output_files:
            raise ValueError("output must be specified when create_output_files is True and it cannot be inferred from input.")
 
        self.output_dir = Path(output) if output is not None else None
        self.input_data = data
        self.ch_names = channels
        self.sfreq = sfreq
        self.model_name = model
        self.epoch_sec = 30 #epoch_sec # we ignore this input for now and enforce 30s epochs
        self.new_sample_rate = 128 # resample to 128 for usleep models
        self.auto_channel_grouping = ['EEG', 'EOG']
        self.onnx_model_path = None
        self.preprocessed_psg = None
        self.channel_groups = None
        self.has_eog = None
        self.session = None
        self.input_name = None
        self.output_name = None
        self.hypnogram = None
        self.probabilities = None

        if self.create_output_files:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def score(self, plot: bool = False):
        self._load_recording()
        self._preprocess()
        self._load_model()
        self._predict()
        self._postprocess()
        if self.create_output_files:
            self._save_results()
            if plot:
                self.plot()
        return self.hypnogram, self.probabilities

    def plot(self):
        """Generates and saves a dashboard plot."""
        if self.hypnogram is not None and self.probabilities is not None and self.raw is not None:
            plot_filename = f"{self.base_filename}_dashboard.png"
            plot_hypnodensity(
                hyp=self.hypnogram,
                ypred=self.probabilities,
                raw=self.raw,
                nclasses=self.probabilities.shape[1],
                figoutdir=self.output_dir,
                filename=plot_filename,
                type='psg'
            )
            print(f"Dashboard plot saved to {self.output_dir / plot_filename}")
        else:
            print("Scoring must be run before plotting.")

    def _load_model(self):
        if self.has_eog:
            model_filename = self.model_name + ".onnx"
            print(f"EOG channels found, loading model {model_filename}...")
        else:
            model_filename = self.model_name + "_eeg.onnx"
            print(f"No EOG channels found, loading EEG-only model: {model_filename}")
        
        model_path = utils.get_model_path(model_filename)
        try:
            
            self.session = ort.InferenceSession(model_path)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
        except Exception as e:
            print(f"Error: Failed to load ONNX model from '{model_path}'. Original error: {e}")
            raise

    def _load_recording(self):
        """Loads a PSG file or creates a raw object from numpy data."""
        print("Loading recording...")
        if self.input_data is not None:
            if self.input_data.ndim != 2:
                raise ValueError("Input data must be a 2D array.")
            
            # name channels if no names given
            n_channels = self.input_data.shape[0]
            if self.ch_names is None: 
                self.ch_names = [f"Ch{i+1:02d}" for i in range(n_channels)]

            info = mne.create_info(ch_names=self.ch_names, sfreq=self.sfreq, ch_types='eeg', verbose=False)
            self.raw = mne.io.RawArray(self.input_data, info, verbose=False)
        else:
            try:
                self.raw = mne.io.read_raw_edf(self.input_file, preload=False, verbose=False, stim_channel=None)
            except ValueError:
                self.raw = mne.io.read_raw_bdf(self.input_file, preload=False, verbose=False, stim_channel=None)


    def _preprocess(self):
        """Preprocesses a raw PSG recording."""
        print("Setting up channels and preprocessing PSG data...")
        
        # Respect user-selected channels if provided; otherwise use all channels
        base_ch_names = list(self.raw.ch_names)
        if self.ch_names:
            # Normalize requested names, keep EDF order, and warn on missing
            requested = [str(n).strip() for n in self.ch_names if n]
            requested_set = set(requested)
            filtered = [ch for ch in base_ch_names if ch in requested_set]
            missing = [ch for ch in requested if ch not in base_ch_names]
            if missing:
                self.logger.warning(f"Requested channels not found in recording and will be ignored: {missing}")
            if filtered:
                base_ch_names = filtered
            else:
                self.logger.warning("None of the requested channels were found. Falling back to all channels in the EDF.")

        channels_to_load, self.channel_groups, self.has_eog = self._get_load_and_group_channels(base_ch_names)
        print(f"Found {len(self.channel_groups)} channel groups.")

        self.raw.pick(channels_to_load)
        self.raw.load_data()
            
        original_sample_rate = self.raw.info['sfreq']
        psg_data = self.raw.get_data().T.astype(np.float64)

        n_samples_in_epoch_original = int(self.epoch_sec * original_sample_rate)
        n_epochs = len(psg_data) // n_samples_in_epoch_original
        psg_data = psg_data[:n_epochs * n_samples_in_epoch_original]

        for i in range(psg_data.shape[1]):
            channel_data = psg_data[:, i]
            p_25 = np.percentile(channel_data, 25)
            p_75 = np.percentile(channel_data, 75)
            iqr = p_75 - p_25
            threshold = 20 * iqr
            psg_data[:, i] = np.clip(channel_data, -threshold, threshold)

        psg_data_resampled = resample_poly(psg_data, self.new_sample_rate, int(original_sample_rate), axis=0)

        psg_data_scaled = np.empty_like(psg_data_resampled, dtype=np.float64)
        for i in range(psg_data_resampled.shape[1]):
            psg_data_scaled[:, i] = self._robust_scale_channel(psg_data_resampled[:, i])
        
        n_samples_in_epoch_final = self.epoch_sec * self.new_sample_rate
        n_epochs_final = len(psg_data_scaled) // n_samples_in_epoch_final
        psg_data_scaled = psg_data_scaled[:n_epochs_final * n_samples_in_epoch_final]
        
        self.preprocessed_psg = psg_data_scaled.reshape(n_epochs_final, n_samples_in_epoch_final, -1).astype(np.float32)
        
        print(f"Study preprocessed successfully. Shape: {self.preprocessed_psg.shape}")




    def _predict(self, batch_size: int = 64):
        """
        Sleepyland-aligned prediction:
        - Window size = model input length (e.g., 35 epochs)
        - Stride (margin) = window_size // 2 (e.g., 17)  → 50% overlap
        - Always include a final window starting at N - L to ensure full tail coverage
        - Coverage-based averaging over overlapping window predictions
        """

        input_name = self.session.get_inputs()[0].name
        output_name = self.session.get_outputs()[0].name

        window_size = int(self.session.get_inputs()[0].shape[1])      # L (epochs per window; fixed to 35)
        n_epochs_total = int(self.preprocessed_psg.shape[0])          # N (total epochs)
        samples_per_epoch = int(self.preprocessed_psg.shape[1])       # S
        n_classes = int(self.session.get_outputs()[0].shape[-1])      # C_out

        margin = window_size // 2
        group_probabilities = []

        for i, channel_group in enumerate(self.channel_groups):
            
            self.logger.info(f"Predicting on group {i+1}/{len(self.channel_groups)}: {channel_group.channel_names}")

            # [N, S, C_in]
            psg_subset = self.preprocessed_psg[:, :, tuple(channel_group.channel_indices)].astype(np.float32)
            n_channels = psg_subset.shape[-1]

            prob_sum = np.zeros((n_epochs_total, n_classes), dtype=np.float32)
            coverage = np.zeros(n_epochs_total, dtype=np.int32)

            if n_epochs_total <= window_size:
                # Short recording: single padded window
                diff = window_size - n_epochs_total
                pad = np.zeros((diff, samples_per_epoch, n_channels), dtype=np.float32) if diff > 0 else None
                window = psg_subset if diff == 0 else np.concatenate([psg_subset, pad], axis=0)
                batch = np.expand_dims(window, 0)  # [1, L, S, C]
                pred = self.session.run([output_name], {input_name: batch})[0][0]  # [L, C]
                pred = pred[:n_epochs_total]  # trim padding
                prob_sum += pred
                coverage += 1
            else:
                # Build starts with stride=margin AND force a final start at N-L
                last_start = n_epochs_total - window_size
                starts = list(range(0, last_start + 1, margin))
                if starts[-1] != last_start:
                    starts.append(last_start)  # ensure tail coverage exactly like sleepyland

                n_windows = len(starts)
                print(f"Total windows to process: {n_windows} (stride={margin}); forcing final start at {last_start}")

                # Build windows as a dense stack (safer than strided view when stride!=1)
                # Shape: [n_windows, L, S, C]
                windows = np.stack([psg_subset[s:s + window_size] for s in starts], axis=0)

                # Batched inference
                for start_idx in range(0, n_windows, batch_size):
                    end_idx = min(start_idx + batch_size, n_windows)
                    batch = windows[start_idx:end_idx]  # [B, L, S, C]
                    pred_batch = self.session.run([output_name], {input_name: batch})[0]  # [B, L, C]

                    # Accumulate predictions into epoch space with coverage counts
                    for j in range(end_idx - start_idx):
                        s = starts[start_idx + j]
                        e = s + window_size
                        prob_sum[s:e] += pred_batch[j]
                        coverage[s:e] += 1

            # Normalize by coverage (triangular divisor)
            group_probs = prob_sum / np.maximum(coverage[:, None], 1e-7)
            group_probabilities.append(group_probs)

        # Ensemble average across channel groups
        self.probabilities = np.mean(np.stack(group_probabilities, axis=0), axis=0)  # [N, C]
        self.hypnogram = self.probabilities.argmax(-1)

        return self.hypnogram, self.probabilities


    def _postprocess(self):
        # Remap stages: 4 -> 5 (REM)
        hypnogram_intermediate = self.hypnogram
        hypnogram_final = np.copy(hypnogram_intermediate)
        hypnogram_final[hypnogram_intermediate == 4] = 5
        self.hypnogram = hypnogram_final

    def _save_results(self):
        """Saves the hypnogram and probabilities to files."""
        print(f"Saving results to {self.output_dir}...")
        
        # save hypnogram to file
        hypnogram_csv_file = self.output_dir / f"{self.base_filename}_hypnogram.csv"
        with open(hypnogram_csv_file, 'w') as f:
            f.write("sleep_stage\n")
            for stage in self.hypnogram:
                f.write(f"{int(stage)}\n")

        # save probabilities
        prob_csv_file = self.output_dir / f"{self.base_filename}_probabilities.csv"
        with open(prob_csv_file, 'w') as f:
            header = "Epoch,Wake,N1,N2,N3,REM,Art\n"
            f.write(header)
            for i, probs in enumerate(self.probabilities):
                prob_str = ",".join(f"{p:.6f}" for p in probs)
                f.write(f"{i},{prob_str},0.000000\n")
        
        print(f"Hypnogram saved to {hypnogram_csv_file}")
        print(f"Probabilities saved to {prob_csv_file}")

    def _parse_channel(self, name: str) -> Dict[str, Any]:
        """
        Parses a channel name and extracts its core properties into a dictionary.
        """
        name_stripped = name.strip()
        upper = name_stripped.upper()
        
        prefix_stripped = re.sub(r'^(EEG|EOG|EMG)\s', '', name_stripped, flags=re.IGNORECASE)
        base, subs = re.subn(r'[:\-]?(A1|A2|M1|M2)$', '', prefix_stripped, flags=re.IGNORECASE)
        base = base.strip().upper()
        base = upper if upper in MASTOIDS else base

        search_name = name_stripped.upper()
        ch_type = 'OTHER'

        # Classify based on unambiguous patterns. Selection logic will handle fallbacks.
        if any(p in search_name for p in UNAMBIGUOUS_EOG_PATTERNS):
            ch_type = 'EOG'
        elif base in EEG_BASES or ('EEG' in search_name and not any(o in search_name for o in OTHER_NON_EEG)):
            ch_type = 'EEG'
        elif base in MASTOIDS:
            ch_type = 'MASTOID'

        return {'name': name_stripped, 'base': base, 'type': ch_type, 'has_mastoid_ref': bool(subs)}

    def _get_load_and_group_channels(self, ch_names: List[str]) -> Tuple[List[str], List[namedtuple], bool]:
        """
        Identifies, selects, and groups channels from a list of channel names.
        """
        ChannelSet = namedtuple("ChannelSet", ["channel_names", "channel_indices"])
        parsed_channels = [self._parse_channel(name) for name in ch_names]
        
        channels_by_base = OrderedDict()
        for ch in parsed_channels:
            channels_by_base.setdefault(ch['base'], []).append(ch)

        unique_channels = []
        for base, candidates in channels_by_base.items():
            if len(candidates) == 1:
                unique_channels.append(candidates[0])
                continue
            
            # Prefer channel with mastoid ref for EEG, without for EOG
            is_eog = any(c['type'] == 'EOG' for c in candidates)
            preference = not is_eog
            best = next((c for c in candidates if c['has_mastoid_ref'] == preference), candidates[0])
            unique_channels.append(best)

        # --- EOG Selection using Preference Order ---
        eeg_channels = [ch for ch in unique_channels if ch['type'] == 'EEG']
        eog_channels = [ch for ch in unique_channels if ch['type'] == 'EOG']
        
        # Candidates for EOG can be actual EOG channels or fallback EEG channels
        eog_candidates = eog_channels + eeg_channels
        
        selected_eog = []
        if eog_candidates:
            for pref in EOG_BASES:
                matches = [ch for ch in eog_candidates if pref in ch['name'].upper()]
                if matches:
                    selected_eog = matches
                    break
        
        # --- Final Channel List Construction ---
        selected_eog_names = {ch['name'] for ch in selected_eog}
        
        # EEG channels are those not chosen to be EOGs
        final_eeg_channels = [ch for ch in eeg_channels if ch['name'] not in selected_eog_names]
        
        scoring_channels = final_eeg_channels + selected_eog
        
        if not scoring_channels:
            scoring_channels = [ch for ch in unique_channels if ch['type'] not in ('OTHER', 'MASTOID')]
            if not scoring_channels: scoring_channels = unique_channels

        eog_detected = bool(selected_eog)

        # --- Grouping Logic ---
        if self.auto_channel_grouping:
            spec = [s.upper() for s in self.auto_channel_grouping if s.upper() != 'MASTOID']
            
            ch_by_type = {}
            # Re-classify channels for grouping now that selection is done
            for ch in scoring_channels:
                final_type = 'EOG' if ch['name'] in selected_eog_names else 'EEG'
                ch_by_type.setdefault(final_type, []).append(ch['name'])

            if not eog_detected:
                spec = ['EEG']

            groups_to_combine = [ch_by_type[t] for t in spec if t in ch_by_type]
            
            if not groups_to_combine:
                print(f"Warning: Could not find any channels of types {spec} for grouping. Defaulting to all available channels as individual groups.")
                channel_groups = [[ch['name']] for ch in scoring_channels]
            else:
                channel_groups = list(product(*groups_to_combine))
            
            # Remove duplicate groups if spec has repeated types (e.g., ['EEG', 'EEG'])
            if len(set(spec)) < len(spec):
                unique_combs = {tuple(sorted(c)) for c in channel_groups}
                channel_groups = sorted(list(unique_combs))
        else:
            channel_groups = [[ch['name'] for ch in scoring_channels]] if scoring_channels else []

        if not channel_groups:
            return [], [], eog_detected

        all_to_load = list(OrderedDict.fromkeys(ch for group in channel_groups for ch in group))
        final_groups = [
            ChannelSet(list(group), [all_to_load.index(ch) for ch in group])
            for group in channel_groups
        ]

        return all_to_load, final_groups, eog_detected

    def _robust_scale_channel(self,x):
        median = np.nanmedian(x, axis=0, keepdims=True)
        q25 = np.nanpercentile(x, 25, axis=0, keepdims=True)
        q75 = np.nanpercentile(x, 75, axis=0, keepdims=True)
        iqr = q75 - q25
        iqr[iqr == 0] = 1.0
        return (x - median) / iqr
    
    def _softmax(self, x: np.ndarray, axis: int = -1) -> np.ndarray:
        """NumPy implementation of softmax"""
        exp_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
        return exp_x / np.sum(exp_x, axis=axis, keepdims=True)
