# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect only the necessary MNE modules to reduce bundle size
mne_modules_to_include = [
    'mne.io',
    'mne.filter',
    'mne.utils',
    'mne.channels',
    'mne.annotations',
    'mne.transforms',
    'mne.surface',
    'mne.bem',
    'mne.externals',
    'mne.cov',
]

# Collect hidden imports from these specific modules
mne_hiddenimports = ['mne']  # Start with the top-level package
for mod in mne_modules_to_include:
    mne_hiddenimports.extend(collect_submodules(mod))

# Collect data files from modules that are likely to have them
mne_datas = []
mne_datas.extend(collect_data_files('mne.io'))
mne_datas.extend(collect_data_files('mne.channels'))
mne_datas.extend(collect_data_files('mne.filter'))
mne_datas.extend(collect_data_files('mne', subdir='data', include_py_files=False))

a = Analysis(
    ['NIDRA/nidra_gui/launcher.py'],
    pathex=['.', 'NIDRA'],
    binaries=[],
    datas=[
        ('NIDRA/nidra_gui/neutralino', 'neutralino'),
        ('docs', 'docs'),
        ('NIDRA/models', 'NIDRA/models'),
        ('examples', 'examples'),
    ] + mne_datas,  # merge mne datas into your project datas
    hiddenimports=[
        'decorator',
        # Only include the scipy modules that are actually used to reduce bundle size.
        # scipy.signal is used for signal processing (e.g., resample_poly).
        # scipy.io is a dependency for mne.io.
        'scipy.signal',
        'scipy.io',
        'webview',
    ] + mne_hiddenimports,  # merge mne hiddenimports
    hookspath=[],  # no external hook files needed
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'notebook', 'jupyter', 'IPython'],
    noarchive=False,
    optimize=2,
    distpath='dist',
    workpath='build',
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
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest='NIDRA.manifest',
    onefile=True,
    icon='docs/logo.ico',
)
