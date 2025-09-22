import subprocess
import threading
import sys
import os
from pathlib import Path
from NIDRA.nidra_gui.app import app
import importlib.resources

def get_resource_path(relative_path):
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
        return os.path.join(base_path, relative_path)

    # For installed packages
    try:
        package_resources = importlib.resources.files('NIDRA.nidra_gui')
        return str(package_resources.joinpath(relative_path))
    except (ModuleNotFoundError, AttributeError):
        # Fallback for development mode
        base_path = os.path.abspath(Path(__file__).parent)
        return os.path.join(base_path, relative_path)

def run_flask():
    """Runs the Flask app."""
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None # We don't want to show the Flask startup message
    app.run(port=5001)

def main():
    """
    Starts the Flask server in a background thread and then launches the Neutralino application.
    """
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Determine the correct binary name based on the OS
    if sys.platform == "win32":
        binary_name = "nidra_gui-win_x64.exe"
    elif sys.platform == "darwin":
        binary_name = "nidra_gui-mac_x64"
    else:
        binary_name = "nidra_gui-linux_x64"

    binary_path = get_resource_path(f"dist/nidra_gui/{binary_name}")

    # The CWD needs to be the directory of the binary for Neutralino to find its resources
    app_dir = os.path.dirname(binary_path)

    try:
        with open(os.devnull, 'w') as devnull:
            subprocess.run(
                [binary_path, '--load-dir-res'],
                cwd=app_dir,
                check=True,
                stdout=devnull,
                stderr=devnull
            )
    except FileNotFoundError:
        print(f"Error: Neutralino binary not found at {binary_path}")
        print("Please ensure the application is installed correctly.")
    except subprocess.CalledProcessError as e:
        print(f"Error running Neutralino application: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    main()
