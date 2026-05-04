# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# 1. Definir archivos de datos
datas = [
    ('config.json', '.'), 
    ('manual.html', '.'), 
    ('models', 'models'),
    ('src/assets', 'src/assets')
]
# Recolectar datos de las librerias
datas += collect_data_files('rapidocr_openvino')
datas += collect_data_files('openvino')

# 2. Recolectar BINARIOS (DLLs) de OpenVINO explícitamente
# Esto es vital para que encuentre los "frontends" (IR, ONNX, etc.)
binaries = collect_dynamic_libs('openvino')

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'keyboard', 
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
    excludes=[],
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
