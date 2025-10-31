import re
import mne
import numpy as np
from pathlib import Path
import onnxruntime as ort
from NIDRA.plotting import plot_hypnodensity
from NIDRA import utils

class ForeheadScorer:
    """
    Scores sleep stages from forehead EEG data.
    """
    def __init__(self, input_file: str = None, output_dir: str = None, data: np.ndarray = None,
                 sfreq: float = None, model_name: str = "ez6",
                 zmax_mode: str = 'two_files', ch_names: list = None,
                 create_output_files: bool = None):
        if input_file is None and data is None:
            raise ValueError("Either 'input_file' or 'data' must be provided.")
        if data is not None and sfreq is None:
            raise ValueError("'sfreq' must be provided when 'data' is given.")

        if input_file:
            input_path = Path(input_file)
            
            # Handle 'one_file' mode first as it's simpler
            if zmax_mode == 'one_file':
                if input_path.is_dir():
                    input_dir = input_path
                    try:
                        self.input_file = next(input_path.glob('*.edf'))
                    except StopIteration:
                        raise FileNotFoundError(f"Could not find an EDF file in directory '{input_path}'.") from None
                else:
                    input_dir = input_path.parent
                    self.input_file = input_path
            
            # Handle 'two_files' mode
            else: # zmax_mode in [None, 'two_files']
                if input_path.is_dir():
                    input_dir = input_path
                    l_file = next(input_path.glob('*[lL].edf'), None)
                    r_file = next(input_path.glob('*[rR].edf'), None)
                    if not l_file or not r_file:
                        raise FileNotFoundError(f"Could not find a complete L/R recording in directory '{input_path}'.")
                    self.input_file = l_file
                else: # input is a file
                    input_dir = input_path.parent
                    input_file_str = str(input_path)
                    if re.search(r'(?i)[_ ]L\.edf$', input_file_str):
                        l_file = input_path
                        r_file = Path(re.sub(r'(?i)([_ ])L\.edf$', r'\1R.edf', input_file_str))
                    elif re.search(r'(?i)[_ ]R\.edf$', input_file_str):
                        r_file = input_path
                        l_file = Path(re.sub(r'(?i)([_ ])R\.edf$', r'\1L.edf', input_file_str))
                    else:
                        raise FileNotFoundError(f"Input file '{input_path}' is not a valid L or R file for two-file mode.")
                    
                    if not l_file.exists() or not r_file.exists():
                        raise FileNotFoundError(f"Could not find the corresponding pair for '{input_path}'.")
                    self.input_file = l_file

            self.base_filename = f"{self.input_file.parent.name}_{self.input_file.stem}"
        else:
            input_dir = None
            self.input_file = None
            self.base_filename = "numpy_input"

        if output_dir is None:
            if input_dir:
                output_dir = Path(input_dir) / "autoscorer_output"

        if create_output_files is None:
            self.create_output_files = True if input_file else False
        else:
            self.create_output_files = create_output_files

        if output_dir is None and self.create_output_files:
            raise ValueError("output_dir must be specified when create_output_files is True and it cannot be inferred from input_file.")

        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.input_data = data
        self.sfreq = sfreq
        self.model_name = model_name
        self.zmax_mode = zmax_mode
        self.ch_names = ch_names
        self.session = None
        self.input_name = None
        self.output_name = None
        self.hypnogram = None
        self.probabilities = None
        self.raw = None
        self.processed_data = None
        self.num_full_seqs = None
        self.raw_predictions = None
        self.target_fs = 64
        self.epoch_size = 30

        if self.create_output_files:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def score(self, plot: bool = False):
        self._load_model()
        self._load_recording()
        self._preprocess()
        self._predict()
        self._postprocess()
        if self.create_output_files:
            self._save_results()
            if plot:
                self.plot()
        return self.hypnogram, self.probabilities

    def plot(self):
        plot_filename = f"{self.base_filename}_dashboard.png"
        plot_hypnodensity(
            hyp=self.hypnogram,
            ypred=self.probabilities,
            raw=self.raw,
            nclasses=self.probabilities.shape[1],
            figoutdir=self.output_dir,
            filename=plot_filename,
            scorer_type='forehead'
        )
        print(f"Dashboard plot saved to {self.output_dir / plot_filename}")

    def _load_model(self):
        model_filename = f"{self.model_name}.onnx"
        model_path = utils.get_model_path(model_filename)
        try:
            self.session = ort.InferenceSession(model_path)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
        except Exception as e:
            print(f"Error: Failed to load ONNX model from '{model_path}'. Original error: {e}")
            raise

    def _load_recording(self):
        """Load EEG recording from NumPy array or EDF(s), normalize to 2-channel Raw object."""

        #  NumPy array input mode (direct memory)
        if self.input_data is not None:
            data = np.asarray(self.input_data, dtype=np.float64)
            if data.ndim != 2 or data.shape[0] != 2:
                raise ValueError("Input data must be a 2D array with 2 channels.")
            if self.sfreq is None:
                raise ValueError("'sfreq' must be provided when 'data' is given.")
            info = mne.create_info(['eegl', 'eegr'], sfreq=float(self.sfreq),
                                   ch_types=['eeg', 'eeg'], verbose=False)
            raw = mne.io.RawArray(data, info, verbose=False)
            raw.resample(self.target_fs, verbose=False)
            raw.filter(l_freq=0.5, h_freq=None, verbose=False)
            self.raw = raw
            return

        # 'two-file' mode 
        if self.zmax_mode in [None, 'two_files']:
            rawL = mne.io.read_raw_edf(self.input_file, preload=True, verbose=False)
            rawR_path = Path(re.sub(r'(?i)([_ ])L\.edf$', r'\1R.edf', str(self.input_file)))
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
            return

        # one-file mode (two+ channels in one EDF) 
        if self.zmax_mode == 'one_file':
            raw = mne.io.read_raw_edf(self.input_file, preload=True, verbose=False)

            # If channel names are not provided, default to the first two.
            if self.ch_names is None:
                self.ch_names = raw.ch_names[:2]
                if len(self.ch_names) < 2:
                    raise ValueError("Could not find at least two channels in the EDF file.")
            
            if len(self.ch_names) != 2:
                raise ValueError("Please provide exactly two channel names for one-file mode.")

            raw.pick(self.ch_names)
            raw.rename_channels({self.ch_names[0]: 'eegl', self.ch_names[1]: 'eegr'})

            raw.resample(self.target_fs, verbose=False)
            raw.filter(l_freq=0.5, h_freq=None, verbose=False)

            self.raw = raw
            return


    def _predict(self):
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

    def _save_results(self):
        hypnogram_path = self.output_dir / f"{self.base_filename}_hypnogram.csv"
        probabilities_path = self.output_dir / f"{self.base_filename}_probabilities.csv"

        with open(hypnogram_path, 'w') as f:
            f.write("sleep_stage\n")
            np.savetxt(f, self.hypnogram, delimiter=",", fmt="%d")
        with open(probabilities_path, 'w') as f:
            header = "Epoch,Wake,N1,N2,N3,REM,Art\n"
            f.write(header)
            for i, probs in enumerate(self.probabilities):
                prob_str = ",".join(f"{p:.6f}" for p in probs)
                f.write(f"{i},{prob_str}\n")
        
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

    def _postprocess(self):
        # get number of complete 30-second epochs that exist in the raw EEG recording
        num_epochs = int(np.floor(self.raw.get_data().shape[1] / (self.epoch_size * self.target_fs)))
        # truncate predictions to match number of full epochs in recording
        ypred_raw = self.raw_predictions[:num_epochs, :]
        # reorder model output to fit standard sleep stage order
        reorder_indices = [4, 2, 1, 0, 3, 5]
        self.probabilities = ypred_raw[:, reorder_indices]
        self.hypnogram = np.argmax(self.probabilities, axis=1)
        # shift A+R classes by 1 to avoid confusion (4 is now unassigned, was traditionally N4)
        self.hypnogram[self.hypnogram == 5] = 6 # artefact class
        self.hypnogram[self.hypnogram == 4] = 5 # REM 
        


