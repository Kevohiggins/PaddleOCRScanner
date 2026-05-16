# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PaddleOCR Scanner — .spec basado en el original pre-traducción que FUNCIONABA
# con OpenVINO, más las dependencias de Argos Translate.
# =============================================================================
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# 1. Datos
datas = [
    ('models', 'models'),
    ('src/assets', 'src/assets')
]

# --- Exactamente como el .spec viejo que funcionaba ---
datas += collect_data_files('rapidocr_openvino')
datas += collect_data_files('openvino')

# --- Nuevo: datos de CTranslate2 y SentencePiece ---
datas += collect_data_files('sentencepiece')

# 2. Binarios — Exactamente como el viejo .spec
binaries = collect_dynamic_libs('openvino')

# --- Nuevo: binarios de CTranslate2 (motor de Argos) ---
# IMPORTANTE: NO usar collect_dynamic_libs aquí porque pone las DLLs en la raíz
# y ctranslate2 las necesita en su propia carpeta para que __init__.py las encuentre.
import glob
VENV_SP = os.path.join('.venv', 'Lib', 'site-packages')
ct2_src = os.path.join(VENV_SP, 'ctranslate2')
for f in glob.glob(os.path.join(ct2_src, '*.dll')) + glob.glob(os.path.join(ct2_src, '*.pyd')):
    binaries.append((f, 'ctranslate2'))
# SentencePiece binding
sp_pyd = os.path.join(VENV_SP, 'sentencepiece', '_sentencepiece.cp312-win_amd64.pyd')
if os.path.exists(sp_pyd):
    binaries.append((sp_pyd, 'sentencepiece'))

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # --- Del .spec viejo que funcionaba ---
        'PIL.Image',
        'rapidocr_openvino',
        'openvino.runtime',
        'openvino.frontend',
        'openvino.preprocess',
        'win32gui',
        'win32process',
        'win32api',
        # --- Nuevo: CTranslate2 ---
        'ctranslate2',
        'ctranslate2._ext',
        'sentencepiece',
        # --- Para accesibilidad ---
        'accessible_output2',
        'accessible_output2.outputs.sapi5',
        'accessible_output2.outputs.nvda',
        'psutil',
        'cv2',
        'translators',
        'js2py',
    ],
    hookspath=[],
    hooksconfig={},
    # Runtime hook SOLO para CTranslate2 (OpenVINO no lo necesitaba antes)
    runtime_hooks=['runtime_hook_openvino.py'],
    excludes=[
        'scipy', 'matplotlib', 'pandas', 'tkinter',
        'notebook', 'ipython',
        'PyQt5', 'PySide2', 'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PaddleOCR Scanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # El viejo usaba True pero con torch es riesgoso
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PaddleOCR Scanner',
)
