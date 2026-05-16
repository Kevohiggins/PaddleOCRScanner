# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import glob
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# --- CONFIGURACIÓN DE RUTAS ---
# Determinamos la ruta del entorno virtual para buscar las DLLs necesarias
VENV_SP = os.path.join('.venv', 'Lib', 'site-packages')

# 1. DATOS (Archivos no ejecutables que el programa necesita)
datas = [
    ('models', 'models'),         # Modelos de OCR y Traducción
    ('src/assets', 'src/assets'), # Iconos y sonidos
    ('manual.html', '.'),         # El manual de usuario en la raíz
]

# Recolectamos datos automáticos de las librerías críticas
datas += collect_data_files('rapidocr_openvino')
datas += collect_data_files('openvino')
datas += collect_data_files('sentencepiece')

# 2. BINARIOS (DLLs y archivos de sistema)
# OpenVINO necesita sus librerías dinámicas para la aceleración por hardware
binaries = collect_dynamic_libs('openvino')

# CTranslate2 (Motor de Traducción): 
# Necesitamos copiar sus DLLs manualmente a su carpeta interna para que Python las encuentre
ct2_src = os.path.join(VENV_SP, 'ctranslate2')
if os.path.exists(ct2_src):
    for f in glob.glob(os.path.join(ct2_src, '*.dll')) + glob.glob(os.path.join(ct2_src, '*.pyd')):
        binaries.append((f, 'ctranslate2'))

# SentencePiece: Motor de procesamiento de texto para la traducción
sp_dir = os.path.join(VENV_SP, 'sentencepiece')
if os.path.exists(sp_dir):
    for f in glob.glob(os.path.join(sp_dir, '*.pyd')) + glob.glob(os.path.join(sp_dir, '*.dll')):
        binaries.append((f, 'sentencepiece'))

# 3. ANÁLISIS DE CÓDIGO
a = Analysis(
    ['src/main.py'],           # Punto de entrada del programa
    pathex=['src'],            # Carpeta donde buscar nuestros módulos (.py)
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PIL.Image',           # Procesamiento de imágenes
        'rapidocr_openvino',    # Motor OCR
        'openvino.runtime',     # Aceleración Intel
        'ctranslate2',          # Motor de traducción Offline
        'sentencepiece',        # Tokenizador de traducción
        'accessible_output2',   # Salida para lectores de pantalla
        'psutil',               # Control de procesos
        'cv2',                  # OpenCV para comparación visual
        'js2py',                # Para servicios de traducción online
    ],
    # runtime_hook gestiona las rutas de las DLLs cuando el EXE se está ejecutando
    runtime_hooks=['runtime_hook_openvino.py'],
    excludes=[
        # Excluimos librerías pesadas que PyInstaller intenta meter por error
        'scipy', 'matplotlib', 'pandas', 'tkinter', 
        'notebook', 'ipython', 'PyQt5', 'PySide2', 'PySide6',
        'torch', 'tensorboard', 'unittest'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 4. CONFIGURACIÓN DEL EJECUTABLE (.EXE)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PaddleOCR Scanner',
    debug=False,               # Poner en True solo para ver errores de consola
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX puede corromper DLLs de IA, mejor dejarlo en False
    console=False,             # False para que no se abra una ventana negra al iniciar
    icon='src/assets/icon.ico' if os.path.exists('src/assets/icon.ico') else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 5. RECOLECCIÓN FINAL (Carpeta DIST)
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
