import subprocess
import threading
import sys
import os
import platform
import socket
import requests
from pathlib import Path
import webbrowser
import time
import multiprocessing
from NIDRA.nidra_gui.app import app
from NIDRA.utils import download_models
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
        base_path = os.path.abspath(os.path.join(Path(__file__).parent, 'NIDRA', 'nidra_gui'))
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


def fallback_gui(url):
    """
    Creates a small Tkinter window to inform the user that the app is running in the browser
    and provides a way to shut down the server by closing the window.
    """
    import tkinter as tk
    from tkinter import font as tkFont
    import webbrowser

    root = tk.Tk()
    root.title("NIDRA GUI Server")

    # Create a more visually appealing font
    default_font = tkFont.nametofont("TkDefaultFont")
    default_font.configure(size=18)
    url_font = tkFont.Font(family=default_font.cget("family"), size=18, underline=True)

    # Set up the window layout
    root.geometry("800x400") # Adjusted for potential download messages
    root.resizable(False, False)
    container = tk.Frame(root, padx=15, pady=15)
    container.pack(expand=True, fill="both")

    # Center the window on the screen
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (root.winfo_width() // 2)
    y = (screen_height // 2) - (root.winfo_height() // 2)
    root.geometry(f'+{x}+{y}')

    # Add informational labels
    tk.Label(container, text="\n\nThe NIDRA GUI is now running in your web browser:").pack(pady=(0, 5))
    
    # Add a clickable URL label
    url_label = tk.Label(container, text=url, fg="blue", cursor="hand2", font=url_font)
    url_label.pack()
    url_label.bind("<Button-1>", lambda e: webbrowser.open(url))
    
    tk.Label(container, text="\n\nClosing this window will shut down NIDRA.\n\n").pack(pady=(5, 0))

    # --- Download Section ---
    status_label = tk.Label(container, text="")
    status_label.pack(pady=(5, 0))
    completion_label = tk.Label(container, text="")
    completion_label.pack(pady=(5, 0))

    def download_in_thread():
        download_needed = download_models(tk_root=root, status_label=status_label, completion_label=completion_label)
        if not download_needed:
            # If no download was needed, we can shrink the window.
            root.after(0, lambda: root.geometry("800x300"))

    download_thread = threading.Thread(target=download_in_thread, daemon=True)
    download_thread.start()

    # Ensure the server shuts down when the window is closed
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def main():
    """
    Starts the Flask server in a background thread and then launches the Neutralino application.
    """

    multiprocessing.set_start_method('spawn', force=True)
    port = find_free_port()
    flask_thread = threading.Thread(target=run_flask, args=(port,), daemon=True)
    flask_thread.start()

    # get platform-specific Neutralino binary path
    if sys.platform == "win32":
        binary_name = "neutralino-win_x64.exe"
    elif sys.platform == "darwin":
        binary_name = "neutralino-mac_10xxx" #workaround for macOS to force browser fallback
    else:
        binary_name = "neutralino-linux_x64"
    binary_path = get_resource_path(f"neutralino/{binary_name}")

    # Launch the Neutralino app (non-blocking)
    time.sleep(1)
    neutralino_process = None
    
    url = f"http://127.0.0.1:{port}"
    try:
        with open(os.devnull, 'w') as devnull:
            neutralino_process = subprocess.Popen(
                [binary_path, '--load-dir-res', f'--url={url}'],
                cwd=os.path.dirname(binary_path),
                stdout=devnull,
                stderr=devnull
            )
        
        # download the models (if first run)
        time.sleep(2)
        download_models()

        # Wait for the Neutralino process to exit
        neutralino_process.wait()

    except Exception as e:
        print(f"Could not launch Neutralino app: {e}")
        print("Falling back to opening in the default web browser.")

        time.sleep(1)
        webbrowser.open(url)

        # small Tkinter window
        # to act as a control panel for shutting down the server.
        fallback_gui(url)
    finally:
        print("Neutralino window closed. Attempting to shut down Flask server...")
        requests.post(f"http://127.0.0.1:{port}/shutdown", timeout=2)


if __name__ == '__main__':
    main()