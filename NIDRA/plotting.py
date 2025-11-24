import sys

class StderrFilter:
    """A class to filter specific messages from stderr."""
    def __init__(self, original_stderr, filter_text):
        self.original_stderr = original_stderr
        self.filter_text = filter_text

    def write(self, text):
        if self.filter_text not in text:
            self.original_stderr.write(text)

    def flush(self):
        self.original_stderr.flush()

# Temporarily replace stderr with the filter
original_stderr = sys.stderr
filter_string = "NotoColorEmoji"
sys.stderr = StderrFilter(original_stderr, filter_string)

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to prevent GUI issues
import matplotlib.pyplot as plt

# Restore the original stderr
sys.stderr = original_stderr
import numpy as np
import seaborn as sns
import pandas as pd
import logging
from scipy import signal
from matplotlib.colors import Normalize
from types import SimpleNamespace

logger = logging.getLogger(__name__)

# =============================================================================
# PLOTTING CONFIGURATION
# =============================================================================
STAGE_CONFIG = {
    'WAKE': {'plot_val': 5, 'color': [234/255, 234/255, 242/255, 0]},
    'N1':   {'plot_val': 3, 'color': [134/255, 46/255, 119/255, .8]},
    'N2':   {'plot_val': 2, 'color': [255/255, 127/255, 0/255, .8], 'scatter_color': [255/255, 127/255, 0/255]},
    'N3':   {'plot_val': 1, 'color': [118/255, 214/255, 255/255, .8], 'scatter_color': [118/255, 214/255, 255/255]},
    'REM':  {'plot_val': 4, 'color': [1/255, 121/255, 51/255, .8], 'scatter_color': [1/255, 121/255, 51/255]},
    'ART':  {'plot_val': 6, 'color': [10/255, 67/255, 122/255, .65], 'scatter_color': 'k'}
}

# Order for the stacked probability plot
PROB_PLOT_ORDER = ['N1', 'N2', 'N3', 'REM', 'WAKE', 'ART']

def _compute_spectrograms(raw, channels, win_sec=30, fmax=30, overlap_sec=15):
    """Computes spectrograms for a list of channels."""
    logger.debug(f"Computing spectrograms for channels: {channels}...")
    sfreq = raw.info['sfreq']
    nperseg = int(win_sec * sfreq)
    noverlap = int(overlap_sec * sfreq)
    
    spectrograms = {}
    
    for ch_name in channels:
        data = raw.get_data(picks=[ch_name]).T.flatten()
        f, tt, Sxx = signal.spectrogram(data, sfreq, nperseg=nperseg, noverlap=noverlap)
        Sxx = 10 * np.log10(Sxx + np.finfo(float).eps)
        
        good_freqs = (f <= fmax)
        f_trimmed = f[good_freqs]
        Sxx_trimmed = Sxx[good_freqs, :]
        
        spectrograms[ch_name] = Sxx_trimmed
        
    tt_hours = tt / 3600
    
    out = SimpleNamespace()
    out.f = f_trimmed
    out.tt = tt_hours
    out.spectrograms = spectrograms
    
    logger.debug("Spectrogram computation finished.")
    return out


def _remap_hypnogram_for_plotting(hyp):
    """Remaps hypnogram values for consistent plotting."""
    # Input hyp values: W=0, N1=1, N2=2, N3=3, REM=5, ART=6
    # Target plot values for y-axis: W=5, N1=3, N2=2, N3=1, REM=4, ART=6
    mapping = {
        0: 5,  # Wake
        1: 3,  # N1
        2: 2,  # N2
        3: 1,  # N3
        5: 4,  # REM
        6: 6   # ART
    }
    
    hyp_plot = hyp.copy().astype(float)
    for original_value, target_value in mapping.items():
        hyp_plot[hyp == original_value] = target_value
        
    return hyp_plot


