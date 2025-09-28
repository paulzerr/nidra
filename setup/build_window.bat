@echo off
setlocal

REM Change to the script's directory so all relative paths work
cd /D "%~dp0"

REM --- Configuration ---
REM The .venv will be created next to the project's root folder
set "VENV_DIR=..\..\.venv"
set "BUILD_DIR=..\build"
set "PYINSTALLER_SPEC_FILE=NIDRA.spec"

REM ============================================================================
REM --- Main Script Logic ---
REM ============================================================================

REM 1. Setup Python Virtual Environment
call :info "Setting up Python virtual environment in '%VENV_DIR%'"

REM Check if the venv already exists by looking for the activate script
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call :info "Virtual environment already exists."
) else (
    call :info "Creating virtual environment..."
    REM Ensure python is on the PATH. You can replace 'python' with 'py -3.10'
    REM if you have the Python Launcher for Windows installed.
    python -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create the virtual environment. Make sure Python is installed and in your PATH.
        exit /b 1
    )
)

call :info "Activating virtual environment..."
call "%VENV_DIR%\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate the virtual environment.
    exit /b 1
)

call :info "Installing dependencies from pyproject.toml..."
pip install ..\
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

REM 2. Prepare Build Directory
call :info "Preparing build directory..."
if exist "%BUILD_DIR%" (
    rmdir /s /q "%BUILD_DIR%"
)
mkdir "%BUILD_DIR%"

REM 3. Build PyInstaller Backend
call :info "Building PyInstaller backend..."
pyinstaller --distpath "%BUILD_DIR%\dist" --workpath "%BUILD_DIR%\pyinstaller_build" "%PYINSTALLER_SPEC_FILE%"
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

REM 4. Post-Build & Cleanup
call :info "Copying executable to 'executables' directory..."
mkdir "..\executables" 2>nul
xcopy "%BUILD_DIR%\dist\NIDRA.exe" "..\executables\NIDRA" /s /i /y /q
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy executable.
    exit /b 1
)

call :info "Cleaning up build artifacts..."
rmdir /s /q "%BUILD_DIR%"

call :info "Build complete! The final executable is in the 'executables' directory."

REM --- End of main script logic ---
goto :eof


REM ============================================================================
REM --- Helper Functions ---
REM ============================================================================

:info
echo [INFO] %~1
goto :eof