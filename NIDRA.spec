# -*- mode: python ; coding: utf-8 -*-
import sys
import glob

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect MNE data files and hidden imports to ensure all necessary files are included,
# especially .pyi stubs for lazy_loader, which was causing build failures.
mne_datas = collect_data_files('mne', include_py_files=True)
mne_hiddenimports = collect_submodules('mne')

# Collect VC Redist DLLs
vc_redist_binaries = [(f, '.') for f in glob.glob('NIDRA/dll/*.dll')]

a = Analysis(
    ['NIDRA/nidra_gui/launcher.py'],
    pathex=['.', 'NIDRA'],
    binaries=vc_redist_binaries,
    datas=[
        ('NIDRA/nidra_gui/neutralino', 'neutralino'),
        ('docs', 'docs'),
        ('NIDRA/models', 'NIDRA/models'),
        ('examples', 'examples'),
    ] + mne_datas,  # merge mne datas into your project datas
    hiddenimports=[
        'decorator',
        'webview',
        'scipy',
        'pandas',
    ]
    + collect_submodules('scipy')
    + collect_submodules('pandas')
    + mne_hiddenimports,  # merge mne hiddenimports
    hookspath=[],  # no external hook files needed
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'notebook', 'jupyter', 'IPython'],
    noarchive=False,
    optimize=0,
    distpath='dist',
    workpath='build',
)

pyz = PYZ(a.pure)

is_macos = sys.platform == 'darwin'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NIDRA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest='NIDRA.manifest',
    onefile=not is_macos,
    icon='docs/logo.ico',
)

if is_macos:
    app = BUNDLE(
        exe,
        name='NIDRA.app',
        icon='docs/logo.ico',
        bundle_identifier=None,
    )
