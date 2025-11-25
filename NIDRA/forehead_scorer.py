import re
import mne
import numpy as np
import logging
from pathlib import Path
import onnxruntime as ort
from NIDRA.plotting import plot_hypnodensity
from NIDRA import utils

class ForeheadScorer:
    def __init__(self, input = None, output: str = None, channels: list = None,
                 sfreq: float = None, model: str = "ez6moe",
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
            if isinstance(input, str):
                input = Path(input)
            if isinstance(input, Path) and input.is_dir():
                mode, single_edf = self._detect_forehead_mode(input)
                self.input = single_edf
                self.forehead_mode = mode
            elif isinstance(input, Path) and input.is_file():
                mode, single_edf = self._detect_forehead_mode(input)
                self.input = single_edf
                self.forehead_mode = mode
            else:
                raise ValueError("No valid input provided")
            self.base_filename = f"{self.input.parent.name}_{self.input.stem}"

        # Core configuration
        self.model_name   = model
        self.sfreq        = sfreq
        self.channels     = channels
        self.epoch_size   = 30 # we ignore this input for now and enforce 30s epochs
        self.target_fs    = 64 # has to stay hardcoded!
        self.hypnodensity = hypnodensity
        self.plot         = plot

        # if hypnogram was not specifically requested and input is data, then don't create it
        if hypnogram is None:
            self.hypnogram = False if self.data else True
        else:
            self.hypnogram = hypnogram

        # if output file is requested, but no output folder is given, use input folder
        if self.hypnogram or self.hypnodensity or self.plot:
            if output is None:
                if not self.data:
                    output = Path(self.input.parent) / "autoscorer_output"
                else:
                    raise ValueError("output must be specified when saving files for in-memory data input.")
            self.output = Path(output)
            self.output.mkdir(parents=True, exist_ok=True)

    def score(self):
        self._load_model()
        self._load_recording()
        self._preprocess()
        self._predict()
        self._postprocess()
        self._save_results()
        self._make_plot()
        return self.sleep_stages, self.probabilities

    def _detect_forehead_mode(self, input_path: Path):
        if input_path.is_dir():
            edf_files = sorted(input_path.glob("*.edf"))
            if not edf_files:
                raise FileNotFoundError(f"Could not find an EDF file in directory '{input_path}'.")
            for f in edf_files:
                if re.search(r'(?i)([_\s]?)L\.edf$', f.name):
                    candidate_r = f.with_name(re.sub(r'(?i)([_\s]?)L\.edf$', r'\1R.edf', f.name))
                    if candidate_r.exists():
                        return 'two_files', f
            return 'one_file', edf_files[0]
        else:
            name_str = str(input_path)
            if re.search(r'(?i)([_ ])?L\.edf$', name_str):
                candidate_r = Path(re.sub(r'(?i)([_ ])?L\.edf$', r'\1R.edf', name_str))
                if candidate_r.exists():
                    return 'two_files', input_path
            if re.search(r'(?i)([_ ])?R\.edf$', name_str):
                candidate_l = Path(re.sub(r'(?i)([_ ])?R\.edf$', r'\1L.edf', name_str))
                if candidate_l.exists():
                    return 'two_files', candidate_l
            return 'one_file', input_path

    def _load_recording(self):
        print(f"Loading data...")
        # array input mode
        if self.data:
            if self.input.ndim != 2 or self.input.shape[0] != 2:
                raise ValueError("Input data must be a 2D array with 2 channels.")
            if self.sfreq is None:
                raise ValueError("'sfreq' must be provided when array input is given.")
            data = np.asarray(self.input, dtype=np.float64)
            info = mne.create_info(['eegl', 'eegr'], sfreq=float(self.sfreq),
                                   ch_types=['eeg', 'eeg'], verbose=False)
            raw = mne.io.RawArray(data, info, verbose=False)
            raw.resample(self.target_fs, verbose=False)
            raw.filter(l_freq=0.5, h_freq=None, verbose=False)
            self.raw = raw
            print(f"Array data loaded.")
            return

        # Two-file mode, expects *R.edf and *L.edf in same folder 
        if self.forehead_mode == 'two_files':
            rawL = mne.io.read_raw_edf(self.input, preload=True, verbose=False)
            rawR_path = Path(re.sub(r'(?i)([_ ])?L\.edf$', r'\1R.edf', str(self.input)))
            if not rawR_path.exists():
                raise FileNotFoundError(f"Could not find corresponding RIGHT channel file at {rawR_path}")
            rawR = mne.io.read_raw_edf(rawR_path, preload=True, verbose=False)
            rawL.resample(self.target_fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)
            rawR.resample(self.target_fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)
            dataL = rawL.get_data().flatten()
            dataR = rawR.get_data().flatten()
            info = mne.create_info(['eegl', 'eegr'], sfreq=self.target_fs,
                                   ch_types=['eeg', 'eeg'], verbose=False)
            self.raw = mne.io.RawArray(np.vstack([dataL, dataR]), info, verbose=False)
            self.logger.info(f"Using channel '{rawL.ch_names[0]}' from {self.input.name} and '{rawR.ch_names[0]}' from {rawR_path.name}")
            print(f"Loading data from: '{self.input}'")
            return

        # one-file mode , expects single edf with 2+ channels 
        if self.forehead_mode == 'one_file':
            raw = mne.io.read_raw_edf(self.input, preload=True, verbose=False)

            # if channel names are not provided, 
            # default to the first two channels with 'eeg' in the name
            # otherwise, default to the first two
            if self.channels is None:
                chs = raw.ch_names
                eeg_like = [ch for ch in chs if 'eeg' in ch.lower()]
                chosen = eeg_like[:2] if len(eeg_like) >= 2 else chs[:2]
                if len(chosen) < 2:
                    raise ValueError("Could not find at least two channels in the EDF file.")
                self.channels = chosen
            
            self.logger.info(f"Channels selected for scoring: {self.channels}")

            # if not exactly two channel names are provided, return error
            if len(self.channels) != 2:
                raise ValueError("Please provide exactly two channel names for one-file mode.")

            raw.pick(self.channels)
            raw.rename_channels({self.channels[0]: 'eegl', self.channels[1]: 'eegr'})
            raw.resample(self.target_fs, verbose=False)
            raw.filter(l_freq=0.5, h_freq=None, verbose=False)

            self.raw = raw
            print(f"Loading data from: '{self.input}'")
            return
            
    def _load_model(self):
        model_filename = f"{self.model_name}.onnx"
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
        seq_length = 100
        sdata = self.raw.get_data()
        for ch in range(sdata.shape[0]):
            sig = sdata[ch]
            mad = np.median(np.abs(sig - np.median(sig)))
            if mad == 0: mad = 1
            norm = (sig - np.median(sig)) / mad
            iqr = np.subtract(*np.percentile(norm, [75, 25]))
            sdata[ch] = np.clip(norm, -20 * iqr, 20 * iqr)
        self.raw._data = sdata
        data_as_array = self.raw.get_data()
        if data_as_array.ndim != 2:
            raise ValueError("Input data must be a 2D array.")
        if data_as_array.shape[0] > data_as_array.shape[1]:
            data_as_array = data_as_array.T
        num_channels, epoch_length = data_as_array.shape[0], self.epoch_size * self.target_fs
        num_epochs = int(np.floor(data_as_array.shape[1] / epoch_length))
        epoched_data = np.full((num_channels, num_epochs, epoch_length), np.nan)
        tidxs = np.arange(0, data_as_array.shape[1] - epoch_length + 1, epoch_length)
        for ch_idx in range(num_channels):
            for e_idx, tidx in enumerate(tidxs):
                epoched_data[ch_idx, e_idx, :] = data_as_array[ch_idx, tidx:tidx + epoch_length]
        num_full_seqs, remainder_epochs = divmod(num_epochs, seq_length)
        num_seqs = num_full_seqs + (1 if remainder_epochs > 0 else 0)
        seqdat = np.full((num_seqs, seq_length, epoched_data.shape[2], epoched_data.shape[0]), np.nan, dtype=np.float32)
        for ct in range(num_full_seqs):
            idx_start, idx_end = ct * seq_length, (ct + 1) * seq_length
            seqdat[ct, :, :, :] = np.transpose(epoched_data[:, idx_start:idx_end, :], (1, 2, 0))
        if remainder_epochs > 0:
            idx_start = num_full_seqs * seq_length
            seqdat[num_full_seqs, :remainder_epochs, :, :] = np.transpose(epoched_data[:, idx_start:, :], (1, 2, 0))
        self.processed_data, self.num_full_seqs = seqdat, num_full_seqs

    def _predict(self):
        print(f"Prediction started...")
        seq_length = 100
        last_seq = self.processed_data[-1]
        last_seq_valid_epochs = int(np.sum(~np.isnan(last_seq.sum(axis=(1, 2)))))
        if last_seq_valid_epochs == seq_length:
            raw_predictions = self.session.run(None, {self.input_name: self.processed_data.astype(np.float32)})[0].reshape(-1, 6)
        else:
            ypred_main = self.session.run(None, {self.input_name: self.processed_data[:self.num_full_seqs].astype(np.float32)})[0].reshape(-1, 6)
            valid_last_seq = last_seq[:last_seq_valid_epochs]
            valid_last_seq = np.expand_dims(valid_last_seq, axis=0)
            ypred_tail = self.session.run(None, {self.input_name: valid_last_seq.astype(np.float32)})[0].reshape(-1, 6)
            raw_predictions = np.concatenate([ypred_main, ypred_tail], axis=0)
        self.raw_predictions = raw_predictions
        print(f"Prediction successful.")

    def _postprocess(self):
        # get number of complete 30-second epochs that exist in the raw EEG recording
        num_epochs = int(np.floor(self.raw.get_data().shape[1] / (self.epoch_size * self.target_fs)))
        # truncate predictions to match number of full epochs in recording
        ypred_raw = self.raw_predictions[:num_epochs, :]
        # reorder model output to fit standard sleep stage order
        reorder_indices = [4, 2, 1, 0, 3, 5]
        self.probabilities = ypred_raw[:, reorder_indices]
        self.sleep_stages = np.argmax(self.probabilities, axis=1)
        # shift A+R classes by 1 to avoid confusion (4 is now unassigned, was traditionally N4)
        self.sleep_stages[self.sleep_stages == 5] = 6 # artefact class
        self.sleep_stages[self.sleep_stages == 4] = 5 # REM 
    
    def _save_results(self):
        
        if self.hypnogram:
            hypnogram_path = self.output / f"{self.base_filename}_hypnogram.csv"
            with open(hypnogram_path, 'w') as f:
                f.write("sleep_stage\n")
                np.savetxt(f, self.sleep_stages, delimiter=",", fmt="%d")
            print(f"Sleep stages saved to: '{hypnogram_path}'")

        if self.hypnodensity:
            hypnodensity_path = self.output / f"{self.base_filename}_hypnodensity.csv"
            with open(hypnodensity_path, 'w') as f:
                header = "Epoch,Wake,N1,N2,N3,REM,Art\n"
                f.write(header)
                for i, probs in enumerate(self.probabilities):
                    prob_str = ",".join(f"{p:.6f}" for p in probs)
                    f.write(f"{i},{prob_str}\n")
            print(f"Classifier probabilities (hypnodensity) saved to: '{hypnodensity_path}'")
                
    def _make_plot(self):
        if self.plot:
            plot_filename = f"{self.base_filename}_graph.png"
            plot_hypnodensity(
                hyp=self.sleep_stages,
                ypred=self.probabilities,
                raw=self.raw,
                nclasses=self.probabilities.shape[1],
                figoutdir=self.output,
                filename=plot_filename,
                type='forehead'
            )
            print(f"Figure saved to {self.output / plot_filename}")

