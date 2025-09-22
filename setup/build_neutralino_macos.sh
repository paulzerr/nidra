#!/bin/bash

# This script builds Neutralino binaries for multiple macOS versions by setting
# the MACOSX_DEPLOYMENT_TARGET environment variable.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
NEUTRALINO_APP_DIR="../NIDRA/nidra_gui"
FINAL_DIST_DIR="../NIDRA/nidra_gui/dist/nidra_gui"
TEMP_BUILD_DIR="temp_macos_builds" # Will be created inside the 'setup' directory

# --- Helper Functions ---
info() {
    echo "[INFO] $1"
}

# --- Main Build Process ---
cd "$(dirname "$0")" # Change to the script's directory (setup)

# 1. Setup
info "Preparing for build..."
rm -rf "$TEMP_BUILD_DIR"
mkdir -p "$TEMP_BUILD_DIR"

# 2. Define macOS targets
declare -A macos_targets
macos_targets["10.15"]="nidra_gui-mac_10"
macos_targets["11.0"]="nidra_gui-mac_11"
macos_targets["12.0"]="nidra_gui-mac_12_and_up"

# 3. Build for each target
for target_version in "${!macos_targets[@]}"; do
    binary_name=${macos_targets[$target_version]}
    info "Building for macOS $target_version -> $binary_name"

    cd "$NEUTRALINO_APP_DIR"

    # Clean previous build artifacts within the app dir
    rm -rf dist bin

    # Set the deployment target and build
    export MACOSX_DEPLOYMENT_TARGET=$target_version
    
    info "Running neu build with MACOSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET..."
    neu update
    neu build --release

    # Move the output binary to the temporary directory
    if [ -f "dist/nidra_gui/nidra_gui-mac_x64" ]; then
        mv "dist/nidra_gui/nidra_gui-mac_x64" "../../setup/$TEMP_BUILD_DIR/$binary_name"
        info "Created and moved binary $binary_name to temp location."
    else
        echo "[ERROR] Build failed for target $target_version, binary not found."
        exit 1
    fi

    cd ../../setup # Return to the setup directory
done

# Unset the environment variable
unset MACOSX_DEPLOYMENT_TARGET

# 4. Finalize
info "Moving all binaries to final destination..."
mkdir -p "$FINAL_DIST_DIR"
mv "$TEMP_BUILD_DIR"/* "$FINAL_DIST_DIR/"

# 5. Final Cleanup
info "Cleaning up temporary build directory..."
rm -rf "$TEMP_BUILD_DIR"

info "Script finished. All binaries are in $FINAL_DIST_DIR."
