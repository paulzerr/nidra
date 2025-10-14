import re
import mne
import numpy as np
from pathlib import Path
import onnxruntime as ort
from NIDRA.plotting import plot_hypnodensity
import importlib.resources
from NIDRA import utils

class ForeheadScorer:
    """
    Scores sleep stages from forehead EEG data.
    """
    def __init__(self, output_dir: str, input_file: str = None, data: np.ndarray = None,
                 model_name: str = "ez6", device_type: str = 'zmax',
                 zmax_mode: str = 'two_files', zmax_ch_names: list = None):
        if input_file is None and data is None:
            raise ValueError("Either 'input_file' or 'data' must be provided.")

        self.output_dir = Path(output_dir)
        self.input_data = data
        if input_file:
            self.input_file = Path(input_file)
            self.base_filename = f"{self.input_file.parent.name}_{self.input_file.stem}"
        else:
            self.input_file = None
            self.base_filename = "numpy_input"

        self.model_name = model_name
        self.device_type = device_type
        self.zmax_mode = zmax_mode
        self.zmax_ch_names = zmax_ch_names
        self.session = None
        self.input_name = None
        self.output_name = None
        self.hypnogram = None
        self.probabilities = None
        self.raw = None
        self.processed_data = None
        self.num_full_seqs = None
        self.raw_predictions = None

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def score(self, plot: bool = False):
        self._load_model()
        self._load_recording()
        self._preprocess()
        self._predict()
        self._postprocess()
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
        if utils.get_app_dir():
            try:
                with importlib.resources.path('NIDRA.models', model_filename) as model_file:
                    self.session = ort.InferenceSession(str(model_file))
                self.input_name = self.session.get_inputs()[0].name
                self.output_name = self.session.get_outputs()[0].name
            except FileNotFoundError:
                print(f"Error: Model file not found at NIDRA/models/{model_filename}")
                raise
        else:
            model_path = utils.get_model_path(model_filename)
            self.session = ort.InferenceSession(model_path)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name

    def _load_recording(self):
        fs = 64
        if self.input_data is not None:
            if self.input_data.ndim != 2 or self.input_data.shape[0] != 2:
                raise ValueError("Input data must be a 2D array with 2 channels.")
            info = mne.create_info(['eegl', 'eegr'], sfreq=fs, ch_types=['eeg', 'eeg'], verbose=False)
            self.raw = mne.io.RawArray(self.input_data, info, verbose=False)
            self.raw.filter(l_freq=0.5, h_freq=None, verbose=False)
            return

        if self.device_type == 'zmax':
            if self.zmax_mode == 'two_files':
                # Assumes the input_file is the path to the LEFT channel EDF,
                # and the RIGHT channel is in the same folder with a similar name.
                rawL = mne.io.read_raw_edf(self.input_file, preload=True, verbose=False)
                rawR_path = Path(re.sub(r'(?i)([_ ])L\.edf$', r'\1R.edf', str(self.input_file)))
                if not rawR_path.exists():
                    raise FileNotFoundError(f"Could not find corresponding RIGHT channel file at {rawR_path}")
                rawR = mne.io.read_raw_edf(rawR_path, preload=True, verbose=False)
                
                # Resample and filter
                rawL.resample(fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)
                rawR.resample(fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)

                dataL = rawL.get_data().flatten()
                dataR = rawR.get_data().flatten()
                info = mne.create_info(['eegl', 'eegr'], sfreq=fs, ch_types=['eeg', 'eeg'], verbose=False)
                self.raw = mne.io.RawArray(np.vstack([dataL, dataR]), info, verbose=False)

            elif self.zmax_mode == 'one_file':
                raw = mne.io.read_raw_edf(self.input_file, preload=True, verbose=False)
                
                if self.zmax_ch_names and len(self.zmax_ch_names) == 2:
                    ch_names = self.zmax_ch_names
                else:
                    if len(raw.ch_names) < 2:
                        raise ValueError("EDF file must have at least two channels for 'one_file' mode when no channels are selected.")
                    ch_names = raw.ch_names[:2]
                
                raw.pick(ch_names)
                raw.rename_channels({ch_names[0]: 'eegl', ch_names[1]: 'eegr'})
                raw.reorder_channels(['eegl', 'eegr'])
                
                # Resample and filter
                raw.resample(fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)
                self.raw = raw

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
        fs = 64
        epoch_size = 30
        sdata = self.raw.get_data()
        for ch in range(sdata.shape[0]):
            sig = sdata[ch]
            mad = np.median(np.abs(sig - np.median(sig)))
            if mad == 0: mad = 1
            norm = (sig - np.median(sig)) / mad
            iqr = np.subtract(*np.percentile(norm, [75, 25]))
            sdata[ch] = np.clip(norm, -20 * iqr, 20 * iqr)
        self.raw._data = sdata

        eegL = self.raw.get_data(picks="eegl").flatten()
        eegR = self.raw.get_data(picks="eegr").flatten()
        data_as_array = np.vstack((eegL.reshape(1, -1), eegR.reshape(1, -1)))

        if data_as_array.ndim != 2:
            raise ValueError("Input data must be a 2D array.")
        if data_as_array.shape[0] > data_as_array.shape[1]:
            data_as_array = data_as_array.T

        num_channels, epoch_length = data_as_array.shape[0], epoch_size * fs
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
        fs = 64
        epoch_size = 30
        # get number of complete 30-second epochs that exist in the raw EEG recording
        num_epochs = int(np.floor(self.raw.get_data().shape[1] / (epoch_size * fs)))
        # truncate predictions to match number of full epochs in recording
        ypred_raw = self.raw_predictions[:num_epochs, :]
        # reorder model output to fit standard sleep stage order
        reorder_indices = [4, 2, 1, 0, 3, 5]
        self.probabilities = ypred_raw[:, reorder_indices]
        self.hypnogram = np.argmax(self.probabilities, axis=1)
        self.hypnogram[self.hypnogram == 5] = 6 # artefact class
        self.hypnogram[self.hypnogram == 4] = 5 # REM 
        


