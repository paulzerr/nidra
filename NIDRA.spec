# -*- mode: python ; coding: utf-8 -*-
import sys
import glob

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect MNE data files and hidden imports to ensure all necessary files are included,
# especially .pyi stubs for lazy_loader, which was causing build failures.
mne_datas = collect_data_files('mne', include_py_files=True)
matplotlib_datas = collect_data_files('matplotlib')
mne_hiddenimports = collect_submodules('mne')

# Collect VC Redist DLLs
vc_redist_binaries = [(f, '.') for f in glob.glob('NIDRA/dll/*.dll')]

# --- Comprehensive Debugging Output ---
print("### DEBUGGING OUTPUT")

# 1. Inspect collected data files
print("\n--- MNE Datas ---")
print(mne_datas)
print("\n--- Matplotlib Datas ---")
print(matplotlib_datas)

# 2. Construct final lists for Analysis
final_datas = [
    ('NIDRA/nidra_gui/neutralino', 'neutralino'),
    ('docs', 'docs'),
    ('NIDRA/models', 'NIDRA/models'),
    ('examples', 'examples'),
] + mne_datas + matplotlib_datas

final_hiddenimports = [
    'decorator',
    'webview',
    'scipy',
    'pandas',
    'werkzeug',
    'matplotlib',
] + collect_submodules('scipy') + collect_submodules('pandas') + collect_submodules('werkzeug') + mne_hiddenimports

# 3. Print the final lists that will be passed to Analysis
print("\n--- Final `datas` for Analysis ---")
print(final_datas)
print("\n--- Final `binaries` for Analysis ---")
print(vc_redist_binaries)
print("\n--- Final `hiddenimports` for Analysis ---")
print(final_hiddenimports)

print("\n### END DEBUGGING OUTPUT")
# ------------------------------------

a = Analysis(
    ['NIDRA/nidra_gui/launcher.py'],
    pathex=['.', 'NIDRA'],
    binaries=vc_redist_binaries,
    datas=final_datas,
    hiddenimports=final_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'notebook', 'jupyter', 'IPython'],
    noarchive=False,
    optimize=0,
    distpath='dist',
    workpath='build',
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
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
    icon='docs/logo.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name='NIDRA',
    bindir='runtime'
)
