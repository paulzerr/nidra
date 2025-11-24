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

class PSGScorer:
    def __init__(self, input = None, output: str = None, channels: list = None, 
                 sfreq: float = None, model: str = "u-sleep-nsrr-2024",
                 hypnogram: bool = None, hypnodensity: bool = False, plot: bool = False):
        
        self.logger = logging.getLogger(__name__)
        self.data = False
        if hasattr(input, "__array__"):
            self.input = input
            self.data = True
            self.base_filename = "array_input"
        else:
            if input is None:
                raise ValueError("No valid input provided")
            if isinstance(input, (str, Path)) and input.is_dir():
                try:
                    self.input = next(input.glob('*.edf'))
                except StopIteration:
                    raise FileNotFoundError(f"Could not find an EDF file in directory '{input}'.")   
            elif isinstance(input, (str, Path)) and input.is_file():
                self.input = input
            else:
                raise ValueError("No valid input provided")
            self.base_filename = f"{self.input.parent.name}_{self.input.stem}"

        self.model           = model if model is not None else "u-sleep-nsrr-2024"
        self.channels        = channels
        self.sfreq           = sfreq
        self.epoch_sec       = 30 # we ignore this input for now and enforce 30s epochs
        self.hypnodensity    = hypnodensity
        self.plot            = plot

        # if hypnogram was not specifically requested and input is data, then don't create it
        if hypnogram is None:
            self.hypnogram = False if self.data else True
        else:
            self.hypnogram = hypnogram
        
        # if output file is requested, but no output folder is given, use input folder
        if self.hypnogram or self.hypnodensity or self.plot:
            if output is None:
                if not self.data:
                    output = self.input.parent / "autoscorer_output"
                else:
                    raise ValueError("output must be specified when saving files for in-memory data input.")
            self.output = Path(output)
            self.output.mkdir(parents=True, exist_ok=True)

    def score(self):
        self._load_recording()
        self._preprocess()
        self._load_model()
        self._predict()
        self._postprocess()
        self._save_results()
        self._make_plot()
        return self.sleep_stages, self.probabilities

    def _load_recording(self):
        print(f"Loading data...")
        if self.data:
            if self.input.ndim != 2:
                raise ValueError("Input data must be a 2D array.")
            if self.sfreq is None:
                raise ValueError("'sfreq' must be provided when 'data' is given.")
            self.input = np.asarray(self.input, dtype=np.float64)
            # name channels if no names given
            n_channels = self.input.shape[0]
            if self.channels is None: 
                self.channels = [f"Ch{i+1:02d}" for i in range(n_channels)]
            # make raw mne object from the numpy array
            info = mne.create_info(channels=self.channels, sfreq=self.sfreq, ch_types='eeg', verbose=False)
            self.raw = mne.io.RawArray(self.input, info, verbose=False)
            print(f"Array data loaded.")
        else:
            try:
                self.raw = mne.io.read_raw_edf(self.input, preload=False, verbose=False, stim_channel=None)
            except ValueError:
                self.raw = mne.io.read_raw_bdf(self.input, preload=False, verbose=False, stim_channel=None)
            print(f"Data loaded from {self.input}...")

    def _load_model(self):
        if self.has_eog:
            model_filename = self.model + ".onnx"
            print(f"EOG channel(s) found, loading model {model_filename}...")
        else:
            model_filename = self.model + "_eeg.onnx"
            print(f"No EOG channels found, loading EEG-only model: {model_filename}")
        
        model_path = utils.get_model_path(model_filename)
        try:
            self.session = ort.InferenceSession(model_path)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            print(f"Model loaded: '{model_path}'")
        except Exception as e:
            print(f"Error: Failed to load ONNX model from '{model_path}'. Original error: {e}")
            raise

    def _preprocess(self):
        target_sf = 128
        # Respect user-selected channels if provided; otherwise use all channels
        base_channels = list(self.raw.ch_names)
        if self.channels:
            # Normalize requested names, keep EDF order, and warn on missing
            requested = [str(n).strip() for n in self.channels if n]
            requested_set = set(requested)
            filtered = [ch for ch in base_channels if ch in requested_set]
            missing = [ch for ch in requested if ch not in base_channels]
            if missing:
                self.logger.warning(f"Requested channels not found in recording and will be ignored: {missing}")
            if filtered:
                base_channels = filtered
            else:
                self.logger.warning("None of the requested channels were found. Falling back to all channels in the EDF.")

        channels_to_load, self.channel_groups, self.has_eog = self._get_load_and_group_channels(base_channels)
        self.logger.info(f"Channels selected for scoring: {channels_to_load}")
        print(f"Found {len(self.channel_groups)} channel groups.")

        self.raw.pick(channels_to_load)
        self.raw.load_data()
            
        original_sample_rate = self.raw.info['sfreq']
        psg_data = self.raw.get_data().T.astype(np.float64)

        n_samples_in_epoch_original = int(self.epoch_sec * original_sample_rate)
        n_epochs = len(psg_data) // n_samples_in_epoch_original
        psg_data = psg_data[:n_epochs * n_samples_in_epoch_original]

        # clip noisy values
        for i in range(psg_data.shape[1]):
            channel_data = psg_data[:, i]
            iqr = np.nanpercentile(channel_data, 75) - np.nanpercentile(channel_data, 25)
            threshold = 20 * iqr
            psg_data[:, i] = np.clip(channel_data, -threshold, threshold)

        psg_data_resampled = resample_poly(psg_data, target_sf, int(original_sample_rate), axis=0)

        # scale data
        psg_data_scaled = np.empty_like(psg_data_resampled, dtype=np.float64)
        for i in range(psg_data_resampled.shape[1]):
            psg_data_scaled[:, i] = self._robust_scale_channel(psg_data_resampled[:, i])
        
        n_samples_in_epoch_final = self.epoch_sec * target_sf
        n_epochs_final = len(psg_data_scaled) // n_samples_in_epoch_final
        psg_data_scaled = psg_data_scaled[:n_epochs_final * n_samples_in_epoch_final]
        
        self.preprocessed_psg = psg_data_scaled.reshape(n_epochs_final, n_samples_in_epoch_final, -1).astype(np.float32)
    
    # alternative predict function that uses overlapping windows.
    # this might have higher accuracy, but does not align well with the original sleepyland/usleep implementation
    # def _predict(self):
    #     print(f"Prediction started.")
    #     window_size = int(self.session.get_inputs()[0].shape[1])      # L (epochs per window; fixed to 35)
    #     n_epochs_total = int(self.preprocessed_psg.shape[0])          # N (total epochs)
    #     samples_per_epoch = int(self.preprocessed_psg.shape[1])       # S
    #     n_classes = int(self.session.get_outputs()[0].shape[-1])      # C_out
    #     batch_size = 64
    #     margin = window_size // 2
    #     group_probabilities = []

    #     for i, channel_group in enumerate(self.channel_groups):
            
    #         self.logger.info(f"Predicting on group {i+1}/{len(self.channel_groups)}: {channel_group.channel_names}")

    #         # [N, S, C_in]
    #         psg_subset = self.preprocessed_psg[:, :, tuple(channel_group.channel_indices)].astype(np.float32)
    #         n_channels = psg_subset.shape[-1]

    #         prob_sum = np.zeros((n_epochs_total, n_classes), dtype=np.float32)
    #         coverage = np.zeros(n_epochs_total, dtype=np.int32)

    #         if n_epochs_total <= window_size:
    #             # Short recording: single padded window
    #             diff = window_size - n_epochs_total
    #             pad = np.zeros((diff, samples_per_epoch, n_channels), dtype=np.float32) if diff > 0 else None
    #             window = psg_subset if diff == 0 else np.concatenate([psg_subset, pad], axis=0)
    #             batch = np.expand_dims(window, 0)  # [1, L, S, C]
    #             pred = self.session.run([self.output_name], {self.input_name: batch})[0][0]  # [L, C]
    #             pred = pred[:n_epochs_total]  # trim padding
    #             prob_sum += pred
    #             coverage += 1
    #         else:
    #             # Build starts with stride=margin AND force a final start at N-L
    #             last_start = n_epochs_total - window_size
    #             starts = list(range(0, last_start + 1, margin))
    #             if starts[-1] != last_start:
    #                 starts.append(last_start)
    #             n_windows = len(starts)

    #             # Build windows as a dense stack
    #             # Shape: [n_windows, L, S, C]
    #             windows = np.stack([psg_subset[s:s + window_size] for s in starts], axis=0)

    #             # Batched inference
    #             for start_idx in range(0, n_windows, batch_size):
    #                 end_idx = min(start_idx + batch_size, n_windows)
    #                 batch = windows[start_idx:end_idx]  # [B, L, S, C]
    #                 pred_batch = self.session.run([self.output_name], {self.input_name: batch})[0]  # [B, L, C]

    #                 # Accumulate predictions into epoch space with coverage counts
    #                 for j in range(end_idx - start_idx):
    #                     s = starts[start_idx + j]
    #                     e = s + window_size
    #                     prob_sum[s:e] += pred_batch[j]
    #                     coverage[s:e] += 1

    #         # Normalize by coverage (triangular divisor)
    #         group_probs = prob_sum / np.maximum(coverage[:, None], 1e-7)
    #         group_probabilities.append(group_probs)

    #     # Ensemble average across channel groups
    #     self.probabilities = np.mean(np.stack(group_probabilities, axis=0), axis=0)  # [N, C]
    #     self.sleep_stages = self.probabilities.argmax(-1)
    #     print(f"Prediction successful.")
    #     return self.sleep_stages, self.probabilities

    def _predict(self):
        print(f"Prediction started.")
        window_size = int(self.session.get_inputs()[0].shape[1])      # L (epochs per window; fixed to 35)
        n_epochs_total = int(self.preprocessed_psg.shape[0])          # N (total epochs)
        samples_per_epoch = int(self.preprocessed_psg.shape[1])       # S
        n_classes = int(self.session.get_outputs()[0].shape[-1])      # C_out
        batch_size = 64
        margin = window_size // 2
        group_probabilities = []

        for i, channel_group in enumerate(self.channel_groups):
            
            self.logger.info(f"Predicting on group {i+1}/{len(self.channel_groups)}: {channel_group.channel_names}")

            # [N, S, C_in]
            psg_subset = self.preprocessed_psg[:, :, tuple(channel_group.channel_indices)].astype(np.float32)
            n_channels = psg_subset.shape[-1]

            # --- Non-overlapping windows (Old Method) ---
            if n_epochs_total <= window_size:
                diff = window_size - n_epochs_total
                pad = np.zeros((diff, samples_per_epoch, n_channels), dtype=np.float32) if diff > 0 else None
                window = psg_subset if diff == 0 else np.concatenate([psg_subset, pad], axis=0)
                batch = np.expand_dims(window, 0)  # [1, L, S, C]
                pred = self.session.run([self.output_name], {self.input_name: batch})[0][0]  # [L, C]
                group_probs = pred[:n_epochs_total]
            else:
                preds = []
                # Calculate starts for non-overlapping windows
                starts = range(0, n_epochs_total, window_size)
                
                for s in starts:
                    e = s + window_size
                    if e <= n_epochs_total:
                        # Full window
                        window = psg_subset[s:e]
                        batch = np.expand_dims(window, 0)
                        pred_batch = self.session.run([self.output_name], {self.input_name: batch})[0][0]
                        preds.append(pred_batch)
                    else:
                        # Partial final window - grab last window_size epochs
                        last_window = psg_subset[-window_size:]
                        batch = np.expand_dims(last_window, 0)
                        pred_batch = self.session.run([self.output_name], {self.input_name: batch})[0][0]
                        # Only take the part that corresponds to the remaining epochs
                        remaining = n_epochs_total - s
                        preds.append(pred_batch[-remaining:])
                
                group_probs = np.concatenate(preds, axis=0)

            group_probabilities.append(group_probs)

        # Ensemble average across channel groups
        self.probabilities = np.mean(np.stack(group_probabilities, axis=0), axis=0)  # [N, C]
        self.sleep_stages = self.probabilities.argmax(-1)
        print(f"Prediction successful.")
        return self.sleep_stages, self.probabilities

    def _postprocess(self):
        # Remap stages: 4 -> 5 (REM)
        self.sleep_stages[self.sleep_stages == 4] = 5


    def _save_results(self):
        
        if self.hypnogram:
            hypnogram_path = self.output / f"{self.base_filename}_hypnogram.csv"
            with open(hypnogram_path, 'w') as f:
                f.write("sleep_stage\n")
                for stage in self.sleep_stages:
                    f.write(f"{int(stage)}\n")
            print(f"Sleep stages saved to: '{hypnogram_path}'")

        if self.hypnodensity:
            hypnodensity_path = self.output / f"{self.base_filename}_hypnodensity.csv"
            with open(hypnodensity_path, 'w') as f:
                header = "Epoch,Wake,N1,N2,N3,REM,Art\n"
                f.write(header)
                for i, probs in enumerate(self.probabilities):
                    prob_str = ",".join(f"{p:.6f}" for p in probs)
                    f.write(f"{i},{prob_str},0.000000\n")
            print(f"Classifier probabilities (hypnodensity) saved to: '{hypnodensity_path}'")

    def _make_plot(self):
        if self.plot:
            plot_filename = f"{self.base_filename}_figure.png"
            plot_hypnodensity(
                hyp=self.sleep_stages,
                ypred=self.probabilities,
                raw=self.raw,
                nclasses=self.probabilities.shape[1],
                figoutdir=self.output,
                filename=plot_filename,
                type='psg'
            )
            print(f"Figure saved to {self.output / plot_filename}")


    def _parse_channel(self, name: str) -> Dict[str, Any]:
        """
        Parses a channel name and extracts its core properties into a dictionary.
        """

        # --- Channel Definitions ---
        MASTOIDS      = {'A1', 'A2', 'M1', 'M2'}
        EEG_BASES     = {'FP1', 'FP2', 'F3', 'F4', 'C3', 'C4', 'P3', 'P4', 
                        'O1', 'O2', 'F7', 'F8', 'T3', 'T4', 'T5', 'T6', 'FZ', 
                        'CZ', 'PZ', 'F1', 'F2'}
        EOG_PATTERNS  = {'EOG', 'LOC', 'ROC', 'E1', 'E2'}
        EOG_BASES     = ('EOG', 'OC', 'E1', 'E2')
        OTHER_NON_EEG = {'EMG', 'ECG', 'EKG'}

        # TODO: one line?
        name_stripped = name.strip()
        upper = name_stripped.upper()
        
        prefix_stripped = re.sub(r'^(EEG|EOG|EMG)\s', '', name_stripped, flags=re.IGNORECASE)
        base, subs = re.subn(r'[:\-]?(A1|A2|M1|M2)$', '', prefix_stripped, flags=re.IGNORECASE)
        base = base.strip().upper()
        base = upper if upper in MASTOIDS else base

        search_name = name_stripped.upper()
        ch_type = 'OTHER'

        # Classify based on unambiguous patterns. Selection logic will handle fallbacks.
        if any(p in search_name for p in EOG_PATTERNS):
            ch_type = 'EOG'
        elif base in EEG_BASES or ('EEG' in search_name and not any(o in search_name for o in OTHER_NON_EEG)):
            ch_type = 'EEG'
        elif base in MASTOIDS:
            ch_type = 'MASTOID'

        return {'name': name_stripped, 'base': base, 'type': ch_type, 'has_mastoid_ref': bool(subs)}

    def _get_load_and_group_channels(self, channels: List[str]) -> Tuple[List[str], List[namedtuple], bool]:
        """
        Identifies, selects, and groups channels from a list of channel names.
        """
        EOG_BASES     = ('EOG', 'OC', 'E1', 'E2')

        ChannelSet = namedtuple("ChannelSet", ["channel_names", "channel_indices"])
        parsed_channels = [self._parse_channel(name) for name in channels]
        
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
        spec = [s.upper() for s in ['EEG', 'EOG'] if s.upper() != 'MASTOID']
        
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
