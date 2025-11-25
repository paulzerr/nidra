<table>
  <tr>
    <td width="200" valign="top"><img src="docs/logo.png" alt="NIDRA Logo" width="200"/></td>
    <td valign="top">
      <h2>NIDRA v0.2.0 - super simple sleep scoring</h2>
      An easy way to use powerful machine learning models to autoscore sleep recordings with excellent accuracy. No programming required, but Python endpoints are available. NIDRA can accurately score recordings from 2-channel EEG wearables such as ZMax (using ezscore-f models), as well as full PSG recordings (using U-Sleep 2.0 via sleepyland).
      <br>
      <h3>Please see the <a href="https://nidra.netlify.app/">NIDRA Manual</a> for a detailed user guide, installation, and examples.</h3>
      <h3>Download the <a href="https://github.com/paulzerr/nidra/releases/latest/download/NIDRA_installer.exe"> NIDRA GUI installer for Windows 10/11</a></h3>
      <h3>Or install from PyPI:</h3> (clean virtual environment recommended)
<pre>
pip install nidra
</pre>
Then launch the GUI:
<pre>
nidra
</pre>
Or use as Python package:
<pre>
import NIDRA
scorer = NIDRA.scorer(
    type  = 'psg',
    input = '/path/to/recording.edf'
)
scorer.score()
</pre>


  </tr>
</table>


## Features
 
  *   Uses state-of-the-art, validated, high-accuracy deep learning models to reliably classify sleep stages.
  *   `ezscore-f` models for 2-channel EEG wearables (e.g., ZMax).
  *   `u-sleep-nsrr-2024` (U-Sleep 2.0) model for full polysomnography.
  *   Simple point-and-click interface (GUI) for non-programmers.
  *   Flexible `NIDRA.scorer()` endpoint for developers and data pipelines.
  *   Autoscore single or multiple files or folders.
  *   Accepts in-memory numpy arrays for real-time applications.
  *   Automatic channel detection.
  *   Outputs sleep stages, classifier probabilities (hypnodensity), and sleep statistics.
  *   Visual reports with spectrograms and hypnograms.
  *   Runs on Windows, macOS, and Linux.


<img src="docs/gui.png" alt="Screenshot of the NIDRA GUI" style="width: 98%; display: block; margin: 20px 0;">
<img src="docs/dashboard.png" alt="Screenshot of the NIDRA dashboard" style="width: 98%; display: block; margin: 20px 0;">

## How to cite NIDRA
If you use NIDRA in your research, please cite both the NIDRA software itself and the paper for the specific model you used.

```
Zerr, P. (2025). NIDRA: super simple sleep scoring. GitHub. https://github.com/paulzerr/nidra
```

## Attribution
ezscore-f (ez6 and ez6moe) models were developed by Coon et al., see:
```
Coon WG, Zerr P, Milsap G, Sikder N, Smith M, Dresler M, Reid M.
ezscore-f: A Set of Freely Available, Validated Sleep Stage Classifiers for Forehead EEG.
```
<a href="https://www.biorxiv.org/content/10.1101/2025.06.02.657451v1">https://www.biorxiv.org/content/10.1101/2025.06.02.657451v1</a>
<br><a href="https://github.com/coonwg1/ezscore">https://ezgithub.com/coonwg1/ezscore</a>
<br><br>

U-Sleep models were developed by  Perslev et al., see:
```
Perslev, M., Darkner, S., Kempfner, L., Nikolic, M., Jennum, P. J., & Igel, C. (2021).
U-Sleep: resilient high-frequency sleep staging.
```
<a href="https://www.nature.com/articles/s41746-021-00440-5">https://www.nature.com/articles/s41746-021-00440-5</a>
<br><a href="https://github.com/perslev/U-Time">https://github.com/perslev/U-Time</a>
<br><br>

The U-Sleep model weights used in this repo were re-trained by Rossi et al., see:
```
Rossi, A. D., Metaldi, M., Bechny, M., Filchenko, I., van der Meer, J., Schmidt, M. H., ... & Fiorillo, L. (2025).
SLEEPYLAND: trust begins with fair evaluation of automatic sleep staging models.
```
<a href="https://arxiv.org/abs/2506.08574v1">https://arxiv.org/abs/2506.08574v1</a>
<br><a href="https://github.com/biomedical-signal-processing/sleepyland">https://github.com/biomedical-signal-processing/sleepyland</a>

## License
This project is licensed under the MIT License. See the LICENSE file for details.
