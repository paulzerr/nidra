Identify the way neutralino needs to be built first for this repo, then do this (unless it is already built), then continue with Pyinstaller:

To build the executable navigate to the `release` directory, deactivate any active conda envs, and activate 'nidra-env', then run `pyinstaller NIDRA.spec > pyinstaller.log 2>&1` to generate the final executable. 

then clean up all build artifacts
