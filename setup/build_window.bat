@echo off
setlocal enabledelayedexpansion

:: Change to the script's directory so all relative paths work
cd /d "%~dp0"

:: --- Configuration ---
set "CONDA_ENV_NAME=nidra-env"
set "BUILD_DIR=..\build"
set "NEUTRALINO_APP_DIR=..\NIDRA\nidra_gui"
set "PYINSTALLER_SPEC_FILE=NIDRA.spec"

:: --- Helper Functions ---
:info
echo [INFO] %~1
goto :eof

:: 0. Install Neutralino CLI
call :info "Checking for Neutralino.js CLI (neu)..."
:: Use 'where' command to check if 'neu' exists in the system's PATH
where neu >nul 2>&1
if %errorlevel% neq 0 (
    call :info "'neu' command not found. Installing Neutralino.js CLI globally..."
    npm install -g @neutralinojs/neu
) else (
    call :info "Neutralino.js CLI is already installed."
)

:: 1. Setup Conda Environment
call :info "Setting up Conda environment..."
conda env list | findstr /C:"%CONDA_ENV_NAME%" >nul
if %errorlevel% == 0 (
    call :info "Conda environment '%CONDA_ENV_NAME%' already exists."
) else (
    call :info "Creating Conda environment '%CONDA_ENV_NAME%'..."
    conda create -n "%CONDA_ENV_NAME%" python=3.10 -y
)
call conda activate "%CONDA_ENV_NAME%"
call :info "Installing dependencies from requirements.txt..."
pip install -r ..\requirements.txt

:: 2. Prepare Build Directory
call :info "Preparing build directory..."
if exist "%BUILD_DIR%" (
    rmdir /s /q "%BUILD_DIR%"
)
mkdir "%BUILD_DIR%"

:: 3. Build Neutralino Frontend
call :info "Building Neutralino frontend..."
cd "%NEUTRALINO_APP_DIR%"
neu update
neu build --release

:: Ensure config is present in dist for the Neutralino binary
copy neutralino.config.json dist\nidra_gui\neutralino.config.json

:: 4. Build PyInstaller Backend
cd ..\..\setup
call :info "Building PyInstaller backend..."
pyinstaller --distpath "%BUILD_DIR%\dist" --workpath "%BUILD_DIR%\pyinstaller_build" "%PYINSTALLER_SPEC_FILE%"

:: 5. Post-Build & Cleanup
call :info "Copying executable to a new 'executables' directory in the root..."
mkdir "..\executables"
xcopy /e /i /y "%BUILD_DIR%\dist\NIDRA" "..\executables\"

call :info "Cleaning up build artifacts..."

:: Clean up build dir
rmdir /s /q "%BUILD_DIR%"

:: Clean up Neutralino build artifacts
cd "%NEUTRALINO_APP_DIR%\dist"
for /d %%i in (*) do (
    if /i not "%%i"=="nidra_gui" (
        rmdir /s /q "%%i"
    )
)
cd nidra_gui
for /f "delims=" %%i in ('dir /b /a-d ^| findstr /v /i /c:"nidra_gui-linux_x64" /c:"nidra_gui-mac_x64" /c:"nidra_gui-win_x64.exe" /c:"neutralino.config.json" /c:"resources.neu"') do (
    del "%%i"
)
cd ..\..\..\setup

:: Remove Neutralino binaries
rmdir /s /q "%NEUTRALINO_APP_DIR%\bin"

call :info "Build complete! The final executable 'NIDRA' is located in the 'executables' directory."
