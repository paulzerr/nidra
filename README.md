<table>
  <tr>
    <td width="200" valign="top"><img src="docs/logo.png" alt="NIDRA Logo" width="200"/></td>
    <td valign="top">
      <h2>NIDRA v0.1.1 - super simple sleep scoring</h2>
      NIDRA is an easy-to-use tool for autoscoring sleep recordings with excellent accuracy using the best currently available machine learning models. No programming required, but a CLI and python endpoints are available. NIDRA can accurately score recordings from 2-channel EEG wearables (such as ZMax), as well as full PSG recordings.
      <br>
      <h3>Download standalone <a href="https://github.com/paulzerr/nidra/releases/latest/download/NIDRA.exe">NIDRA for Windows 10/11</a></h3>
      <h3>Please see the <a href="https://nidra.netlify.app/">NIDRA Manual</a> for a detailed user guide, installation, and examples, </h3>
    </td>
  </tr>
</table>


### Or install with pip:

```
pip install nidra
```

**Note:** If you installed via pip, the first time you run NIDRA, the necessary model files will be automatically downloaded from [https://huggingface.co/pzerr/NIDRA_models/](https://huggingface.co/pzerr/NIDRA_models/) (~152MB). 

### Launch the GUI with:

```
nidra
```

## Citation
If you use NIDRA please cite this repository:
```
Zerr, P. (2025). NIDRA: super simple sleep scoring. GitHub. https://github.com/paulzerr/nidra
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
