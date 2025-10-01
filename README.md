# NIDRA v0.1 - super simple sleep scoring

<table>
  <tr>
    <td width="200" valign="top"><img src="docs/logo.png" alt="NIDRA Logo" width="200"/></td>
    <td valign="top">
      <ul>
        <li>Neural networks can perform highly accurate, automated sleep scoring, but these technologies are often difficult to implement.</li>  
        <li>NIDRA is a fool-proof, simple-to-use tool for scoring sleep recordings using the best currently available autoscoring machine learning algorithms. No programming required, but a CLI and python endpoints are available.</li>
        <li>NIDRA can autoscore data from polysomnography (PSG) recordings, as well as from 2-channel EEG wearables (such as ZMax).</li>
        <li>NIDRA enables anyone, including researchers without any programming experience, to use cutting-edge sleep scoring models.</li>
        <li>NIDRA uses the highly accurate U-Sleep2.0 and ez6moe models by default. Both models have been validated (see below) and perform sleep scoring on the level of human interrater agreement.</li>
        <li>NIDRA lives here: <a href="https://github.com/paulzerr/nidra">github.com/paulzerr/nidra</a></li>
      </ul>
    </td>
  </tr>
</table>

<h2>For a detailed user guide, please see the <a href="https://nidra.netlify.app/">NIDRA Manual</a></h2>
## Installation

### Option 1: Standalone executable
The easiest way to use NIDRA on Windows is via the portable, ready-to-go executable which requires no installation.

### **[Download standalone NIDRA for Windows](LINK)**

**Note:** due to the restrictive environment of Windows, you may see a "Search on app store" popup window. Click "No". You may also see the blue Smartscreen warning. In that case click "run anyway". Should this fail, try installing via pip (see below).

### Option 2: Install from PyPI
First, make sure you have Python installed (3.10 or later recommended). 
It is highly recommended to create a clean virtual environment to install NIDRA. This prevents conflicts with other packages.

