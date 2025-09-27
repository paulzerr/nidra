#!/bin/bash

# ==============================================================================
# IMPORTANT: This script MUST be run on a macOS machine with the Xcode
# Command Line Tools installed. It cannot be run on Linux or Windows.
#
# To install the tools on macOS, run this command in the terminal:
#   xcode-select --install
# ==============================================================================

# This script builds three distinct macOS architectural variants of a Neutralino app.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
NEUTRALINO_APP_DIR="../NIDRA/nidra_gui"
FINAL_DIST_DIR="../NIDRA/nidra_gui/dist/nidra_gui"
TEMP_BUILD_DIR="temp_macos_builds"

# --- Helper Functions ---
info() {
    echo "[INFO] $1"
}

error() {
    echo "[ERROR] $1" >&2
}

# --- Main Build Process ---
cd "$(dirname "$0")" # Change to the script's directory (setup)

# 1. Setup
info "Preparing for multi-architecture macOS build..."
rm -rf "$TEMP_BUILD_DIR"
mkdir -p "$TEMP_BUILD_DIR"

# 2. Define the architectural targets
APP_ID="nidra_gui" # Must match the "applicationId" in your neutralino.config.json
targets=("mac_x64" "mac_arm64" "mac_universal")

# 3. Build each target variant
for target in "${targets[@]}"; do
    binary_name="${APP_ID}-${target}"
    info "--- Building variant: $binary_name ---"

    arch_flag=""
    target_version=""

    case "$target" in
        "mac_x64")
            info "Config: Intel-only for max compatibility (macOS 10.15+)."
            arch_flag="-arch x86_64"
            target_version="10.15"
            ;;
        "mac_arm64")
            info "Config: Apple Silicon-only for native performance (macOS 11.0+)."
            arch_flag="-arch arm64"
            target_version="11.0"
            ;;
        "mac_universal")
            info "Config: Universal binary for modern Macs (macOS 11.0+)."
            arch_flag="-arch x86_64 -arch arm64"
            target_version="11.0"
            ;;
    esac

    cd "$NEUTRALINO_APP_DIR"
    rm -rf dist bin

    # Set environment variables to force the compiler's behavior
    export MACOSX_DEPLOYMENT_TARGET=$target_version
    export CXXFLAGS="$arch_flag -mmacosx-version-min=$target_version"
    export LDFLAGS="$arch_flag -mmacosx-version-min=$target_version"

    info "Running 'neu build' with CXXFLAGS: $CXXFLAGS"
    neu build --release

    # The output binary from 'neu build' is *always* named <app_id>-mac_x64,
    # regardless of its actual architecture. The flags determine its contents.
    source_binary_path="dist/$APP_ID/${APP_ID}-mac_x64"

    if [ -f "$source_binary_path" ]; then
        mv "$source_binary_path" "../../setup/$TEMP_BUILD_DIR/$binary_name"
        info "Successfully created and moved: $binary_name"
    else
        error "Build failed for target '$target'. Binary not found at '$source_binary_path'."
        unset MACOSX_DEPLOYMENT_TARGET CXXFLAGS LDFLAGS
        exit 1
    fi

    cd ../../setup
done

# Unset environment variables
unset MACOSX_DEPLOYMENT_TARGET CXXFLAGS LDFLAGS

# 4. Finalize
info "--- Finalizing Build ---"
info "Moving all binaries to final destination: $FINAL_DIST_DIR"
mkdir -p "$FINAL_DIST_DIR"
mv "$TEMP_BUILD_DIR"/* "$FINAL_DIST_DIR/"
rm -rf "$TEMP_BUILD_DIR"

info "Script finished successfully. Binaries are in $FINAL_DIST_DIR."