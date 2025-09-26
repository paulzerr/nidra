# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['../NIDRA/nidra_gui/launcher.py'],
    pathex=['..', '../NIDRA/nidra_gui', '../NIDRA'],
    binaries=[],
    datas=[
        ('../NIDRA/models', 'models'),
        ('../NIDRA/nidra_gui/neutralino', 'neutralino'),
        ('../docs', 'docs')
    ],
    hiddenimports=['decorator', 'scipy', 'scipy.io', 'webview', 'mne'],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'notebook', 'jupyter', 'IPython'],
    noarchive=False,
    optimize=0,
    distpath='../build/dist',
    workpath='../build/pyinstaller_build',
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
