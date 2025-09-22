#!/bin/bash

cd "$(dirname "$0")" # Change to the script's directory so all relative paths work
set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
CONDA_ENV_NAME="nidra-env"
BUILD_DIR="../build"
NEUTRALINO_APP_DIR="../NIDRA/nidra_gui"
PYINSTALLER_SPEC_FILE="NIDRA.spec"

# --- Helper Functions ---
info() {
    echo "[INFO] $1"
}

# 1. Setup Conda Environment
info "Setting up Conda environment..."
if conda env list | grep -q "$CONDA_ENV_NAME"; then
    info "Conda environment '$CONDA_ENV_NAME' already exists."
else
    info "Creating Conda environment '$CONDA_ENV_NAME'..."
    conda create -n "$CONDA_ENV_NAME" python=3.10 -y
fi
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV_NAME"
info "Installing dependencies from requirements.txt..."
pip install -r ../requirements.txt

# 2. Prepare Build Directory
info "Preparing build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# 3. Build Neutralino Frontend
info "Building Neutralino frontend..."
cd "$NEUTRALINO_APP_DIR"
neu update
neu build --release

# Ensure config is present in dist for the Neutralino binary
cp neutralino.config.json dist/nidra_gui/neutralino.config.json

# 4. Build PyInstaller Backend
cd ../../setup # Return to the setup directory
info "Building PyInstaller backend..."
pyinstaller --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/pyinstaller_build" "$PYINSTALLER_SPEC_FILE"

# 5. Post-Build & Cleanup
info "Copying executable to a new 'dist' directory in the root..."
mkdir -p "../executables"
cp -r "$BUILD_DIR/dist/NIDRA" "../executables/"

info "Cleaning up build artifacts..."

# Clean up build dir
rm -rf "$BUILD_DIR"

# Clean up Neutralino build artifacts
# Enable extended globbing to exclude files from deletion
shopt -s extglob
cd "$NEUTRALINO_APP_DIR/dist"
# Remove everything except the 'nidra_gui' directory which contains executables
rm -rf !(nidra_gui)
cd nidra_gui
# Remove everything except the final executables and the config file
rm -rf !(nidra_gui-linux_x64|nidra_gui-mac_x64|nidra_gui-win_x64.exe|neutralino.config.json|resources.neu)

# Remove Neutralino binaries
rm -rf "$NEUTRALINO_APP_DIR/bin"

info "Build complete! The final executable 'NIDRA' is located in the project root directory."
