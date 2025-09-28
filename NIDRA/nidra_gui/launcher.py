import subprocess
import threading
import sys
import os
import socket
import requests
from pathlib import Path
import webbrowser
import time
import multiprocessing
from NIDRA.nidra_gui.app import app, check_ping
import time
import importlib.resources
import atexit
import psutil

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
    cli.show_server_banner = lambda *x: None # don't show the Flask startup message
    app.run(port=port)


def main():
    """
    Starts the Flask server in a background thread and then launches the Neutralino application.
    """

    multiprocessing.set_start_method('spawn', force=True)
    port = find_free_port()
    
    # Start the ping check thread (used to keep app alive)
    app.last_ping = time.time()
    ping_thread = threading.Thread(target=check_ping, args=(port,), daemon=True)
    ping_thread.start()

    flask_thread = threading.Thread(target=run_flask, args=(port,), daemon=True)
    flask_thread.start()

    # get platform-specific Neutralino binary path
    # TODO: robustify platform recognition
    if sys.platform == "win32":
        binary_name = "neutralino-win_x64.exe"
    elif sys.platform == "darwin":
        binary_name = "neutralino-mac_10xxx" #workaround for macOS to force browser fallback
    else:
        binary_name = "neutralino-linux_x64"
    binary_path = get_resource_path(f"neutralino/{binary_name}")

    
    time.sleep(1)
    neutralino_process = None
    
    def cleanup():
        """Ensure Neutralino and any of its children are terminated."""
        if neutralino_process and neutralino_process.poll() is None:
            print("Terminating Neutralino process...")
            try:
                # Launch the Neutralino app (non-blocking)
                parent = psutil.Process(neutralino_process.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
            except psutil.NoSuchProcess:
                pass # Process already terminated

    atexit.register(cleanup)

    url = f"http://127.0.0.1:{port}"
    try:
        with open(os.devnull, 'w') as devnull:
            neutralino_process = subprocess.Popen(
                [binary_path, '--load-dir-res', f'--url={url}'],
                cwd=os.path.dirname(binary_path),
                stdout=devnull,
                stderr=devnull
            )
        
        # Wait for the Neutralino process to exit
        neutralino_process.wait()

    except Exception as e:
        print(f"Could not launch Neutralino app: {e}")
        print("Falling back to opening in the default web browser.")

        time.sleep(1)
        webbrowser.open(url)

        # Keep the main thread alive to allow the Flask server to run
        while flask_thread.is_alive():
            time.sleep(1)

    finally:
        print("Neutralino window closed. Attempting to shut down Flask server...")
        try:
            requests.post(f"http://127.0.0.1:{port}/shutdown", timeout=2)
        except requests.exceptions.RequestException:
            # This is expected if the server is already down
            pass


if __name__ == '__main__':
    main()
