
import time
import os
import socket
import threading
import webbrowser
import multiprocessing
from werkzeug.serving import make_server
from NIDRA.nidra_gui import app as nidra_app


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

class ServerWrapper(threading.Thread):
    """A Werkzeug server that can be stopped programmatically."""
    def __init__(self, app, port):
        super().__init__(daemon=True)
        self.server = make_server('127.0.0.1', port, app, threaded=True)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        print("Starting Flask server...")
        self.server.serve_forever()

    def shutdown(self):
        print("Shutting down Flask server...")
        self.server.shutdown()

def main():
    """
    Starts the Flask server in a background thread and then launches the browser.
    """
    multiprocessing.set_start_method('spawn', force=True)

    # One-shot silent Matplotlib font cache build to suppress FreeType emoji noise
    try:
        import contextlib, logging
        # Temporarily silence Matplotlib/font_manager during cache priming
        mpl_logger = logging.getLogger('matplotlib')
        fm_logger = logging.getLogger('matplotlib.font_manager')
        prev_mpl_level = mpl_logger.level
        prev_fm_level = fm_logger.level
        mpl_logger.setLevel(logging.CRITICAL)
        fm_logger.setLevel(logging.CRITICAL)
        with open(os.devnull, 'w') as devnull, contextlib.redirect_stderr(devnull):
            import matplotlib
            matplotlib.use('Agg', force=True)
            from matplotlib import font_manager
            font_manager.FontManager()
        # restore levels
        mpl_logger.setLevel(prev_mpl_level)
        fm_logger.setLevel(prev_fm_level)
    except Exception:
        pass

    # start the flask server in its own process
    port = find_free_port()
    server = ServerWrapper(nidra_app.app, port)
    server.start()

    run_neutralino = False  # use browser by default, TODO: fix neutralino madness

    if not run_neutralino:
        # --- Browser-based GUI Logic ---
        url = f"http://127.0.0.1:{port}"
        time.sleep(1)
        webbrowser.open(url)
        try:
            server.join()
        except KeyboardInterrupt:
            server.shutdown()
            server.join()
    # else:
    #     if sys.platform == "win32":
    #         binary_name = "neutralino-win_x64.exe"
    #     elif sys.platform == "darwin":
    #         binary_name = "neutralino-mac_10"
    #     else:
    #         binary_name = "neutralino-linux_x64"
    #     binary_path = get_resource_path(f"neutralino/{binary_name}")

    #     url = f"http://127.0.0.1:{port}"
    #     neutralino_process = None
    #     try:
    #         time.sleep(1)
    #         with open(os.devnull, 'w') as devnull:
    #             neutralino_process = subprocess.Popen(
    #                 [binary_path, f'--url={url}'],
    #                 cwd=os.path.dirname(binary_path),
    #                 stdout=devnull, stderr=devnull
    #             )
    #         neutralino_process.wait() 

    #     except FileNotFoundError:
    #         print(f"Neutralino binary not found at {binary_path}.")
    #         print("Falling back to opening in the default web browser.")
    #         webbrowser.open(url)
    #         server.join() 

    #     except KeyboardInterrupt:
    #         print("\nCtrl+C detected. Shutting down Neutralino and server...")
    #         if neutralino_process:
    #             neutralino_process.terminate()
        
    #     finally:
    #         print("Shutting down server...")
    #         server.shutdown()
    #         server.join()

    print("Server has shut down. Exiting.")

if __name__ == '__main__':
    main()
