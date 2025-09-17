"""
Configuration parameters for NIDRA sleep scoring.
"""
from pathlib import Path
import importlib.resources

# --- Model Paths ---
MODEL_DIR = Path(__file__).parent / "models"
FOREHEAD_MODEL_PATH = MODEL_DIR / "ez6.onnx"
PSG_MODEL_PATH = MODEL_DIR



# TODO: this actually needs to be hardcoded in the function
# --- Forehead Scorer Settings ---
FOREHEAD_SEQ_LENGTH = 100
FOREHEAD_FS = 64

# --- PSG Scorer Settings ---
PSG_NEW_SAMPLE_RATE = 128
PSG_AUTO_CHANNEL_GROUPING = ['EEG', 'EOG']


######################################


# TODO: put this somewhere else, we need it
EPOCH_SIZE = 30



"""
NIDRA Configuration Module
Configuration constants for the NIDRA Sleep Autoscorer GUI
"""


# --- Font File Configuration ---
_FONT_FILE = importlib.resources.files("NIDRA.assets").joinpath("font.ttf")

class Config:
    def __init__(self):
        # --- File Paths ---
        self._FONT_FILE = importlib.resources.files("NIDRA.assets").joinpath("font.ttf")
        self._HELP_FILE = importlib.resources.files("NIDRA").joinpath("help_info.html")

        # --- UI Configuration (granular control over all visual elements) ---
        self.CONFIG = {
            # --- Fonts (Scalers applied on startup) ---
            "FONT_SIZE_REGULAR_SCALER": 3.0,
            "FONT_SIZE_MEDIUM_SCALER": 3.5,
            "FONT_SIZE_LARGE_SCALER": 4.0,

            # --- Window & Dialog Sizes ---
            "FILE_DIALOG_WIDTH": 900,
            "FILE_DIALOG_HEIGHT": 600,

            # --- Widget & Layout Sizes (heights reduced for a more compact layout) ---
            "BROWSE_BUTTON_WIDTH": 300,
            "BROWSE_BUTTON_HEIGHT": 54,
            "INPUT_FIELD_HEIGHT": 50,
            "RUN_BUTTON_HEIGHT": 120,

            # --- Spacing ---
            "SPACER_HEIGHT_SMALL": 5,         # Reduced spacing between main sections
            "SPACER_HEIGHT_MEDIUM": 25,
            "SPACER_HEIGHT_LARGE": 50,

            "PANEL_PADDING_X": 20,
            "PANEL_PADDING_Y": 20,

            # --- Colors & Theming ---
            "CONSOLE_BG_COLOR": (0, 0, 0, 255),
            "CONSOLE_TEXT_COLOR": (0, 200, 0, 255),
            "HYPERLINK_COLOR": (80, 160, 240, 255),

            # --- Behavior & Options ---
            "DEFAULT_OUTPUT_FOLDER_NAME": "autoscorer_output",
            "OPTION_GEN_PROBS_DEFAULT": True,
            "OPTION_GEN_PLOT_DEFAULT": True,
            "OPTION_GEN_STATS_DEFAULT": True,
            "OPTION_SCORE_SUBDIRS_DEFAULT": False,
        }

        # --- UI Text (change all user-facing text here) ---
        self.TEXTS = {
            "WINDOW_TITLE": "NIDRA Sleep Autoscorer",
            "INPUT_TITLE": "Input Directory",
            "MODEL_TITLE": "Model",
            "OPTIONS_TITLE": "Options",
            "OPTIONS_PROBS": "Generate probabilities",
            "OPTIONS_PLOT": "Generate graph",
            "OPTIONS_STATS": "Generate sleep statistics",
            "OPTIONS_SCORE_SINGLE": "Score single recording",
            "OPTIONS_SCORE_SUBDIRS": "Score all recordings (in subfolders)",
            "DATA_SOURCE_TITLE": "Data Source",
            "DATA_SOURCE_FEE": "EEG wearable (e.g. ZMax)   ",
            "DATA_SOURCE_PSG": "full PSG (EEG, optional: EOG, EMG)   ",
            "OUTPUT_TITLE": "Output Directory",
            "RUN_BUTTON": "Run NIDRA autoscoring",
            "BROWSE_BUTTON": "Browse files...",
            "HELP_TITLE": "Help & Info (opens in browser)",
            "CONSOLE_INIT_MESSAGE": "Start by selecting a directory containing a sleep recording, or subfolders with one sleep recording each (Input Directory).",
        }

        # --- Constants for Dear PyGui Widget Tags ---
        self.TAGS = {
            "PRIMARY_WINDOW": "Primary Window",
            "LEFT_PANEL": "left_panel",
            "RIGHT_PANEL": "right_panel",
            "CONSOLE_PANEL": "console_panel",
            "HELP_PANEL": "help_panel",
            "INPUT_DIR_TEXT": "input_dir_path_tag",
            "OUTPUT_DIR_TEXT": "output_dir_path_tag",
            "MODEL_NAME": "model_name_combo_tag",
            "RUN_BUTTON": "run_button_tag",
            "CONSOLE_TEXT": "console_text_tag",
            "INPUT_DIALOG": "input_dialog_tag",
            "OUTPUT_DIALOG": "output_dialog_tag",
            "HYPERLINK_BTN": "hyperlink_button_tag",
            "HELP_CONTENT_TEXT": "help_content_text_tag",
            "OPTIONS_PROBS": "options_probs_tag",
            "OPTIONS_PLOT": "options_plot_tag",
            "OPTIONS_STATS": "options_stats_tag",
            "OPTIONS_SUBDIRS": "options_subdirs_tag",
            "SCORING_MODE": "scoring_mode_radio_tag",
            "DATA_SOURCE": "data_source_combo_tag",
            "FONT_LARGE": "large_font_tag",
            "FONT_MEDIUM": "medium_font_tag",
            "FONT_ITALIC": "italic_font_tag",
        }

    @property
    def FONT_FILE(self):
        return self._FONT_FILE

    @property
    def HELP_FILE(self):
        return self._HELP_FILE

# Create single instance
config = Config()