def plot_hypnodensity(hyp, ypred, raw, nclasses=6, figoutdir='./', filename='figure.png', type='forehead'):
    """
    Plots a hypnodensity graph, which is a combination of a hypnogram and the softmax probabilities of the sleep stage predictions.

    Parameters
    ----------
    hyp : np.ndarray
        The ground truth hypnogram.
    ypred : np.ndarray
        The predicted hypnogram (probabilities).
    nclasses : int
        The number of sleep stages.
    figoutdir : str
        The directory where the figure will be saved.
    filename : str
        The filename for the saved plot (default: 'figure.png').
    type : str
        The type of scorer ('forehead' or 'psg'), which determines the plot layout.
    """
    try:
        logger.info(f"Scoring complete. Making graph...")

        # Set plot style
        sns.set_style("white")
        sns.set_context("paper", font_scale=1)

        mosaic = [['a', 'ar'], ['b', 'br'], ['c', 'cr'], ['d', 'nr']]
        figsize = (19, 7)
        height_ratios = [1, 1, 1, 1]
        right_extra_axs = ['ar', 'br', 'cr', 'nr']

        fig = plt.figure(figsize=figsize)
        axs = fig.subplot_mosaic(
            mosaic,
            empty_sentinel=None,
            gridspec_kw={"height_ratios": height_ratios, "hspace": 0.3, "width_ratios": [15 * (19 / 16), 1], "wspace": -0.05},
        )

        t = np.arange(0, len(hyp)) / 2 / 60  # Convert epochs to hours

        # Hypnogram uses standard order: W=0, N1=1, N2=2, N3=3, R=4, A=5
        hyp_plot = _remap_hypnogram_for_plotting(hyp)

        axs['b'].plot(t, hyp_plot, drawstyle="steps-post")
        axs['b'].set_ylabel('Hypnogram')

        for stage, config in STAGE_CONFIG.items():
            if 'scatter_color' in config:
                size = 25 if stage != 'ART' else 25 / 2
                axs['b'].scatter(t[hyp_plot == config['plot_val']], hyp_plot[hyp_plot == config['plot_val']],
                               color=config['scatter_color'], s=size, marker='o', zorder=2)

        axs['b'].set_yticks(ticks=[STAGE_CONFIG[s]['plot_val'] for s in ['N3', 'N2', 'N1', 'REM', 'WAKE', 'ART']],
                           labels=['N3', 'N2', 'N1', 'REM', 'WAKE', 'ART'])
        axs['b'].set_xticks(range(0, int(max(t)) + 1, 1))
        axs['b'].set_xlim(t.min(), t.max())
        ylmin, ylmax = axs['b'].get_ylim()
        axs['b'].set_ylim(ylmin - .125, ylmax + .125)
        axs['b'].grid(True, which='major', axis='x', color='#EEEEEE', lw=0.8)

        # Plot sleep stage decoder softmax probabilities
        # Determine plotting order and labels from config
        if nclasses == 5:
            plot_order_indices = [1, 2, 3, 4, 0] # N1, N2, N3, R, W
            prob_plot_labels = [s for s in PROB_PLOT_ORDER if s != 'ART']
        else: # nclasses == 6
            plot_order_indices = [1, 2, 3, 4, 0, 5] # N1, N2, N3, R, W, ART
            prob_plot_labels = PROB_PLOT_ORDER

        ypred_plotting = ypred[:, plot_order_indices]
        probs_df = pd.DataFrame(ypred_plotting, columns=prob_plot_labels)
        
        palette = [STAGE_CONFIG[s]['color'] for s in prob_plot_labels]

        probs_df.plot(kind="area", color=palette, stacked=True, lw=0, ax=axs['a'])
        axs['a'].set_xlim(0, ypred.shape[0])
        axs['a'].set_ylim(0, 1)
        axs['a'].set_ylabel("Probability")
        axs['a'].set_yticks([0, .25, .5, .75, 1])
        axs['a'].set_yticklabels([0, '', .5, '', 1])
        tickpos = np.arange(0, len(ypred) + 1, 1 * 2 * 60)
        axs['a'].set_xticks(ticks=tickpos, labels=[f"{int(hour)}h" for hour in np.arange(0, int(len(ypred) / 2 / 60) + 1)])
        axs['a'].set_xlabel('')
        axs['a'].grid(True, which='major', axis='x', color='#EEEEEE', lw=0.8)
        axs['a'].set_xticklabels([])
        axs['a'].legend(loc="right")

        # --- Spectrogram plotting ---
        if type == 'psg':
            # Create a list of preferred channels (EEG but not EOG)
            preferred_chans = [ch for ch in raw.ch_names if 'EEG' in ch.upper() and 'EOG' not in ch.upper()]
            
            # If no preferred channels, try to at least exclude EOG
            if not preferred_chans:
                preferred_chans = [ch for ch in raw.ch_names if 'EOG' not in ch.upper()]

            # If the list is still empty (e.g., only EOG channels), use all channels as a last resort
            if not preferred_chans:
                preferred_chans = raw.ch_names
            
            # Now, select from the preferred_chans list
            frontal_ch = next((ch for ch in preferred_chans if 'F' in ch.upper()), preferred_chans[0])
            occipital_ch = next((ch for ch in preferred_chans if 'O' in ch.upper()), preferred_chans[-1])

            # Ensure two different channels are selected if possible
            if frontal_ch == occipital_ch and len(preferred_chans) > 1:
                channels_to_plot = preferred_chans[:2]
            else:
                channels_to_plot = [frontal_ch, occipital_ch]
            
            spctgm_object = _compute_spectrograms(raw, channels_to_plot)
            f = spctgm_object.f
            tt = spctgm_object.tt
            
            for ax_key, ch_name in zip(['c', 'd'], channels_to_plot):
                Sxx = spctgm_object.spectrograms[ch_name]
                vmin, vmax = np.percentile(Sxx, [5, 95])
                norm = Normalize(vmin=vmin, vmax=vmax)
                axs[ax_key].pcolormesh(tt, f, Sxx, norm=norm, cmap='Spectral_r', shading="auto")
                axs[ax_key].set_ylabel(f"{ch_name}" + "\nFrequency [Hz]")
                
                axs[ax_key].set_xlim(tt.min(), tt.max())
                axs[ax_key].grid(True, which='major', axis='x', color='#EEEEEE', lw=0.8)
        else: # forehead
            channels_to_plot = raw.ch_names[:2]
            spctgm_object = _compute_spectrograms(raw, channels_to_plot)
            f = spctgm_object.f
            tt = spctgm_object.tt
            
            for ax_key, ch_name in zip(['c', 'd'], channels_to_plot):
                Sxx = spctgm_object.spectrograms[ch_name]
                vmin, vmax = np.percentile(Sxx, [5, 95])
                norm = Normalize(vmin=vmin, vmax=vmax)
                axs[ax_key].pcolormesh(tt, f, Sxx, norm=norm, cmap='Spectral_r', shading="auto")
                axs[ax_key].set_ylabel(f"{ch_name}" + "\nFrequency [Hz]")
                
                axs[ax_key].set_xlim(tt.min(), tt.max())
                axs[ax_key].grid(True, which='major', axis='x', color='#EEEEEE', lw=0.8)

        # Hide the right-hand axes
        for extra in right_extra_axs:
            axs[extra].set_visible(False)
            axs[ax_key].set_xlabel("Time (hrs)")

        figsavgname = f'{figoutdir}/{filename}'
        fig.savefig(figsavgname, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig) 

    except Exception as e:
        logger.error(f"Error generating dashboard plot: {e}", exc_info=True)
        # Ensure the figure is closed even if an error occurs
        if 'fig' in locals():
            plt.close(fig)
        raise

