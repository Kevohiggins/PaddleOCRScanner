# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# 1. Definir archivos de datos (LIMPIO: sin config.json ni manual.html)
datas = [
    ('models', 'models'),
    ('src/assets', 'src/assets')
]

# Recolectar datos de las librerías necesarias
datas += collect_data_files('rapidocr_openvino')
datas += collect_data_files('openvino')

# 2. Recolectar BINARIOS (DLLs) de OpenVINO
binaries = collect_dynamic_libs('openvino')

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PIL.Image', 
        'rapidocr_openvino', 
        'openvino.runtime',
        'openvino.frontend',
        'openvino.preprocess',
        'win32gui',
        'win32process',
        'win32api'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'keyboard', 'pynput', 'paddle', 'paddleocr', 'paddlex', 'paddle2onnx',
        'scipy', 'matplotlib', 'pandas', 'tkinter',
        'PyQt5', 'PySide2', 'PySide6', 'notebook', 'ipython',
        'setuptools', 'distutils', 'docutils',
        'PIL.ImageQt', 'PIL.ImageTk', 'jedi', 'sqlite3',
        'huggingface_hub', 'requests', 'urllib3', 'cryptography',
        'pyasn1', 'pyasn1_modules', 'rsa', 'cachetools'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# FILTRO AGRESIVO DE BINARIOS
# Eliminamos todo lo que no sea esencial para ahorrar espacio
excluded_bin_patterns = [
    'ffmpeg', 'videoio', 'highgui', 'opencv_ml', 'opencv_objdetect', 'opencv_photo',
    'tensorflow', 'pytorch', 'caffe', 'paddle', 'opencl',
    'openvino_tensorflow_frontend', 'openvino_pytorch_frontend',
    'openvino_caffe_frontend', 'openvino_paddle_frontend'
]

a.binaries = [
    b for b in a.binaries 
    if not any(p in b[0].lower() for p in excluded_bin_patterns)
]

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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='PaddleOCR Scanner',
)
