import subprocess
import threading
import sys
import os
import socket
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

def find_free_port(preferred_ports=[5001, 5002, 5003, 62345, 62346, 62347, 62348, 62349]):
    """
    Finds a free port on the host machine.
    It first tries a list of preferred ports and then falls back to a random port.
    """
    for port in preferred_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue  # Port is already in use

    # If no preferred ports are available, ask the OS for a random one
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    except Exception as e:
        raise RuntimeError("Could not find any free port.") from e

def run_flask(port):
    """Runs the Flask app on a given port."""
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None # We don't want to show the Flask startup message
    app.run(port=port)

def main():
    """
    Starts the Flask server in a background thread and then launches the Neutralino application.
    """
    port = find_free_port()
    flask_thread = threading.Thread(target=run_flask, args=(port,), daemon=True)
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
            # Construct the URL with the dynamic port
            url = f"http://127.0.0.1:{port}"

            subprocess.run(
                [binary_path, '--load-dir-res', f'--url={url}'],
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
