import re
import mne
import numpy as np
from pathlib import Path
import onnxruntime as ort
from NIDRA.config import FOREHEAD_MODEL_PATH, FOREHEAD_SEQ_LENGTH, FOREHEAD_FS
from NIDRA.plotting import plot_hypnodensity

class ForeheadScorer:
    """
    Scores sleep stages from forehead EEG data.
    """
    def __init__(self, output_dir: str, input_file: str = None, data: np.ndarray = None, model_name: str = "u-sleep-forehead-2024"):
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

        self.model_path = FOREHEAD_MODEL_PATH
        self.model_name = model_name
        self.seq_length = FOREHEAD_SEQ_LENGTH
        self.fs = FOREHEAD_FS
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

    def _load_model(self):
        model_file = self.model_path.parent / f"{self.model_name}.onnx"
        self.session = ort.InferenceSession(str(model_file))
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def _load_recording(self):
        if self.input_data is not None:
            if self.input_data.ndim != 2 or self.input_data.shape[0] != 2:
                raise ValueError("Input data must be a 2D array with 2 channels.")
            info = mne.create_info(['eegl', 'eegr'], sfreq=self.fs, ch_types=['eeg', 'eeg'], verbose=False)
            self.raw = mne.io.RawArray(self.input_data, info, verbose=False)
            self.raw.filter(l_freq=0.5, h_freq=None, verbose=False)
        else:
            rawL = mne.io.read_raw_edf(self.input_file, preload=True, verbose=False).resample(self.fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)
            rawR_path = Path(re.sub(r'(?i)([_ ])L\.edf$', r'\1R.edf', str(self.input_file)))
            rawR = mne.io.read_raw_edf(rawR_path, preload=True, verbose=False).resample(self.fs, verbose=False).filter(l_freq=0.5, h_freq=None, verbose=False)
            dataL = rawL.get_data().flatten()
            dataR = rawR.get_data().flatten()
            info = mne.create_info(['eegl', 'eegr'], sfreq=self.fs, ch_types=['eeg', 'eeg'], verbose=False)
            self.raw = mne.io.RawArray(np.vstack([dataL, dataR]), info, verbose=False)

    def _predict(self):
        last_seq = self.processed_data[-1]
        last_seq_valid_epochs = int(np.sum(~np.isnan(last_seq.sum(axis=(1, 2)))))
        if last_seq_valid_epochs == self.seq_length:
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

        num_channels, epoch_length = data_as_array.shape[0], 30 * self.fs
        num_epochs = int(np.floor(data_as_array.shape[1] / epoch_length))

        epoched_data = np.full((num_channels, num_epochs, epoch_length), np.nan)
        tidxs = np.arange(0, data_as_array.shape[1] - epoch_length + 1, epoch_length)
        for ch_idx in range(num_channels):
            for e_idx, tidx in enumerate(tidxs):
                epoched_data[ch_idx, e_idx, :] = data_as_array[ch_idx, tidx:tidx + epoch_length]

        num_full_seqs, remainder_epochs = divmod(num_epochs, self.seq_length)
        num_seqs = num_full_seqs + (1 if remainder_epochs > 0 else 0)

        seqdat = np.full((num_seqs, self.seq_length, epoched_data.shape[2], epoched_data.shape[0]), np.nan, dtype=np.float32)
        for ct in range(num_full_seqs):
            idx_start, idx_end = ct * self.seq_length, (ct + 1) * self.seq_length
            seqdat[ct, :, :, :] = np.transpose(epoched_data[:, idx_start:idx_end, :], (1, 2, 0))
        if remainder_epochs > 0:
            idx_start = num_full_seqs * self.seq_length
            seqdat[num_full_seqs, :remainder_epochs, :, :] = np.transpose(epoched_data[:, idx_start:, :], (1, 2, 0))

        self.processed_data, self.num_full_seqs = seqdat, num_full_seqs

    def _postprocess(self):
        # get number of complete 30-second epochs that exist in the raw EEG recording
        num_epochs = int(np.floor(self.raw.get_data().shape[1] / (30 * self.fs)))
        # truncate predictions to match number of full epochs in recording
        ypred_raw = self.raw_predictions[:num_epochs, :]
        # reorder model output to fit standard sleep stage order
        reorder_indices = [4, 2, 1, 0, 3, 5]
        self.probabilities = ypred_raw[:, reorder_indices]
        self.hypnogram = np.argmax(self.probabilities, axis=1)
        self.hypnogram[self.hypnogram == 5] = 6 # artefact class
        self.hypnogram[self.hypnogram == 4] = 5 # REM 
        