**Windows:**
```
python -m venv nidra-env
nidra-env\Scripts\activate
pip install nidra
```
**Mac/Linux:**
```
python -m venv nidra-env
source nidra-env/bin/activate
pip install nidra
```
**Or install using Conda (Windows/Mac/Linux):**
First install e.g., [Miniconda](https://www.anaconda.com/download/success).
```
conda create -n nidra-env
conda activate nidra-env
pip install nidra
```
Launch the graphical interface:
```
nidra
```
**Note:** If you installed via pip, the first time you run NIDRA, the necessary model files will be automatically downloaded from [https://huggingface.co/pzerr/NIDRA_models/](https://huggingface.co/pzerr/NIDRA_models/) (~152MB). 

### Option 3: Install from source
**macOS and Linux:**
```
git clone https://github.com/paulzerr/nidra.git
cd NIDRA
python -m venv nidra-env
source nidra-env/bin/activate
pip install .
```
**Windows:**
```
git clone https://github.com/paulzerr/nidra.git
cd NIDRA
python -m venv nidra-env
nidra-env\Scripts\activate
pip install .
```

## Graphical User Interface (GUI)
The GUI provides an intuitive, point-and-click way to score sleep recordings. The easiest way to launch the GUI is by running the standalone executable. If you installed NIDRA as a package, you can launch it by opening your terminal and running the command: `nidra`

<img src="docs/gui.png" alt="Screenshot of the NIDRA GUI" style="width: 90%; display: block; margin: 20px 0;">
<b>Fig.1</b> - Screenshot of the GUI

### Quick Guide
1.  **Input Folder**: Select the directory containing the sleep recording data.
2.  **Output Folder**: Select the directory where the results will be saved.
3.  **Scoring Mode**: Choose to score a single recording or batch-process all subdirectories, eaching containing one recording.
4.  **Data Source**: Select "Forehead EEG" or "PSG".
5.  **Model**: Select the appropriate model for your data source. Default models are reliable.
6.  **Options**: Choose whether to generate plots and statistics.
7.  **Run**: Start the scoring process.

A more detailed walkthrough is provided in the sections below.

## Preparing Your Data
For NIDRA to process your recordings, your files and folders must be organized in a specific way.

*   **File Format:** Currently NIDRA exclusively works with European Data Format (.edf) files.
*   **Channel Labels:** Ideally your EDF files have standard channel labels (e.g., 'EEG Fpz-Cz', 'EOG left', 'Fp1', 'O2-M1') for PSG data, as NIDRA uses these to identify channel types.

Whether you are scoring a single file or batch processing, NIDRA expects each recording session to be in its own folder. When using the "Score all subdirectories" mode, NIDRA will treat every subfolder in your input directory as a separate recording.

**Structure for Forehead EEG (e.g., ZMax):**
For two-channel forehead EEG data, the left and right channel files must be in the same directory. For ZMax data, these are typically named `EEG_L.edf` and `EEG_R.edf`.
```
forehead_study/
├── subject_01/
|   ├── EEG_L.edf
|   └── EEG_R.edf
├── subject_02/
|   ├── night01_L.edf
|   └── night01_R.edf
```
**Structure for PSG:**
Similarly, for PSG data, each EDF file should be in its own directory. NIDRA can process multiple recordings in subdirectories, as shown in this example with three recordings:
```
psg_study/
├── subject_02/
|   └── night_recording_1.edf
├── subject_03/
|   └── night_recording_2.edf
└── subject_04/
    └── another_night.edf
```

## Model Validation and Performance
The models included in NIDRA have been rigorously validated against manually scored data from human experts. Below is a summary of their performance.

### ez6 and ez6moe for Forehead EEG
The `ez6moe` model was validated against expert-scored PSG recordings. The confusion matrix below shows the model's predictions (y-axis) versus the expert labels (x-axis). The diagonal represents correct classifications. As you can see, the model shows high agreement with the expert scorer, particularly for Wake, N2, and REM sleep.

<img src="docs/matrix.png" alt="Confusion matrix of the ez6moe model" style="width: 60%; max-width: 600px; display: block; margin: 20px 0;">
<b>Fig.2</b> - Confusion matrix (vs. manually scored PSG) of the artefact-aware ez6moe model.

Key performance metrics, such as accuracy and Cohen's Kappa (a measure of inter-rater agreement), are comparable to the agreement levels seen between different human experts. For full details, please refer to the original publication.

### U-Sleep for PSG
The U-Sleep model is a well-established, state-of-the-art algorithm for PSG sleep scoring. The version used in NIDRA (`u-sleep-nsrr-2024`) is a robust implementation trained on a large dataset. It demonstrates high performance across diverse populations and recording conditions. For detailed performance metrics, please see the original U-Sleep and SLEEPYLAND publications linked in the Attribution section.

## Understanding Your Results
Once NIDRA has finished processing, you will find several output files in your specified output directory. Here's what they are and how to use them.

### The Output Files
For each recording, NIDRA generates up to four files:
*   **Hypnogram File (`..._hypnogram.csv`):** A CSV file with a single column of numbers, where each number is the sleep stage for one 30-second epoch.
*   **Probabilities File (`..._probabilities.csv`):** This file contains the raw classifier probabilities for each sleep stage for every epoch. Each row corresponds to an epoch, and each column corresponds to a sleep stage (Wake, N1, N2, N3, REM, Artifact).
*   **Dashboard Plot (`..._dashboard.png`):** A graph with a hypnogram, a time-frequency representation, and a hypnodensity plot visualizing classifier probabilities.
*   **Sleep Statistics (`..._sleep_statistics.csv`):** A summary of sleep metrics like Total Sleep Time, Sleep Efficiency, and time spent in each stage.

### Sleep Stage Key
The hypnogram uses the following standard numeric codes for sleep stages:
*   **0:** Wake
*   **1:** N1
*   **2:** N2
*   **3:** N3
*   **5:** REM
*   **6:** Artifact

## Commandline interface (CLI)
The basic command is `nidra score`. You must provide the input path, output directory, and the type of scorer.
```
nidra score --input_path /path/to/data --output_dir /path/to/output --scorer_type forehead
```
### Example: Batch Processing a Full Study
Let's say you have a study with data structured as recommended in the "Preparing Your Data" section. You can process all subjects with a single command by pointing the `--input_path` to the main study directory.
```
nidra score --input_path /my_study_data/ --output_dir /my_study_results/ --scorer_type forehead --model_name ez6moe
```
NIDRA will automatically find the subdirectories, process the recording in each one, and place the results in a correspondingly named folder inside `/my_study_results/`.

## Python Endpoints
You can use NIDRA as a Python package to integrate automated scoring directly into your data analysis pipelines.

The main entry point is the `NIDRA.scorer()` factory function. You call this function to create a scorer instance, providing it with the configuration for your scoring task. Then, you call the `.score()` method on the returned object to run the analysis.

#### `NIDRA.scorer(...)` Parameters
When creating a scorer, you must provide the following arguments:
*   `scorer_type` (str): The type of data. Must be either `'forehead'` or `'psg'`.
*   `output_dir` (str): The path to the directory where results will be saved.
*   `input_file` (str, optional): The full path to the input EDF file. Required if not providing data as a NumPy array.
*   `data` (np.ndarray, optional): An in-memory NumPy array of the EEG/PSG data. If you use this, `input_file` should be `None`.
*   `model_name` (str, optional): The name of the model to use. If not provided, a default model will be selected.
*   **For PSG data from NumPy array:**
    *   `sfreq` (float): The sampling frequency of the data.
    *   `ch_names` (list of str): A list of channel names.

#### `scorer.score(...)` Method
This method runs the scoring process. It takes one optional argument:
*   `plot` (bool, optional): If `True`, a graph will be generated. Defaults to `False`.

**Returns:**
The method returns a tuple containing two NumPy arrays:
1.  **hypnogram** (`numpy.ndarray`): A 1D array of integers representing the sleep stage for each 30-second epoch. See the [Sleep Stage Key](#understanding-results) for the meaning of each integer.
2.  **probabilities** (`numpy.ndarray`): A 2D array of shape (n_epochs, n_classes). Each row corresponds to an epoch, and each column contains the model's predicted probability for a specific sleep stage.

### Example 1: Scoring a PSG File
This example shows how to score a single PSG recording from an EDF file.
```
import NIDRA

# Initialize the scorer
scorer = NIDRA.scorer(
    scorer_type='psg',
    input_file='/path/to/your/data/sleep_recording.edf',
    output_dir='/path/to/your/output',
    model_name='u-sleep-nsrr-2024'
)

# Run scoring
hypnogram, probabilities = scorer.score(plot=True)

```

### Example 2: Scoring In-Memory NumPy Data
You can also score data that you already have in memory as a NumPy array. This is useful for real-time applications or custom data loading pipelines. When scoring PSG data from an array, you must provide the sampling frequency (`sfreq`). Providing channel names is recommended but optional; if not provided, they will be auto-generated. All channels are then assumed to contain EEG data.
```
import NIDRA
import numpy as np

# Create some dummy PSG data
sfreq = 256
ch_names = ['F3-A2', 'C4-A1', 'O2-A1', 'EOG-L']
n_samples = sfreq * 60 * 60  # 1 hour of data
dummy_data = np.random.randn(len(ch_names), n_samples)

scorer = NIDRA.scorer(
    scorer_type='psg',
    output_dir='/path/to/numpy_psg_output',
    data=dummy_data,
    sfreq=sfreq
)
hypnogram, probabilities = scorer.score()

```
### Example 3: Batch Processing a Study
For batch processing, NIDRA provides a convenient `batch_scorer`. This function automatically discovers all valid recordings in the subdirectories of your input path, mirroring the behavior of the GUI. This is the recommended way to process a full study. Please see the [Preparing Your Data](#preparing-your-data) section for details on how to structure your study directory.
```
import NIDRA

batch = NIDRA.batch_scorer(
    input_dir='/path/to/your/study_data',
    output_dir='/path/to/your/study_output',
    scorer_type='forehead',  # or 'psg'
    model_name='ez6moe'
)

batch.score(plot=True, gen_stats=True)



```
This simplified approach removes the need to manually loop through directories and handle file paths, making your analysis scripts cleaner and more reliable.

## How to Cite NIDRA
If you use NIDRA in your research, please cite both the NIDRA software itself and the paper for the specific model you used.

### 1. Citing the NIDRA Software
Please cite this repository to ensure reproducibility:
```
Zerr, P. (2025). NIDRA: super simple sleep scoring. GitHub. https://github.com/paulzerr/nidra
```
### 2. Citing the Scoring Model
**If you used the ez6 or ez6moe models:**
```
Coon WG, Zerr P, Milsap G, et al. (2025). "ezscore-f: A Set of Freely Available, Validated Sleep Stage Classifiers for Forehead EEG." bioRxiv. doi: 10.1101/2025.06.02.657451.
```
**If you used the u-sleep-nsrr-2024 model:**
Please cite the original U-Sleep paper and the SLEEPYLAND paper for the re-trained model weights:
```
Perslev, M., et al. (2021). "U-Sleep: resilient high-frequency sleep staging." NPJ digital medicine.
Rossi, A. D., et al. (2025). "SLEEPYLAND: trust begins with fair evaluation of automatic sleep staging models." arXiv preprint.
```

## Attribution
ez6 and ez6moe models were developed by Coon et al., see:
<br>Coon WG, Zerr P, Milsap G, Sikder N, Smith M, Dresler M, Reid M.
<br>"ezscore-f: A Set of Freely Available, Validated Sleep Stage Classifiers for Forehead EEG."
<br><a href="https://www.biorxiv.org/content/10.1101/2025.06.02.657451v1">https://www.biorxiv.org/content/10.1101/2025.06.02.657451v1</a>
<br><a href="https://github.com/coonwg1/ezscore">github.com/coonwg1/ezscore</a>

U-Sleep models were developed by  Perslev et al., see:
<br>Perslev, M., Darkner, S., Kempfner, L., Nikolic, M., Jennum, P. J., & Igel, C. (2021).
<br>U-Sleep: resilient high-frequency sleep staging. NPJ digital medicine
<br><a href="https://www.nature.com/articles/s41746-021-00440-5">https://www.nature.com/articles/s41746-021-00440-5</a>
<br><a href="https://github.com/perslev/U-Time">https://github.com/perslev/U-Time</a>

The U-Sleep model weights used in this repo were re-trained by Rossi et al., see:
<br>Rossi, A. D., Metaldi, M., Bechny, M., Filchenko, I., van der Meer, J., Schmidt, M. H., ... & Fiorillo, L. (2025).
<br>SLEEPYLAND: trust begins with fair evaluation of automatic sleep staging models. arXiv preprint arXiv:2506.08574.
<br><a href="https://arxiv.org/abs/2506.08574v1">https://arxiv.org/abs/2506.08574v1</a>

## License
This project is licensed under the MIT License. See the LICENSE file for details.

## Contact
For questions, bug reports, or feedback, please contact Paul Zerr at [zerr.paul@gmail.com](mailto:zerr.paul@gmail.com).
