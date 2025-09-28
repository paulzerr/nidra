# -*- mode: python ; coding: utf-8 -*-

import os

# Get the directory of the spec file
# PyInstaller provides the SPEC_DIR variable, which is the absolute path to the directory containing the spec file.
spec_dir = SPEC_DIR
# Get the project root (one level up from the spec file dir)
root_dir = os.path.dirname(spec_dir)

a = Analysis(
    [os.path.join(root_dir, 'NIDRA', 'nidra_gui', 'launcher.py')],
    pathex=[root_dir, os.path.join(root_dir, 'NIDRA', 'nidra_gui'), os.path.join(root_dir, 'NIDRA')],
    binaries=[],
    datas=[
        (os.path.join(root_dir, 'NIDRA', 'nidra_gui', 'neutralino'), 'neutralino'),
        (os.path.join(root_dir, 'docs'), 'docs'),
        (os.path.join(root_dir, 'NIDRA', 'models'), 'NIDRA/models')
    ],
    hiddenimports=['decorator', 'scipy', 'scipy.io', 'webview', 'mne'],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'notebook', 'jupyter', 'IPython'],
    noarchive=False,
    optimize=0,
    distpath=os.path.join(root_dir, 'build', 'dist'),
    workpath=os.path.join(root_dir, 'build', 'pyinstaller_build'),
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NIDRA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)
